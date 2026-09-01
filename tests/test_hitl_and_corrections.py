"""P1/P2 tests for HITL persistence and manual correction workflows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio

from ebook_translator.agent.pipeline import AgentContext
from ebook_translator.db.database import Database
from ebook_translator.models import Book, Chunk
import ebook_translator.server as server


@pytest_asyncio.fixture
async def correction_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = Database(tmp_path / "corrections.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="book.txt", title="Source"))
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="manual-1",
                original_text="Original",
            )
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ?", (book_id,)
    )
    chunk_id = (await cursor.fetchone())["id"]
    monkeypatch.setattr(server, "db", database)
    yield database, book_id, chunk_id
    await database.close()


@pytest.mark.asyncio
async def test_manual_correction_is_done_and_requeue_is_retryable(correction_db) -> None:
    database, book_id, chunk_id = correction_db

    result = await server.update_chunk_translation(
        chunk_id, server.UpdateChunkRequest(translated_text="User approved")
    )
    assert result["ok"] is True
    cursor = await database.conn.execute(
        "SELECT translated_text, status FROM chunks WHERE id = ?", (chunk_id,)
    )
    row = await cursor.fetchone()
    assert row["translated_text"] == "User approved"
    assert row["status"] == "done"
    assert await database.get_pending_chunks(book_id) == []

    await server.requeue_chunk(chunk_id)
    retryable = await database.get_pending_chunks(book_id)
    assert [chunk.id for chunk in retryable] == [chunk_id]


@pytest.mark.asyncio
async def test_confirm_metadata_persists_localized_title(correction_db) -> None:
    database, book_id, _ = correction_db

    await server.confirm_metadata(
        book_id,
        server.ConfirmMetadataRequest(
            title="Original Title",
            localized_title="Tiêu đề bản địa hóa",
            author="Author",
            source_lang="en",
            target_lang="vi",
            category="van_hoc",
        ),
    )

    book = await database.get_book(book_id)
    assert book is not None
    assert book.localized_title == "Tiêu đề bản địa hóa"
    assert book.category == "van_hoc"


@pytest.mark.asyncio
async def test_research_endpoint_forwards_feedback_and_force_search(
    correction_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book_id, _ = correction_db
    captured: dict[str, object] = {}

    async def fake_preview(_: str) -> str:
        return "preview"

    async def fake_research(
        preview: str,
        ctx: AgentContext,
        user_feedback: str = "",
        force_search: bool = False,
    ) -> AgentContext:
        captured.update(
            preview=preview,
            vendor=ctx.vendor,
            feedback=user_feedback,
            force_search=force_search,
        )
        ctx.title = "Resolved"
        ctx.localized_title = "Đã xác minh"
        return ctx

    import ebook_translator.agent.pipeline as agent_pipeline

    monkeypatch.setattr(server, "get_preview_text", fake_preview)
    monkeypatch.setattr(agent_pipeline, "research_agent", fake_research)

    result = await server.research_book(
        book_id,
        server.AnalyzeRequest(
            vendor="openai",
            api_key="test-key",
            model="test-model",
            user_feedback="Known edition from 2012",
            force_search=True,
        ),
    )

    assert captured == {
        "preview": "preview",
        "vendor": "openai",
        "feedback": "Known edition from 2012",
        "force_search": True,
    }
    assert result["localized_title"] == "Đã xác minh"


def test_connect_migrates_legacy_books_table_with_localized_title(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE books ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, title TEXT DEFAULT '', "
        "author TEXT DEFAULT '', source_lang TEXT DEFAULT 'en', target_lang TEXT DEFAULT 'vi', "
        "category TEXT DEFAULT 'general', status TEXT DEFAULT 'pending', total_chunks INTEGER DEFAULT 0, "
        "done_chunks INTEGER DEFAULT 0, failed_chunks INTEGER DEFAULT 0)"
    )
    connection.commit()
    connection.close()

    async def verify() -> None:
        database = Database(db_path)
        await database.connect()
        cursor = await database.conn.execute("PRAGMA table_info(books)")
        columns = {row["name"] for row in await cursor.fetchall()}
        assert "localized_title" in columns
        await database.close()

    import asyncio

    asyncio.run(verify())
