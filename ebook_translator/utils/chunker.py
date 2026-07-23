"""Chunking engine — paragraph-level with oversize protection.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import hashlib
import re

import tiktoken

from ebook_translator.models import Chunk, ChunkStatus

# Maximum tokens per chunk before sentence-level split
MAX_TOKENS_PER_CHUNK = 4000
# Model used for token estimation
TOKENIZER_MODEL = "gpt-4"


def _count_tokens(text: str) -> int:
    """Estimate token count using tiktoken."""
    encoder = tiktoken.encoding_for_model(TOKENIZER_MODEL)
    return len(encoder.encode(text))


def _hash_text(text: str) -> str:
    """SHA-256 fingerprint of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_oversize_paragraph(text: str) -> list[str]:
    """Split a paragraph exceeding MAX_TOKENS by sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        candidate = f"{current} {sent}".strip() if current else sent
        if _count_tokens(candidate) > MAX_TOKENS_PER_CHUNK and current:
            chunks.append(current)
            current = sent
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_book(book_id: int, chapters: list[list[str]]) -> list[Chunk]:
    """Convert parsed chapters into Chunk models with hashes and token counts.

    Args:
        book_id: Database ID for the book.
        chapters: List of chapters, each chapter is a list of paragraph strings.

    Returns:
        Flat list of Chunk objects ready for DB insertion.
    """
    chunks: list[Chunk] = []

    for chapter_idx, paragraph_list in enumerate(chapters):
        for para_idx, paragraph in enumerate(paragraph_list):
            token_count = _count_tokens(paragraph)

            if token_count > MAX_TOKENS_PER_CHUNK:
                sub_paras = _split_oversize_paragraph(paragraph)
                for sub_idx, sub_para in enumerate(sub_paras):
                    content_hash = _hash_text(sub_para)
                    chunks.append(
                        Chunk(
                            book_id=book_id,
                            chapter_idx=chapter_idx,
                            paragraph_idx=para_idx * 1000 + sub_idx,
                            content_hash=content_hash,
                            original_text=sub_para,
                            token_count=_count_tokens(sub_para),
                            status=ChunkStatus.PENDING,
                        )
                    )
            else:
                content_hash = _hash_text(paragraph)
                chunks.append(
                    Chunk(
                        book_id=book_id,
                        chapter_idx=chapter_idx,
                        paragraph_idx=para_idx,
                        content_hash=content_hash,
                        original_text=paragraph,
                        token_count=token_count,
                        status=ChunkStatus.PENDING,
                    )
                )

    return chunks
