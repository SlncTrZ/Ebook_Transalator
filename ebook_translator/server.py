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
    """Model dữ liệu yêu cầu nhập sách từ đường dẫn đĩa cục bộ.

    Attributes:
        file_path: Đường dẫn tới file sách cần nhập (.epub, .txt).
    """

    file_path: str


class TestConnectionRequest(BaseModel):
    """Model dữ liệu yêu cầu kiểm tra kết nối API vendor AI hoặc lấy danh sách model.

    Attributes:
        vendor: Tên vendor AI (mặc định "openai").
        api_key: Khóa API kết nối.
        model: Tên mô hình AI.
        base_url: Đường dẫn URL tùy chỉnh của API endpoint.
    """

    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


class VendorConfigRequest(BaseModel):
    """Model dữ liệu cấu hình thông tin nhà cung cấp API AI.

    Attributes:
        vendor: Tên nhà cung cấp AI.
        api_key: Khóa API kết nối.
        model: Tên mô hình mặc định.
        base_url: Đường dẫn API endpoint tùy chỉnh.
    """

    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


class CreateGlossaryRequest(BaseModel):
    """Model dữ liệu yêu cầu tạo mới mục thuật ngữ trong glossary.

    Attributes:
        book_id: ID cuốn sách liên quan.
        source_term: Thuật ngữ ngôn ngữ gốc.
        target_term: Thuật ngữ dịch sang ngôn ngữ đích.
        notes: Ghi chú bổ sung (tùy chọn).
    """

    book_id: int
    source_term: str
    target_term: str
    notes: str = ""


class UpdateBookRequest(BaseModel):
    """Model dữ liệu yêu cầu cập nhật thông tin metadata cuốn sách.

    Attributes:
        title: Tiêu đề gốc của sách.
        author: Tác giả sách.
        localized_title: Tiêu đề dịch/bản địa hóa.
        category: Thể loại sách.
        source_lang: Mã ngôn ngữ gốc.
        target_lang: Mã ngôn ngữ đích.
    """

    title: str | None = None
    author: str | None = None
    localized_title: str | None = None
    category: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None


class UpdateChunkRequest(BaseModel):
    """Model dữ liệu yêu cầu cập nhật văn bản dịch của một chunk.

    Attributes:
        translated_text: Đoạn văn bản dịch mới.
    """

    translated_text: str


class AnalyzeRequest(BaseModel):
    """Model dữ liệu yêu cầu phân tích sách hoặc nghiên cứu thông tin qua Agent.

    Attributes:
        vendor: Tên nhà cung cấp AI.
        api_key: Khóa API kết nối.
        model: Tên mô hình AI sử dụng.
        base_url: URL API tùy chỉnh.
        user_feedback: Ý kiến/gợi ý bổ sung từ người dùng.
        force_search: Bắt buộc tìm kiếm web lại hay không.
    """

    vendor: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    user_feedback: str = ""
    force_search: bool = False


class StartTranslateRequest(BaseModel):
    """Model dữ liệu yêu cầu bắt đầu tiến trình dịch sách.

    Attributes:
        file_path: Đường dẫn file sách.
        vendor: Tên nhà cung cấp AI.
        api_key: Khóa API kết nối.
        model: Tên mô hình AI.
        source_lang: Ngôn ngữ gốc.
        target_lang: Ngôn ngữ đích.
        category: Thể loại sách.
        base_url: URL API tùy chỉnh.
        chapter_start: Chỉ số chương bắt đầu.
        chapter_end: Chỉ số chương kết thúc.
        agentic: Cờ bật chế độ dịch Agentic.
    """

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
    """Model dữ liệu yêu cầu tiếp tục công việc dịch bị tạm dừng.

    Attributes:
        api_key: Khóa API kết nối vendor.
        base_url: URL API tùy chỉnh của vendor.
    """

    api_key: str = ""
    base_url: str = ""


