"""Regression tests for oversized paragraph segmentation and ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

import ebook_translator.utils.chunker as chunker
from ebook_translator.db.database import Database
from ebook_translator.models import Book


def test_oversize_paragraph_segments_do_not_collide_with_next_paragraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chunker,
        "_count_tokens",
        lambda text: 5001 if text == "Oversize paragraph" else 1,
    )
    monkeypatch.setattr(
        chunker,
        "_split_oversize_paragraph",
        lambda text: ["Segment one", "Segment two"],
    )

    chunks = chunker.chunk_book(7, [["Oversize paragraph", "Next paragraph"]])

    assert [(c.paragraph_idx, c.segment_idx, c.original_text) for c in chunks] == [
        (0, 0, "Segment one"),
        (0, 1, "Segment two"),
        (1, 0, "Next paragraph"),
    ]


@pytest.mark.asyncio
async def test_segment_idx_migrates_and_controls_chunk_order(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy-segments.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            title TEXT DEFAULT '',
            author TEXT DEFAULT '',
            localized_title TEXT DEFAULT '',
            source_lang TEXT DEFAULT 'en',
            target_lang TEXT DEFAULT 'vi',
            category TEXT DEFAULT 'general',
            status TEXT DEFAULT 'pending',
            total_chunks INTEGER DEFAULT 0,
            done_chunks INTEGER DEFAULT 0,
            failed_chunks INTEGER DEFAULT 0
        );
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            chapter_idx INTEGER NOT NULL,
            paragraph_idx INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            original_text TEXT NOT NULL,
            translated_text TEXT,
            status TEXT DEFAULT 'pending',
            token_count INTEGER DEFAULT 0,
            error_log TEXT
        );
        """
    )
    connection.commit()
    connection.close()

    database = Database(db_path)
    await database.connect()
    cursor = await database.conn.execute("PRAGMA table_info(chunks)")
    columns = {row["name"] for row in await cursor.fetchall()}
    assert "segment_idx" in columns

    book_id = await database.insert_book(Book(file_path="book.txt", title="Segments"))
    await database.conn.executemany(
        "INSERT INTO chunks (book_id, chapter_idx, paragraph_idx, segment_idx, content_hash, original_text) "
        "VALUES (?, 0, 0, ?, ?, ?)",
        [
            (book_id, 1, "b", "second"),
            (book_id, 0, "a", "first"),
        ],
    )
    await database.conn.commit()

    pending = await database.get_pending_chunks(book_id)
    assert [(c.paragraph_idx, c.segment_idx, c.original_text) for c in pending] == [
        (0, 0, "first"),
        (0, 1, "second"),
    ]
    await database.close()
