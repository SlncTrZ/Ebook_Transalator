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

import tempfile

from fastapi import FastAPI, HTTPException, UploadFile, File
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
from ebook_translator.agent.web_search import get_preview_text, extract_metadata

logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────────────

PARSERS = {".epub": EpubParser(), ".txt": TxtParser()}
DB_PATH = os.environ.get("ET_DB_PATH")
db: Database | None = None
active_pipeline: TranslationPipeline | None = None
active_book_id: int | None = None
_cancel_event = asyncio.Event()


# ── Request/Response models ──────────────────────────────────────────────


class ImportBookRequest(BaseModel):
    file_path: str


class TestConnectionRequest(BaseModel):
    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


class VendorConfigRequest(BaseModel):
    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


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
    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    user_feedback: str = ""
    force_search: bool = False


class StartTranslateRequest(BaseModel):
    file_path: str
    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"
    base_url: str = ""
    chapter_start: int = 0
    chapter_end: int = 99999
    agentic: bool = False


class ConfirmMetadataRequest(BaseModel):
    title: str = ""
    author: str = ""
    localized_title: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
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
    allow_origins=["*"],
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
async def create_book(req: ImportBookRequest) -> dict:
    d = _get_db()
    parser = _get_parser(req.file_path)
    try:
        parsed = parser.parse(req.file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    book = Book(
        file_path=req.file_path,
        title=parsed.title,
        author=parsed.author,
    )
    book_id = await d.insert_book(book)
    chunks = chunk_book(book_id, parsed.chapters)
    await d.insert_chunks(chunks)
    await d.conn.execute(
        "UPDATE books SET total_chunks = ? WHERE id = ?", (len(chunks), book_id)
    )
    await d.conn.commit()
    return {
        "id": book_id,
        "title": parsed.title,
        "chunks": len(chunks),
        "status": "pending",
    }


@app.post("/api/books/upload")
async def upload_book(file: UploadFile = File(...)) -> dict:
    """Upload file -> save tam -> parse -> import."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".epub", ".txt"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Only .epub and .txt allowed.",
        )

    # Save to temp
    temp_dir = Path(tempfile.gettempdir()) / "ebook_translator_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{int(__import__('time').time())}_{file.filename}"

    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    # Parse
    d = _get_db()
    parser = _get_parser(str(temp_path))
    try:
        parsed = parser.parse(str(temp_path))
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e)) from e

    title = parsed.title
    # Neu title la temp filename -> dung original filename
    if not title or "test_upload" in title or "tmp" in title:
        title = Path(file.filename).stem

    book = Book(
        file_path=str(temp_path),
        title=title,
        author=parsed.author,
    )
    book_id = await d.insert_book(book)
    chunks = chunk_book(book_id, parsed.chapters)
    await d.insert_chunks(chunks)
    await d.conn.execute(
        "UPDATE books SET total_chunks = ? WHERE id = ?", (len(chunks), book_id)
    )
    await d.conn.commit()

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


@app.delete("/api/books/{book_id}")
async def delete_book(book_id: int) -> dict:
    """Xoa sach khoi thu vien."""
    d = _get_db()
    await d.conn.execute("DELETE FROM glossary WHERE book_id = ?", (book_id,))
    await d.conn.execute("DELETE FROM chunks WHERE book_id = ?", (book_id,))
    await d.conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    await d.conn.commit()
    return {"ok": True}


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
    from ebook_translator.translator.adapters import VENDORS

    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    api_key = req.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key required")

    base_url = req.base_url
    if not base_url:
        v = VENDORS.get(req.vendor)
        if v:
            base_url = v.base_url

    model = req.model or (
        VENDORS.get(req.vendor).default_model
        if VENDORS.get(req.vendor)
        else "gpt-4o-mini"
    )

    try:
        preview = await get_preview_text(book.file_path)
        result = await extract_metadata(
            preview=preview,
            api_key=api_key,
            model=model,
            base_url=base_url,
            user_feedback=req.user_feedback,
            force_search=req.force_search,
        )
        return {
            "title": result.title or book.title,
            "author": result.author or book.author,
            "source_lang": result.source_lang,
            "target_lang": result.target_lang,
            "localized_title": result.localized_title,
            "category": result.category,
            "description": result.description,
            "confidence": result.confidence,
            "sources": result.sources,
            "from_knowledge": result.from_knowledge,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/books/{book_id}/research")
async def research_book(book_id: int, req: AnalyzeRequest) -> dict:
    """Research Agent: phân tích sách 1 lần, trả metadata + glossary. HITL tại đây."""
    from ebook_translator.agent.pipeline import AgentContext, research_agent
    from ebook_translator.translator.adapters import VENDORS

    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    api_key = req.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key required")

    base_url = req.base_url or (
        VENDORS.get(req.vendor).base_url if VENDORS.get(req.vendor) else ""
    )
    model = req.model or (
        VENDORS.get(req.vendor).default_model
        if VENDORS.get(req.vendor)
        else "gpt-4o-mini"
    )

    ctx = AgentContext(book_id=book_id, api_key=api_key, model=model, base_url=base_url)
    preview = await get_preview_text(book.file_path)
    ctx = await research_agent(preview, ctx)

    # Luu glossary suggestions vao DB ngay
    for term in ctx.glossary_terms:
        existing = await d.get_glossary(book_id)
        if not any(g.source_term == term["source"] for g in existing):
            await d.conn.execute(
                "INSERT INTO glossary (book_id, source_term, target_term, notes) VALUES (?, ?, ?, 'research_agent')",
                (book_id, term["source"], term["target"]),
            )
    await d.conn.commit()

    return {
        "title": ctx.title,
        "author": ctx.author,
        "source_lang": ctx.source_lang,
        "target_lang": ctx.target_lang,
        "category": ctx.category,
        "localized_title": ctx.localized_title or ctx.title,
        "description": ctx.book_summary,
        "style_notes": ctx.style_notes,
        "confidence": 0.9 if ctx.glossary_terms else 0.5,
        "sources": [r.get("url", "") for r in ctx.search_results]
        if ctx.search_results
        else [],
        "from_knowledge": not bool(ctx.search_results),
        "glossary_suggestions": ctx.glossary_terms,
    }


@app.post("/api/books/{book_id}/confirm-metadata")
async def confirm_metadata(book_id: int, req: ConfirmMetadataRequest) -> dict:
    """HITL: Lưu metadata user đã duyệt vào DB."""
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    await d.conn.execute(
        "UPDATE books SET title=?, author=?, source_lang=?, target_lang=?, category=? WHERE id=?",
        (
            req.title or book.title,
            req.author or book.author,
            req.source_lang,
            req.target_lang,
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

    if active_pipeline:
        _cancel_event.set()
        await asyncio.sleep(0.5)
    _cancel_event.clear()

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
        await d.conn.execute(
            "UPDATE books SET total_chunks = ? WHERE id = ?", (len(chunks), book_id)
        )
        await d.conn.commit()

    api_key = (
        req.api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("API_KEY", "")
    )
    active_book_id = book_id

    if not req.agentic:
        config = TranslationConfig(
            vendor=req.vendor,
            api_key=api_key,
            model=req.model or "gpt-4o-mini",
            base_url=req.base_url,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
        )
        # Cap nhat total_chunks truoc khi chay background task
        is_range = req.chapter_end < 99999 or req.chapter_start > 0
        if is_range:
            cursor = await d.conn.execute(
                "SELECT COUNT(*) as cnt FROM chunks WHERE book_id = ? AND status = 'pending'",
                (book_id,),
            )
            row = await cursor.fetchone()
            all_total = row["cnt"] if row else 0
            # Uoc luong so chunk trong range (ty le theo chapter)
            cursor2 = await d.conn.execute(
                "SELECT COUNT(*) as cnt, MAX(chapter_idx) as max_ch FROM chunks WHERE book_id = ?",
                (book_id,),
            )
            row2 = await cursor2.fetchone()
            if row2 and row2["max_ch"] > 0:
                ratio = (req.chapter_end - req.chapter_start + 1) / (row2["max_ch"] + 1)
                est = max(1, int(all_total * ratio))
                await d.conn.execute(
                    "UPDATE books SET total_chunks = ? WHERE id = ?", (est, book_id)
                )
                await d.conn.commit()

        active_pipeline = TranslationPipeline(d, config)
        asyncio.create_task(
            _run_translation(book_id, req.chapter_start, req.chapter_end)
        )
        return {"book_id": book_id, "status": "started"}


async def _run_translation(
    book_id: int, chapter_start: int = 0, chapter_end: int = 99999
) -> None:
    global active_pipeline, active_book_id
    d = _get_db()
    pipeline = active_pipeline
    if pipeline is None:
        return

    try:
        glossary = await d.get_glossary(book_id)
        pending = await d.get_pending_chunks(book_id)
        if chapter_end < 99999 or chapter_start > 0:
            pending = [
                c for c in pending if chapter_start <= c.chapter_idx + 1 <= chapter_end
            ]
        total = len(pending)
        if total > 0:
            await d.conn.execute(
                "UPDATE books SET total_chunks = ? WHERE id = ?", (total, book_id)
            )
            await d.conn.commit()

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


@app.post("/api/translate/agentic")
async def translate_agentic(req: StartTranslateRequest) -> dict:
    """Translate Agent + Deterministic Validation."""
    from ebook_translator.agent.pipeline import (
        AgentContext,
    )

    global active_pipeline, active_book_id, _cancel_event
    d = _get_db()

    if active_pipeline:
        _cancel_event.set()
    await asyncio.sleep(0.5)
    _cancel_event.clear()

    api_key = (
        req.api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("API_KEY", "")
    )
    cursor = await d.conn.execute(
        "SELECT id FROM books WHERE file_path = ?", (req.file_path,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Book not found, import first")
    book_id = row["id"]
    active_book_id = book_id

    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404)

    ctx = AgentContext(
        book_id=book_id,
        api_key=api_key,
        model=req.model or "gpt-4o-mini",
        source_lang=book.source_lang,
        target_lang=book.target_lang,
        category=book.category,
        base_url=req.base_url,
        title=book.title,
        author=book.author,
    )

    asyncio.create_task(
        _run_agentic_translate(d, book_id, ctx, req.chapter_start, req.chapter_end)
    )
    return {"book_id": book_id, "status": "agentic_started"}


async def _run_agentic_translate(
    d: Database,
    book_id: int,
    ctx: AgentContext,
    chapter_start: int,
    chapter_end: int,
) -> None:
    """Background task: Translate Agent + Validation."""
    from ebook_translator.agent.pipeline import translate_agent_with_validation

    try:
        glossary = await d.get_glossary(book_id)
        pending = await d.get_pending_chunks(book_id)
        if chapter_end < 99999 or chapter_start > 0:
            pending = [
                c for c in pending if chapter_start <= c.chapter_idx + 1 <= chapter_end
            ]
        ctx.total_chunks = len(pending)

        for chunk in pending:
            if _cancel_event.is_set():
                break
            try:
                translated = await translate_agent_with_validation(
                    chunk, glossary, ctx, d
                )
                if chunk.id is not None:
                    await d.update_chunk_result(chunk.id, translated, "done")
                ctx.done_chunks += 1
            except Exception as e:
                if chunk.id is not None:
                    await d.mark_chunk_failed(chunk.id, str(e))
                ctx.failed_chunks += 1

        await d.update_book_status(book_id)
    except Exception as e:
        logger.exception("Agentic translate failed: %s", e)
    finally:
        global active_pipeline
        active_pipeline = None


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


@app.get("/api/vendors")
@app.get("/api/vendors")
async def list_vendors() -> list[dict]:
    """Danh sach vendor AI ho tro."""
    from ebook_translator.translator.adapters import VENDORS

    return [
        {
            "id": v.id,
            "name": v.name,
            "base_url": v.base_url,
            "default_model": v.default_model,
            "models": v.models,
            "requires_api_key": v.requires_api_key,
            "docs_url": v.docs_url,
        }
        for v in VENDORS.values()
    ]


@app.post("/api/vendors/{vendor_id}/models")
async def get_vendor_models(vendor_id: str, req: TestConnectionRequest) -> list[str]:
    """Fetch danh sach model that tu vendor API."""
    from ebook_translator.translator.adapters import fetch_vendor_models

    try:
        models = await fetch_vendor_models(
            vendor_id=vendor_id,
            api_key=req.api_key,
            base_url=req.base_url or None,
        )
        return models
    except Exception:
        return []


@app.post("/api/test-connection")
async def test_connection(req: TestConnectionRequest) -> dict:
    """Test API connection voi vendor dang chon."""
    from ebook_translator.translator.adapters import create_adapter

    adapter = create_adapter(
        vendor_id=req.vendor,
        api_key=req.api_key,
        model=req.model or "gpt-4o-mini",
        base_url=req.base_url or "",
    )

    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Reply with exactly: OK"},
    ]

    try:
        import asyncio

        result = await asyncio.wait_for(adapter.translate(test_messages), timeout=15)
        return {"status": "ok", "reply": result[:100]}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}


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