class ConfirmMetadataRequest(BaseModel):
    """Model dữ liệu xác nhận metadata sách do người dùng xem duyệt.

    Attributes:
        title: Tiêu đề sách.
        author: Tác giả sách.
        localized_title: Tiêu đề bản dịch.
        source_lang: Ngôn ngữ gốc.
        target_lang: Ngôn ngữ dịch.
        category: Thể loại sách.
    """

    title: str = ""
    author: str = ""
    localized_title: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"


class ExportBookRequest(BaseModel):
    """Model dữ liệu yêu cầu xuất bản dịch sách ra tập tin.

    Attributes:
        output_path: Đường dẫn file xuất (tùy chọn).
        mode: Chế độ xuất ("translated" hoặc "bilingual").
        format: Định dạng xuất ("txt" hoặc "epub").
        chapter_start: Chương bắt đầu xuất.
        chapter_end: Chương kết thúc xuất.
    """

    output_path: str = ""
    mode: str = "translated"
    format: str = "txt"
    chapter_start: int = 1
    chapter_end: int = 99999


# ── Lifespan ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Quản lý vòng đời ứng dụng FastAPI: khởi tạo kết nối Database khi khởi động và đóng kết nối khi dừng.

    Args:
        app: Đối tượng ứng dụng FastAPI.

    Yields:
        AsyncGenerator: Generator bất đồng bộ cho lifespan context.

    Side-effects:
        Khởi tạo đối tượng Database toàn cục và thực hiện kết nối/đóng DB.
    """
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
    """Lấy danh sách tất cả các cuốn sách có trong cơ sở dữ liệu.

    Returns:
        list[dict]: Danh sách từ điển chứa thông tin các cuốn sách, sắp xếp theo ID giảm dần.

    Side-effects:
        Truy vấn bảng `books` trong cơ sở dữ liệu SQLite.
    """
    d = _get_db()
    cursor = await d.conn.execute("SELECT * FROM books ORDER BY id DESC")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/books")
async def create_book(req: ImportBookRequest) -> dict:
    """Nhập sách mới từ đường dẫn file, phân tích các chương và lưu thông tin sách kèm các chunk vào cơ sở dữ liệu.

    Args:
        req: Chứa đường dẫn file sách cần nhập (`file_path`).

    Returns:
        dict: Thông tin cuốn sách mới được tạo bao gồm id, title, số lượng chunks và trạng thái ("pending").

    Side-effects:
        Đọc và phân tích file sách, ghi thông tin sách và các chunk vào DB; ném HTTPException (400) nếu lỗi định dạng hoặc parse.
    """
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
    """Tải lên file sách (.epub hoặc .txt), lưu tạm thời trên đĩa, phân tích nội dung và khởi tạo sách trong cơ sở dữ liệu.

    Args:
        file: Tập tin sách tải lên từ yêu cầu của client.

    Returns:
        dict: Thông tin cuốn sách vừa tạo gồm id, title, số lượng chunks và trạng thái "pending".

    Side-effects:
        Ghi file tải lên vào thư mục tạm trên đĩa, đọc parse file, ghi bản ghi vào bảng `books` và `chunks` trong DB; ném HTTPException (400, 413, 500) khi gặp lỗi.
    """
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
    """Lấy thông tin chi tiết của một cuốn sách theo ID.

    Args:
        book_id: ID của cuốn sách cần tra cứu.

    Returns:
        dict: Các thuộc tính thông tin của cuốn sách.

    Side-effects:
        Truy vấn DB bảng `books`; ném HTTPException (404) nếu không tìm thấy sách.
    """
    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return {k: v for k, v in book.__dict__.items() if not k.startswith("_")}


@app.delete("/api/books/{book_id}")
async def delete_book(book_id: int) -> dict:
    """Xóa cuốn sách và toàn bộ dữ liệu liên quan (glossary, chunks) khỏi cơ sở dữ liệu.

    Args:
        book_id: ID cuốn sách cần xóa.

    Returns:
        dict: Kết quả thao tác `{"ok": True}`.

    Side-effects:
        Xóa dữ liệu tương ứng trong các bảng `glossary`, `chunks`, `books` và commit DB.
    """
    d = _get_db()
    await d.conn.execute("DELETE FROM glossary WHERE book_id = ?", (book_id,))
    await d.conn.execute("DELETE FROM chunks WHERE book_id = ?", (book_id,))
    await d.conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    await d.conn.commit()
    return {"ok": True}


@app.patch("/api/books/{book_id}")
async def update_book(book_id: int, req: UpdateBookRequest) -> dict:
    """Cập nhật các trường thông tin metadata của cuốn sách trong cơ sở dữ liệu.

    Args:
        book_id: ID của cuốn sách cần cập nhật.
        req: Dữ liệu chứa các trường thông tin cập nhật (title, author, localized_title, category, source_lang, target_lang).

    Returns:
        dict: Kết quả thao tác `{"ok": True}`.

    Side-effects:
        Cập nhật bản ghi trong bảng `books` và commit DB.
    """
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
    """Sử dụng Web Search Agent để phân tích văn bản xem trước của sách và trích xuất/đề xuất metadata bản địa hóa.

    Args:
        book_id: ID cuốn sách cần phân tích.
        req: Cấu hình kết nối API AI (vendor, api_key, model, base_url, user_feedback, force_search).

    Returns:
        dict: Metadata phân tích được (tiêu đề gốc/dịch, tác giả, ngôn ngữ, thể loại, mô tả, độ tin cậy, nguồn tham khảo).

    Side-effects:
        Đọc file sách lấy văn bản xem trước, thực hiện tìm kiếm web và gọi API LLM; ném HTTPException (400, 404, 500) nếu lỗi.
    """
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
    if not req.model:
        raise HTTPException(status_code=400, detail="Select a model fetched from the provider")
    model = req.model

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
    """Sử dụng Research Agent phân tích sách, trích xuất metadata và tự động lưu các gợi ý thuật ngữ vào glossary DB.

    Args:
        book_id: ID cuốn sách cần nghiên cứu.
        req: Cấu hình kết nối API AI và phản hồi của người dùng.

    Returns:
        dict: Kết quả phân tích chi tiết gồm thông tin sách, ghi chú phong cách và danh sách gợi ý thuật ngữ (glossary_suggestions).

    Side-effects:
        Gửi yêu cầu tới Research Agent, chèn các thuật ngữ gợi ý mới vào bảng `glossary` trong DB; ném HTTPException khi lỗi.
    """
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
    if not req.model:
        raise HTTPException(status_code=400, detail="Select a model fetched from the provider")
    model = req.model

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
    """Lưu thông tin metadata cuốn sách do người dùng xác nhận vào cơ sở dữ liệu sau bước HITL.

    Args:
        book_id: ID cuốn sách.
        req: Thông tin metadata đã được người dùng chỉnh sửa/xác nhận.

    Returns:
        dict: Kết quả thao tác `{"ok": True}`.

    Side-effects:
        Cập nhật bản ghi bảng `books` trong DB; ném HTTPException (404) nếu không tìm thấy sách.
    """
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
    """Lấy danh sách các chunk của một cuốn sách, hỗ trợ lọc theo trạng thái dịch.

    Args:
        book_id: ID cuốn sách.
        status: Trạng thái chunk cần lọc (tùy chọn, ví dụ: 'pending', 'done', 'failed').

    Returns:
        list[dict]: Danh sách thông tin cơ bản của các chunk sắp xếp theo chỉ số chương, đoạn và phân đoạn.

    Side-effects:
        Truy vấn dữ liệu từ bảng `chunks` trong DB.
    """
    d = _get_db()
    sql = "SELECT id, chapter_idx, paragraph_idx, segment_idx, status, token_count, error_log FROM chunks WHERE book_id = ?"
    params: list = [book_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY chapter_idx, paragraph_idx, segment_idx"
    cursor = await d.conn.execute(sql, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@app.patch("/api/chunks/{chunk_id}")
async def update_chunk_translation(chunk_id: int, req: UpdateChunkRequest) -> dict:
    """Lưu văn bản dịch do người dùng chỉnh sửa cho một chunk và đánh dấu trạng thái chunk là 'done'.

    Args:
        chunk_id: ID của chunk cần cập nhật.
        req: Chứa nội dung văn bản dịch mới (`translated_text`).

    Returns:
        dict: Kết quả thao tác `{"ok": True, "chunk_id": chunk_id}`.

    Side-effects:
        Cập nhật bảng `chunks` trong DB và tính toán lại trạng thái tiến độ chung của sách; ném HTTPException (404) nếu không tìm thấy chunk.
    """
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
    """Lưu bản dịch của chunk vào bộ nhớ dịch (Translation Memory) để tái sử dụng giữa các cuốn sách.

    Args:
        chunk_id: ID của chunk dịch.
        req: Chứa nội dung dịch cần ghi nhớ (`translated_text`).

    Returns:
        dict: Kết quả thao tác `{"ok": True, "chunk_id": chunk_id, "stored": "translation_memory"}`.

    Side-effects:
        Truy vấn DB lấy hash nội dung và văn bản gốc, lưu vào bộ nhớ dịch của Database; ném HTTPException (400, 404) nếu sai dữ liệu.
    """
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
    """Đặt lại trạng thái của chunk thành 'pending' để sẵn sàng dịch lại mà không làm thay đổi văn bản gốc.

    Args:
        chunk_id: ID của chunk cần đưa lại vào hàng đợi dịch.

    Returns:
        dict: Thông tin phản hồi `{"ok": True, "chunk_id": chunk_id, "status": "pending"}`.

    Side-effects:
        Cập nhật bảng `chunks` (đặt `status='pending'`, xóa `error_log`), tính toán lại trạng thái tiến độ sách trong DB; ném HTTPException (404) nếu không tìm thấy chunk.
    """
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
    """Thực hiện kiểm tra chất lượng dịch (QA) tự động trên các chunk đã dịch trong phạm vi chương được chọn.

    Args:
        book_id: ID cuốn sách cần kiểm tra.
        chapter_start: Chỉ số chương bắt đầu (mặc định 1).
        chapter_end: Chỉ số chương kết thúc (mặc định 99999).

    Returns:
        dict: Thống kê số chunk đã kiểm tra, số lỗi/cảnh báo và danh sách thông tin chi tiết các chunk bị lỗi.

    Side-effects:
        Đọc danh sách thuật ngữ và các chunk đã dịch từ DB, thực hiện thuật toán QA deterministic; ném HTTPException (404) nếu không có sách.
    """
    from ebook_translator.translator.qa import check_translation

    d = _get_db()
    book = await d.get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    glossary = await d.get_glossary(book_id)
    sql = (
        "SELECT id, chapter_idx, paragraph_idx, segment_idx, original_text, translated_text, status "
        "FROM chunks WHERE book_id = ? AND translated_text IS NOT NULL"
    )
    params: list[int] = [book_id]
    if chapter_end < 99999 or chapter_start > 1:
        sql += " AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ?"
        params.extend([chapter_start, chapter_end])
    sql += " ORDER BY chapter_idx, paragraph_idx, segment_idx"
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
    """Lấy danh sách các chunk kèm văn bản gốc và văn bản dịch phục vụ giao diện người đọc (Reader UI).

    Args:
        book_id: ID cuốn sách.
        chapter_start: Chỉ số chương bắt đầu.
        chapter_end: Chỉ số chương kết thúc.
        status_filter: Bộ lọc theo trạng thái dịch ('all', 'done', 'pending', v.v.).

    Returns:
        dict: Tổng số chunk, danh sách các chương có sẵn và mảng chi tiết các chunk.

    Side-effects:
        Truy vấn dữ liệu bảng `chunks` từ cơ sở dữ liệu.
    """
    d = _get_db()
    sql = (
        "SELECT id, chapter_idx, paragraph_idx, segment_idx, original_text, translated_text, status "
        "FROM chunks WHERE book_id = ?"
    )
    params: list = [book_id]
    if chapter_end < 99999 or chapter_start > 1:
        sql += " AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ?"
        params.extend([chapter_start, chapter_end])
    if status_filter != "all":
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY chapter_idx, paragraph_idx, segment_idx"
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
    """Lấy danh sách tất cả các mục thuật ngữ (glossary) thuộc về cuốn sách.

    Args:
        book_id: ID cuốn sách cần lấy thuật ngữ.

    Returns:
        list[dict]: Danh sách các đối tượng thuật ngữ (id, source_term, target_term, notes).

    Side-effects:
        Truy vấn dữ liệu từ bảng `glossary` trong DB.
    """
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
    """Tạo mới một mục thuật ngữ trong bảng glossary của cuốn sách.

    Args:
        req: Thông tin thuật ngữ cần tạo (book_id, source_term, target_term, notes).

    Returns:
        dict: ID của mục thuật ngữ vừa được tạo `{"id": lastrowid}`.

    Side-effects:
        Thêm bản ghi mới vào bảng `glossary` và commit DB.
    """
    d = _get_db()
    cursor = await d.conn.execute(
        "INSERT INTO glossary (book_id, source_term, target_term, notes) VALUES (?, ?, ?, ?)",
        (req.book_id, req.source_term, req.target_term, req.notes),
    )
    await d.conn.commit()
    return {"id": cursor.lastrowid}


@app.delete("/api/glossary/{entry_id}")
async def delete_glossary(entry_id: int) -> dict:
    """Xóa một mục thuật ngữ khỏi cơ sở dữ liệu theo ID mục.

    Args:
        entry_id: ID của mục thuật ngữ cần xóa.

    Returns:
        dict: Kết quả thao tác `{"ok": True}`.

    Side-effects:
        Xóa bản ghi khỏi bảng `glossary` và commit DB.
    """
    d = _get_db()
    await d.conn.execute("DELETE FROM glossary WHERE id = ?", (entry_id,))
    await d.conn.commit()
    return {"ok": True}


# ── Translation ──────────────────────────────────────────────────────────


@app.post("/api/translate/start")
async def start_translate(req: StartTranslateRequest) -> dict:
    """Bắt đầu một công việc dịch sách theo chế độ tiêu chuẩn (standard mode) chạy ngầm dưới nền.

    Args:
        req: Cấu hình tham số dịch (file_path, vendor, api_key, model, ngôn ngữ, phạm vi chương, v.v.).

    Returns:
        dict: Thông tin job khởi tạo gồm book_id, job_id, status ("started") và mode ("standard").

    Side-effects:
        Hủy job đang chạy nếu có, tạo hoặc lấy book_id từ DB, khởi tạo bản ghi `translation_job` và chạy tác vụ ngầm `_run_translation`; ném HTTPException (400) nếu lỗi cấu hình.
    """
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

    if not req.model:
        raise HTTPException(status_code=400, detail="Select a model fetched from the provider")

    config = TranslationConfig(
        vendor=req.vendor,
        api_key=api_key,
        model=req.model,
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
    """Gửi tín hiệu hủy công việc dịch sách đang chạy và đóng pipeline dịch.

    Returns:
        dict: Trạng thái phản hồi `{"status": "cancelled"}`.

    Side-effects:
        Kích hoạt sự kiện `_cancel_event`, đóng `active_pipeline` và cập nhật trạng thái job trong DB thành 'cancelled'.
    """
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
    """Bắt đầu tiến trình dịch sách theo chế độ Agentic kết hợp tự động kiểm định (Deterministic Validation) chạy ngầm.

    Args:
        req: Cấu hình dịch (file_path, vendor, api_key, model, phạm vi chương).

    Returns:
        dict: Thông tin job gồm book_id, job_id, status ("started") và mode ("agentic").

    Side-effects:
        Hủy job cũ nếu có, tạo `translation_job` và chạy tác vụ ngầm `_run_agentic_translate`; ném HTTPException (400, 404) nếu lỗi.
    """
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
    if not req.model:
        raise HTTPException(status_code=400, detail="Select a model fetched from the provider")
    ctx = AgentContext(
        book_id=book_id,
        vendor=req.vendor,
        api_key=api_key,
        model=req.model,
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
    """Truy vấn tiến độ dịch thực tế của cuốn sách theo phạm vi chương yêu cầu.

    Args:
        book_id: ID cuốn sách.
        chapter_start: Chương bắt đầu (mặc định 0).
        chapter_end: Chương kết thúc (mặc định 99999).

    Returns:
        dict: Thống kê tiến độ gồm total, done, failed và status của tiến trình.

    Side-effects:
        Truy vấn dữ liệu tiến độ chunk từ cơ sở dữ liệu.
    """
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
    """Xuất bản dịch của sách ra file theo chế độ (đơn ngữ/song ngữ), định dạng (txt/epub) và khoảng chương tùy chọn.

    Args:
        book_id: ID cuốn sách cần xuất file.
        req: Cấu hình tham số xuất (output_path, mode, format, chapter_start, chapter_end).

    Returns:
        dict: Đường dẫn file xuất (`path`), `mode`, và `format`.

    Side-effects:
        Đọc dữ liệu từ DB và ghi tập tin kết quả ra đĩa; ném HTTPException (400, 404) nếu lỗi.
    """
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
    """Tải xuống file sách đã được dịch và xuất ra định dạng EPUB/TXT.

    Args:
        book_id: ID cuốn sách cần tải về.

    Returns:
        FileResponse: Phản hồi tập tin tải về cho client.

    Side-effects:
        Đọc file trên đĩa; ném HTTPException (404) nếu không tìm thấy sách hoặc file xuất chưa tạo.
    """
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
    """Lấy thông tin công việc dịch gần đây nhất của một cuốn sách.

    Args:
        book_id: ID cuốn sách cần kiểm tra.

    Returns:
        dict: Dữ liệu công việc dịch gần nhất (job_id, status, mode, v.v.).

    Side-effects:
        Truy vấn DB; ném HTTPException (404) nếu không tìm thấy job dịch nào.
    """
    job = await _get_db().get_latest_job(book_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No translation job found")
    return job


@app.get("/api/jobs/{job_id}/resume-plan")
async def job_resume_plan(job_id: int) -> dict:
    """Lấy kế hoạch tiếp tục công việc dịch bao gồm thông tin job, tiến độ và danh sách ID các chunk chưa dịch.

    Args:
        job_id: ID công việc dịch.

    Returns:
        dict: Thông tin kế hoạch gồm `job`, `progress`, và `remaining_chunk_ids`.

    Side-effects:
        Truy vấn DB; ném HTTPException (404, 409) nếu job không tồn tại hoặc không ở trạng thái tạm dừng/thất bại.
    """
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
    """Tiếp tục thực thi một công việc dịch sách đã bị tạm dừng hoặc thất bại trước đó.

    Args:
        job_id: ID của công việc dịch cần tiếp tục.
        req: Cấu hình thông tin xác thực API key và base_url nếu cần.

    Returns:
        dict: Kết quả khởi động lại gồm job_id, book_id, status ("running"), mode, và số chunk còn lại (`remaining`).

    Side-effects:
        Khởi tạo lại pipeline/context dịch, tạo tác vụ ngầm chạy tiếp, cập nhật lại trạng thái job trong DB; ném HTTPException (400, 404, 409) khi có lỗi.
    """
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
    """Lấy dữ liệu chẩn đoán chi tiết của một công việc dịch theo ID job.

    Args:
        job_id: ID công việc dịch.

    Returns:
        dict: Thông tin chẩn đoán lỗi, số lần thử và chi tiết thực thi của job.

    Side-effects:
        Truy vấn DB; ném HTTPException (404) nếu job không tồn tại.
    """
    try:
        return await _get_db().get_job_diagnostics(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/diagnostics")
async def diagnostics() -> dict:
    """Lấy các chỉ số chẩn đoán vận hành hệ thống cục bộ (đếm dữ liệu database và bộ đếm runtime metrics).

    Returns:
        dict: Dữ liệu chẩn đoán gồm thông tin database và runtime metrics snapshot.

    Side-effects:
        Đọc trạng thái DB và tạo snapshot chỉ số runtime.
    """
    from ebook_translator.translator.metrics import snapshot

    return {
        "database": await _get_db().get_diagnostics(),
        "runtime": snapshot(),
    }


# ── Info / Config ────────────────────────────────────────────────────────


@app.get("/api/vendors")
async def list_vendors() -> list[dict]:
    """Lấy danh sách các nhà cung cấp AI dịch thuật được hệ thống hỗ trợ kèm mô tả và cấu hình mặc định.

    Returns:
        list[dict]: Danh sách từ điển thông tin cấu hình của từng vendor AI.

    Side-effects:
        Đọc dữ liệu từ cấu hình tĩnh `VENDORS`.
    """
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
    """Truy vấn trực tiếp danh sách các mô hình AI khả dụng từ API của nhà cung cấp.

    Args:
        vendor_id: Mã định danh của vendor AI.
        req: Thông tin kết nối gồm api_key và base_url.

    Returns:
        list[str]: Danh sách tên các model hỗ trợ từ vendor.

    Side-effects:
        Gửi yêu cầu mạng tới API external của vendor; ném HTTPException (502) nếu truy vấn thất bại.
    """
    from ebook_translator.translator.adapters import fetch_vendor_models

    try:
        return await fetch_vendor_models(
            vendor_id=vendor_id,
            api_key=req.api_key,
            base_url=req.base_url or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model discovery failed: {exc}") from exc


@app.post("/api/test-connection")
async def test_connection(req: TestConnectionRequest) -> dict:
    """Thực hiện kiểm tra kết nối API tới nhà cung cấp AI bằng cách gửi tin nhắn thử nghiệm.

    Args:
        req: Thông tin cấu hình kết nối (vendor, api_key, model, base_url).

    Returns:
        dict: Kết quả kiểm tra chứa status ("ok" hoặc "error") và văn bản phản hồi hoặc mô tả lỗi.

    Side-effects:
        Tạo adapter kết nối và gửi yêu cầu dịch thử tới API vendor với thời gian timeout 15 giây; ném HTTPException (400) nếu chưa chọn model.
    """
    from ebook_translator.translator.adapters import create_adapter

    if not req.model:
        raise HTTPException(status_code=400, detail="Select a model fetched from the provider")

    adapter = create_adapter(
        vendor_id=req.vendor,
        api_key=req.api_key,
        model=req.model,
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
    """Lấy danh sách các thể loại sách được hỗ trợ dịch thuật kèm mô tả chi tiết từng thể loại.

    Returns:
        dict[str, str]: Ánh xạ từ mã thể loại (category code) sang thông tin mô tả thể loại.

    Side-effects:
        Đọc từ danh mục enum `BookCategory` và từ điển `CATEGORY_INFO`.
    """
    return {c.value: CATEGORY_INFO[c] for c in BookCategory}


@app.get("/api/prompt-preview/{category}")
async def prompt_preview(category: str) -> dict:
    """Lấy nội dung system prompt mẫu được áp dụng tương ứng với thể loại sách chỉ định.

    Args:
        category: Mã thể loại sách cần xem trước prompt.

    Returns:
        dict: Chứa mã thể loại (`category`) và nội dung câu lệnh hệ thống (`prompt`).

    Side-effects:
        Ném HTTPException (400) nếu mã thể loại không hợp lệ.
    """
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
