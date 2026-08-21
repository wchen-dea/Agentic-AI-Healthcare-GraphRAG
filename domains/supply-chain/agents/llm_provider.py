from typing import Any

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
                "Pull one with: docker exec -it infra-ollama ollama pull qwen2.5:7b"
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
        except requests.RequestException as exc:
            return f"LLM error: unable to reach Ollama at {self.base_url}: {exc}"

        if response.status_code != 200:
            body = response.text
            if "not found" in body.lower():
                available_msg = ", ".join(available_models) if available_models else "none"
                return (
                    f"LLM error: requested model '{selected_model}' was not found. "
                    f"Configured model: '{self.configured_model}'. Available models: {available_msg}. "
                    "Pull a model with: docker exec -it infra-ollama ollama pull qwen2.5:7b"
                )
            return f"LLM error: {body}"

        return str(response.json().get("response") or "")


def create_provider(provider_name: str, *, base_url: str, configured_model: str) -> Any:
    if provider_name == "ollama":
        return OllamaProvider(base_url=base_url, configured_model=configured_model)
    raise LLMProviderError(f"Unsupported LLM provider '{provider_name}'")
