"""Tests for file parsers — EPUB and TXT.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ebook_translator.parsers.base import BaseParser
from ebook_translator.parsers.txt_parser import TxtParser


class TestTxtParser:
    """Test TXT parser with encoding detection and chapter splitting."""

    @pytest.fixture
    def parser(self) -> TxtParser:
        return TxtParser()

    def test_is_parser(self, parser: TxtParser) -> None:
        assert isinstance(parser, BaseParser)

    def test_empty_file(self, parser: TxtParser, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = parser.parse(str(f))
        assert result.chapters == []

    def test_simple_paragraphs(self, parser: TxtParser, tmp_path: Path) -> None:
        f = tmp_path / "simple.txt"
        f.write_text("Para one.\n\nPara two.\n\nPara three.", encoding="utf-8")
        result = parser.parse(str(f))
        assert len(result.chapters) == 1  # No chapter header → single chapter
        assert len(result.chapters[0]) == 3

    def test_chapter_splitting_vietnamese(self, parser: TxtParser, tmp_path: Path) -> None:
        f = tmp_path / "chapters.txt"
        f.write_text("Chương 1\n\nFirst paragraph.\n\nSecond paragraph.\n\nChương 2\n\nThird paragraph.", encoding="utf-8")
        result = parser.parse(str(f))
        assert len(result.chapters) == 2
        assert "First paragraph." in result.chapters[0]
        assert "Third paragraph." in result.chapters[1]

    def test_chapter_splitting_english(self, parser: TxtParser, tmp_path: Path) -> None:
        f = tmp_path / "english.txt"
        f.write_text("Chapter 1\n\nFirst.\n\nChapter II\n\nSecond.", encoding="utf-8")
        result = parser.parse(str(f))
        assert len(result.chapters) == 2

    def test_title_from_filename(self, parser: TxtParser, tmp_path: Path) -> None:
        f = tmp_path / "My_Great_Book.txt"
        f.write_text("Some content.", encoding="utf-8")
        result = parser.parse(str(f))
        assert result.title == "My_Great_Book"

    def test_utf8_by_default(self, parser: TxtParser, tmp_path: Path) -> None:
        """UTF-8 text should be handled correctly."""
        f = tmp_path / "utf8.txt"
        f.write_text("Tiếng Việt có dấu: Ứng dụng dịch thuật.", encoding="utf-8")
        result = parser.parse(str(f))
        assert "Ứng dụng dịch thuật" in result.chapters[0][0]

    def test_file_not_found(self, parser: TxtParser) -> None:
        with pytest.raises(ValueError, match="Cannot read file"):
            parser.parse("/nonexistent/path/file.txt")
