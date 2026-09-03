"""P0.1 routing tests for Standard vs Agentic translation starts.

These tests intentionally mock background scheduling and never call external AI providers.
"""

from __future__ import annotations

from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from ebook_translator.db.database import Database
from ebook_translator.models import Book, Chunk
import ebook_translator.server as server


class DummyPipeline:
    """Minimal TranslationPipeline replacement for routing-only tests."""

    def __init__(self, db: Database, config: Any) -> None:
        self.db = db
        self.config = config

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def routing_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = Database(tmp_path / "routing.db")
    await database.connect()

    book = Book(file_path=str(tmp_path / "book.txt"), title="Routing Test")
    book_id = await database.insert_book(book)
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="hash-chapter-1",
                original_text="Chapter one.",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=1,
                paragraph_idx=0,
                content_hash="hash-chapter-2",
                original_text="Chapter two.",
            ),
        ]
    )

    monkeypatch.setattr(server, "db", database)
    monkeypatch.setattr(server, "active_pipeline", None)
    monkeypatch.setattr(server, "active_book_id", None)
    server._cancel_event.clear()
    monkeypatch.setattr(server, "TranslationPipeline", DummyPipeline)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)

    yield database, book_id, book.file_path

    server.active_pipeline = None
    server.active_book_id = None
    server._cancel_event.clear()
    await database.close()


def _capture_tasks(monkeypatch: pytest.MonkeyPatch) -> list[Coroutine[Any, Any, Any]]:
    scheduled: list[Coroutine[Any, Any, Any]] = []

    def capture(coro: Coroutine[Any, Any, Any]) -> object:
        scheduled.append(coro)
        return object()

    monkeypatch.setattr(server.asyncio, "create_task", capture)
    return scheduled


def _assert_scheduled(
    scheduled: list[Coroutine[Any, Any, Any]],
    expected_name: str,
    chapter_start: int,
    chapter_end: int,
) -> None:
    assert len(scheduled) == 1
    coro = scheduled[0]
    try:
        assert coro.cr_code.co_name == expected_name
        assert coro.cr_frame is not None
        assert coro.cr_frame.f_locals["chapter_start"] == chapter_start
        assert coro.cr_frame.f_locals["chapter_end"] == chapter_end
    finally:
        coro.close()


@pytest.mark.asyncio
async def test_standard_full_book_starts_background_task(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book_id, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    response = await server.start_translate(
        server.StartTranslateRequest(file_path=file_path, model="provider-model")
    )

    assert response == {"book_id": book_id, "job_id": 1, "status": "started", "mode": "standard"}
    _assert_scheduled(scheduled, "_run_translation", 0, 99999)


@pytest.mark.asyncio
async def test_standard_range_starts_background_task(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book_id, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    response = await server.start_translate(
        server.StartTranslateRequest(
            file_path=file_path,
            model="provider-model",
            chapter_start=1,
            chapter_end=1,
        )
    )

    assert response == {"book_id": book_id, "job_id": 1, "status": "started", "mode": "standard"}
    _assert_scheduled(scheduled, "_run_translation", 1, 1)


@pytest.mark.asyncio
async def test_agentic_full_book_starts_agentic_task(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book_id, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    response = await server.translate_agentic(
        server.StartTranslateRequest(file_path=file_path, model="provider-model")
    )

    assert response == {"book_id": book_id, "job_id": 1, "status": "started", "mode": "agentic"}
    _assert_scheduled(scheduled, "_run_agentic_translate", 0, 99999)


@pytest.mark.asyncio
async def test_agentic_range_starts_agentic_task(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, book_id, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    response = await server.translate_agentic(
        server.StartTranslateRequest(
            file_path=file_path,
            model="provider-model",
            chapter_start=1,
            chapter_end=1,
        )
    )

    assert response == {"book_id": book_id, "job_id": 1, "status": "started", "mode": "agentic"}
    _assert_scheduled(scheduled, "_run_agentic_translate", 1, 1)


@pytest.mark.asyncio
async def test_standard_endpoint_rejects_legacy_agentic_flag(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    with pytest.raises(server.HTTPException) as exc_info:
        await server.start_translate(
            server.StartTranslateRequest(file_path=file_path, agentic=True)
        )

    assert exc_info.value.status_code == 400
    assert scheduled == []


@pytest.mark.asyncio
async def test_translation_start_requires_explicit_provider_model(
    routing_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, file_path = routing_db
    scheduled = _capture_tasks(monkeypatch)

    with pytest.raises(server.HTTPException) as exc_info:
        await server.start_translate(server.StartTranslateRequest(file_path=file_path))

    assert exc_info.value.status_code == 400
    assert "Select a model fetched from the provider" in exc_info.value.detail
    assert scheduled == []
