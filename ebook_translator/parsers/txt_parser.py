"""TXT parser — auto-detect encoding, heuristic chapter split.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import re

import chardet

from .base import BaseParser, ParsedBook

# Common chapter markers (Vietnamese + English + Chinese)
CHAPTER_PATTERNS = re.compile(
    r"^(?:"
    r"(?:chương|chapter|ch|section|phần|book|vol)\s*[\dIVXL]+"
    r"|"
    r"\d+\.\s*"
    r"|"
    r"第[\u4e00-\u9fff\u3000-\u303f]+"
    r")",
    re.IGNORECASE,
)


class TxtParser(BaseParser):
    """Parse .txt files with encoding detection and chapter splitting."""

    def _detect_encoding(self, file_path: str) -> str:
        try:
            with open(file_path, "rb") as f:
                raw = f.read(1024 * 64)
                result = chardet.detect(raw)
                return result.get("encoding", "utf-8") or "utf-8"
        except OSError as e:
            raise ValueError(f"Cannot read file: {e}") from e

    def parse(self, file_path: str) -> ParsedBook:
        enc = self._detect_encoding(file_path)
        try:
            with open(file_path, encoding=enc, errors="replace") as f:
                text = f.read()
        except OSError as e:
            raise ValueError(f"Cannot read file: {e}") from e

        # Split into lines, strip whitespace
        lines = [line.strip() for line in text.splitlines()]

        # Group into paragraphs (blank line = separator)
        paragraphs: list[str] = []
        current = []
        for line in lines:
            if not line:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(line)
        if current:
            paragraphs.append(" ".join(current))

        # Heuristic chapter split
        chapters: list[list[str]] = []
        current_chapter: list[str] = []
        for para in paragraphs:
            if CHAPTER_PATTERNS.match(para):
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
        parsed.title = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
        parsed.chapters = chapters
        parsed.raw_metadata = {"encoding": enc}
        return parsed
