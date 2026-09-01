"""P1.5 tests for context-isolated cache and explicit translation memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebook_translator.db.database import Database
from ebook_translator.models import Book, CacheEntry, Chunk
from ebook_translator.translator.metrics import reset_for_tests, snapshot
from ebook_translator.translator.pipeline import TranslationConfig, TranslationPipeline
import ebook_translator.server as server


@pytest.mark.asyncio
async def test_exact_cache_isolated_by_context_hash(tmp_path: Path) -> None:
    database = Database(tmp_path / "cache.db")
    await database.connect()
    await database.set_cached(
        CacheEntry(
            content_hash="same-source",
            context_hash="context-a",
            source_lang="en",
            target_lang="vi",
            model="model-x",
            translated_text="A",
        )
    )
    await database.set_cached(
        CacheEntry(
            content_hash="same-source",
            context_hash="context-b",
            source_lang="en",
            target_lang="vi",
            model="model-x",
            translated_text="B",
        )
    )

    assert await database.get_cached("same-source", "en", "vi", "model-x", "context-a") == "A"
    assert await database.get_cached("same-source", "en", "vi", "model-x", "context-b") == "B"
    assert await database.get_cached("same-source", "en", "vi", "model-x", "other") is None
    await database.close()


@pytest.mark.asyncio
async def test_translation_memory_requires_explicit_promotion_and_overrides_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_for_tests()
    database = Database(tmp_path / "memory.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="one.txt", title="One"))
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="shared-hash",
                original_text="Shared source",
            )
        ]
    )
    cursor = await database.conn.execute("SELECT id FROM chunks WHERE book_id = ?", (book_id,))
    chunk_id = (await cursor.fetchone())["id"]
    monkeypatch.setattr(server, "db", database)

    await server.update_chunk_translation(
        chunk_id,
        server.UpdateChunkRequest(translated_text="Manual correction only"),
    )
    assert await database.get_translation_memory("shared-hash", "en", "vi") is None

    await server.remember_chunk_translation(
        chunk_id,
        server.UpdateChunkRequest(translated_text="Approved reusable translation"),
    )
    assert (
        await database.get_translation_memory("shared-hash", "en", "vi")
        == "Approved reusable translation"
    )

    second_id = await database.insert_book(Book(file_path="two.txt", title="Two"))
    chunk = Chunk(
        book_id=second_id,
        chapter_idx=0,
        paragraph_idx=0,
        content_hash="shared-hash",
        original_text="Shared source",
    )
    await database.insert_chunks([chunk])
    pending = await database.get_pending_chunks(second_id)

    class FailIfCalled:
        async def generate(self, *args, **kwargs):
            raise AssertionError("Provider must not be called on translation-memory hit")

    pipeline = TranslationPipeline(database, TranslationConfig(model="model-y", max_retries=1))
    pipeline._gateway = FailIfCalled()
    result = await pipeline.translate_chunk(pending[0], [])

    assert result == "Approved reusable translation"
    assert snapshot()["translation_memory_hits"] == 1
    await database.close()
