"""Lightweight in-process operational metrics for local diagnosis.

Updated: 2026-10-08 19:09
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class VendorMetrics:
    """Lưu trữ chỉ số vận hành cho một nhà cung cấp dịch vụ.

    Attributes:
        calls: Số lượt gọi.
        errors: Số lượt gọi bị lỗi.
        total_latency_ms: Tổng độ trễ tính bằng millisecond.
    """

    calls: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    @property
    def average_latency_ms(self) -> float:
        """Tính độ trễ trung bình trên mỗi lượt gọi (millisecond).

        Returns:
            Độ trễ trung bình nếu calls > 0, ngược lại trả về 0.0.
        """
        return self.total_latency_ms / self.calls if self.calls else 0.0


_vendor_metrics: defaultdict[str, VendorMetrics] = defaultdict(VendorMetrics)
_cache_hits = 0
_translation_memory_hits = 0


def record_provider_call(vendor: str, latency_ms: float, *, error: bool = False) -> None:
    """Ghi nhận một lượt gọi nhà cung cấp dịch vụ.

    Args:
        vendor: Tên nhà cung cấp dịch vụ.
        latency_ms: Độ trễ của lượt gọi tính bằng millisecond (tối thiểu là 0.0).
        error: Cờ xác định lượt gọi có gặp lỗi hay không.
    """
    metrics = _vendor_metrics[vendor]
    metrics.calls += 1
    metrics.total_latency_ms += max(0.0, latency_ms)
    if error:
        metrics.errors += 1


def record_cache_hit() -> None:
    """Tăng số lượt truy xuất bộ nhớ đệm (cache hit) thành công."""
    global _cache_hits
    _cache_hits += 1


def record_translation_memory_hit() -> None:
    """Tăng số lượt truy xuất bộ nhớ dịch (translation memory hit) thành công."""
    global _translation_memory_hits
    _translation_memory_hits += 1


def snapshot() -> dict:
    """Tạo bản chụp trạng thái các chỉ số vận hành hiện tại.

    Returns:
        Dict chứa cache_hits, translation_memory_hits và thông tin chỉ số
        gồm calls, errors, average_latency_ms của từng provider đã sắp xếp theo tên.
    """
    return {
        "cache_hits": _cache_hits,
        "translation_memory_hits": _translation_memory_hits,
        "providers": {
            vendor: {
                "calls": metrics.calls,
                "errors": metrics.errors,
                "average_latency_ms": round(metrics.average_latency_ms, 2),
            }
            for vendor, metrics in sorted(_vendor_metrics.items())
        },
    }


def reset_for_tests() -> None:
    """Đặt lại toàn bộ chỉ số vận hành và dữ liệu provider về trạng thái ban đầu."""
    global _cache_hits, _translation_memory_hits
    _vendor_metrics.clear()
    _cache_hits = 0
    _translation_memory_hits = 0
