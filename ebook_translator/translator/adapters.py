"""Vendor adapters — dịch vụ AI đa vendor (OpenAI, Anthropic, Gemini, Ollama...).

Mỗi vendor implement 2 method:
- translate(messages) -> str
- fetch_models() -> list[str]  (lấy danh sách model thật từ API)

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-10-08 19:04
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
        default_model="",
        docs_url="https://platform.openai.com/api-keys",
    ),
    "deepseek": VendorInfo(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    "groq": VendorInfo(
        id="groq",
        name="Groq (free, fast)",
        base_url="https://api.groq.com/openai/v1",
        default_model="",
        docs_url="https://console.groq.com/keys",
    ),
    "together": VendorInfo(
        id="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="",
        docs_url="https://api.together.xyz/settings/api-keys",
    ),
    "ollama": VendorInfo(
        id="ollama",
        name="Ollama (local)",
        base_url="http://localhost:11434",
        default_model="",
        requires_api_key=False,
        docs_url="https://ollama.com/",
    ),
    "anthropic": VendorInfo(
        id="anthropic",
        name="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        default_model="",
        docs_url="https://console.anthropic.com/",
    ),
    "google": VendorInfo(
        id="google",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="",
        docs_url="https://aistudio.google.com/apikey",
    ),
}


# ── Base adapter ─────────────────────────────────────────────────────────


class BaseAdapter(ABC):
    """Abstract adapter — mỗi vendor implement riêng."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        """Khởi tạo BaseAdapter với khóa API, mô hình dịch và URL gốc dịch vụ.

        Args:
            api_key: Khóa xác thực API của vendor.
            model: Tên mô hình AI được sử dụng.
            base_url: URL cơ sở của API (tự động loại bỏ dấu / ở cuối).

        Side-effects:
            Gán các thuộc tính api_key, model và base_url vào instance.
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def translate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Gửi yêu cầu dịch bất đồng bộ tới vendor API.

        Args:
            messages: Danh sách các dict chứa tin nhắn hội thoại (role, content).
            temperature: Tham số kiểm soát độ sáng tạo/ngẫu nhiên (mặc định 0.3).
            response_format: Cấu hình định dạng đầu ra mong muốn (nếu có).

        Returns:
            Văn bản phản hồi từ mô hình AI.

        Side-effects:
            Thực hiện yêu cầu I/O mạng bất đồng bộ tới vendor API trong các lớp con.
        """
        ...

    @abstractmethod
    async def fetch_models(self) -> list[str]:
        """Lấy danh sách model thật từ API vendor."""
        ...


# ── OpenAI-compatible adapter (Deepseek, Groq, Together...) ────────────


class OpenAICompatibleAdapter(BaseAdapter):
    """Dùng chung cho mọi vendor OpenAI-compatible."""

    async def translate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Gửi yêu cầu tạo hoàn thành hội thoại tới endpoint /chat/completions theo chuẩn OpenAI API.

        Args:
            messages: Danh sách tin nhắn dạng dict với thông tin role và content.
            temperature: Độ ngẫu nhiên của câu trả lời (mặc định 0.3).
            response_format: Tham số tùy chỉnh định dạng phản hồi (vd: JSON mode).

        Returns:
            Văn bản phản hồi đã loại bỏ khoảng trắng thừa hai đầu.

        Side-effects:
            Gửi truy vấn HTTP POST bất đồng bộ tới endpoint /chat/completions qua httpx.AsyncClient.
            Bắn ngoại lệ httpx.HTTPStatusError nếu API trả về mã lỗi HTTP.
        """
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if response_format:
                payload["response_format"] = response_format
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    async def fetch_models(self) -> list[str]:
        """GET /models and return provider-reported model IDs verbatim."""
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/models",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", []) if m.get("id")]

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


# ── Ollama adapter (API format khac: /api/tags) ──────────────────────────


