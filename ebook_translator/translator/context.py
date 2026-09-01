"""Bounded long-form translation context construction."""

from __future__ import annotations

from dataclasses import dataclass

from ebook_translator.db.database import Database
from ebook_translator.models import Chunk


@dataclass(frozen=True)
class TranslationContext:
    previous_source: str = ""
    previous_translation: str = ""
    next_source: str = ""

    def render(self) -> str:
        sections: list[str] = []
        if self.previous_source or self.previous_translation:
            block = "[Previous Context]"
            if self.previous_source:
                block += f"\nSource: {self.previous_source}"
            if self.previous_translation:
                block += f"\nApproved/Done translation: {self.previous_translation}"
            sections.append(block)
        if self.next_source:
            sections.append(f"[Next Source Context]\n{self.next_source}")
        return "\n\n".join(sections)


class ContextBuilder:
    """Build small deterministic neighborhood context from canonical chunks."""

    def __init__(self, db: Database, max_chars: int = 2400) -> None:
        self._db = db
        self._max_chars = max(256, max_chars)

    async def build_for_chunk(self, chunk: Chunk) -> TranslationContext:
        try:
            connection = self._db.conn
        except (AttributeError, RuntimeError):
            return TranslationContext()

        cursor = await connection.execute(
            "SELECT chapter_idx, paragraph_idx, segment_idx, original_text, translated_text, status "
            "FROM chunks WHERE book_id = ? AND chapter_idx = ? "
            "AND paragraph_idx IN (?, ?) ORDER BY paragraph_idx, segment_idx",
            (
                chunk.book_id,
                chunk.chapter_idx,
                max(0, chunk.paragraph_idx - 1),
                chunk.paragraph_idx + 1,
            ),
        )
        rows = await cursor.fetchall()

        previous_source_parts: list[str] = []
        previous_translation_parts: list[str] = []
        next_source_parts: list[str] = []
        for row in rows:
            if row["paragraph_idx"] < chunk.paragraph_idx:
                if row["original_text"]:
                    previous_source_parts.append(row["original_text"])
                if row["status"] == "done" and row["translated_text"]:
                    previous_translation_parts.append(row["translated_text"])
            elif row["paragraph_idx"] > chunk.paragraph_idx and row["original_text"]:
                next_source_parts.append(row["original_text"])

        previous_source = " ".join(part.strip() for part in previous_source_parts if part.strip())
        previous_translation = " ".join(
            part.strip() for part in previous_translation_parts if part.strip()
        )
        next_source = " ".join(part.strip() for part in next_source_parts if part.strip())

        return self._bounded(previous_source, previous_translation, next_source)

    def _bounded(
        self, previous_source: str, previous_translation: str, next_source: str
    ) -> TranslationContext:
        # Prefer approved/done translation, then adjacent source. Deterministic truncation.
        remaining = self._max_chars

        def take(text: str, budget: int) -> str:
            if not text or budget <= 0:
                return ""
            if len(text) <= budget:
                return text
            return text[: max(0, budget - 1)].rstrip() + "…"

        previous_translation = take(previous_translation, remaining)
        remaining -= len(previous_translation)
        previous_source = take(previous_source, remaining // 2 if previous_translation else remaining)
        remaining -= len(previous_source)
        next_source = take(next_source, remaining)

        return TranslationContext(
            previous_source=previous_source,
            previous_translation=previous_translation,
            next_source=next_source,
        )
