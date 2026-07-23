"""Deterministic Validation — Kiểm tra bản dịch bằng Regex/String, không dùng AI.

Rule: Chỉ kiểm tra glossary terms CÓ XUẤT HIỆN trong source text.
Bỏ qua term không xuất hiện → tránh false positive, tránh infinite loop.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import re

MAX_RETRIES = 2  # Tối đa 2 lần retry, sau đó bỏ qua


def check_glossary_terms(
    source_text: str,
    translated_text: str,
    glossary_terms: list[dict],
) -> list[str]:
    """Quét source text trước, chỉ kiểm tra terms CÓ XUẤT HIỆN trong source.

    Args:
        source_text: Text gốc của chunk.
        translated_text: Bản dịch cần kiểm tra.
        glossary_terms: List {"source": ..., "target": ...}.

    Returns:
        List target terms bị thiếu trong bản dịch (empty = pass).
    """
    missing: list[str] = []
    translated_lower = translated_text.lower()

    for term in glossary_terms:
        source = term.get("source", "").strip()
        target = term.get("target", "").strip()
        if not source or not target:
            continue

        # Chỉ kiểm tra nếu term CÓ trong source text
        if source.lower() in source_text.lower():
            if target.lower() not in translated_lower:
                missing.append(target)

    return missing


def build_retry_prompt(
    original: str,
    translated: str,
    missing_terms: list[str],
) -> str:
    """Tạo prompt yêu cầu Translate Agent dịch lại, nhấn mạnh term bị thiếu."""
    terms_str = "\n".join(f"  - {t}" for t in missing_terms)
    return (
        f"Missing glossary terms in your translation:\n{terms_str}\n\n"
        f"Please retranslate and INCLUDE these terms:\n\n"
        f"[Original]\n{original}\n\n[Previous]\n{translated}\n"
    )


def validate_and_fix(
    source_text: str,
    translated: str,
    required_terms: list[dict],
) -> tuple[str, list[str]]:
    """Kiểm tra + tự động fix capitalization đơn giản.

    Returns:
        (translated đã sửa, list missing terms cần retry).
    """
    result = translated

    # Auto-fix capitalization
    for term in required_terms:
        target = term.get("target", "").strip()
        if not target:
            continue
        if target.lower() in source_text.lower():
            pattern = re.compile(re.escape(target), re.IGNORECASE)
            if pattern.search(result) and target not in result:
                result = pattern.sub(target, result)

    missing = check_glossary_terms(source_text, result, required_terms)
    return result, missing
