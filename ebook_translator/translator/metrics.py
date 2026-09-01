"""Lightweight in-process operational metrics for local diagnosis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class VendorMetrics:
    calls: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    @property
    def average_latency_ms(self) -> float:
        return self.total_latency_ms / self.calls if self.calls else 0.0


_vendor_metrics: defaultdict[str, VendorMetrics] = defaultdict(VendorMetrics)
_cache_hits = 0
_translation_memory_hits = 0


def record_provider_call(vendor: str, latency_ms: float, *, error: bool = False) -> None:
    metrics = _vendor_metrics[vendor]
    metrics.calls += 1
    metrics.total_latency_ms += max(0.0, latency_ms)
    if error:
        metrics.errors += 1


def record_cache_hit() -> None:
    global _cache_hits
    _cache_hits += 1


def record_translation_memory_hit() -> None:
    global _translation_memory_hits
    _translation_memory_hits += 1


def snapshot() -> dict:
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
    global _cache_hits, _translation_memory_hits
    _vendor_metrics.clear()
    _cache_hits = 0
    _translation_memory_hits = 0
