"""Tests for chunking engine.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations


from ebook_translator.models import ChunkStatus
from ebook_translator.utils.chunker import chunk_book


class TestChunker:
    """Test paragraph-level chunking with hash and oversize protection."""

    def test_empty_book(self) -> None:
        chunks = chunk_book(1, [])
        assert chunks == []

    def test_single_paragraph(self) -> None:
        chapters = [["Hello world."]]
        chunks = chunk_book(1, chapters)
        assert len(chunks) == 1
        assert chunks[0].book_id == 1
        assert chunks[0].original_text == "Hello world."
        assert chunks[0].status == ChunkStatus.PENDING
        assert chunks[0].content_hash  # Hash is non-empty
        assert chunks[0].chapter_idx == 0
        assert chunks[0].paragraph_idx == 0

    def test_multiple_chapters(self) -> None:
        chapters = [
            ["P1.", "P2."],
            ["P3.", "P4."],
        ]
        chunks = chunk_book(1, chapters)
        assert len(chunks) == 4
        assert [c.chapter_idx for c in chunks] == [0, 0, 1, 1]
        assert [c.paragraph_idx for c in chunks] == [0, 1, 0, 1]

    def test_hash_consistency(self) -> None:
        """Same text → same hash."""
        chapters = [["Fixed text."]]
        c1 = chunk_book(1, chapters)
        c2 = chunk_book(2, chapters)
        assert c1[0].content_hash == c2[0].content_hash
        assert c1[0].book_id != c2[0].book_id  # Different book, same hash
