"""P0.3 tests for canonical chunk progress and range isolation."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from ebook_translator.db.database import Database
from ebook_translator.models import Book, Chunk
import ebook_translator.server as server


@pytest_asyncio.fixture
async def progress_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = Database(tmp_path / "progress.db")
    await database.connect()

    book = Book(file_path=str(tmp_path / "book.txt"), title="Progress Test")
    book_id = await database.insert_book(book)
    chunks = [
        Chunk(
            book_id=book_id,
            chapter_idx=0,
            paragraph_idx=0,
            content_hash="h1",
            original_text="A",
        ),
        Chunk(
            book_id=book_id,
            chapter_idx=0,
            paragraph_idx=1,
            content_hash="h2",
            original_text="B",
        ),
        Chunk(
            book_id=book_id,
            chapter_idx=1,
            paragraph_idx=0,
            content_hash="h3",
            original_text="C",
        ),
    ]
    await database.insert_chunks(chunks)

    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? ORDER BY chapter_idx, paragraph_idx",
        (book_id,),
    )
    ids = [row["id"] for row in await cursor.fetchall()]

    monkeypatch.setattr(server, "db", database)
    yield database, book_id, ids
    await database.close()


@pytest.mark.asyncio
async def test_all_pending_is_pending(progress_db) -> None:
    database, book_id, _ = progress_db
    progress = await database.get_chunk_progress(book_id)

    assert progress == {
        "total": 3,
        "done": 0,
        "failed": 0,
        "pending": 3,
        "status": "pending",
    }


@pytest.mark.asyncio
async def test_progress_is_derived_from_chunks_not_book_counters(progress_db) -> None:
    database, book_id, ids = progress_db
    await database.conn.execute(
        "UPDATE books SET total_chunks = 99, done_chunks = 88, failed_chunks = 77 WHERE id = ?",
        (book_id,),
    )
    await database.conn.commit()

    await database.update_chunk_result(ids[0], "Translated A", "done")
    await database.mark_chunk_failed(ids[1], "provider error")

    progress = await database.get_chunk_progress(book_id)
    assert progress["total"] == 3
    assert progress["done"] == 1
    assert progress["failed"] == 1
    assert progress["pending"] == 1
    assert progress["status"] == "translating"


@pytest.mark.asyncio
async def test_update_book_status_refreshes_legacy_snapshots(progress_db) -> None:
    database, book_id, ids = progress_db
    await database.update_chunk_result(ids[0], "A", "done")
    await database.update_chunk_result(ids[1], "B", "done")
    await database.mark_chunk_failed(ids[2], "bad")

    await database.update_book_status(book_id)
    cursor = await database.conn.execute(
        "SELECT total_chunks, done_chunks, failed_chunks, status FROM books WHERE id = ?",
        (book_id,),
    )
    row = await cursor.fetchone()

    assert dict(row) == {
        "total_chunks": 3,
        "done_chunks": 2,
        "failed_chunks": 1,
        "status": "failed",
    }


@pytest.mark.asyncio
async def test_range_progress_is_exact_not_ratio(progress_db) -> None:
    database, book_id, ids = progress_db
    await database.update_chunk_result(ids[0], "A", "done")
    await database.update_chunk_result(ids[1], "B", "done")

    chapter_one = await database.get_chunk_progress(book_id, 1, 1)
    chapter_two = await database.get_chunk_progress(book_id, 2, 2)

    assert chapter_one == {
        "total": 2,
        "done": 2,
        "failed": 0,
        "pending": 0,
        "status": "done",
    }
    assert chapter_two == {
        "total": 1,
        "done": 0,
        "failed": 0,
        "pending": 1,
        "status": "pending",
    }


@pytest.mark.asyncio
async def test_status_endpoint_uses_requested_scope(progress_db) -> None:
    database, book_id, ids = progress_db
    await database.update_chunk_result(ids[0], "A", "done")
    await database.update_chunk_result(ids[1], "B", "done")

    result = await server.translate_status(book_id, chapter_start=1, chapter_end=1)

    assert result == {
        "total": 2,
        "done": 2,
        "failed": 0,
        "status": "done",
    }
