# Progress Report — 23/07/2026

## Tổng quan

Hoàn thiện Ebook Translator từ Phase 1 (MVP CLI) lên Phase 3 (Agentic Pipeline + HITL + Multi-Vendor).
Dự án đã có đủ core tính năng để chạy dịch thực tế.

---

## Tính năng đã xây dựng

### 1. Parser & Encoding

- [x] Parser `.epub` (ebooklib + BeautifulSoup)
- [x] Parser `.txt` với **score-based encoding detection**: thử 9 encoding châu Á, chọn cái ít replacement chars nhất
- [x] Fix: GB18030 cho tiếng Trung (chardet detect sai KOI8-U)
- [x] Verified với Calibre: khớp **100% số paragraph** (12,428/12,428) trên 2 file Trung Quốc

### 2. Agentic Pipeline (`agent/pipeline.py`)

- [x] **Research Agent**: 1 lần duy nhất trên preview → sinh metadata + glossary → **dừng chờ duyệt**
- [x] **Translate Agent**: Cache check + context injection (book info, glossary, style notes)
- [x] **Deterministic Validation**: Regex check glossary terms — **chỉ check terms CÓ trong source text**, max 2 retries, không infinite loop
- [x] Re-search: nếu AI không tự tin, search DuckDuckGo lần 2

### 3. Multi-Vendor AI (`translator/adapters.py`)

- [x] 7 vendors: OpenAI, DeepSeek, Groq, Together, Ollama, Anthropic, Gemini
- [x] Adapter pattern: OpenAI-compatible (chung) + Anthropic riêng + Gemini riêng + Ollama riêng
- [x] Fetch live models từ API vendor
- [x] Test & Save API key
- [x] Fix: `base_url` luôn được fill từ vendor (không phụ thuộc model)

### 4. Prompt Routing (`translator/prompts.py`)

- [x] 12 categories với style guide riêng + few-shot examples:
  - Tiên hiệp → "hắn", Hán-Việt, trang trọng
  - Võ hiệp → hào sảng, nội công, giang hồ
  - Khoa học viễn tưởng → chính xác, kỹ thuật
  - Kỳ ảo → ma pháp, huyền bí, sử thi
  - Kinh dị → căng thẳng, hồi hộp
  - Ngôn tình → lãng mạn, ngọt ngào
  - Trinh thám → logic, manh mối
  - Hài hước → dí dỏm, khôi hài
  - Văn học, Lịch sử, Hiện đại, Tổng hợp

### 5. Web Search (`agent/web_search.py`)

- [x] DuckDuckGo free search (không cần API key)
- [x] AI knowledge first → DuckDuckGo fallback → LLM re-analyze
- [x] Research Agent hướng dẫn search trang gốc Trung Quốc (qidian.com) để lấy category chính xác

### 6. Frontend (React + Tauri)

- [x] **Library tab**: Import bằng path, upload file, preset test buttons, **🗑 xoá sách**
- [x] **Translate tab**: Analyze Metadata → Confirm → Chapter range → Start/Cancel
- [x] **Reader tab**: Song ngữ gốc/dịch, chapter range, status filter
- [x] **Glossary tab**: CRUD từ điển, tự động lưu từ Research Agent
- [x] **Export tab**: Mode (dịch/song ngữ), Format (txt/epub), Chapter range, custom filename
- [x] **Settings tab**: Vendor selector, API key + Test & Save, Model selector, **🟢 Server Status**
- [x] Fix: state persist trong localStorage (confirmed, models, api key, vendor)

### 7. Backend API

- [x] RESTful: Books, Chunks, Glossary, Translate, Export, Vendors, Categories
- [x] Polling progress (`GET /api/translate/status/{id}` thay SSE)
- [x] AutoFormat pipeline: chuẩn hóa dấu câu, khoảng trắng, viết hoa, fix typo

### 8. Bug Fixes

