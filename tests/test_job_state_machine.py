"""Formal translation-job lifecycle and resume-plan tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebook_translator.db.database import Database
from ebook_translator.jobs.state import IllegalJobTransition, JobStatus, assert_job_transition
from ebook_translator.models import Book, Chunk


def test_job_state_machine_accepts_expected_transitions() -> None:
    legal = [
        (JobStatus.PENDING, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.PAUSED),
        (JobStatus.PAUSED, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.DONE),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.CANCELLED),
        (JobStatus.RUNNING, JobStatus.INTERRUPTED),
        (JobStatus.INTERRUPTED, JobStatus.RUNNING),
        (JobStatus.FAILED, JobStatus.RUNNING),
    ]

    for current, target in legal:
        assert_job_transition(current, target)


def test_job_state_machine_rejects_terminal_or_invalid_transitions() -> None:
    for current, target in [
        (JobStatus.DONE, JobStatus.RUNNING),
        (JobStatus.CANCELLED, JobStatus.RUNNING),
        (JobStatus.PENDING, JobStatus.DONE),
    ]:
        with pytest.raises(IllegalJobTransition):
            assert_job_transition(current, target)


async def _build_book(database: Database) -> tuple[int, list[int]]:
    book_id = await database.insert_book(Book(file_path="book.txt", title="Resume"))
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="resume-1",
                original_text="Chapter one",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=1,
                paragraph_idx=0,
                content_hash="resume-2",
                original_text="Chapter two",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=2,
                paragraph_idx=0,
                content_hash="resume-3",
                original_text="Chapter three",
            ),
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? ORDER BY chapter_idx", (book_id,)
    )
    return book_id, [row["id"] for row in await cursor.fetchall()]


@pytest.mark.asyncio
async def test_interrupted_range_job_resume_plan_excludes_done_and_out_of_scope(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "resume-range.db"
    first = Database(db_path)
    await first.connect()
    book_id, chunk_ids = await _build_book(first)
    job_id = await first.create_translation_job(
        book_id, "standard", "openai", "model-a", 2, 3
    )
    await first.update_chunk_result(chunk_ids[1], "Done chapter two", "done")
    await first.mark_chunk_failed(chunk_ids[2], "temporary")
    await first.close()

    restarted = Database(db_path)
    await restarted.connect()
    job = await restarted.get_translation_job(job_id)
    assert job is not None
    assert job["status"] == "interrupted"

    plan = await restarted.get_job_resume_plan(job_id)
    assert [chunk.id for chunk in plan["remaining_chunks"]] == [chunk_ids[2]]
    assert plan["progress"]["total"] == 2
    assert plan["progress"]["done"] == 1
    assert plan["progress"]["failed"] == 1

    resumed = await restarted.resume_translation_job(job_id)
    assert resumed["job"]["status"] == "running"
    assert resumed["job"]["resume_count"] == 1
    assert resumed["job"]["finished_at"] is None
    await restarted.close()


@pytest.mark.asyncio
async def test_done_and_cancelled_jobs_are_not_resumable(tmp_path: Path) -> None:
    database = Database(tmp_path / "terminal.db")
    await database.connect()
    book_id, _ = await _build_book(database)

    done_job = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 0, 99999
    )
    await database.finish_translation_job(done_job, "done")
    with pytest.raises(IllegalJobTransition):
        await database.get_job_resume_plan(done_job)

    cancelled_job = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 0, 99999
    )
    await database.finish_translation_job(cancelled_job, "cancelled")
    with pytest.raises(IllegalJobTransition):
        await database.get_job_resume_plan(cancelled_job)
    await database.close()


@pytest.mark.asyncio
async def test_job_transition_is_idempotent_for_same_status(tmp_path: Path) -> None:
    database = Database(tmp_path / "idempotent.db")
    await database.connect()
    book_id, _ = await _build_book(database)
    job_id = await database.create_translation_job(
        book_id, "agentic", "google", "gemini", 0, 99999
    )

    first = await database.transition_translation_job(job_id, JobStatus.RUNNING)
    second = await database.transition_translation_job(job_id, JobStatus.RUNNING)
    assert first["status"] == "running"
    assert second["status"] == "running"
    assert second["resume_count"] == 0
    await database.close()


@pytest.mark.asyncio
async def test_attempt_history_is_per_job_and_chunk(tmp_path: Path) -> None:
    database = Database(tmp_path / "attempts.db")
    await database.connect()
    book_id, chunk_ids = await _build_book(database)
    job_id = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 1, 1
    )

    first = await database.start_job_chunk_attempt(job_id, chunk_ids[0])
    await database.finish_job_chunk_attempt(first, "failed", "rate limit")
    second = await database.start_job_chunk_attempt(job_id, chunk_ids[0])
    await database.finish_job_chunk_attempt(second, "done")

    summary = await database.get_job_attempt_summary(job_id)
    assert summary == {
        "attempts": 2,
        "done_attempts": 1,
        "failed_attempts": 1,
    }

    cursor = await database.conn.execute(
        "SELECT attempt_no, status, error_summary FROM translation_job_attempts "
        "WHERE job_id = ? ORDER BY attempt_no",
        (job_id,),
    )
    rows = await cursor.fetchall()
    assert [(row["attempt_no"], row["status"]) for row in rows] == [
        (1, "failed"),
        (2, "done"),
    ]
    assert rows[0]["error_summary"] == "rate limit"

    diagnostics = await database.get_job_diagnostics(job_id)
    assert diagnostics == {
        "job_id": job_id,
        "status": "running",
        "resume_count": 0,
        "total": 1,
        "done": 0,
        "failed": 0,
        "pending": 1,
        "attempts": 2,
        "done_attempts": 1,
        "failed_attempts": 1,
    }
    await database.close()


@pytest.mark.asyncio
async def test_restart_reconciles_running_chunk_attempt(tmp_path: Path) -> None:
    db_path = tmp_path / "attempt-restart.db"
    first = Database(db_path)
    await first.connect()
    book_id, chunk_ids = await _build_book(first)
    job_id = await first.create_translation_job(
        book_id, "standard", "openai", "model-a", 1, 1
    )
    attempt_id = await first.start_job_chunk_attempt(job_id, chunk_ids[0])
    await first.close()

    restarted = Database(db_path)
    await restarted.connect()
    cursor = await restarted.conn.execute(
        "SELECT status, error_summary, finished_at FROM translation_job_attempts WHERE id = ?",
        (attempt_id,),
    )
    row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert "Process restarted" in row["error_summary"]
    assert row["finished_at"] is not None
    await restarted.close()


@pytest.mark.asyncio
async def test_latest_resumable_job_filters_terminal_jobs(tmp_path: Path) -> None:
    database = Database(tmp_path / "resumable-list.db")
    await database.connect()
    book_id, _ = await _build_book(database)

    done_job = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 0, 99999
    )
    await database.finish_translation_job(done_job, "done")
    failed_job = await database.create_translation_job(
        book_id, "standard", "openai", "model-a", 0, 99999
    )
    await database.finish_translation_job(failed_job, "failed", "temporary")

    resumable = await database.list_resumable_jobs(book_id)
    assert [job["id"] for job in resumable] == [failed_job]
    latest = await database.get_latest_resumable_job(book_id)
    assert latest is not None
    assert latest["id"] == failed_job
    await database.close()


@pytest.mark.asyncio
async def test_legacy_job_table_migrates_resume_count(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy-jobs.db"
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
        CREATE TABLE translation_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            vendor TEXT DEFAULT '',
            model TEXT DEFAULT '',
            chapter_start INTEGER DEFAULT 0,
            chapter_end INTEGER DEFAULT 99999,
            status TEXT DEFAULT 'pending',
            error_summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            started_at TEXT,
            finished_at TEXT
        );
        """
    )
    connection.commit()
    connection.close()

    database = Database(db_path)
    await database.connect()
    cursor = await database.conn.execute("PRAGMA table_info(translation_jobs)")
    columns = {row["name"] for row in await cursor.fetchall()}
    assert "resume_count" in columns
    await database.close()
