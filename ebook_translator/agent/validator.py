"""Deterministic Validation — Kiểm tra bản dịch bằng Regex/String, không dùng AI.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import re


def check_glossary_terms(translated: str, required_terms: list[dict]) -> list[str]:
    """Quét bản dịch, tìm các glossary term bị thiếu.

    Args:
        translated: Bản dịch cần kiểm tra.
        required_terms: List {"source": ..., "target": ...} các term bắt buộc.

    Returns:
        List các target term bị thiếu (empty = pass).
    """
    missing: list[str] = []
    translated_lower = translated.lower()

    for term in required_terms:
        target = term.get("target", "").strip()
        if not target:
            continue
        if target.lower() not in translated_lower:
            missing.append(target)

    return missing


def check_capitalization(translated: str, proper_nouns: list[str]) -> list[str]:
    """Kiểm tra danh từ riêng có được viết hoa chữ cái đầu không.

    Args:
        translated: Bản dịch.
        proper_nouns: List các từ cần viết hoa (VD: ["Thiên Địa Pháp Tắc", "Hỏa Cầu Thuật"]).

    Returns:
        List các từ bị viết sai capitalization.
    """
    errors: list[str] = []
    for noun in proper_nouns:
        if noun.lower() in translated.lower():
            if noun not in translated:
                errors.append(noun)
    return errors


def build_retry_prompt(
    original: str,
    translated: str,
    missing_terms: list[str],
) -> str:
    """Tạo prompt yêu cầu Translate Agent dịch lại, nhấn mạnh các term bị thiếu.

    Args:
        original: Text gốc.
        translated: Bản dịch lỗi.
        missing_terms: Các term bị thiếu (cần có trong bản dịch mới).

    Returns:
        Prompt string để gửi lại cho Translate Agent.
    """
    terms_str = "\n".join(f"  - {t}" for t in missing_terms)
    return (
        f"The previous translation is MISSING these required glossary terms:\n"
        f"{terms_str}\n\n"
        f"Please retranslate and make SURE these terms appear in the output.\n\n"
        f"[Original]\n{original}\n\n[Previous Translation (for reference)]\n{translated}\n"
    )


def validate_and_fix(translated: str, required_terms: list[dict]) -> tuple[str, list[str]]:
    """Kiểm tra và tự động sửa lỗi đơn giản (capitalization).

    Args:
        translated: Bản dịch.
        required_terms: Glossary terms.

    Returns:
        (translated đã sửa, list lỗi không tự sửa được cần retry).
    """
    result = translated
    unfixable: list[str] = []

    # Tự động fix capitalization cho các proper nouns
    for term in required_terms:
        target = term.get("target", "").strip()
        if not target:
            continue

        # Nếu term xuất hiện trong text nhưng sai capitalization → tự fix
        pattern = re.compile(re.escape(target), re.IGNORECASE)
        if pattern.search(result) and target not in result:
            result = pattern.sub(target, result)

    # Kiểm tra còn thiếu term nào không
    missing = check_glossary_terms(result, required_terms)

    return result, missing
