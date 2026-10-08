"""Data Models — Pydantic for type safety and validation.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-10-08 19:16
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChunkStatus(str, Enum):
    """Trạng thái xử lý của đơn vị dịch (chunk)."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class BookCategory(str, Enum):
    """Thể loại sách dùng để phân loại và định hình ngữ cảnh dịch."""

    LITERATURE = "van_hoc"
    HISTORY = "lich_su"
    MODERN = "hien_dai"
    XIANXIA = "tien_hiep"
    WUXIA = "vo_hiep"
    SCI_FI = "khoa_hoc"
    FANTASY = "ky_ao"
    HORROR = "kinh_di"
    ROMANCE = "ngon_tinh"
    MYSTERY = "trinh_tham"
    COMEDY = "hai_huoc"
    GENERAL = "general"


@dataclass
class Book:
    """Metadata for an ebook being translated."""

    id: int | None = None
    file_path: str = ""
    title: str = ""
    author: str = ""
    localized_title: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: BookCategory = BookCategory.GENERAL
    status: str = "pending"
    total_chunks: int = 0
    done_chunks: int = 0
    failed_chunks: int = 0

    def __post_init__(self) -> None:
        """Kiểm tra và ép kiểu thuộc tính category về BookCategory Enum.

        Returns:
            None.
        """
        if not isinstance(self.category, BookCategory):
            try:
                self.category = BookCategory(self.category)
            except ValueError:
                self.category = BookCategory.GENERAL


@dataclass
class Chunk:
    """A single translatable text unit (paragraph-level)."""

    id: int | None = None
    book_id: int = 0
    chapter_idx: int = 0
    paragraph_idx: int = 0
    segment_idx: int = 0
    content_hash: str = ""
    original_text: str = ""
    translated_text: str | None = None
    status: ChunkStatus = ChunkStatus.PENDING
    token_count: int = 0
    error_log: str | None = None


@dataclass
class GlossaryEntry:
    """A term mapping for consistency across translations."""

    id: int | None = None
    book_id: int = 0
    source_term: str = ""
    target_term: str = ""
    notes: str = ""


@dataclass
class CacheEntry:
    """Cached translation result keyed by content hash."""

    id: int | None = None
    content_hash: str = ""
    context_hash: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    model: str = ""
    translated_text: str = ""
    created_at: str | None = None
