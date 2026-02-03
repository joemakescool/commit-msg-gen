"""LLM Client Package"""

from src.llm.base import LLMClient, LLMResponse, LLMError, SYSTEM_PROMPT, validate_commit_message
from src.llm.claude import ClaudeClient
from src.llm.ollama import OllamaClient

PROVIDERS = {
    "claude": ClaudeClient,
    "ollama": OllamaClient,
}

AUTO_DETECT_ORDER = [OllamaClient, ClaudeClient]


def get_client(provider: str = "auto", model: str | None = None) -> LLMClient:
    """Get an LLM client. Provider can be 'claude', 'ollama', or 'auto'."""
    if provider in PROVIDERS:
        return PROVIDERS[provider](model=model)

    if provider == "auto":
        for client_class in AUTO_DETECT_ORDER:
            try:
                return client_class(model=model)
            except LLMError:
                continue

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


__all__ = [
    "LLMClient",
    "LLMResponse",
    "LLMError",
    "ClaudeClient",
    "OllamaClient",
    "get_client",
    "PROVIDERS",
    "SYSTEM_PROMPT",
    "validate_commit_message",
]
