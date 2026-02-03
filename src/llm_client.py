"""
LLM Client Module

Provides a unified interface for different LLM providers.
Uses the Strategy pattern - swap providers without changing calling code.

Supported providers:
- Claude (Anthropic API)
- Ollama (local models)
"""

import os
import re
import json
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
import urllib.request
import urllib.error

from src import COMMIT_TYPE_NAMES  # Centralized in __init__.py


# Shared system prompt for consistent behavior across providers
SYSTEM_PROMPT = """You are a senior software engineer specialized in writing precise, informative git commit messages. You have mass-reviewed thousands of pull requests at major tech companies and open-source projects.

Your expertise:
- Deep understanding of conventional commit format (type, scope, subject, body)
- Ability to identify the PRIMARY purpose of a change from a diff
- Writing for future developers who will read git log at 2am debugging production

Your standards:
- Every word earns its place—no filler, no fluff
- The diff shows WHAT; you explain WHY
- Specific verbs over vague ones (never "update", "change", "modify")
- Bullets add context the subject line can't capture"""


def validate_commit_message(content: str) -> tuple[bool, str]:
    """
    Validate that response looks like a proper commit message.

    Returns:
        (is_valid, error_message)
    """
    if not content or len(content.strip()) < 10:
        return False, "Response too short"

    # Check for conventional commit format: type(scope): or type:
    # Uses centralized COMMIT_TYPE_NAMES from src/__init__.py
    types_pattern = '|'.join(COMMIT_TYPE_NAMES)
    pattern = rf'^({types_pattern})(\(.+\))?!?:'
    first_line = content.strip().split('\n')[0]

    if not re.match(pattern, first_line):
        return False, f"Missing conventional commit format. Got: {first_line[:50]}"

    return True, ""


@dataclass
class LLMResponse:
    """
    Structured response from any LLM provider.
    
    Why wrap the response?
    - Unified interface across providers
    - Easy to add metadata (tokens, latency)
    - Simpler to mock in tests
    """
    content: str
    model: str = ""
    tokens_used: int = 0


class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass


class LLMClient(ABC):
    """
    Abstract base for LLM clients.
    
    Why ABC over Protocol?
    - We want to enforce implementation
    - Clearer error messages if methods missing
    - Can add shared helper methods later
    """
    
    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        """Generate a response from the prompt."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass


# =============================================================================
# Claude (Anthropic) Client
# =============================================================================

class ClaudeClient(LLMClient):
    """
    Claude API client via Anthropic SDK.

    Best for: Production use, highest quality
    Requires: ANTHROPIC_API_KEY environment variable
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 1000  # Increased for detailed commit messages
    TEMPERATURE = 0.4  # Lower = more consistent, professional output
    MAX_RETRIES = 2  # Retry on malformed response

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or self.DEFAULT_MODEL

        if not self.api_key:
            raise LLMError(
                "No API key found. Set ANTHROPIC_API_KEY environment variable:\n"
                "  export ANTHROPIC_API_KEY='your-key-here'"
            )

        # Lazy import - only load SDK if using Claude
        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        except ImportError:
            raise LLMError(
                "Anthropic SDK not installed. Run:\n"
                "  pip install anthropic"
            )

    @property
    def name(self) -> str:
        return f"Claude ({self.model})"

    def generate(self, prompt: str) -> LLMResponse:
        from anthropic import APIError, AuthenticationError

        last_error = ""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Add retry context if this is a retry
                retry_prompt = prompt
                if attempt > 0:
                    retry_prompt = f"{prompt}\n\nIMPORTANT: Your previous response was invalid ({last_error}). Start directly with the commit type, e.g., 'feat(scope):'"

                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.MAX_TOKENS,
                    temperature=self.TEMPERATURE,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": retry_prompt}]
                )

                content = ""
                for block in response.content:
                    if block.type == "text":
                        content = block.text.strip()
                        break

                # Validate response format
                is_valid, error = validate_commit_message(content)
                if not is_valid:
                    last_error = error
                    if attempt < self.MAX_RETRIES:
                        continue  # Retry
                    # On final attempt, return anyway (let user see what we got)

                return LLMResponse(
                    content=content,
                    model=self.model,
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens
                )

            except AuthenticationError:
                raise LLMError("Invalid API key. Check your ANTHROPIC_API_KEY.")
            except APIError as e:
                raise LLMError(f"Claude API error: {e.message}")

        # Should not reach here, but just in case
        raise LLMError(f"Failed after {self.MAX_RETRIES} retries: {last_error}")


# =============================================================================
# Ollama Client (Local models)
# =============================================================================

