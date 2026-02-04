"""Ollama LLM Client for Local Models"""

import os
import json
import http.client
import socket
import urllib.request
import urllib.error

from src.llm.base import LLMClient, LLMResponse, LLMError, SYSTEM_PROMPT, validate_commit_message


class OllamaClient(LLMClient):
    """Ollama client for local models. Requires: ollama serve"""

    DEFAULT_MODEL = "mistral:7b"
    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_TIMEOUT = 300  # 5 minutes for CPU inference
    MAX_RETRIES = 2

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or self.DEFAULT_MODEL
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)
        self.timeout = int(os.environ.get("CM_TIMEOUT", self.DEFAULT_TIMEOUT))
        self._verify_connection()

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"

    def _verify_connection(self) -> None:
        """Check if Ollama is running and accessible."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.URLError:
            raise LLMError("Ollama not running. Start with: ollama serve")

    def _is_model_loaded(self) -> bool:
        """Check if the model is currently loaded in memory."""
        try:
            req = urllib.request.Request(f"{self.host}/api/ps")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                loaded_models = [m.get('name', '') for m in data.get('models', [])]
                return any(self.model in m or m in self.model for m in loaded_models)
        except (urllib.error.URLError, json.JSONDecodeError):
            return False

    def warmup(self) -> None:
        """Pre-load the model with a tiny request."""
        if self._is_model_loaded():
            return

        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": "hi",
            "stream": False,
            "options": {"num_predict": 1},
            "keep_alive": "10m",
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout):
                pass
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass

    def _call_api(self, prompt: str) -> dict:
        """Make a single API call to Ollama."""
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.4,
                "num_predict": 1000,
            }
        }

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def generate(self, prompt: str) -> LLMResponse:
        """Call Ollama's generate API with retry logic."""
        last_error = ""

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                retry_prompt = prompt
                if attempt > 0:
                    retry_prompt = f"{prompt}\n\nIMPORTANT: Your previous response was invalid ({last_error}). Start directly with the commit type, e.g., 'feat(scope):'"

                result = self._call_api(retry_prompt)
                content = result.get("response", "").strip()

                is_valid, error = validate_commit_message(content)
                if not is_valid:
                    last_error = error
                    if attempt < self.MAX_RETRIES:
                        continue

                return LLMResponse(
                    content=content,
                    model=self.model,
                    tokens_used=result.get("eval_count", 0)
                )

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise LLMError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
                raise LLMError(f"Ollama error ({e.code}): {e.reason}")
            except urllib.error.URLError as e:
                if isinstance(e.reason, socket.timeout):
                    raise LLMError(f"Request timed out after {self.timeout}s. Try:\n  - Pre-load model: cm --warmup\n  - Increase timeout: set CM_TIMEOUT=600")
                if "Connection refused" in str(e):
                    raise LLMError("Ollama not running. Start with: ollama serve")
                raise LLMError(f"Ollama request failed: {e}")
            except socket.timeout:
                raise LLMError(f"Request timed out after {self.timeout}s. Try:\n  - Pre-load model: cm --warmup\n  - Increase timeout: set CM_TIMEOUT=600")
            except json.JSONDecodeError:
                raise LLMError("Invalid response from Ollama. Try a different model or simpler change.")
            except http.client.HTTPException as e:
                raise LLMError(f"Incomplete response from Ollama: {e}. The model may have run out of memory.")
            except OSError as e:
                raise LLMError(f"Connection to Ollama lost: {e}. Check that 'ollama serve' is still running.")

        raise LLMError(f"Failed after {self.MAX_RETRIES} retries: {last_error}")
