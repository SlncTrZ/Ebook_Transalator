"""Standard translation category routing tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ebook_translator.models import BookCategory, Chunk
from ebook_translator.translator.pipeline import TranslationConfig, TranslationPipeline


@dataclass
class FakeBook:
    category: BookCategory


class FakeDb:
    def __init__(self, category: BookCategory) -> None:
        self.category = category
        self.get_book_calls = 0

    async def get_book(self, book_id: int):
        self.get_book_calls += 1
        return FakeBook(self.category)

    async def get_translation_memory(self, *args, **kwargs):
        return None

    async def get_cached(self, *args, **kwargs):
        return None

    async def set_cached(self, *args, **kwargs):
        return None


class CaptureGateway:
    def __init__(self) -> None:
        self.messages: list[dict] | None = None

    async def generate(self, messages: list[dict], **kwargs) -> str:
        self.messages = messages
        return "translated"


@pytest.mark.asyncio
async def test_standard_translation_uses_persisted_book_category() -> None:
    db = FakeDb(BookCategory.SCI_FI)
    pipeline = TranslationPipeline(db, TranslationConfig(model="fake"))
    gateway = CaptureGateway()
    pipeline._gateway = gateway
    chunk = Chunk(
        book_id=7,
        chapter_idx=0,
        paragraph_idx=0,
        content_hash="category-sci-fi",
        original_text="The reactor is unstable.",
    )

    result = await pipeline.translate_chunk(chunk, [])

    assert result == "translated"
    assert gateway.messages is not None
    system = gateway.messages[0]["content"]
    assert "KHOA HỌC VIỄN TƯỞNG" in system
    assert "chính xác, logic" in system
    assert db.get_book_calls == 1


@pytest.mark.asyncio
async def test_category_resolution_is_cached_per_book() -> None:
    db = FakeDb(BookCategory.HORROR)
    pipeline = TranslationPipeline(db, TranslationConfig(model="fake"))

    first = await pipeline._resolve_category(3)
    second = await pipeline._resolve_category(3)

    assert first is BookCategory.HORROR
    assert second is BookCategory.HORROR
    assert db.get_book_calls == 1


def test_explicit_category_overrides_persisted_lookup() -> None:
    config = TranslationConfig(model="fake", category=BookCategory.MYSTERY.value)

    assert config.category is BookCategory.MYSTERY


def test_unknown_category_falls_back_to_general() -> None:
    config = TranslationConfig(model="fake", category="not-a-category")

    assert config.category is BookCategory.GENERAL


def test_category_prompts_are_distinct() -> None:
    db = FakeDb(BookCategory.GENERAL)
    pipeline = TranslationPipeline(db, TranslationConfig(model="fake"))
    chunk = Chunk(
        book_id=1,
        chapter_idx=0,
        paragraph_idx=0,
        content_hash="distinct",
        original_text="Text",
    )

    sci_fi = pipeline._build_messages(chunk, [], BookCategory.SCI_FI)[0]["content"]
    romance = pipeline._build_messages(chunk, [], BookCategory.ROMANCE)[0]["content"]
    general = pipeline._build_messages(chunk, [], BookCategory.GENERAL)[0]["content"]

    assert sci_fi != romance
    assert romance != general
    assert sci_fi != general
