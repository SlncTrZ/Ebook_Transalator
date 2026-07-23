"""FastAPI server — REST API cho Tauri frontend, SSE progress.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ebook_translator.db.database import Database
from ebook_translator.export.epub_writer import export_epub
from ebook_translator.models import Book, BookCategory
from ebook_translator.parsers.epub_parser import EpubParser
from ebook_translator.parsers.txt_parser import TxtParser
from ebook_translator.translator.pipeline import TranslationConfig, TranslationPipeline
from ebook_translator.translator.prompts import CATEGORY_INFO, get_system_prompt
from ebook_translator.utils.chunker import chunk_book

logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────────────

PARSERS = {".epub": EpubParser(), ".txt": TxtParser()}
DB_PATH = os.environ.get("ET_DB_PATH")
db: Database | None = None
active_pipeline: TranslationPipeline | None = None
active_book_id: int | None = None
_cancel_event = asyncio.Event()


# ── Request/Response models ──────────────────────────────────────────────


class StartTranslateRequest(BaseModel):
    file_path: str
    api_key: str = ""
    model: str = "gpt-4o-mini"
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"
    base_url: str = "https://api.openai.com/v1"


class CreateGlossaryRequest(BaseModel):
    book_id: int
    source_term: str
    target_term: str
    notes: str = ""


class UpdateBookRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    category: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None


class AnalyzeRequest(BaseModel):
    api_key: str = ""
    model: str = "gpt-4o-mini"


class ConfirmMetadataRequest(BaseModel):
    title: str = ""
    author: str = ""
    localized_title: str = ""
    source_lang: str = "en"
    category: str = "general"


# ── Lifespan ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    global db
    db = Database(DB_PATH)
    await db.connect()
    yield
    if db:
        await db.close()


app = FastAPI(title="Ebook Translator API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_db() -> Database:
    if db is None:
        raise RuntimeError("Database not initialized")
    return db


def _get_parser(file_path: str):
    ext = Path(file_path).suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Supported: {list(PARSERS)}",
        )
    return parser


# ── Books ────────────────────────────────────────────────────────────────


@app.get("/api/books")
async def list_books() -> list[dict]:
    d = _get_db()
    cursor = await d.conn.execute("SELECT * FROM books ORDER BY id DESC")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/books")
async def create_book(file_path: str = Query(...)) -> dict:
    d = _get_db()
    parser = _get_parser(file_path)
    try:
        parsed = parser.parse(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    book = Book(
        file_path=file_path,
        title=parsed.title,
        author=parsed.author,
    )
    book_id = await d.insert_book(book)
    chunks = chunk_book(book_id, parsed.chapters)
    await d.insert_chunks(chunks)
    return {
        "id": book_id,
        "title": parsed.title,
        "chunks": len(chunks),
        "status": "pending",
    }


@app.get("/api/books/{book_id}")
async def get_book(book_id: int) -> dict:
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return {k: v for k, v in book.__dict__.items() if not k.startswith("_")}


@app.patch("/api/books/{book_id}")
async def update_book(book_id: int, req: UpdateBookRequest) -> dict:
    d = _get_db()
    sets = []
    params = []
    for field in ("title", "author", "source_lang", "target_lang"):
        val = getattr(req, field, None)
        if val is not None:
            sets.append(f"{field} = ?")
            params.append(val)
    if req.category:
        sets.append("category = ?")
        params.append(req.category)
    if sets:
        params.append(book_id)
        await d.conn.execute(f"UPDATE books SET {', '.join(sets)} WHERE id = ?", params)
        await d.conn.commit()
    return {"ok": True}


# ── Web Search + HITL (Phase 3) ───────────────────────────────────────────


@app.post("/api/books/{book_id}/analyze")
async def analyze_book(book_id: int, req: AnalyzeRequest) -> dict:
    """Web Search Agent: phân tích metadata sách, đề xuất bản địa hóa."""
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    api_key = req.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key required")

    try:
        preview = await get_preview_text(book.file_path)
        result = await extract_metadata(
            preview=preview, api_key=api_key, model=req.model
        )
        return {
            "title": result.title or book.title,
            "author": result.author or book.author,
            "source_lang": result.source_lang,
            "localized_title": result.localized_title,
            "category": result.category,
            "description": result.description,
            "confidence": result.confidence,
            "sources": result.sources,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/books/{book_id}/confirm-metadata")
async def confirm_metadata(book_id: int, req: ConfirmMetadataRequest) -> dict:
    """HITL: Lưu metadata user đã duyệt vào DB."""
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    await d.conn.execute(
        "UPDATE books SET title=?, author=?, source_lang=?, category=? WHERE id=?",
        (
            req.title or book.title,
            req.author or book.author,
            req.source_lang,
            req.category,
            book_id,
        ),
    )
    await d.conn.commit()
    return {"ok": True}


# ── Chunks ───────────────────────────────────────────────────────────────


@app.get("/api/books/{book_id}/chunks")
async def list_chunks(book_id: int, status: str | None = None) -> list[dict]:
    d = _get_db()
    sql = "SELECT id, chapter_idx, paragraph_idx, status, token_count, error_log FROM chunks WHERE book_id = ?"
    params: list = [book_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY chapter_idx, paragraph_idx"
    cursor = await d.conn.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── Glossary ─────────────────────────────────────────────────────────────


@app.get("/api/books/{book_id}/glossary")
async def get_glossary(book_id: int) -> list[dict]:
    d = _get_db()
    entries = await d.get_glossary(book_id)
    return [
        {
            "id": e.id,
            "source_term": e.source_term,
            "target_term": e.target_term,
            "notes": e.notes,
        }
        for e in entries
    ]


@app.post("/api/glossary")
async def create_glossary(req: CreateGlossaryRequest) -> dict:
    d = _get_db()
    cursor = await d.conn.execute(
        "INSERT INTO glossary (book_id, source_term, target_term, notes) VALUES (?, ?, ?, ?)",
        (req.book_id, req.source_term, req.target_term, req.notes),
    )
    await d.conn.commit()
    return {"id": cursor.lastrowid}


@app.delete("/api/glossary/{entry_id}")
async def delete_glossary(entry_id: int) -> dict:
    d = _get_db()
    await d.conn.execute("DELETE FROM glossary WHERE id = ?", (entry_id,))
    await d.conn.commit()
    return {"ok": True}


# ── Translation ──────────────────────────────────────────────────────────


@app.post("/api/translate/start")
async def start_translate(req: StartTranslateRequest) -> dict:
    global active_pipeline, active_book_id, _cancel_event
    d = _get_db()

    # Cancel any active translation
    if active_pipeline:
        _cancel_event.set()
        await asyncio.sleep(0.5)

    _cancel_event.clear()

    # Find or create book
    cursor = await d.conn.execute(
        "SELECT id FROM books WHERE file_path = ?", (req.file_path,)
    )
    row = await cursor.fetchone()
    if row:
        book_id = row["id"]
    else:
        parser = _get_parser(req.file_path)
        parsed = parser.parse(req.file_path)
        book = Book(
            file_path=req.file_path,
            title=parsed.title,
            author=parsed.author,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            category=BookCategory(req.category)
            if req.category
            else BookCategory.GENERAL,
        )
        book_id = await d.insert_book(book)
        chunks = chunk_book(book_id, parsed.chapters)
        await d.insert_chunks(chunks)

    config = TranslationConfig(
        api_key=req.api_key or os.environ.get("OPENAI_API_KEY", ""),
        model=req.model,
        base_url=req.base_url,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
    )
    active_book_id = book_id
    active_pipeline = TranslationPipeline(d, config)

    # Run in background
    asyncio.create_task(_run_translation(book_id))
    return {"book_id": book_id, "status": "started"}


async def _run_translation(book_id: int) -> None:
    global active_pipeline, active_book_id
    d = _get_db()
    pipeline = active_pipeline
    if pipeline is None:
        return

    try:
        glossary = await d.get_glossary(book_id)
        pending = await d.get_pending_chunks(book_id)
        total = len(pending)

        for _, chunk in enumerate(pending):
            if _cancel_event.is_set():
                logger.info("Translation cancelled for book %d", book_id)
                break

            try:
                translated = await pipeline.translate_chunk(chunk, glossary)
                if chunk.id is not None:
                    await d.update_chunk_result(chunk.id, translated, "done")
            except Exception as e:
                if chunk.id is not None:
                    await d.mark_chunk_failed(chunk.id, str(e))

        await d.update_book_status(book_id)
    except Exception as e:
        logger.error("Translation error: %s", e)
    finally:
        await pipeline.close()
        active_pipeline = None
        active_book_id = None


@app.post("/api/translate/cancel")
async def cancel_translate() -> dict:
    global active_pipeline
    _cancel_event.set()
    if active_pipeline:
        await active_pipeline.close()
        active_pipeline = None
    return {"status": "cancelled"}


@app.get("/api/translate/progress/{book_id}")
async def translate_progress(book_id: int):
    """SSE endpoint — push realtime progress updates."""

    async def event_generator() -> AsyncGenerator:
        d = _get_db()
        while True:
            if _cancel_event.is_set():
                yield {"event": "cancelled", "data": json.dumps({"book_id": book_id})}
                return

            cursor = await d.conn.execute(
                "SELECT total_chunks, done_chunks, failed_chunks, status FROM books WHERE id = ?",
                (book_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "Book not found"}),
                }
                return

            data = {
                "total": row["total_chunks"],
                "done": row["done_chunks"],
                "failed": row["failed_chunks"],
                "status": row["status"],
            }
            yield {"event": "progress", "data": json.dumps(data)}

            if row["status"] in ("done", "failed"):
                yield {"event": "complete", "data": json.dumps(data)}
                return

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


# ── Export ───────────────────────────────────────────────────────────────


@app.post("/api/export/{book_id}")
async def export_book(book_id: int) -> dict:
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    output = await export_epub(d, book_id, book.file_path)
    return {"path": output}


@app.get("/api/export/{book_id}/download")
async def download_export(book_id: int):
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    src = Path(book.file_path)
    output = str(src.parent / f"{src.stem}_vn{src.suffix}")
    if not Path(output).exists():
        raise HTTPException(
            status_code=404, detail="Export file not found, run export first"
        )
    return FileResponse(
        output, media_type="application/epub+zip", filename=Path(output).name
    )


# ── Info / Config ────────────────────────────────────────────────────────


@app.get("/api/categories")
async def list_categories() -> dict[str, str]:
    return {c.value: CATEGORY_INFO[c] for c in BookCategory}


@app.get("/api/prompt-preview/{category}")
async def prompt_preview(category: str) -> dict:
    try:
        cat = BookCategory(category)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid category: {category}"
        ) from e
    prompt = get_system_prompt(cat)
    return {"category": category, "prompt": prompt}


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    try:
        port = int(os.environ.get("ET_PORT", "8080"))
    except (ValueError, TypeError):
        port = 8080
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
