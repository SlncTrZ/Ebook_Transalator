"""P0.2 tests for the unified LLM gateway and vendor routing."""

from __future__ import annotations

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


def test_gateway_resolves_vendor_defaults() -> None:
    gateway = LLMGateway(LLMConfig(vendor="anthropic", api_key="key"))
    assert gateway.config.vendor == "anthropic"
    assert gateway.config.model == "claude-3-haiku-20240307"
    assert gateway.config.base_url == "https://api.anthropic.com/v1"


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
