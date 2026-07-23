"""AutoFormat — làm sạch và chuẩn hóa văn bản dịch tự động.

Giống tính năng Polish của Calibre nhưng nhẹ hơn, tập trung vào:
- Chuẩn hóa dấu câu, khoảng trắng
- Viết hoa đầu câu
- Chuẩn hóa dấu ngoặc kép
- Fix lỗi chính tả phổ biến (kiểu "không" -> "không")

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import re


def autoformat(text: str) -> str:
    """Chuẩn hóa văn bản dịch: dấu câu, khoảng trắng, viết hoa.

    Args:
        text: Bản dịch thô từ AI.

    Returns:
        Văn bản đã format.
    """
    result = text

    # 1. Xoá khoảng trắng thừa (đầu/cuối dòng, nhiều space liên tiếp)
    result = re.sub(r" +", " ", result)  # Nhiều space -> 1 space
    result = re.sub(r"\n{3,}", "\n\n", result)  # Nhiều newline -> 2 newlines

    # 2. Dấu câu: thêm space sau dấu . ! ? nếu thiếu
    result = re.sub(r"([.!?])([A-Za-zÀ-Ỹà-ỹ])", r"\1 \2", result)

    # 3. Xoá space trước dấu câu
    result = re.sub(r" +([.,;:!?])", r"\1", result)

    # 4. Chuẩn hóa dấu ngoặc kép: "..." -> "..."
    result = result.replace('"', '"').replace('"', '"')
    result = result.replace("\u2018", "'").replace("\u2019", "'")

    # 5. Viết hoa đầu câu
    result = _capitalize_sentences(result)

    # 6. Fix lỗi chính tả phổ biến trong tiếng Việt
    result = _fix_common_typos(result)

    return result.strip()


def _capitalize_sentences(text: str) -> str:
    """Viết hoa chữ cái đầu mỗi câu."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    capitalized = []
    for sent in sentences:
        if sent and sent[0].isalpha():
            sent = sent[0].upper() + sent[1:]
        capitalized.append(sent)
    return " ".join(capitalized)


_TYPOS: dict[str, str] = {
    # Lỗi chính tả tiếng Việt phổ biến
    "không": "không",
    "chả": "chả",
    "hok": "không",
    "ko": "không",
    "kô": "không",
    "dc": "được",
    "đc": "được",
    "đk": "được",
    "mà": "mà",
    "mừ": "mà",
    "z": "vậy",
    "vậy": "vậy",
    "thui": "thôi",
    "thoy": "thôi",
    "hok": "không",
    "ng\u01b0ời": "người",
    # Dấu câu lặp
    "!!!": "!",
    "??": "?",
    "..": ".",
    "...": "...",
}


def _fix_common_typos(text: str) -> str:
    """Fix lỗi chính tả + dấu câu lặp."""
    result = text
    for wrong, correct in _TYPOS.items():
        result = result.replace(wrong, correct)
    return result


def autoformat_chunk(original: str, translated: str) -> str:
    """Format chunk dịch: giữ nguyên dấu câu của bản gốc nếu có.

    Args:
        original: Text gốc (để tham khảo dấu câu).
        translated: Bản dịch cần format.

    Returns:
        Bản dịch đã format.
    """
    formatted = autoformat(translated)

    # Nếu original kết thúc bằng . ! ? thì translated cũng phải kết thúc bằng dấu đó
    if original.strip() and formatted.strip():
        orig_end = original.strip()[-1]
        trans_end = formatted.strip()[-1]
        if orig_end in ".!?" and trans_end not in ".!?":
            formatted = formatted.rstrip() + orig_end

    return formatted
