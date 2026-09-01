"""Translation pipeline — cache-first, retry with exponential backoff (vendor-agnostic).

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ebook_translator.db.database import Database
from ebook_translator.models import BookCategory, CacheEntry, Chunk, GlossaryEntry
from ebook_translator.translator.adapters import VENDORS
from ebook_translator.translator.cache_key import prompt_fingerprint
from ebook_translator.translator.context import ContextBuilder
from ebook_translator.translator.gateway import LLMConfig, LLMGateway
from ebook_translator.translator.metrics import (
    record_cache_hit,
    record_translation_memory_hit,
)
from ebook_translator.translator.prompts import get_system_prompt
from ebook_translator.translator.qa import check_translation

logger = logging.getLogger(__name__)

@dataclass
class TranslationConfig:
    """Configuration for the translation pipeline."""

    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: BookCategory | str | None = None
    max_retries: int = 3
    request_timeout: int = 120

    def __post_init__(self) -> None:
        """Auto-fill base_url + default model tu vendor."""
        v = VENDORS.get(self.vendor)
        if v:
            self.base_url = self.base_url or v.base_url
            if not self.model:
                self.model = v.default_model
        if self.category is not None and not isinstance(self.category, BookCategory):
            try:
                self.category = BookCategory(self.category)
            except ValueError:
                logger.warning("Unknown category %r; falling back to general", self.category)
                self.category = BookCategory.GENERAL


_RETRY_EXCEPTIONS = (
    # httpx HTTP status errors
    Exception,  # catch-all for API errors
)


class TranslationPipeline:
    """Manages the async translation loop with cache and retry (vendor-agnostic)."""

    def __init__(self, db: Database, config: TranslationConfig) -> None:
        self._db = db
        self._config = config
        self._gateway = LLMGateway(
            LLMConfig(
                vendor=config.vendor,
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
            )
        )
        self._book_categories: dict[int, BookCategory] = {}
        self._context_builder = ContextBuilder(db)

    async def close(self) -> None:
        pass

    def _build_user_prompt(
        self,
        chunk: Chunk,
        glossary: list[GlossaryEntry],
        context_text: str = "",
    ) -> str:
        sections: list[str] = []
        if context_text:
            sections.append(context_text)
        if glossary:
            terms = "\n".join(
                f"{g.source_term} -> {g.target_term}" for g in glossary
            )
            sections.append(
                "[Glossary - use target terms EXACTLY as written]\n" + terms
            )
        sections.append(f"[Text]\n{chunk.original_text}")
        return "\n\n".join(sections)

    async def _resolve_category(self, book_id: int) -> BookCategory:
        """Resolve category from explicit config or the persisted book, then cache it."""
        if isinstance(self._config.category, BookCategory):
            return self._config.category
        cached = self._book_categories.get(book_id)
        if cached is not None:
            return cached
        book = await self._db.get_book(book_id)
        category = book.category if book is not None else BookCategory.GENERAL
        if not isinstance(category, BookCategory):
            try:
                category = BookCategory(category)
            except ValueError:
                category = BookCategory.GENERAL
        self._book_categories[book_id] = category
        return category

    def _build_messages(
        self,
        chunk: Chunk,
        glossary: list[GlossaryEntry],
        category: BookCategory,
        context_text: str = "",
    ) -> list[dict]:
        system = get_system_prompt(
            category,
            source_lang=self._config.source_lang,
            target_lang=self._config.target_lang,
        )
        user = self._build_user_prompt(chunk, glossary, context_text)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def _call_api(self, messages: list[dict]) -> str:
        """Generate through the unified LLM gateway."""
        return await self._gateway.generate(messages, temperature=0.3)

    async def translate_chunk(self, chunk: Chunk, glossary: list[GlossaryEntry]) -> str:
        """Translate one chunk: cache check -> API call with retry -> save cache."""

        # Step 1: user-approved translation memory outranks model cache.
        remembered = await self._db.get_translation_memory(
            chunk.content_hash,
            self._config.source_lang,
            self._config.target_lang,
        )
        if remembered is not None:
            record_translation_memory_hit()
            logger.info("Translation Memory HIT for hash=%s", chunk.content_hash[:12])
            return remembered

        # Step 2: exact-response cache is isolated by the complete prompt context.
        category = await self._resolve_category(chunk.book_id)
        context = await self._context_builder.build_for_chunk(chunk)
        messages = self._build_messages(chunk, glossary, category, context.render())
        context_hash = prompt_fingerprint(messages)
        cached = await self._db.get_cached(
            content_hash=chunk.content_hash,
            source=self._config.source_lang,
            target=self._config.target_lang,
            model=self._config.model,
            context_hash=context_hash,
        )
        if cached is not None:
            record_cache_hit()
            logger.info("Cache HIT for hash=%s", chunk.content_hash[:12])
            return cached

        # Step 3: API call with retry
        result: str | None = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    logger.warning(
                        "Retry %d for hash=%s",
                        attempt.retry_state.attempt_number,
                        chunk.content_hash[:12],
                    )
                result = await self._call_api(messages)

        if result is None:
            raise RuntimeError(
                f"Translation failed after {self._config.max_retries} retries"
            )

        qa = check_translation(chunk.original_text, result, glossary)
        for issue in qa.issues:
            log = logger.error if issue.severity == "error" else logger.warning
            log("QA %s for hash=%s: %s", issue.code, chunk.content_hash[:12], issue.message)

        # Step 4: Save to cache
        cache_entry = CacheEntry(
            content_hash=chunk.content_hash,
            context_hash=context_hash,
            source_lang=self._config.source_lang,
            target_lang=self._config.target_lang,
            model=self._config.model,
            translated_text=result,
        )
        await self._db.set_cached(cache_entry)

        return result

    async def run_book(self, book_id: int) -> None:
        """Translate all pending chunks for a book."""
        glossary = await self._db.get_glossary(book_id)
        pending = await self._db.get_pending_chunks(book_id)
        if pending:
            total = len(pending)
            logger.info("Starting translation for book %d - %d chunks", book_id, total)

            for idx, chunk in enumerate(pending):
                try:
                    translated = await self.translate_chunk(chunk, glossary)
                    if chunk.id is not None:
                        await self._db.update_chunk_result(chunk.id, translated, "done")
                    logger.info(
                        "[%d/%d] OK hash=%s", idx + 1, total, chunk.content_hash[:12]
                    )
                except Exception as e:
                    logger.error(
                        "[%d/%d] FAILED hash=%s: %s",
                        idx + 1,
                        total,
                        chunk.content_hash[:12],
                        e,
                    )
                    if chunk.id is not None:
                        await self._db.mark_chunk_failed(chunk.id, str(e))

            await self._db.update_book_status(book_id)
            logger.info("Translation complete for book %d", book_id)
