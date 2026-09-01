# Ebook Translator

Công cụ dịch E-book local-first hướng tới một **Translation Workbench**: research, Human-in-the-Loop, translation, inspection, correction, resume và export.

> **Project status:** active development. Standard translation, parser/chunker/cache, multi-vendor adapters, Research/HITL, reader và export đã có. Agentic routing, multi-vendor Agentic calls, progress state, EPUB fidelity và workflow tests vẫn đang được chuẩn hóa. Xem [`MASTER_PLAN.md`](MASTER_PLAN.md) để biết target contract và implementation order.


## Tính năng

| Tính năng | Mô tả |
|---|---|
| **🤖 Agentic Pipeline** | **Partial** — Research → HITL → Translate → Deterministic Validation; orchestration đang được chuẩn hóa theo Master Plan |
| **🌐 Multi-Vendor** | Adapter layer hỗ trợ OpenAI, DeepSeek, Groq, Together, Ollama, Anthropic, Gemini; Agentic/Research chưa dùng thống nhất adapter cho mọi vendor |
| **🎭 12 Category** | Style guide riêng cho từng thể loại (Tiên hiệp, Võ hiệp, Sci-fi, Kỳ ảo...) |
| **📖 Song ngữ Reader** | Xem gốc/dịch song song theo chapter |
| **📝 Glossary** | Tự động sinh từ Research Agent, chỉnh sửa thủ công |
| **🔍 Web Search** | DuckDuckGo free — tìm metadata + category từ trang gốc |
| **✅ HITL** | Duyệt metadata + glossary trước khi dịch |
| **🔐 Cache** | Fingerprinting SHA-256, tránh tốn token dịch lại |
| **🎨 AutoFormat** | Chuẩn hóa dấu câu, khoảng trắng, viết hoa, fix typo |
| **📦 Export** | TXT + EPUB hiện hoạt động; source-EPUB fidelity (CSS/assets/TOC/spine) là target P1, chưa được coi là hoàn tất |
| **🗑 Quản lý** | Import/Upload, xoá sách, chapter range |

## Quick Start

```bash
# 1. Cài đặt
pip install -r requirements.txt

# 2. Chạy backend
python -m ebook_translator.server

# 3. Mở frontend (terminal khác)
cd frontend && npm install && npm run dev

# 4. Mở http://localhost:5173
```

## API Endpoints

| Endpoint | Chức năng |
|---|---|
| `GET /api/books` | Danh sách sách |
| `POST /api/books` | Import sách (path) |
| `POST /api/books/upload` | Upload file |
| `POST /api/books/{id}/research` | **Research Agent** — phân tích, sinh glossary |
| `POST /api/books/{id}/confirm-metadata` | Xác nhận metadata |
| `POST /api/translate/start` | Dịch (Standard pipeline) |
| `POST /api/translate/agentic` | Dịch (Agentic pipeline) |
| `GET /api/translate/status/{id}` | Polling progress |
| `GET /api/books/{id}/reader` | Song ngữ reader |
| `GET /api/vendors` | Danh sách vendor AI |
| `POST /api/test-connection` | Test API key |

## Kiến trúc

Kiến trúc bên dưới mô tả baseline hiện tại. Target architecture và migration constraints nằm trong [`MASTER_PLAN.md`](MASTER_PLAN.md) và [`Architect.md`](Architect.md).


```
frontend/          Tauri + React (TypeScript) — 5 tabs
ebook_translator/
├── agent/          Research Agent + Translate Agent + Validator
├── db/             SQLite (WAL mode) + aiosqlite
├── parsers/        EPUB (ebooklib) + TXT (chardet + score-based)
├── translator/     Adapter pattern (7 vendors) + Prompt Router
├── utils/          Chunker + AutoFormat + Fingerprinting
└── export/         Rebuild .epub giữ nguyên CSS
```

## Yêu cầu

- Python 3.12+
- Node.js 20+
- Rust (cho Tauri desktop build)

## Project documents

- [`MASTER_PLAN.md`](MASTER_PLAN.md) — source of truth cho product direction, target architecture, roadmap và junior guardrails.
- [`Architect.md`](Architect.md) — kiến trúc và migration map.
- [`Plan.md`](Plan.md) — kế hoạch lịch sử ban đầu; không còn là roadmap điều hành chính.
- [`progress.md`](progress.md) — progress log lịch sử, không phải specification.

## License

MIT © 2026 Trương Công Định (SlncTrZ)
