import logging

import httpx

from app.config import settings

logger = logging.getLogger("openrouter")


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    """Chat-completions client for OpenRouter (https://openrouter.ai).

    The app's LLM (currently deepseek/deepseek-v4-flash, see settings.llm_model)
    is accessed through OpenRouter rather than DeepSeek's own API.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._api_key = api_key or settings.openrouter_api_key
        self._base_url = (base_url or settings.openrouter_base_url).rstrip("/")

    def chat(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        payload = {
            "model": model or settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

        data = response.json()
        usage = data.get("usage", {})
        logger.info(
            "openrouter_call model=%s input_tokens=%s output_tokens=%s",
            payload["model"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise OpenRouterError(f"Unexpected OpenRouter response shape: {data}") from exc
