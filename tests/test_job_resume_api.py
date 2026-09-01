"""Integration tests for persisted job resume wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

import ebook_translator.server as server
from ebook_translator.db.database import Database
from ebook_translator.models import Book, Chunk


async def _seed_interrupted_job(
    database: Database,
    *,
    vendor: str = "ollama",
    mode: str = "standard",
    chapter_start: int = 1,
    chapter_end: int = 2,
) -> tuple[int, int, list[int]]:
    book_id = await database.insert_book(
        Book(file_path="resume.txt", title="Resume API", source_lang="en", target_lang="vi")
    )
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="api-1",
                original_text="One",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=1,
                paragraph_idx=0,
                content_hash="api-2",
                original_text="Two",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=2,
                paragraph_idx=0,
                content_hash="api-3",
                original_text="Three",
            ),
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? ORDER BY chapter_idx", (book_id,)
    )
    chunk_ids = [row["id"] for row in await cursor.fetchall()]
    job_id = await database.create_translation_job(
        book_id, mode, vendor, "test-model", chapter_start, chapter_end
    )
    await database.transition_translation_job(job_id, "interrupted", "simulated restart")
    return book_id, job_id, chunk_ids


@pytest.fixture(autouse=True)
def reset_server_globals() -> None:
    server.active_pipeline = None
    server.active_book_id = None
    server.active_job_id = None
    server._cancel_event.clear()
    yield
    server.active_pipeline = None
    server.active_book_id = None
    server.active_job_id = None
    server._cancel_event.clear()


@pytest.mark.asyncio
async def test_resume_plan_endpoint_returns_only_retryable_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "resume-plan-api.db")
    await database.connect()
    book_id, job_id, chunk_ids = await _seed_interrupted_job(database)
    await database.update_chunk_result(chunk_ids[0], "Done", "done")
    monkeypatch.setattr(server, "db", database)

    result = await server.job_resume_plan(job_id)

    assert result["job"]["id"] == job_id
    assert result["progress"]["total"] == 2
    assert result["remaining_chunk_ids"] == [chunk_ids[1]]
    await database.close()


@pytest.mark.asyncio
async def test_resume_standard_job_schedules_same_persisted_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "resume-standard-api.db")
    await database.connect()
    book_id, job_id, chunk_ids = await _seed_interrupted_job(database)
    await database.update_chunk_result(chunk_ids[0], "Done", "done")
    monkeypatch.setattr(server, "db", database)

    scheduled: list[object] = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(server.asyncio, "create_task", fake_create_task)

    response = await server.resume_translation_job(job_id, server.ResumeJobRequest())

    assert response == {
        "job_id": job_id,
        "book_id": book_id,
        "status": "running",
        "mode": "standard",
        "remaining": 1,
    }
    assert len(scheduled) == 1
    job = await database.get_translation_job(job_id)
    assert job is not None
    assert job["status"] == "running"
    assert job["resume_count"] == 1
    assert server.active_job_id == job_id
    assert server.active_book_id == book_id
    assert server.active_pipeline is not None
    await database.close()


@pytest.mark.asyncio
async def test_resume_agentic_job_schedules_same_persisted_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "resume-agentic-api.db")
    await database.connect()
    book_id, job_id, _ = await _seed_interrupted_job(database, mode="agentic")
    monkeypatch.setattr(server, "db", database)

    scheduled: list[object] = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(server.asyncio, "create_task", fake_create_task)

    response = await server.resume_translation_job(job_id, server.ResumeJobRequest())

    assert response["job_id"] == job_id
    assert response["book_id"] == book_id
    assert response["mode"] == "agentic"
    assert response["status"] == "running"
    assert len(scheduled) == 1
    assert server.active_job_id == job_id
    assert server.active_book_id == book_id
    job = await database.get_translation_job(job_id)
    assert job is not None
    assert job["status"] == "running"
    assert job["resume_count"] == 1
    await database.close()


@pytest.mark.asyncio
async def test_resume_cloud_job_requires_credential_without_persisting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "resume-key-api.db")
    await database.connect()
    _, job_id, _ = await _seed_interrupted_job(database, vendor="openai")
    monkeypatch.setattr(server, "db", database)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(server.HTTPException) as exc_info:
        await server.resume_translation_job(job_id, server.ResumeJobRequest())

    assert exc_info.value.status_code == 400
    assert "credentials are not persisted" in exc_info.value.detail
    job = await database.get_translation_job(job_id)
    assert job is not None
    assert job["status"] == "interrupted"
    await database.close()


class FakePipeline:
    def __init__(self) -> None:
        self.closed = False

    async def translate_chunk(self, chunk, glossary) -> str:
        return f"translated:{chunk.original_text}"

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_standard_worker_records_chunk_attempt_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "attempt-worker.db")
    await database.connect()
    book_id, job_id, chunk_ids = await _seed_interrupted_job(
        database, chapter_start=1, chapter_end=1
    )
    await database.resume_translation_job(job_id)
    monkeypatch.setattr(server, "db", database)
    pipeline = FakePipeline()
    server.active_pipeline = pipeline
    server.active_book_id = book_id
    server.active_job_id = job_id

    await server._run_translation(book_id, job_id, 1, 1)

    summary = await database.get_job_attempt_summary(job_id)
    assert summary == {
        "attempts": 1,
        "done_attempts": 1,
        "failed_attempts": 0,
    }
    cursor = await database.conn.execute(
        "SELECT status, translated_text FROM chunks WHERE id = ?", (chunk_ids[0],)
    )
    row = await cursor.fetchone()
    assert row["status"] == "done"
    assert row["translated_text"] == "translated:One"
    job = await database.get_translation_job(job_id)
    assert job is not None
    assert job["status"] == "done"
    assert pipeline.closed is True
    await database.close()
