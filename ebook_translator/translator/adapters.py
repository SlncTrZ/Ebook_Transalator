"""Vendor adapters — dịch vụ AI đa vendor (OpenAI, Anthropic, Gemini, Ollama...).

Mỗi vendor implement 2 method:
- translate(messages) → str
- Có riêng base_url, model list, timeout

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VendorInfo:
    """Thông tin vendor cho UI."""

    id: str
    name: str
    base_url: str
    default_model: str
    models: list[str] = field(default_factory=list)
    requires_api_key: bool = True
    docs_url: str = ""


# ── Danh sách vendor hỗ trợ ──────────────────────────────────────────────

VENDORS: dict[str, VendorInfo] = {
    "openai": VendorInfo(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        models=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        docs_url="https://platform.openai.com/api-keys",
    ),
    "deepseek": VendorInfo(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        models=["deepseek-chat", "deepseek-reasoner"],
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    "groq": VendorInfo(
        id="groq",
        name="Groq (free, fast)",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
        docs_url="https://console.groq.com/keys",
    ),
    "together": VendorInfo(
        id="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="mistralai/Mixtral-8x22B-Instruct-v0.1",
        models=[
            "mistralai/Mixtral-8x22B-Instruct-v0.1",
            "meta-llama/Llama-3-70b-chat-hf",
        ],
        docs_url="https://api.together.xyz/settings/api-keys",
    ),
    "ollama": VendorInfo(
        id="ollama",
        name="Ollama (local)",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        models=["llama3.2", "llama3.1", "qwen2.5", "gemma2", "mistral"],
        requires_api_key=False,
        docs_url="https://ollama.com/",
    ),
    "anthropic": VendorInfo(
        id="anthropic",
        name="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-haiku-20240307",
        models=[
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-opus-20240229",
            "claude-3-5-sonnet-20241022",
        ],
        docs_url="https://console.anthropic.com/",
    ),
    "google": VendorInfo(
        id="google",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
        models=[
            "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        docs_url="https://aistudio.google.com/apikey",
    ),
}

# ── Base adapter ─────────────────────────────────────────────────────────


class BaseAdapter(ABC):
    """Abstract adapter — mỗi vendor implement riêng."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @abstractmethod
    async def translate(self, messages: list[dict]) -> str:
        """Gọi API dịch, trả về text đã dịch."""
        ...

    @abstractmethod
    def build_headers(self) -> dict[str, str]: ...

    @abstractmethod
    def build_payload(self, messages: list[dict]) -> dict: ...


# ── OpenAI-compatible adapter (Deepseek, Groq, Together, Ollama...) ──────


class OpenAICompatibleAdapter(BaseAdapter):
    """Dùng chung cho mọi vendor OpenAI-compatible."""

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def build_payload(self, messages: list[dict]) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.build_headers(),
                json=self.build_payload(messages),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()


# ── Anthropic adapter ────────────────────────────────────────────────────


class AnthropicAdapter(BaseAdapter):
    """Adapter riêng cho Anthropic Claude API."""

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def build_payload(self, messages: list[dict]) -> dict:
        # Anthropic format: system riêng, messages là array
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": chat_messages,
        }
        if system:
            payload["system"] = system
        return payload

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                headers=self.build_headers(),
                json=self.build_payload(messages),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()


# ── Google Gemini adapter ────────────────────────────────────────────────


class GeminiAdapter(BaseAdapter):
    """Adapter riêng cho Google Gemini API."""

    def build_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def build_payload(self, messages: list[dict]) -> dict:
        # Gemini format: contents array, system_instruction riêng
        system = ""
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            },
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        return payload

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                headers=self.build_headers(),
                json=self.build_payload(messages),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Factory ──────────────────────────────────────────────────────────────


def create_adapter(
    vendor_id: str, api_key: str, model: str, base_url: str | None = None
) -> BaseAdapter:
    """Tạo adapter phù hợp với vendor.

    Args:
        vendor_id: 'openai', 'deepseek', 'groq', 'together', 'ollama', 'anthropic', 'google'
        api_key: API key (có thể empty nếu vendor ko cần)
        model: Model name
        base_url: Override base URL (optional)

    Returns:
        BaseAdapter instance
    """
    vendor = VENDORS.get(vendor_id)
    url = base_url or (vendor.base_url if vendor else "")

    if vendor_id == "anthropic":
        return AnthropicAdapter(api_key, model, url)
    elif vendor_id == "google":
        return GeminiAdapter(api_key, model, url)
    else:
        return OpenAICompatibleAdapter(api_key, model, url)
