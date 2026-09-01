"""FastAPI server — REST API cho Tauri frontend, SSE progress.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import asyncio
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

from ebook_translator.db.database import Database
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
active_job_id: int | None = None
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
    localized_title: str | None = None
    category: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None


class UpdateChunkRequest(BaseModel):
    translated_text: str


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


class ResumeJobRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""


class ConfirmMetadataRequest(BaseModel):
    title: str = ""
    author: str = ""
    localized_title: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"


class ExportBookRequest(BaseModel):
    output_path: str = ""
    mode: str = "translated"
    format: str = "txt"
    chapter_start: int = 1
    chapter_end: int = 99999


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
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
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

    # Save to temp without trusting the client filename or buffering the whole file.
    temp_dir = Path(tempfile.gettempdir()) / "ebook_translator_uploads"
    safe_name = Path(file.filename).name
    max_upload_bytes = 200 * 1024 * 1024
    written = 0
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{int(__import__('time').time())}_{safe_name}"
        with open(temp_path, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_upload_bytes:
                    destination.close()
                    temp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Upload exceeds 200 MiB limit")
                destination.write(chunk)
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save upload: {e}"
        ) from e

    # Parse
    d = _get_db()
    parser = _get_parser(str(temp_path))
    try:
        parsed = parser.parse(str(temp_path))
    except Exception as e:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
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
    for field in ("title", "author", "localized_title", "source_lang", "target_lang"):
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
    v = VENDORS.get(req.vendor)
    if not api_key and (v is None or v.requires_api_key):
        raise HTTPException(status_code=400, detail="API key required")

    base_url = req.base_url
    if not base_url and v:
        base_url = v.base_url

    model = req.model or (v.default_model if v else "gpt-4o-mini")

    try:
        preview = await get_preview_text(book.file_path)
        result = await extract_metadata(
            preview=preview,
            api_key=api_key,
            model=model,
            base_url=base_url,
            vendor=req.vendor,
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
    v = VENDORS.get(req.vendor)
    if not api_key and (v is None or v.requires_api_key):
        raise HTTPException(status_code=400, detail="API key required")

    base_url = req.base_url or (v.base_url if v else "")
    model = req.model or (v.default_model if v else "gpt-4o-mini")

    ctx = AgentContext(
        book_id=book_id,
        vendor=req.vendor,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    preview = await get_preview_text(book.file_path)
    ctx = await research_agent(
        preview,
        ctx,
        user_feedback=req.user_feedback,
        force_search=req.force_search,
    )

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
        "UPDATE books SET title=?, author=?, localized_title=?, source_lang=?, target_lang=?, category=? WHERE id=?",
        (
            req.title or book.title,
            req.author or book.author,
            req.localized_title or book.localized_title,
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


@app.patch("/api/chunks/{chunk_id}")
async def update_chunk_translation(chunk_id: int, req: UpdateChunkRequest) -> dict:
    """Persist a user-approved translation. Done chunks are not auto-retranslated."""
    d = _get_db()
    cursor = await d.conn.execute(
        "SELECT book_id FROM chunks WHERE id = ?", (chunk_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    await d.conn.execute(
        "UPDATE chunks SET translated_text = ?, status = 'done', error_log = NULL WHERE id = ?",
        (req.translated_text, chunk_id),
    )
    await d.conn.commit()
    await d.update_book_status(row["book_id"])
    return {"ok": True, "chunk_id": chunk_id}


@app.post("/api/chunks/{chunk_id}/translation-memory")
async def remember_chunk_translation(chunk_id: int, req: UpdateChunkRequest) -> dict:
    """Explicitly promote a translation into reusable cross-book memory."""
    d = _get_db()
    cursor = await d.conn.execute(
        "SELECT c.content_hash, c.original_text, b.source_lang, b.target_lang "
        "FROM chunks c JOIN books b ON b.id = c.book_id WHERE c.id = ?",
        (chunk_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    if not req.translated_text.strip():
        raise HTTPException(status_code=400, detail="Translation memory entry cannot be empty")
    await d.set_translation_memory(
        row["content_hash"],
        row["original_text"],
        row["source_lang"],
        row["target_lang"],
        req.translated_text,
        origin="manual",
    )
    return {"ok": True, "chunk_id": chunk_id, "stored": "translation_memory"}


@app.post("/api/chunks/{chunk_id}/requeue")
async def requeue_chunk(chunk_id: int) -> dict:
    """Mark one chunk retryable without touching its source text."""
    d = _get_db()
    cursor = await d.conn.execute(
        "SELECT book_id FROM chunks WHERE id = ?", (chunk_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    await d.conn.execute(
        "UPDATE chunks SET status = 'pending', error_log = NULL WHERE id = ?",
        (chunk_id,),
    )
    await d.conn.commit()
    await d.update_book_status(row["book_id"])
    return {"ok": True, "chunk_id": chunk_id, "status": "pending"}


@app.get("/api/books/{book_id}/qa")
async def book_qa(
    book_id: int,
    chapter_start: int = 1,
    chapter_end: int = 99999,
) -> dict:
    """Run deterministic QA over translated chunks in the requested scope."""
    from ebook_translator.translator.qa import check_translation

    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    glossary = await d.get_glossary(book_id)
    sql = (
        "SELECT id, chapter_idx, paragraph_idx, original_text, translated_text, status "
        "FROM chunks WHERE book_id = ? AND translated_text IS NOT NULL"
    )
    params: list[int] = [book_id]
    if chapter_end < 99999 or chapter_start > 1:
        sql += " AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ?"
        params.extend([chapter_start, chapter_end])
    sql += " ORDER BY chapter_idx, paragraph_idx"
    cursor = await d.conn.execute(sql, params)
    rows = await cursor.fetchall()

    chunk_results: list[dict] = []
    issue_count = 0
    error_count = 0
    warning_count = 0
    for row in rows:
        result = check_translation(
            row["original_text"], row["translated_text"] or "", glossary
        )
        issues = [issue.__dict__ for issue in result.issues]
        if not issues:
            continue
        issue_count += len(issues)
        error_count += sum(issue["severity"] == "error" for issue in issues)
        warning_count += sum(issue["severity"] == "warning" for issue in issues)
        chunk_results.append(
            {
                "chunk_id": row["id"],
                "chapter_idx": row["chapter_idx"],
                "paragraph_idx": row["paragraph_idx"],
                "passed": result.passed,
                "issues": issues,
            }
        )

    return {
        "book_id": book_id,
        "checked_chunks": len(rows),
        "issue_chunks": len(chunk_results),
        "issues": issue_count,
        "errors": error_count,
        "warnings": warning_count,
        "chunks": chunk_results,
    }


@app.get("/api/books/{book_id}/reader")
async def reader_chunks(
    book_id: int,
    chapter_start: int = 1,
    chapter_end: int = 99999,
    status_filter: str = "all",
) -> dict:
    """Reader endpoint: tra ve chunks voi original + translated text."""
    d = _get_db()
    sql = (
        "SELECT id, chapter_idx, paragraph_idx, original_text, translated_text, status "
        "FROM chunks WHERE book_id = ?"
    )
    params: list = [book_id]
    if chapter_end < 99999 or chapter_start > 1:
        sql += " AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ?"
        params.extend([chapter_start, chapter_end])
    if status_filter != "all":
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY chapter_idx, paragraph_idx"
    cursor = await d.conn.execute(sql, params)
    rows = await cursor.fetchall()
    chunks = [dict(r) for r in rows]
    return {
        "total": len(chunks),
        "chapters": sorted({r["chapter_idx"] for r in chunks}),
        "chunks": chunks,
    }


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
    global active_pipeline, active_book_id, active_job_id, _cancel_event
    d = _get_db()

    if active_job_id is not None:
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

    if req.agentic:
        raise HTTPException(
            status_code=400,
            detail="Agentic translation must use /api/translate/agentic",
        )

    config = TranslationConfig(
        vendor=req.vendor,
        api_key=api_key,
        model=req.model or "gpt-4o-mini",
        base_url=req.base_url,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
    )

    active_pipeline = TranslationPipeline(d, config)
    active_job_id = await d.create_translation_job(
        book_id,
        "standard",
        req.vendor,
        config.model,
        req.chapter_start,
        req.chapter_end,
    )
    asyncio.create_task(
        _run_translation(book_id, active_job_id, req.chapter_start, req.chapter_end)
    )
    return {
        "book_id": book_id,
        "job_id": active_job_id,
        "status": "started",
        "mode": "standard",
    }


async def _run_translation(
    book_id: int,
    job_id: int | None = None,
    chapter_start: int = 0,
    chapter_end: int = 99999,
) -> None:
    global active_pipeline, active_book_id, active_job_id
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
        for _, chunk in enumerate(pending):
            if _cancel_event.is_set():
                logger.info("Translation cancelled for book %d", book_id)
                break

            attempt_id: int | None = None
            try:
                if job_id is not None and chunk.id is not None:
                    attempt_id = await d.start_job_chunk_attempt(job_id, chunk.id)
                translated = await pipeline.translate_chunk(chunk, glossary)
                if chunk.id is not None:
                    await d.update_chunk_result(chunk.id, translated, "done")
                if attempt_id is not None:
                    await d.finish_job_chunk_attempt(attempt_id, "done")
            except Exception as e:
                if chunk.id is not None:
                    await d.mark_chunk_failed(chunk.id, str(e))
                if attempt_id is not None:
                    await d.finish_job_chunk_attempt(attempt_id, "failed", str(e)[:500])

        await d.update_book_status(book_id)
        if job_id is not None:
            if _cancel_event.is_set():
                await d.finish_translation_job(job_id, "cancelled")
            else:
                scoped = await d.get_chunk_progress(book_id, chapter_start, chapter_end)
                await d.finish_translation_job(job_id, str(scoped["status"]))
    except Exception as e:
        logger.error("Translation error: %s", e)
        if job_id is not None:
            await d.finish_translation_job(job_id, "failed", str(e)[:500])
    finally:
        await pipeline.close()
        active_pipeline = None
        active_book_id = None
        active_job_id = None


@app.post("/api/translate/cancel")
async def cancel_translate() -> dict:
    global active_pipeline, active_job_id
    _cancel_event.set()
    if active_pipeline:
        await active_pipeline.close()
        active_pipeline = None
    if active_job_id is not None:
        await _get_db().finish_translation_job(active_job_id, "cancelled")
        active_job_id = None
    return {"status": "cancelled"}


@app.post("/api/translate/agentic")
async def translate_agentic(req: StartTranslateRequest) -> dict:
    """Translate Agent + Deterministic Validation."""
    from ebook_translator.agent.pipeline import (
        AgentContext,
    )

    global active_pipeline, active_book_id, active_job_id, _cancel_event
    d = _get_db()

    if active_job_id is not None:
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

    from ebook_translator.translator.adapters import VENDORS

    vendor_info = VENDORS.get(req.vendor)
    ctx = AgentContext(
        book_id=book_id,
        vendor=req.vendor,
        api_key=api_key,
        model=req.model or (vendor_info.default_model if vendor_info else "gpt-4o-mini"),
        source_lang=book.source_lang,
        target_lang=book.target_lang,
        category=book.category,
        base_url=req.base_url or (vendor_info.base_url if vendor_info else ""),
        title=book.title,
        author=book.author,
    )

    active_job_id = await d.create_translation_job(
        book_id,
        "agentic",
        req.vendor,
        ctx.model,
        req.chapter_start,
        req.chapter_end,
    )
    asyncio.create_task(
        _run_agentic_translate(
            d,
            book_id,
            ctx,
            req.chapter_start,
            req.chapter_end,
            active_job_id,
        )
    )
    return {
        "book_id": book_id,
        "job_id": active_job_id,
        "status": "started",
        "mode": "agentic",
    }


async def _run_agentic_translate(
    d: Database,
    book_id: int,
    ctx: AgentContext,
    chapter_start: int,
    chapter_end: int,
    job_id: int | None = None,
) -> None:
    """Background task: Translate Agent + Validation."""
    from ebook_translator.agent.pipeline import translate_agent_with_validation  # noqa: F811

    try:
        glossary = await d.get_glossary(book_id)
        pending = await d.get_pending_chunks(book_id)
        if chapter_end < 99999 or chapter_start > 0:
            pending = [
                c for c in pending if chapter_start <= c.chapter_idx + 1 <= chapter_end
            ]
        for chunk in pending:
            if _cancel_event.is_set():
                break
            attempt_id: int | None = None
            try:
                if job_id is not None and chunk.id is not None:
                    attempt_id = await d.start_job_chunk_attempt(job_id, chunk.id)
                translated = await translate_agent_with_validation(
                    chunk, glossary, ctx, d
                )
                if chunk.id is not None:
                    await d.update_chunk_result(chunk.id, translated, "done")
                if attempt_id is not None:
                    await d.finish_job_chunk_attempt(attempt_id, "done")
            except Exception as e:
                if chunk.id is not None:
                    await d.mark_chunk_failed(chunk.id, str(e))
                if attempt_id is not None:
                    await d.finish_job_chunk_attempt(attempt_id, "failed", str(e)[:500])

        await d.update_book_status(book_id)
        if job_id is not None:
            if _cancel_event.is_set():
                await d.finish_translation_job(job_id, "cancelled")
            else:
                scoped = await d.get_chunk_progress(book_id, chapter_start, chapter_end)
                await d.finish_translation_job(job_id, str(scoped["status"]))
    except Exception as e:
        logger.exception("Agentic translate failed: %s", e)
        if job_id is not None:
            await d.finish_translation_job(job_id, "failed", str(e)[:500])
    finally:
        global active_pipeline, active_job_id
        active_pipeline = None
        active_job_id = None


@app.get("/api/translate/status/{book_id}")
async def translate_status(
    book_id: int,
    chapter_start: int = 0,
    chapter_end: int = 99999,
) -> dict:
    """Polling endpoint backed by canonical chunk state for the requested scope."""
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        return {
            "total": 0,
            "done": 0,
            "failed": 0,
            "status": "not_found",
        }

    progress = await d.get_chunk_progress(book_id, chapter_start, chapter_end)
    return {
        "total": progress["total"],
        "done": progress["done"],
        "failed": progress["failed"],
        "status": progress["status"],
    }


# ── Export ───────────────────────────────────────────────────────────────


@app.post("/api/export/{book_id}")
async def export_book(book_id: int, req: ExportBookRequest) -> dict:
    """Export với nhiều chế độ: mode (translated|bilingual), format (txt|epub), chapter range."""
    from ebook_translator.export.export_engine import export_book as do_export

    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    safe_title = "".join(
        c if c.isalnum() or c in " -_" else "_" for c in (book.title or "untitled")
    )
    safe_author = "".join(
        c if c.isalnum() or c in " -_" else "_" for c in (book.author or "unknown")
    )
    output_path = req.output_path or f"{safe_title} - {safe_author}.{req.format}"

    try:
        result = await do_export(
            d,
            book_id,
            output_path,
            req.mode,
            req.format,
            req.chapter_start,
            req.chapter_end,
        )
        return {"path": result, "mode": req.mode, "format": req.format}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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


@app.get("/api/jobs/{book_id}/latest")
async def latest_translation_job(book_id: int) -> dict:
    job = await _get_db().get_latest_job(book_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No translation job found")
    return job


@app.get("/api/jobs/{job_id}/resume-plan")
async def job_resume_plan(job_id: int) -> dict:
    try:
        plan = await _get_db().get_job_resume_plan(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {
        "job": plan["job"],
        "progress": plan["progress"],
        "remaining_chunk_ids": [chunk.id for chunk in plan["remaining_chunks"]],
    }


@app.post("/api/jobs/{job_id}/resume")
async def resume_translation_job(job_id: int, req: ResumeJobRequest) -> dict:
    global active_pipeline, active_book_id, active_job_id, _cancel_event

    if active_job_id is not None:
        raise HTTPException(status_code=409, detail="Another translation job is active")

    d = _get_db()
    try:
        plan = await d.get_job_resume_plan(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    job = plan["job"]
    book = await d.get_book(job["book_id"])
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    from ebook_translator.translator.adapters import VENDORS

    vendor_info = VENDORS.get(job["vendor"])
    api_key = (
        req.api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("API_KEY", "")
    )
    if not api_key and (vendor_info is None or vendor_info.requires_api_key):
        raise HTTPException(
            status_code=400,
            detail="API key required to resume this provider; credentials are not persisted",
        )

    base_url = req.base_url or (vendor_info.base_url if vendor_info else "")
    _cancel_event.clear()
    active_book_id = book.id
    active_job_id = job_id

    await d.resume_translation_job(job_id)

    if job["mode"] == "standard":
        config = TranslationConfig(
            vendor=job["vendor"],
            api_key=api_key,
            model=job["model"],
            base_url=base_url,
            source_lang=book.source_lang,
            target_lang=book.target_lang,
            category=book.category,
        )
        active_pipeline = TranslationPipeline(d, config)
        asyncio.create_task(
            _run_translation(
                book.id,
                job_id,
                job["chapter_start"],
                job["chapter_end"],
            )
        )
    elif job["mode"] == "agentic":
        from ebook_translator.agent.pipeline import AgentContext

        ctx = AgentContext(
            book_id=book.id,
            vendor=job["vendor"],
            api_key=api_key,
            model=job["model"],
            source_lang=book.source_lang,
            target_lang=book.target_lang,
            category=book.category,
            base_url=base_url,
            title=book.title,
            author=book.author,
        )
        active_pipeline = None
        asyncio.create_task(
            _run_agentic_translate(
                d,
                book.id,
                ctx,
                job["chapter_start"],
                job["chapter_end"],
                job_id,
            )
        )
    else:
        active_job_id = None
        active_book_id = None
        raise HTTPException(status_code=409, detail=f"Unsupported job mode: {job['mode']}")

    return {
        "job_id": job_id,
        "book_id": book.id,
        "status": "running",
        "mode": job["mode"],
        "remaining": len(plan["remaining_chunks"]),
    }


@app.get("/api/jobs/{job_id}/diagnostics")
async def job_diagnostics(job_id: int) -> dict:
    try:
        return await _get_db().get_job_diagnostics(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/diagnostics")
async def diagnostics() -> dict:
    """Local operational counters for diagnosis; no external telemetry."""
    from ebook_translator.translator.metrics import snapshot

    return {
        "database": await _get_db().get_diagnostics(),
        "runtime": snapshot(),
    }


# ── Info / Config ────────────────────────────────────────────────────────


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
