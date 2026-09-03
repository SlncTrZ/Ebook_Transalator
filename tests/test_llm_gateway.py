"""Tests for the unified LLM gateway, provider routing, and live model discovery."""

from __future__ import annotations

import httpx
import pytest

from ebook_translator.translator.adapters import (
    AnthropicAdapter,
    GeminiAdapter,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    create_adapter,
)
from ebook_translator.translator.gateway import LLMConfig, LLMGateway
import ebook_translator.translator.gateway as gateway_module


@pytest.mark.parametrize(
    ("vendor", "expected_type"),
    [
        ("openai", OpenAICompatibleAdapter),
        ("deepseek", OpenAICompatibleAdapter),
        ("groq", OpenAICompatibleAdapter),
        ("together", OpenAICompatibleAdapter),
        ("anthropic", AnthropicAdapter),
        ("google", GeminiAdapter),
        ("ollama", OllamaAdapter),
    ],
)
def test_create_adapter_routes_vendor(vendor: str, expected_type: type) -> None:
    adapter = create_adapter(vendor, "key", "model")
    assert isinstance(adapter, expected_type)


def test_gateway_uses_provider_base_url_but_never_hardcodes_model() -> None:
    gateway = LLMGateway(LLMConfig(vendor="anthropic", api_key="key"))
    assert gateway.config.vendor == "anthropic"
    assert gateway.config.model == ""
    assert gateway.config.base_url == "https://api.anthropic.com/v1"


def test_custom_base_url_is_preserved_and_trailing_slash_is_normalized() -> None:
    adapter = create_adapter(
        "ollama",
        "",
        "qwen-test",
        "http://192.168.1.171:11434/",
    )
    assert adapter.base_url == "http://192.168.1.171:11434"
    assert adapter.model == "qwen-test"


@pytest.mark.asyncio
async def test_ollama_models_are_fetched_from_configured_remote_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "models": [
                    {"name": "qwen3:14b"},
                    {"name": "gemma3:12b"},
                ]
            }

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, **_: object) -> FakeResponse:
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: FakeClient())
    adapter = OllamaAdapter("", "", "http://192.168.1.171:11434/")

    models = await adapter.fetch_models()

    assert calls == ["http://192.168.1.171:11434/api/tags"]
    assert models == ["qwen3:14b", "gemma3:12b"]


@pytest.mark.asyncio
async def test_openai_compatible_model_discovery_returns_provider_ids_unfiltered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"id": "chat-model"},
                    {"id": "embedding-model"},
                    {"id": "provider-special-model"},
                ]
            }

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, *_: object, **__: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: FakeClient())
    adapter = OpenAICompatibleAdapter("key", "", "https://provider.example/v1")

    assert await adapter.fetch_models() == [
        "chat-model",
        "embedding-model",
        "provider-special-model",
    ]


@pytest.mark.asyncio
async def test_gateway_forwards_generation_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeAdapter:
        async def translate(
            self,
            messages: list[dict],
            *,
            temperature: float = 0.3,
            response_format: dict | None = None,
        ) -> str:
            calls.append(
                {
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": response_format,
                }
            )
            return "ok"

    monkeypatch.setattr(gateway_module, "create_adapter", lambda **_: FakeAdapter())
    gateway = LLMGateway(LLMConfig(vendor="google", api_key="key", model="gemini-test"))
    messages = [{"role": "user", "content": "Return JSON"}]

    result = await gateway.generate(
        messages,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    assert result == "ok"
    assert calls == [
        {
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
    ]