- [x] Validator: chỉ check terms CÓ trong source text (tránh false positive)
- [x] `__post_init__`: set base_url luôn, không phụ thuộc model
- [x] `total_chunks`: đếm live từ chunks table, không dùng books.done_chunks stale
- [x] `localized_title`: lưu field riêng trong AgentContext
- [x] Model: không ghi đè model user đã chọn
- [x] Connection lost: polling thay SSE
- [x] Chapter range filter trong _run_translation
- [x] CORS: allow frontend dev server (port 5173)
- [x] Parser: score-based encoding, giữ line-by-line (không gộp paragraph)

---

## Cấu trúc dự án hiện tại

```
ebook_translator/
├── agent/
│   ├── __init__.py
│   ├── pipeline.py        # Research Agent + Translate Agent + Validation
│   ├── validator.py        # Deterministic validation (Regex, không AI)
│   └── web_search.py       # DuckDuckGo + LLM metadata extract
├── db/
│   └── database.py         # SQLite WAL + aiosqlite
├── export/
│   ├── epub_writer.py       # Export .epub giữ CSS
│   └── export_engine.py     # Export engine: mode, format, range
├── parsers/
│   ├── base.py
│   ├── epub_parser.py       # ebooklib
│   └── txt_parser.py        # Score-based encoding detection
├── translator/
│   ├── adapters.py           # 7 vendors
│   ├── pipeline.py           # Cache + retry
│   └── prompts.py            # 12 categories + style guides
├── utils/
│   ├── autoformat.py         # Text cleanup
│   └── chunker.py            # SHA-256 fingerprint + paragraph chunking
├── models.py
├── cli.py
└── server.py                 # FastAPI (20+ endpoints)

frontend/
├── src/
│   ├── components/
│   │   ├── Library.tsx       # Import + Delete
│   │   ├── TranslateView.tsx # Translate flow + progress
│   │   ├── MetadataReview.tsx # Research + HITL
│   │   ├── GlossaryEditor.tsx
│   │   ├── Reader.tsx        # Song ngữ
│   │   ├── ExportTab.tsx     # Export options
│   │   └── Settings.tsx      # Vendor + API key + Model
│   ├── api.ts
│   ├── App.tsx
│   └── App.css
```

---

## API Endpoints

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | /api/books | Danh sách sách |
| POST | /api/books | Import (JSON path) |
| POST | /api/books/upload | Upload file |
| DELETE | /api/books/{id} | Xoá sách |
| PATCH | /api/books/{id} | Cập nhật metadata |
| POST | /api/books/{id}/research | Research Agent |
| POST | /api/books/{id}/analyze | Analyze cũ |
| POST | /api/books/{id}/confirm-metadata | HITL confirm |
| GET | /api/books/{id}/chunks | Danh sách chunks |
| GET | /api/books/{id}/glossary | Glossary entries |
| POST | /api/glossary | Thêm glossary term |
| DELETE | /api/glossary/{id} | Xoá glossary term |
| GET | /api/books/{id}/reader | Song ngữ reader |
| POST | /api/translate/start | Start translate |
| POST | /api/translate/agentic | Agentic translate |
| POST | /api/translate/cancel | Cancel |
| GET | /api/translate/status/{id} | Polling progress |
| POST | /api/export/{book_id} | Export sách |
| GET | /api/export/{book_id}/download | Download file |
| GET | /api/vendors | Danh sách vendor |
| POST | /api/vendors/{id}/models | Fetch models |
| POST | /api/test-connection | Test API key |
| GET | /api/categories | Danh sách category |

---

## Chưa làm

- [ ] Phase 4: Cover AI (Stable Diffusion) — tạm gác
- [ ] Tauri desktop build (cần Windows SDK)
- [ ] Export .mobi (cần Calibre)
- [ ] Unit test cho agentic pipeline
- [ ] Error recovery cho background task crash
- [ ] Admin dashboard (thống kê token usage, tốc độ dịch)

---

*Dự án bởi **Trương Công Định (SlncTrZ)** — Ebook Translator v0.2.0*
