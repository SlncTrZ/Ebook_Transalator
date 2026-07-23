"""TXT parser — auto-detect encoding, heuristic chapter split.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import re

import chardet

from .base import BaseParser, ParsedBook

# Fallback chain: uu tien encoding Chau A (chardet hay nham KOI8-U <-> GBK)
_ENCODING_PRIORITY = [
    "utf-8",
    "gb18030",
    "gbk",
    "gb2312",
    "big5",
    "shift_jis",
    "euc-jp",
    "euc-kr",
    "utf-16",
]

_CHAPTER_PATTERNS = re.compile(
    r"^(?:"
    r"(?:chương|chapter|ch|section|phần|book|vol)\s*[\dIVXL]+"
    r"|"
    r"\d+\.\s*"
    r"|"
    r"第[\u4e00-\u9fff\u3000-\u303f]+[章节回]"
    r")",
    re.IGNORECASE,
)


def _score_encoding(raw: bytes, enc: str) -> float:
    """Decode bytes with encoding, return ratio of valid chars (0-1)."""
    try:
        decoded = raw.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        return 0.0
    if not decoded:
        return 0.0
    replacement_count = decoded.count("\ufffd")
    return 1.0 - (replacement_count / len(decoded))


class TxtParser(BaseParser):
    """Parse .txt files with encoding detection and chapter splitting."""

    def _detect_encoding(self, file_path: str) -> str:
        """Detect encoding: score-based, uu tien encoding co it replacement chars nhat."""
        try:
            with open(file_path, "rb") as f:
                raw = f.read(1024 * 64)
        except OSError as e:
            raise ValueError(f"Cannot read file: {e}") from e

        best_enc = "utf-8"
        best_score = 0.0

        for enc in _ENCODING_PRIORITY:
            score = _score_encoding(raw, enc)
            if score > best_score:
                best_score = score
                best_enc = enc
            if score > 0.99:
                break

        # Neu khong encoding nao dat > 50%, fallback chardet
        if best_score < 0.5:
            try:
                result = chardet.detect(raw)
                det = result.get("encoding", "") or ""
                if det and result.get("confidence", 0) > 0.3:
                    return det
            except Exception:
                pass

        return best_enc

    def parse(self, file_path: str) -> ParsedBook:
        enc = self._detect_encoding(file_path)
        try:
            with open(file_path, encoding=enc, errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise ValueError(f"Cannot read file: {e}") from e

        lines = [line.strip() for line in text.splitlines()]

        paragraphs: list[str] = []
        for line in lines:
            if line:
                paragraphs.append(line)

        chapters: list[list[str]] = []
        current_chapter: list[str] = []
        for para in paragraphs:
            if _CHAPTER_PATTERNS.match(para):
                if current_chapter:
                    chapters.append(current_chapter)
                current_chapter = [para]
            else:
                current_chapter.append(para)

        if current_chapter:
            chapters.append(current_chapter)

        if not chapters and paragraphs:
            chapters = [paragraphs]

        parsed = ParsedBook()
        parsed.title = (
            file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        )
        parsed.chapters = chapters
        parsed.raw_metadata = {"encoding": enc}
        return parsed
