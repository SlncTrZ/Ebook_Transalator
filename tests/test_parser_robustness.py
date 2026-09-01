"""TXT encoding/chapter parsing and multilingual sentence split regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

import ebook_translator.utils.chunker as chunker
from ebook_translator.parsers.txt_parser import TxtParser


def test_txt_parser_handles_utf8_bom_and_numeric_chinese_chapters(tmp_path: Path) -> None:
    path = tmp_path / "novel.txt"
    path.write_bytes("第12章 开始\n第一段\n第二章 继续\n第二段".encode("utf-8-sig"))

    parsed = TxtParser().parse(str(path))

    assert parsed.raw_metadata["encoding"] == "utf-8-sig"
    assert parsed.chapters == [
        ["第12章 开始", "第一段"],
        ["第二章 继续", "第二段"],
    ]


def test_txt_parser_does_not_misread_western_single_byte_text_as_gb18030(
    tmp_path: Path,
) -> None:
    path = tmp_path / "western.txt"
    expected = "Chapter 1\nCafé déjà vu — résumé."
    path.write_bytes(expected.encode("cp1252"))

    parsed = TxtParser().parse(str(path))

    assert parsed.chapters[0][0] == "Chapter 1"
    assert parsed.chapters[0][1] == "Café déjà vu — résumé."
    assert parsed.raw_metadata["encoding"].lower() not in {"gb18030", "gbk", "gb2312"}


def test_cjk_sentence_split_does_not_require_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chunker, "MAX_TOKENS_PER_CHUNK", 5)
    monkeypatch.setattr(chunker, "_count_tokens", len)

    parts = chunker._split_oversize_paragraph("第一句。第二句！第三句？")

    assert parts == ["第一句。", "第二句！", "第三句？"]
