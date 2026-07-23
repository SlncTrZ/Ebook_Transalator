"""SQLite database manager — WAL mode, async via aiosqlite.

Tables: books, chunks, glossary, cache.
Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite

from ebook_translator.models import Book, CacheEntry, Chunk, GlossaryEntry

DB_PATH = Path.home() / ".ebook_translator" / "library.db"

SQL_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    title TEXT DEFAULT '',
    author TEXT DEFAULT '',
    source_lang TEXT DEFAULT 'en',
    target_lang TEXT DEFAULT 'vi',
    category TEXT DEFAULT 'general',
    status TEXT DEFAULT 'pending',
    total_chunks INTEGER DEFAULT 0,
    done_chunks INTEGER DEFAULT 0,
    failed_chunks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_idx INTEGER NOT NULL,
    paragraph_idx INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT,
    status TEXT DEFAULT 'pending',
    token_count INTEGER DEFAULT 0,
    error_log TEXT,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    notes TEXT DEFAULT '',
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    model TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(content_hash, source_lang, target_lang, model)
);

CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON cache(content_hash, source_lang, target_lang, model);
CREATE INDEX IF NOT EXISTS idx_glossary_book ON glossary(book_id);
"""


class Database:
    """Async database manager wrapping aiosqlite."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def connect(self) -> None:
        """Open connection and apply schema."""
        self._connection = await aiosqlite.connect(str(self._db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SQL_SCHEMA)
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    # ---- Books ----

    async def insert_book(self, book: Book) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO books (file_path, title, author, source_lang, target_lang, category) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (book.file_path, book.title, book.author, book.source_lang, book.target_lang, book.category.value),
        )
        await self.conn.commit()
        row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("Failed to insert book — no rowid returned.")
        return row_id

    async def get_book(self, book_id: int) -> Book | None:
        cursor = await self.conn.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = await cursor.fetchone()
        return Book(**dict(row)) if row else None

    async def update_book_status(self, book_id: int) -> None:
        await self.conn.execute(
            "UPDATE books SET status = CASE "
            "WHEN failed_chunks > 0 THEN 'failed' "
            "WHEN done_chunks = total_chunks AND total_chunks > 0 THEN 'done' "
            "ELSE 'translating' END "
            "WHERE id = ?",
            (book_id,),
        )
        await self.conn.commit()

    # ---- Chunks ----

    async def insert_chunks(self, chunks: list[Chunk]) -> None:
        await self.conn.executemany(
            "INSERT INTO chunks (book_id, chapter_idx, paragraph_idx, content_hash, original_text, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(c.book_id, c.chapter_idx, c.paragraph_idx, c.content_hash, c.original_text, c.token_count) for c in chunks],
        )
        await self.conn.commit()

    async def get_pending_chunks(self, book_id: int) -> list[Chunk]:
        cursor = await self.conn.execute(
            "SELECT * FROM chunks WHERE book_id = ? AND status = 'pending' ORDER BY chapter_idx, paragraph_idx",
            (book_id,),
        )
        rows = await cursor.fetchall()
        return [Chunk(**dict(r)) for r in rows]

    async def update_chunk_result(self, chunk_id: int, translated: str, status: str) -> None:
        await self.conn.execute(
            "UPDATE chunks SET translated_text = ?, status = ? WHERE id = ?",
            (translated, status, chunk_id),
        )
        await self.conn.commit()

    async def mark_chunk_failed(self, chunk_id: int, error: str) -> None:
        await self.conn.execute(
            "UPDATE chunks SET status = 'failed', error_log = ? WHERE id = ?",
            (error, chunk_id),
        )
        await self.conn.commit()

    # ---- Cache ----

    async def get_cached(self, content_hash: str, source: str, target: str, model: str) -> str | None:
        cursor = await self.conn.execute(
            "SELECT translated_text FROM cache WHERE content_hash=? AND source_lang=? AND target_lang=? AND model=?",
            (content_hash, source, target, model),
        )
        row = await cursor.fetchone()
        return row["translated_text"] if row else None

    async def set_cached(self, entry: CacheEntry) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO cache (content_hash, source_lang, target_lang, model, translated_text) "
            "VALUES (?, ?, ?, ?, ?)",
            (entry.content_hash, entry.source_lang, entry.target_lang, entry.model, entry.translated_text),
        )
        await self.conn.commit()

    # ---- Glossary ----

    async def get_glossary(self, book_id: int) -> list[GlossaryEntry]:
        cursor = await self.conn.execute("SELECT * FROM glossary WHERE book_id = ?", (book_id,))
        rows = await cursor.fetchall()
        return [GlossaryEntry(**dict(r)) for r in rows]
