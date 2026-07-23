"""Vendor adapters — dịch vụ AI đa vendor (OpenAI, Anthropic, Gemini, Ollama...).

Mỗi vendor implement 2 method:
- translate(messages) -> str
- fetch_models() -> list[str]  (lấy danh sách model thật từ API)

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


# ── Danh sách vendor hỗ trợ (models mặc định, sẽ được fetch lại sau) ─────────

VENDORS: dict[str, VendorInfo] = {
    "openai": VendorInfo(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        docs_url="https://platform.openai.com/api-keys",
    ),
    "deepseek": VendorInfo(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    "groq": VendorInfo(
        id="groq",
        name="Groq (free, fast)",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        docs_url="https://console.groq.com/keys",
    ),
    "together": VendorInfo(
        id="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="mistralai/Mixtral-8x22B-Instruct-v0.1",
        docs_url="https://api.together.xyz/settings/api-keys",
    ),
    "ollama": VendorInfo(
        id="ollama",
        name="Ollama (local)",
        base_url="http://localhost:11434",
        default_model="llama3.2",
        requires_api_key=False,
        docs_url="https://ollama.com/",
    ),
    "anthropic": VendorInfo(
        id="anthropic",
        name="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-haiku-20240307",
        docs_url="https://console.anthropic.com/",
    ),
    "google": VendorInfo(
        id="google",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
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
    async def translate(self, messages: list[dict]) -> str: ...

    @abstractmethod
    async def fetch_models(self) -> list[str]:
        """Lấy danh sách model thật từ API vendor."""
        ...


# ── OpenAI-compatible adapter (Deepseek, Groq, Together...) ────────────


class OpenAICompatibleAdapter(BaseAdapter):
    """Dùng chung cho mọi vendor OpenAI-compatible."""

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    async def fetch_models(self) -> list[str]:
        """GET /v1/models -> list model IDs."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    # Loc chat models (bo qua embedding)
                    chat_keywords = [
                        "gpt",
                        "chat",
                        "instruct",
                        "turbo",
                        "deepseek",
                        "llama",
                        "mixtral",
                        "qwen",
                        "gemma",
                        "mistral",
                        "claude",
                        "command",
                    ]
                    filtered = [
                        m for m in models if any(k in m.lower() for k in chat_keywords)
                    ]
                    return filtered or models[:30]
        except Exception:
            pass
        return []

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


# ── Ollama adapter (API format khac: /api/tags) ──────────────────────────


class OllamaAdapter(BaseAdapter):
    """Adapter rieng cho Ollama (API local, format khac)."""

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        # Chuyen doi messages -> Ollama prompt format
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt = f"[System]\n{content}\n\n"
            elif role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()

    async def fetch_models(self) -> list[str]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    return models
        except Exception:
            pass
        return []


# ── Anthropic adapter ────────────────────────────────────────────────────


class AnthropicAdapter(BaseAdapter):
    """Adapter rieng cho Anthropic Claude API."""

    # Anthropic khong co public model list API -> hardcode + fallback
    FALLBACK_MODELS = [
        "claude-3-haiku-20240307",
        "claude-3-sonnet-20240229",
        "claude-3-opus-20240229",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ]

    async def translate(self, messages: list[dict]) -> str:
        import httpx

        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {"model": self.model, "max_tokens": 4096, "messages": chat_messages}
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()

    async def fetch_models(self) -> list[str]:
        return self.FALLBACK_MODELS


# ── Google Gemini adapter ────────────────────────────────────────────────


class GeminiAdapter(BaseAdapter):
    """Adapter rieng cho Google Gemini API."""

    async def translate(self, messages: list[dict]) -> str:
        import httpx

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
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
        }
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    async def fetch_models(self) -> list[str]:
        import httpx

        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    models = [
                        m["name"].replace("models/", "")
                        for m in resp.json().get("models", [])
                    ]
                    chat_models = [m for m in models if "gemini" in m.lower()]
                    return chat_models[:20]
        except Exception:
            pass
        return [
            "gemini-2.0-flash",
            "gemini-2.0-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]


# ── Factory ──────────────────────────────────────────────────────────────


def create_adapter(
    vendor_id: str, api_key: str, model: str, base_url: str | None = None
) -> BaseAdapter:
    """Tao adapter phu hop voi vendor."""
    vendor = VENDORS.get(vendor_id)
    url = base_url or (vendor.base_url if vendor else "")

    if vendor_id == "anthropic":
        return AnthropicAdapter(api_key, model, url)
    elif vendor_id == "google":
        return GeminiAdapter(api_key, model, url)
    elif vendor_id == "ollama":
        return OllamaAdapter(api_key, model, url)
    else:
        return OpenAICompatibleAdapter(api_key, model, url)


async def fetch_vendor_models(
    vendor_id: str, api_key: str, base_url: str | None = None
) -> list[str]:
    """Fetch danh sach model that tu vendor API.

    Args:
        vendor_id: Ten vendor.
        api_key: API key (can cho mot so vendor).
        base_url: Override base URL.

    Returns:
        List model IDs (empty neu khong fetch duoc).
    """
    vendor = VENDORS.get(vendor_id)
    url = base_url or (vendor.base_url if vendor else "")
    adapter = create_adapter(vendor_id, api_key, "", url)
    try:
        return await adapter.fetch_models()
    except Exception:
        return []
