import httpx
import pytest

from app.services.openrouter import OpenRouterClient, OpenRouterError


def _make_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("POST", "https://x"))


def test_chat_returns_message_content(monkeypatch):
    def fake_post(*args, **kwargs):
        return _make_response(
            {
                "choices": [{"message": {"content": "hello world"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenRouterClient(api_key="k", base_url="https://openrouter.ai/api/v1")
    result = client.chat("system", "user")

    assert result == "hello world"


def test_chat_uses_configured_model_by_default(monkeypatch):
    captured = {}

    def fake_post(*args, **kwargs):
        captured["model"] = kwargs["json"]["model"]
        return _make_response({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenRouterClient(api_key="k")
    client.chat("system", "user")

    assert captured["model"] == "deepseek/deepseek-v4-flash"


def test_chat_raises_on_http_error(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenRouterClient(api_key="k")
    with pytest.raises(OpenRouterError):
        client.chat("system", "user")


def test_chat_raises_on_unexpected_shape(monkeypatch):
    def fake_post(*args, **kwargs):
        return _make_response({"unexpected": "shape"})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = OpenRouterClient(api_key="k")
    with pytest.raises(OpenRouterError):
        client.chat("system", "user")
