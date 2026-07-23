# Ebook Translator

Công cụ dịch thuật E-book tự động với Agentic AI pipeline — research, translate, validate.
Hỗ trợ 7+ vendor AI, 12 thể loại văn phong, glossary tự động, và xác thực đầu vào Human-in-the-Loop.

## Tính năng

| Tính năng | Mô tả |
|---|---|
| **🤖 Agentic Pipeline** | Research → HITL → Translate → Deterministic Validation |
| **🌐 Multi-Vendor** | OpenAI, DeepSeek, Groq, Together, Ollama, Anthropic, Gemini |
| **🎭 12 Category** | Style guide riêng cho từng thể loại (Tiên hiệp, Võ hiệp, Sci-fi, Kỳ ảo...) |
| **📖 Song ngữ Reader** | Xem gốc/dịch song song theo chapter |
| **📝 Glossary** | Tự động sinh từ Research Agent, chỉnh sửa thủ công |
| **🔍 Web Search** | DuckDuckGo free — tìm metadata + category từ trang gốc |
| **✅ HITL** | Duyệt metadata + glossary trước khi dịch |
| **🔐 Cache** | Fingerprinting SHA-256, tránh tốn token dịch lại |
| **🎨 AutoFormat** | Chuẩn hóa dấu câu, khoảng trắng, viết hoa, fix typo |
| **📦 Export .epub** | Giữ nguyên CSS gốc |
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

## License

MIT © 2026 Trương Công Định (SlncTrZ)
