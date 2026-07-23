"""Translation pipeline — cache-first, retry with exponential backoff.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ebook_translator.db.database import Database
from ebook_translator.models import CacheEntry, Chunk, GlossaryEntry

logger = logging.getLogger(__name__)

# Default system prompt for plain translation (no routing yet)
SYSTEM_PROMPT = (
    "You are a professional literary translator. Translate the following text "
    "from {source_lang} to {target_lang}. Preserve the original meaning, tone, "
    "and style. Return only the translated text, no explanations."
)


@dataclass
class TranslationConfig:
    """Configuration for the translation pipeline."""

    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    source_lang: str = "en"
    target_lang: str = "vi"
    max_retries: int = 3
    request_timeout: int = 60


class TranslationPipeline:
    """Manages the async translation loop with cache and retry."""

    def __init__(self, db: Database, config: TranslationConfig) -> None:
        self._db = db
        self._config = config
        self._http = httpx.AsyncClient(timeout=config.request_timeout)

    async def close(self) -> None:
        await self._http.aclose()

    def _build_user_prompt(self, chunk: Chunk, glossary: list[GlossaryEntry]) -> str:
        prompt = chunk.original_text
        if glossary:
            terms = "\n".join(f"{g.source_term} → {g.target_term}" for g in glossary)
            prompt = f"[Glossary]\n{terms}\n\n[Text]\n{chunk.original_text}"
        return prompt

    def _build_messages(
        self, chunk: Chunk, glossary: list[GlossaryEntry]
    ) -> list[dict]:
        system = SYSTEM_PROMPT.format(
            source_lang=self._config.source_lang,
            target_lang=self._config.target_lang,
        )
        user = self._build_user_prompt(chunk, glossary)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def _call_api(self, messages: list[dict]) -> str:
        """Call OpenAI-compatible API with streaming disabled."""
        response = await self._http.post(
            f"{self._config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._config.model,
                "messages": messages,
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    async def translate_chunk(self, chunk: Chunk, glossary: list[GlossaryEntry]) -> str:
        """Translate one chunk: cache check → API call with retry → save cache."""

        # Step 1: Cache check
        cached = await self._db.get_cached(
            content_hash=chunk.content_hash,
            source=self._config.source_lang,
            target=self._config.target_lang,
            model=self._config.model,
        )
        if cached is not None:
            logger.info("Cache HIT for hash=%s", chunk.content_hash[:12])
            return cached

        # Step 2: Build messages
        messages = self._build_messages(chunk, glossary)

        # Step 3: API call with retry
        result: str | None = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception_type(
                (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
            ),
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

        # Step 4: Save to cache
        cache_entry = CacheEntry(
            content_hash=chunk.content_hash,
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
        total = len(pending)
        logger.info("Starting translation for book %d — %d chunks", book_id, total)

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
