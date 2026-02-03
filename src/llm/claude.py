"""Claude (Anthropic) LLM Client"""

import os

from src.llm.base import LLMClient, LLMResponse, LLMError, SYSTEM_PROMPT, validate_commit_message


class ClaudeClient(LLMClient):
    """Claude API client. Requires ANTHROPIC_API_KEY env var."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 1000
    TEMPERATURE = 0.4
    MAX_RETRIES = 2

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or self.DEFAULT_MODEL

        if not self.api_key:
            raise LLMError(
                "No API key found. Set ANTHROPIC_API_KEY environment variable:\n"
                "  export ANTHROPIC_API_KEY='your-key-here'"
            )

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

                is_valid, error = validate_commit_message(content)
                if not is_valid:
                    last_error = error
                    if attempt < self.MAX_RETRIES:
                        continue

                return LLMResponse(
                    content=content,
                    model=self.model,
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens
                )

            except AuthenticationError:
                raise LLMError("Invalid API key. Check your ANTHROPIC_API_KEY.")
            except APIError as e:
                raise LLMError(f"Claude API error: {e.message}")

        raise LLMError(f"Failed after {self.MAX_RETRIES} retries: {last_error}")
