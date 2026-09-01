"""P0.4 lifecycle tests: translate, cache, retry, range, export."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from ebook_translator.db.database import Database
from ebook_translator.export.export_engine import export_book
from ebook_translator.models import Book, Chunk
from ebook_translator.translator.pipeline import TranslationConfig, TranslationPipeline


class FakeGateway:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def generate(self, messages: list[dict], **_: object) -> str:
        self.calls += 1
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return str(value)


@pytest_asyncio.fixture
async def lifecycle_db(tmp_path: Path):
    database = Database(tmp_path / "lifecycle.db")
    await database.connect()
    book = Book(
        file_path=str(tmp_path / "book.txt"),
        title="Lifecycle Book",
        author="Test Author",
    )
    book_id = await database.insert_book(book)
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="life-1",
                original_text="Alpha",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=1,
                paragraph_idx=0,
                content_hash="life-2",
                original_text="Beta",
            ),
        ]
    )
    yield database, book_id, tmp_path
    await database.close()


@pytest.mark.asyncio
async def test_translate_cache_and_export_txt(lifecycle_db) -> None:
    database, book_id, tmp_path = lifecycle_db
    pipeline = TranslationPipeline(
        database,
        TranslationConfig(model="fake-model", max_retries=1),
    )
    gateway = FakeGateway(["Bản dịch Alpha", "Bản dịch Beta"])
    pipeline._gateway = gateway

    await pipeline.run_book(book_id)

    assert gateway.calls == 2
    progress = await database.get_chunk_progress(book_id)
    assert progress["status"] == "done"
    assert progress["done"] == 2

    # A second run must not call the provider because there are no retryable chunks.
    await pipeline.run_book(book_id)
    assert gateway.calls == 2

    output = tmp_path / "translated.txt"
    result = await export_book(database, book_id, str(output), format="txt")
    assert result == str(output)
    text = output.read_text(encoding="utf-8")
    assert "Bản dịch Alpha" in text
    assert "Bản dịch Beta" in text


@pytest.mark.asyncio
async def test_failed_chunk_is_retryable_on_next_run(lifecycle_db) -> None:
    database, book_id, _ = lifecycle_db
    pipeline = TranslationPipeline(
        database,
        TranslationConfig(model="fake-model", max_retries=1),
    )
    first = FakeGateway([RuntimeError("temporary failure"), "Beta translated"])
    pipeline._gateway = first
    await pipeline.run_book(book_id)

    first_progress = await database.get_chunk_progress(book_id)
    assert first_progress["failed"] == 1
    assert first_progress["done"] == 1

    retry_pipeline = TranslationPipeline(
        database,
        TranslationConfig(model="fake-model", max_retries=1),
    )
    retry = FakeGateway(["Alpha recovered"])
    retry_pipeline._gateway = retry
    await retry_pipeline.run_book(book_id)

    progress = await database.get_chunk_progress(book_id)
    assert retry.calls == 1
    assert progress["failed"] == 0
    assert progress["done"] == 2
    assert progress["status"] == "done"


@pytest.mark.asyncio
async def test_range_translation_leaves_other_chapters_pending(lifecycle_db) -> None:
    database, book_id, _ = lifecycle_db
    pipeline = TranslationPipeline(
        database,
        TranslationConfig(model="range-model", max_retries=1),
    )
    pipeline._gateway = FakeGateway(["Only chapter one"])

    pending = await database.get_pending_chunks(book_id)
    chapter_one = [c for c in pending if c.chapter_idx == 0]
    glossary = await database.get_glossary(book_id)
    for chunk in chapter_one:
        translated = await pipeline.translate_chunk(chunk, glossary)
        assert chunk.id is not None
        await database.update_chunk_result(chunk.id, translated, "done")

    chapter_one_progress = await database.get_chunk_progress(book_id, 1, 1)
    whole_book = await database.get_chunk_progress(book_id)

    assert chapter_one_progress["status"] == "done"
    assert chapter_one_progress["total"] == 1
    assert whole_book["done"] == 1
    assert whole_book["pending"] == 1
    assert whole_book["status"] == "translating"
