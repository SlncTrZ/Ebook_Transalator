"""Unified LLM gateway for Standard, Research, and Agentic workflows."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from ebook_translator.translator.adapters import VENDORS, BaseAdapter, create_adapter
from ebook_translator.translator.metrics import record_provider_call


@dataclass
class LLMConfig:
    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    def resolved(self) -> "LLMConfig":
        vendor = VENDORS.get(self.vendor)
        return LLMConfig(
            vendor=self.vendor,
            api_key=self.api_key,
            model=self.model or (vendor.default_model if vendor else ""),
            base_url=self.base_url or (vendor.base_url if vendor else ""),
        )


class LLMGateway:
    """One provider-agnostic entry point for model generation."""

    def __init__(self, config: LLMConfig) -> None:
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
