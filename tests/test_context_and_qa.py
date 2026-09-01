"""Long-form context and deterministic QA tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import ebook_translator.server as server
from ebook_translator.db.database import Database
from ebook_translator.models import Book, Chunk, GlossaryEntry
from ebook_translator.translator.context import ContextBuilder
from ebook_translator.translator.qa import check_translation


@pytest.mark.asyncio
async def test_context_builder_uses_same_chapter_neighbors_and_done_translation(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="book.txt", title="Context"))
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="c0",
                original_text="Previous source",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=1,
                content_hash="c1",
                original_text="Current source",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=2,
                content_hash="c2",
                original_text="Next source",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=1,
                paragraph_idx=0,
                content_hash="other",
                original_text="Other chapter",
            ),
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? AND chapter_idx = 0 ORDER BY paragraph_idx",
        (book_id,),
    )
    ids = [row["id"] for row in await cursor.fetchall()]
    await database.update_chunk_result(ids[0], "Previous translation", "done")

    current = Chunk(
        id=ids[1],
        book_id=book_id,
        chapter_idx=0,
        paragraph_idx=1,
        content_hash="c1",
        original_text="Current source",
    )
    context = await ContextBuilder(database).build_for_chunk(current)

    assert context.previous_source == "Previous source"
    assert context.previous_translation == "Previous translation"
    assert context.next_source == "Next source"
    rendered = context.render()
    assert "Other chapter" not in rendered
    assert "Previous translation" in rendered
    await database.close()


@pytest.mark.asyncio
async def test_context_builder_budget_is_deterministic(tmp_path: Path) -> None:
    database = Database(tmp_path / "budget.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="book.txt", title="Budget"))
    long_text = "x" * 1000
    await database.insert_chunks(
        [
            Chunk(book_id=book_id, chapter_idx=0, paragraph_idx=0, content_hash="a", original_text=long_text),
            Chunk(book_id=book_id, chapter_idx=0, paragraph_idx=1, content_hash="b", original_text="current"),
            Chunk(book_id=book_id, chapter_idx=0, paragraph_idx=2, content_hash="c", original_text=long_text),
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? ORDER BY paragraph_idx", (book_id,)
    )
    ids = [row["id"] for row in await cursor.fetchall()]
    await database.update_chunk_result(ids[0], "y" * 1000, "done")
    current = Chunk(
        id=ids[1],
        book_id=book_id,
        chapter_idx=0,
        paragraph_idx=1,
        content_hash="b",
        original_text="current",
    )

    builder = ContextBuilder(database, max_chars=300)
    first = await builder.build_for_chunk(current)
    second = await builder.build_for_chunk(current)

    assert first == second
    assert len(first.previous_source) + len(first.previous_translation) + len(first.next_source) <= 300
    await database.close()


def test_qa_detects_glossary_and_number_mismatch() -> None:
    glossary = [GlossaryEntry(source_term="reactor", target_term="lò phản ứng")]
    result = check_translation(
        "The reactor has 12 modules.",
        "Thiết bị có 10 mô-đun.",
        glossary,
    )

    codes = {issue.code for issue in result.issues}
    assert "number_mismatch" in codes
    assert "glossary_violation" in codes
    assert result.passed is False


def test_qa_detects_empty_translation() -> None:
    result = check_translation("Source", "")

    assert result.passed is False
    assert [issue.code for issue in result.issues] == ["missing_translation"]


def test_qa_marks_identical_source_as_warning_not_hard_failure() -> None:
    result = check_translation("Hello world", "Hello world")

    assert any(issue.code == "source_residue" for issue in result.issues)
    assert result.passed is True


def test_qa_accepts_exact_lowercase_glossary_target() -> None:
    glossary = [GlossaryEntry(source_term="Core", target_term="lõi năng lượng")]
    result = check_translation("Core online.", "lõi năng lượng đã hoạt động.", glossary)

    assert not any(issue.code == "glossary_violation" for issue in result.issues)


@pytest.mark.asyncio
async def test_book_qa_endpoint_returns_structured_chunk_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "qa-api.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="qa.txt", title="QA"))
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="qa-1",
                original_text="The reactor has 12 modules.",
            )
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ?", (book_id,)
    )
    chunk_id = (await cursor.fetchone())["id"]
    await database.update_chunk_result(chunk_id, "Thiết bị có 10 mô-đun.", "done")
    await database.conn.execute(
        "INSERT INTO glossary (book_id, source_term, target_term) VALUES (?, ?, ?)",
        (book_id, "reactor", "lò phản ứng"),
    )
    await database.conn.commit()
    monkeypatch.setattr(server, "db", database)

    result = await server.book_qa(book_id)

    assert result["checked_chunks"] == 1
    assert result["issue_chunks"] == 1
    assert result["errors"] == 1
    assert result["warnings"] == 1
    codes = {issue["code"] for issue in result["chunks"][0]["issues"]}
    assert codes == {"number_mismatch", "glossary_violation"}
    await database.close()
