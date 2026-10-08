"""Unified LLM gateway for Standard, Research, and Agentic workflows.

Updated: 2026-10-08 19:12
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from ebook_translator.translator.adapters import VENDORS, BaseAdapter, create_adapter
from ebook_translator.translator.metrics import record_provider_call


@dataclass
class LLMConfig:
    """Cấu hình kết nối cho LLM provider.

    Attributes:
        vendor: Tên nhà cung cấp dịch vụ LLM.
        api_key: Khóa API để xác thực.
        model: Tên mô hình cần sử dụng.
        base_url: Đường dẫn API gốc.
    """

    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    def resolved(self) -> "LLMConfig":
        """Trả về cấu hình mới với model và base_url mặc định từ vendor nếu chưa được chỉ định.

        Returns:
            LLMConfig: Đối tượng cấu hình đã chuẩn hóa.
        """
        vendor = VENDORS.get(self.vendor)
        return LLMConfig(
            vendor=self.vendor,
            api_key=self.api_key,
            model=self.model or (vendor.default_model if vendor else ""),
            base_url=self.base_url or (vendor.base_url if vendor else ""),
        )


class LLMGateway:
    """Cổng kết nối độc lập với provider để tạo văn bản từ mô hình LLM."""

    def __init__(self, config: LLMConfig) -> None:
        """Khởi tạo gateway và adapter xử lý dựa trên cấu hình truyền vào.

        Args:
            config: Cấu hình LLMConfig.
        """
        self.config = config.resolved()
        self.adapter: BaseAdapter = create_adapter(
            vendor_id=self.config.vendor,
            api_key=self.config.api_key,
            model=self.config.model,
            base_url=self.config.base_url,
        )

    async def generate(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> str:
        """Gửi danh sách tin nhắn tới adapter để sinh nội dung và đo lường thời gian thực thi.

        Args:
            messages: Danh sách tin nhắn đầu vào dạng dict.
            temperature: Tham số kiểm soát độ ngẫu nhiên khi sinh văn bản.
            response_format: Cấu trúc định dạng phản hồi mong muốn (tùy chọn).

        Returns:
            str: Chuỗi văn bản phản hồi từ mô hình.
        """
        started = perf_counter()
        try:
            result = await self.adapter.translate(
                messages,
                temperature=temperature,
                response_format=response_format,
            )
        except Exception:
            record_provider_call(
                self.config.vendor,
                (perf_counter() - started) * 1000,
                error=True,
            )
            raise
        record_provider_call(
            self.config.vendor,
            (perf_counter() - started) * 1000,
        )
        return result
