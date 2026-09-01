"""P2 persisted translation job and restart recovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebook_translator.db.database import Database
from ebook_translator.models import Book


@pytest.mark.asyncio
async def test_translation_job_lifecycle_and_diagnostics(tmp_path: Path) -> None:
    database = Database(tmp_path / "jobs.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="book.txt", title="Jobs"))

    job_id = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 1, 4
    )
    latest = await database.get_latest_job(book_id)
    assert latest is not None
    assert latest["id"] == job_id
    assert latest["status"] == "running"

    diagnostics = await database.get_diagnostics()
    assert diagnostics["jobs"] == 1
    assert diagnostics["running_jobs"] == 1

    await database.finish_translation_job(job_id, "done")
    latest = await database.get_latest_job(book_id)
    assert latest is not None
    assert latest["status"] == "done"
    assert latest["finished_at"] is not None
    await database.close()


@pytest.mark.asyncio
async def test_running_job_is_marked_interrupted_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "recovery.db"
    first = Database(db_path)
    await first.connect()
    book_id = await first.insert_book(Book(file_path="book.txt", title="Recovery"))
    await first.create_translation_job(book_id, "agentic", "google", "gemini", 0, 99999)
    await first.close()

    restarted = Database(db_path)
    await restarted.connect()
    latest = await restarted.get_latest_job(book_id)
    assert latest is not None
    assert latest["status"] == "interrupted"
    assert "Process restarted" in latest["error_summary"]

    diagnostics = await restarted.get_diagnostics()
    assert diagnostics["running_jobs"] == 0
    assert diagnostics["interrupted_jobs"] == 1
    await restarted.close()