class OllamaAdapter(BaseAdapter):
    """Adapter riêng cho Ollama (API local, format khác)."""

    async def translate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Chuyển đổi tin nhắn hội thoại thành prompt Ollama và gửi yêu cầu sinh văn bản.

        Args:
            messages: Danh sách tin nhắn hội thoại cần gom thành prompt duy nhất.
            temperature: Tham số ngẫu nhiên truyền vào options của Ollama (mặc định 0.3).
            response_format: Tham số định dạng (không được xử lý trực tiếp bởi adapter này).

        Returns:
            Văn bản phản hồi từ mô hình Ollama cục bộ.

        Side-effects:
            Gửi truy vấn HTTP POST bất đồng bộ tới endpoint /api/generate qua httpx.AsyncClient.
            Bắn ngoại lệ httpx.HTTPStatusError nếu có lỗi kết nối hoặc HTTP.
        """
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
                    "options": {"temperature": temperature},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()

    async def fetch_models(self) -> list[str]:
        """Truy vấn danh sách các mô hình khả dụng từ instance Ollama cục bộ.

        Returns:
            Danh sách tên các mô hình (dựa trên trường 'name' trong kết quả /api/tags).

        Side-effects:
            Gửi truy vấn HTTP GET bất đồng bộ tới endpoint /api/tags qua httpx.AsyncClient.
            Bắn ngoại lệ httpx.HTTPStatusError nếu có lỗi HTTP.
        """
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", []) if m.get("name")]


# ── Anthropic adapter ────────────────────────────────────────────────────


class AnthropicAdapter(BaseAdapter):
    """Adapter riêng cho Anthropic Claude API."""

    async def translate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Tách tin nhắn system và gửi yêu cầu hoàn thành tới endpoint /messages của Anthropic.

        Args:
            messages: Danh sách các tin nhắn hội thoại (system, user, assistant).
            temperature: Tham số ngẫu nhiên của phản hồi (mặc định 0.3).
            response_format: Không áp dụng trực tiếp cho Anthropic adapter.

        Returns:
            Văn bản trả về từ khối phản hồi đầu tiên của mô hình Claude.

        Side-effects:
            Gửi truy vấn HTTP POST bất đồng bộ tới endpoint /messages với header x-api-key.
            Bắn ngoại lệ httpx.HTTPStatusError nếu API báo lỗi.
        """
        import httpx

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
            "temperature": temperature,
        }
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
        """Lấy toàn bộ danh sách mô hình từ Anthropic API bằng cơ chế phân trang.

        Returns:
            Danh sách chuỗi các ID mô hình do Anthropic cung cấp.

        Side-effects:
            Thực hiện liên tiếp các truy vấn HTTP GET phân trang (tối đa 20 trang) qua httpx.AsyncClient.
            Bắn ngoại lệ httpx.HTTPStatusError nếu xảy ra lỗi mạng hoặc HTTP.
        """
        import httpx

        models: list[str] = []
        after_id = ""
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(20):
                params: dict[str, str | int] = {"limit": 100}
                if after_id:
                    params["after_id"] = after_id
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                models.extend(m["id"] for m in data.get("data", []) if m.get("id"))
                if not data.get("has_more"):
                    break
                after_id = data.get("last_id", "")
                if not after_id:
                    break
        return models


# ── Google Gemini adapter ────────────────────────────────────────────────


class GeminiAdapter(BaseAdapter):
    """Adapter riêng cho Google Gemini API."""

    async def translate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Chuyển đổi messages sang định dạng Gemini REST API và gửi yêu cầu sinh nội dung.

        Args:
            messages: Danh sách tin nhắn (system sẽ chuyển thành system_instruction, user/assistant thành contents).
            temperature: Tham số ngẫu nhiên nằm trong generationConfig (mặc định 0.3).
            response_format: Không áp dụng trực tiếp trong adapter này.

        Returns:
            Nội dung văn bản được phản hồi từ candidate đầu tiên của Gemini.

        Side-effects:
            Gửi truy vấn HTTP POST bất đồng bộ tới endpoint :generateContent với api_key trong URL query.
            Bắn ngoại lệ httpx.HTTPStatusError nếu yêu cầu thất bại.
        """
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
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096},
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
        """Lấy danh sách các mô hình khả dụng từ Gemini REST API qua truy vấn phân trang.

        Returns:
            Danh sách tên các mô hình Gemini (đã loại bỏ tiền tố 'models/').

        Side-effects:
            Thực hiện các truy vấn HTTP GET phân trang (dùng pageToken) tới endpoint /models qua httpx.AsyncClient.
            Bắn ngoại lệ httpx.HTTPStatusError nếu có lỗi API.
        """
        import httpx

        models: list[str] = []
        page_token = ""
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(20):
                params = {"key": self.api_key, "pageSize": 100}
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(f"{self.base_url}/models", params=params)
                resp.raise_for_status()
                data = resp.json()
                models.extend(
                    m["name"].replace("models/", "")
                    for m in data.get("models", [])
                    if m.get("name")
                )
                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break
        return models


# ── Factory ──────────────────────────────────────────────────────────────


def create_adapter(
    vendor_id: str, api_key: str, model: str, base_url: str | None = None
) -> BaseAdapter:
    """Tạo đối tượng adapter tương ứng với vendor_id chỉ định.

    Args:
        vendor_id: Mã nhận dạng vendor (vd: 'anthropic', 'google', 'ollama', 'openai', ...).
        api_key: Khóa API sử dụng cho adapter.
        model: Tên mô hình mặc định hoặc được chọn.
        base_url: URL cơ sở tùy chỉnh cho endpoint (nếu None sẽ dùng URL mặc định của vendor).

    Returns:
        Instance của lớp con BaseAdapter phù hợp với vendor (AnthropicAdapter, GeminiAdapter, OllamaAdapter hoặc OpenAICompatibleAdapter).

    Side-effects:
        Không có side-effect mạng hay sửa đổi trạng thái bên ngoài.
    """
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
        Provider-reported model IDs. Provider/network errors are propagated.
    """
    vendor = VENDORS.get(vendor_id)
    url = base_url or (vendor.base_url if vendor else "")
    adapter = create_adapter(vendor_id, api_key, "", url)
    return await adapter.fetch_models()
