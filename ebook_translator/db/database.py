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
    localized_title TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS translation_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    vendor TEXT DEFAULT '',
    model TEXT DEFAULT '',
    chapter_start INTEGER DEFAULT 0,
    chapter_end INTEGER DEFAULT 99999,
    status TEXT DEFAULT 'pending',
    error_summary TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT,
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

CREATE TABLE IF NOT EXISTS translation_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    context_hash TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    model TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(content_hash, context_hash, source_lang, target_lang, model)
);

CREATE TABLE IF NOT EXISTS translation_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    source_text TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    origin TEXT DEFAULT 'manual',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(content_hash, source_lang, target_lang)
);

CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON cache(content_hash, source_lang, target_lang, model);
CREATE INDEX IF NOT EXISTS idx_translation_cache_lookup ON translation_cache(content_hash, context_hash, source_lang, target_lang, model);
CREATE INDEX IF NOT EXISTS idx_translation_memory_lookup ON translation_memory(content_hash, source_lang, target_lang);
CREATE INDEX IF NOT EXISTS idx_glossary_book ON glossary(book_id);
CREATE INDEX IF NOT EXISTS idx_jobs_book ON translation_jobs(book_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON translation_jobs(status);
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
        columns = {
            row["name"]
            for row in await (await self._connection.execute("PRAGMA table_info(books)")).fetchall()
        }
        if "localized_title" not in columns:
            await self._connection.execute(
                "ALTER TABLE books ADD COLUMN localized_title TEXT DEFAULT ''"
            )
        await self._connection.execute(
            "UPDATE translation_jobs SET status = 'interrupted', finished_at = datetime('now'), "
            "error_summary = CASE WHEN error_summary = '' THEN 'Process restarted before completion' ELSE error_summary END "
            "WHERE status = 'running'"
        )
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    # ---- Books ----

    async def insert_book(self, book: Book) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO books (file_path, title, author, localized_title, source_lang, target_lang, category) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                book.file_path,
                book.title,
                book.author,
                book.localized_title,
                book.source_lang,
                book.target_lang,
                book.category.value,
            ),
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

    async def get_chunk_progress(
        self,
        book_id: int,
        chapter_start: int = 0,
        chapter_end: int = 99999,
    ) -> dict[str, int | str]:
        """Aggregate canonical progress directly from chunks.

        Chapter inputs are 1-based when a range is supplied. A chapter_start of 0
        means full-book scope for backward compatibility with the API defaults.
        """
        sql = (
            "SELECT "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed, "
            "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending "
            "FROM chunks WHERE book_id = ?"
        )
        params: list[int] = [book_id]
        if chapter_end < 99999 or chapter_start > 0:
            sql += " AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ?"
            params.extend([max(1, chapter_start), chapter_end])

        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        total = int(row["total"] or 0) if row else 0
        done = int(row["done"] or 0) if row else 0
        failed = int(row["failed"] or 0) if row else 0
        pending = int(row["pending"] or 0) if row else 0

        if total == 0 or pending == total:
            status = "pending"
        elif pending > 0:
            status = "translating"
        elif failed > 0:
            status = "failed"
        else:
            status = "done"

        return {
            "total": total,
            "done": done,
            "failed": failed,
            "pending": pending,
            "status": status,
        }

    async def update_book_status(self, book_id: int) -> None:
        """Refresh legacy book counters from canonical chunk state."""
        progress = await self.get_chunk_progress(book_id)
        await self.conn.execute(
            "UPDATE books SET total_chunks = ?, done_chunks = ?, failed_chunks = ?, status = ? "
            "WHERE id = ?",
            (
                progress["total"],
                progress["done"],
                progress["failed"],
                progress["status"],
                book_id,
            ),
        )
        await self.conn.commit()

    # ---- Chunks ----

    async def insert_chunks(self, chunks: list[Chunk]) -> None:
        await self.conn.executemany(
            "INSERT INTO chunks (book_id, chapter_idx, paragraph_idx, content_hash, original_text, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    c.book_id,
                    c.chapter_idx,
                    c.paragraph_idx,
                    c.content_hash,
                    c.original_text,
                    c.token_count,
                )
                for c in chunks
            ],
        )
        await self.conn.commit()

    async def get_pending_chunks(self, book_id: int) -> list[Chunk]:
        """Return retryable chunks: never translated or previously failed."""
        cursor = await self.conn.execute(
            "SELECT * FROM chunks WHERE book_id = ? AND status IN ('pending', 'failed') "
            "ORDER BY chapter_idx, paragraph_idx",
            (book_id,),
        )
        rows = await cursor.fetchall()
        return [Chunk(**dict(r)) for r in rows]

    async def update_chunk_result(
        self, chunk_id: int, translated: str, status: str
    ) -> None:
        await self.conn.execute(
            "UPDATE chunks SET translated_text = ?, status = ? WHERE id = ?",
            (translated, status, chunk_id),
        )
        cursor = await self.conn.execute(
            "SELECT book_id FROM chunks WHERE id = ?", (chunk_id,)
        )
        row = await cursor.fetchone()
        await self.conn.commit()
        if row:
            await self.update_book_status(row["book_id"])

    async def mark_chunk_failed(self, chunk_id: int, error: str) -> None:
        await self.conn.execute(
            "UPDATE chunks SET status = 'failed', error_log = ? WHERE id = ?",
            (error, chunk_id),
        )
        cursor = await self.conn.execute(
            "SELECT book_id FROM chunks WHERE id = ?", (chunk_id,)
        )
        row = await cursor.fetchone()
        await self.conn.commit()
        if row:
            await self.update_book_status(row["book_id"])

    # ---- Translation jobs ----

    async def create_translation_job(
        self,
        book_id: int,
        mode: str,
        vendor: str,
        model: str,
        chapter_start: int,
        chapter_end: int,
    ) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO translation_jobs "
            "(book_id, mode, vendor, model, chapter_start, chapter_end, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'running', datetime('now'))",
            (book_id, mode, vendor, model, chapter_start, chapter_end),
        )
        await self.conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create translation job")
        return int(cursor.lastrowid)

    async def finish_translation_job(
        self, job_id: int, status: str, error_summary: str = ""
    ) -> None:
        await self.conn.execute(
            "UPDATE translation_jobs SET status = ?, error_summary = ?, finished_at = datetime('now') "
            "WHERE id = ?",
            (status, error_summary, job_id),
        )
        await self.conn.commit()

    async def get_latest_job(self, book_id: int) -> dict | None:
        cursor = await self.conn.execute(
            "SELECT * FROM translation_jobs WHERE book_id = ? ORDER BY id DESC LIMIT 1",
            (book_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_diagnostics(self) -> dict[str, int]:
        cursor = await self.conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM books) AS books, "
            "(SELECT COUNT(*) FROM chunks) AS chunks, "
            "(SELECT COUNT(*) FROM chunks WHERE status = 'done') AS done_chunks, "
            "(SELECT COUNT(*) FROM chunks WHERE status = 'failed') AS failed_chunks, "
            "(SELECT COUNT(*) FROM translation_cache) AS cache_entries, "
            "(SELECT COUNT(*) FROM translation_memory) AS translation_memory_entries, "
            "(SELECT COUNT(*) FROM translation_jobs) AS jobs, "
            "(SELECT COUNT(*) FROM translation_jobs WHERE status = 'running') AS running_jobs, "
            "(SELECT COUNT(*) FROM translation_jobs WHERE status = 'interrupted') AS interrupted_jobs"
        )
        row = await cursor.fetchone()
        return {key: int(row[key] or 0) for key in row.keys()} if row else {}

    # ---- Translation memory ----

    async def get_translation_memory(
        self, content_hash: str, source: str, target: str
    ) -> str | None:
        cursor = await self.conn.execute(
            "SELECT translated_text FROM translation_memory "
            "WHERE content_hash = ? AND source_lang = ? AND target_lang = ?",
            (content_hash, source, target),
        )
        row = await cursor.fetchone()
        return row["translated_text"] if row else None

    async def set_translation_memory(
        self,
        content_hash: str,
        source_text: str,
        source: str,
        target: str,
        translated: str,
        origin: str = "manual",
    ) -> None:
        await self.conn.execute(
            "INSERT INTO translation_memory "
            "(content_hash, source_text, source_lang, target_lang, translated_text, origin) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(content_hash, source_lang, target_lang) DO UPDATE SET "
            "source_text = excluded.source_text, translated_text = excluded.translated_text, "
            "origin = excluded.origin, updated_at = datetime('now')",
            (content_hash, source_text, source, target, translated, origin),
        )
        await self.conn.commit()

    # ---- Exact response cache ----

    async def get_cached(
        self,
        content_hash: str,
        source: str,
        target: str,
        model: str,
        context_hash: str = "",
    ) -> str | None:
        cursor = await self.conn.execute(
            "SELECT translated_text FROM translation_cache "
            "WHERE content_hash = ? AND context_hash = ? AND source_lang = ? "
            "AND target_lang = ? AND model = ?",
            (content_hash, context_hash, source, target, model),
        )
        row = await cursor.fetchone()
        return row["translated_text"] if row else None

    async def set_cached(self, entry: CacheEntry) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO translation_cache "
            "(content_hash, context_hash, source_lang, target_lang, model, translated_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry.content_hash,
                entry.context_hash,
                entry.source_lang,
                entry.target_lang,
                entry.model,
                entry.translated_text,
            ),
        )
        await self.conn.commit()

    # ---- Glossary ----

    async def get_glossary(self, book_id: int) -> list[GlossaryEntry]:
        cursor = await self.conn.execute(
            "SELECT * FROM glossary WHERE book_id = ?", (book_id,)
        )
        rows = await cursor.fetchall()
        return [GlossaryEntry(**dict(r)) for r in rows]
