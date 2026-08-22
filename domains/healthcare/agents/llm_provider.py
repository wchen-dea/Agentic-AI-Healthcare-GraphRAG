from typing import Any

import os

import requests


class LLMProviderError(RuntimeError):
    pass


class OllamaProvider:
    def __init__(self, *, base_url: str, configured_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.configured_model = configured_model

    @staticmethod
    def _model_base_name(model_name: str) -> str:
        return model_name.split(":", 1)[0]

    def available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code != 200:
                return []
            models = response.json().get("models", [])
            return [model.get("name") for model in models if model.get("name")]
        except Exception:
            return []

    def resolve_model(self) -> tuple[str | None, list[str]]:
        configured = (self.configured_model or "").strip()
        available = self.available_models()

        if not configured:
            return (available[0], available) if available else (None, [])

        if configured in available:
            return configured, available

        configured_base = self._model_base_name(configured)
        for name in available:
            if self._model_base_name(name) == configured_base:
                return name, available

        if available:
            return available[0], available

        return None, []

    def generate(
        self,
        *,
        prompt: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float = 0.2,
    ) -> str:
        selected_model, available_models = self.resolve_model()
        if not selected_model:
            return (
                "LLM error: no Ollama models are installed. "
                "Pull one with: docker exec -it healthcare-ollama ollama pull llama3.1"
            )

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
                timeout=timeout_seconds,
            )
        except requests.Timeout:
            return (
                "LLM error: Ollama request timed out after "
                f"{timeout_seconds} seconds. "
                "Check model availability, prompt size, or increase LLM_TIMEOUT_SECONDS."
            )
        except requests.RequestException:
            return "LLM error: unable to reach the inference endpoint. Check connectivity."

        if response.status_code != 200:
            body = response.text[:200]
            if "not found" in body.lower():
                return (
                    f"LLM error: requested model '{selected_model}' was not found. "
                    "Pull a model with: docker exec -it healthcare-ollama ollama pull llama3.1"
                )
            return "LLM error: model returned a non-200 response."

        try:
            return str(response.json().get("response") or "")
        except (ValueError, KeyError):
            return "LLM error: invalid response format from inference endpoint."


class OpenAIProvider:
    def __init__(self, *, configured_model: str) -> None:
        self.model = configured_model or "gpt-4.1-mini"
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    def generate(
        self,
        *,
        prompt: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float = 0.2,
    ) -> str:
        if not self.api_key:
            return "LLM error: OPENAI_API_KEY not set."
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout_seconds,
            )
        except requests.Timeout:
            return f"LLM error: OpenAI request timed out after {timeout_seconds} seconds."
        except requests.RequestException:
            return "LLM error: unable to reach the OpenAI API."

        if response.status_code != 200:
            return f"LLM error: OpenAI returned status {response.status_code}."

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError):
            return "LLM error: invalid response format from OpenAI."


class AnthropicProvider:
    def __init__(self, *, configured_model: str) -> None:
        self.model = configured_model or "claude-sonnet-4-20250514"
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    def generate(
        self,
        *,
        prompt: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float = 0.2,
    ) -> str:
        if not self.api_key:
            return "LLM error: ANTHROPIC_API_KEY not set."
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=timeout_seconds,
            )
        except requests.Timeout:
            return f"LLM error: Anthropic request timed out after {timeout_seconds} seconds."
        except requests.RequestException:
            return "LLM error: unable to reach the Anthropic API."

        if response.status_code != 200:
            return f"LLM error: Anthropic returned status {response.status_code}."

        try:
            return response.json()["content"][0]["text"]
        except (ValueError, KeyError, IndexError):
            return "LLM error: invalid response format from Anthropic."


class FallbackProvider:
    """Wraps a primary and fallback provider; falls back on error responses."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(self, **kwargs: Any) -> str:
        result = self.primary.generate(**kwargs)
        if result.startswith("LLM error:"):
            return self.fallback.generate(**kwargs)
        return result


def create_provider(provider_name: str, *, base_url: str, configured_model: str) -> Any:
    if provider_name == "ollama":
        return OllamaProvider(base_url=base_url, configured_model=configured_model)
    if provider_name == "openai":
        return OpenAIProvider(configured_model=configured_model)
    if provider_name == "anthropic":
        return AnthropicProvider(configured_model=configured_model)
    raise LLMProviderError(f"Unsupported LLM provider '{provider_name}'")
