"""
LLM Client Module

Provides a unified interface for different LLM providers.
Uses the Strategy pattern - swap providers without changing calling code.

Supported providers:
- Claude (Anthropic API)
- Ollama (local models)
"""

import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
import urllib.request
import urllib.error


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
        
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = ""
            for block in response.content:
                if block.type == "text":
                    content = block.text.strip()
                    break
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens
            )
            
        except AuthenticationError:
            raise LLMError("Invalid API key. Check your ANTHROPIC_API_KEY.")
        except APIError as e:
            raise LLMError(f"Claude API error: {e.message}")


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
    
    DEFAULT_MODEL = "llama3.2:3b"
    DEFAULT_HOST = "http://localhost:11434"
    
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
    
    def generate(self, prompt: str) -> LLMResponse:
        """
        Call Ollama's generate API.
        
        Uses urllib to avoid adding requests as a dependency.
        """
        url = f"{self.host}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,  # Get complete response at once
            "options": {
                "temperature": 0.7,
                "num_predict": 1000,  # Increased for detailed commit messages
            }
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            return LLMResponse(
                content=result.get("response", "").strip(),
                model=self.model,
                tokens_used=result.get("eval_count", 0)
            )
            
        except urllib.error.URLError as e:
            if "Connection refused" in str(e):
                raise LLMError(f"Ollama not running. Start with: ollama serve")
            raise LLMError(f"Ollama request failed: {e}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise LLMError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
            raise LLMError(f"Ollama error ({e.code}): {e.reason}")
        except json.JSONDecodeError:
            raise LLMError("Invalid response from Ollama")
        except TimeoutError:
            raise LLMError(
                f"Request timed out. Model '{self.model}' may need to be pulled.\n"
                f"Run: ollama pull {self.model}"
            )


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