class OllamaClient(LLMClient):
    """
    Ollama client for local model inference.

    Best for: Free usage, privacy, offline work
    Requires: Ollama running locally (ollama serve)

    Recommended models for commit messages:
    - llama3.2:3b    (fastest, ~2GB RAM)
    - mistral:7b     (balanced, ~4GB RAM)
    - qwen2.5-coder:7b (code-optimized, ~4GB RAM)
    """

    DEFAULT_MODEL = "mistral:7b"
    DEFAULT_HOST = "http://localhost:11434"
    MAX_RETRIES = 2  # Retry on malformed response

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)

        # Verify Ollama is running
        self._verify_connection()

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"

    def _verify_connection(self) -> None:
        """Check if Ollama is running and accessible."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                pass  # Connection successful
        except urllib.error.URLError:
            raise LLMError(
                f"Ollama not running. Start with: ollama serve"
            )

    def _is_model_loaded(self) -> bool:
        """Check if the model is currently loaded in memory."""
        try:
            req = urllib.request.Request(f"{self.host}/api/ps")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                loaded_models = [m.get('name', '') for m in data.get('models', [])]
                # Check if our model (or a variant of it) is loaded
                return any(self.model in m or m in self.model for m in loaded_models)
        except (urllib.error.URLError, json.JSONDecodeError):
            return False

    def warmup(self) -> None:
        """Pre-load the model with a tiny request. Call this before generate() for faster response."""
        if self._is_model_loaded():
            return  # Model already loaded, skip warmup

        # Send minimal prompt to trigger model loading
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1},  # Generate just 1 token
            "keep_alive": "10m",  # Keep model loaded for 10 minutes
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as response:
                pass  # Just wait for model to load
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass  # If warmup fails, main generate will handle the error

    def _call_api(self, prompt: str) -> dict:
        """Make a single API call to Ollama."""
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,  # System prompt for Ollama
            "stream": False,
            "keep_alive": "10m",  # Keep model loaded for 10 minutes between runs
            "options": {
                "temperature": 0.4,
                "num_predict": 1000,
            }
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=180) as response:
            return json.loads(response.read().decode('utf-8'))

    def generate(self, prompt: str) -> LLMResponse:
        """
        Call Ollama's generate API with retry logic.

        Uses urllib to avoid adding requests as a dependency.
        """
        last_error = ""

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Add retry context if this is a retry
                retry_prompt = prompt
                if attempt > 0:
                    retry_prompt = f"{prompt}\n\nIMPORTANT: Your previous response was invalid ({last_error}). Start directly with the commit type, e.g., 'feat(scope):'"

                result = self._call_api(retry_prompt)
                content = result.get("response", "").strip()

                # Validate response format
                is_valid, error = validate_commit_message(content)
                if not is_valid:
                    last_error = error
                    if attempt < self.MAX_RETRIES:
                        continue  # Retry
                    # On final attempt, return anyway

                return LLMResponse(
                    content=content,
                    model=self.model,
                    tokens_used=result.get("eval_count", 0)
                )

            except urllib.error.HTTPError as e:
                # HTTPError must come before URLError (it's a subclass)
                if e.code == 404:
                    raise LLMError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
                raise LLMError(f"Ollama error ({e.code}): {e.reason}")
            except urllib.error.URLError as e:
                # URLError can wrap socket.timeout
                if isinstance(e.reason, socket.timeout):
                    raise LLMError(
                        f"Request timed out after 3 minutes. Try a smaller model:\n"
                        f"  cm -m llama3.2:3b"
                    )
                if "Connection refused" in str(e):
                    raise LLMError(f"Ollama not running. Start with: ollama serve")
                raise LLMError(f"Ollama request failed: {e}")
            except socket.timeout:
                raise LLMError(
                    f"Request timed out after 3 minutes. Try a smaller model:\n"
                    f"  cm -m llama3.2:3b"
                )
            except json.JSONDecodeError:
                raise LLMError("Invalid response from Ollama")

        # Should not reach here
        raise LLMError(f"Failed after {self.MAX_RETRIES} retries: {last_error}")


# =============================================================================
# Factory function
# =============================================================================

def get_client(provider: str = "auto", model: str | None = None) -> LLMClient:
    """
    Get an LLM client for the specified provider.
    
    Args:
        provider: 'claude', 'ollama', or 'auto' (tries ollama first, then claude)
        model: Override the default model for the provider
        
    Returns:
        Configured LLMClient instance
    
    Examples:
        client = get_client()  # Auto-detect
        client = get_client("ollama", "mistral:7b")
        client = get_client("claude")
    """
    if provider == "claude":
        return ClaudeClient(model=model)
    
    if provider == "ollama":
        return OllamaClient(model=model)
    
    if provider == "auto":
        # Try Ollama first (free), fall back to Claude
        try:
            return OllamaClient(model=model)
        except LLMError:
            pass
        
        try:
            return ClaudeClient(model=model)
        except LLMError:
            pass
        
        raise LLMError(
            "No LLM provider available.\n\n"
            "Option 1 - Use Ollama (free, local):\n"
            "  1. Install: https://ollama.ai\n"
            "  2. Start: ollama serve\n"
            "  3. Pull: ollama pull llama3.2:3b\n\n"
            "Option 2 - Use Claude API:\n"
            "  export ANTHROPIC_API_KEY='your-key-here'"
        )
    
    raise LLMError(f"Unknown provider: {provider}. Use 'claude', 'ollama', or 'auto'.")


# =============================================================================
# CLI test
# =============================================================================

if __name__ == "__main__":
    import sys
    
    print("LLM Client Test")
    print("=" * 40)
    
    # Parse optional provider argument
    provider = sys.argv[1] if len(sys.argv) > 1 else "auto"
    model = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Provider: {provider}")
    if model:
        print(f"Model: {model}")
    print()
    
    try:
        client = get_client(provider, model)
        print(f"✓ Connected to {client.name}")
        
        # Simple test prompt
        test_prompt = """Write a commit message for this change:
- Added hello.py that prints "Hello, World!"

Output only the commit message in this format:
type(scope): subject

- bullet point"""
        
        print("\nGenerating test message...")
        response = client.generate(test_prompt)
        
        print(f"\n✓ Response ({response.tokens_used} tokens):")
        print("-" * 40)
        print(response.content)
        print("-" * 40)
        
    except LLMError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
