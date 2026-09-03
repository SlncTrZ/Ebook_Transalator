# Ebook Translator

Công cụ dịch E-book local-first hướng tới một **Translation Workbench**: research, Human-in-the-Loop, translation, inspection, correction, resume và export.

> **Project status:** v1.0 candidate / internal beta. Core translation, Standard/Agentic routing, unified LLM gateway, resumable persisted jobs, deterministic QA, HITL, Translation Memory, source-preserving EPUB export, parser hardening, workbench UI và Windows NSIS desktop packaging đều đã được triển khai/verify. Việc còn lại trước `v1.0-rc1` là full packaged pipeline validation bằng sách thật. Xem [`MASTER_PLAN.md`](MASTER_PLAN.md) và [`progress.md`](progress.md).


## Tính năng

| Tính năng | Mô tả |
|---|---|
| **Agentic Pipeline** | Research → HITL → Translate → deterministic validation; Standard và Agentic đều dùng persisted job lifecycle và resumable execution |
| **Multi-Vendor** | Unified LLM Gateway + adapter layer cho OpenAI-compatible, DeepSeek, Groq, Together, Ollama, Anthropic và Gemini; mọi provider có editable API Base URL và model list được fetch live trực tiếp từ provider |
| **Category-aware prompts** | Standard và Agentic dùng category/style context thay vì prompt generic |
| **Song ngữ Reader + QA** | So sánh gốc/dịch, chỉnh sửa thủ công, requeue, deterministic QA issues theo chunk |
| **Glossary** | Book-scoped exact terminology, chỉnh sửa thủ công và inject vào prompt |
| **Research / HITL** | Metadata research, user feedback, optional web verification và confirm trước khi dịch |
| **Cache + Translation Memory** | Exact response cache tách biệt với user-approved Translation Memory |
| **Crash-safe jobs** | Persisted job state, interrupted recovery, range-safe resume, attempt history và diagnostics |
| **Export** | TXT + source-preserving EPUB; giữ CSS/assets/TOC/spine/package resources, hỗ trợ segmented paragraphs |
| **Workbench UI** | Desktop-oriented Library → Translate → Inspect → Glossary → Export → Settings với Design Taste guardrails |

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
| `GET /api/vendors` | Danh sách vendor AI + default endpoint metadata |
| `POST /api/vendors/{id}/models` | Fetch live model list từ Base URL đang cấu hình |
| `POST /api/test-connection` | Test provider + model + custom Base URL |

## Kiến trúc

Kiến trúc bên dưới mô tả baseline hiện tại. Target architecture và migration constraints nằm trong [`MASTER_PLAN.md`](MASTER_PLAN.md) và [`Architect.md`](Architect.md).


```
frontend/          Tauri + React (TypeScript) — workbench shell
ebook_translator/
├── agent/          Research Agent + Translate Agent + Validator
├── db/             SQLite (WAL mode) + aiosqlite
├── parsers/        EPUB (ebooklib) + TXT (chardet + score-based)
├── translator/     LLM Gateway + adapters + context + QA + cache/TM
├── utils/          Chunker + AutoFormat + Fingerprinting
├── jobs/           Explicit persisted job lifecycle / resume helpers
└── export/         Source-preserving EPUB + TXT export
```

## Yêu cầu

- Python 3.12+
- Node.js 22/24 stable recommended for frontend build
- Rust + Cargo (cho Tauri desktop build)

### Release verification status

- Backend regression suite: **85 tests passing** at the latest verified checkpoint, including complex EPUB round-trip, 2,500-chunk resume/progress stress coverage, remote Ollama model discovery, and explicit-provider-model routing.
- TypeScript compile: **passing**.
- Frontend production build: **passing under Node 22.23.2** after a clean optional-dependency install. The `/mnt/pc-dev` filesystem does not permit npm symlink creation, so local non-committed `.bin` wrappers are required on this host; application source and lockfile do not need a workaround.
- Production npm dependency audit (`--omit=dev`): **0 vulnerabilities** at the latest verified checkpoint.
- Python sidecar: build + startup/shutdown smoke test **passing**.
- Rust stable toolchain: verified locally with `rustc 1.98.0` / `cargo 1.98.0`. Linux `cargo check` now reaches native Tauri system dependencies and is blocked by missing `glib-2.0` development libraries on this host.
- Windows Gate 2: **PASS** on `x86_64-pc-windows-msvc` — `cargo check --locked`, Tauri release compile, NSIS bundle and silent install all verified.
- Packaged runtime smoke: **PASS** for app launch, backend HTTP 200, and sidecar shutdown/port release after lifecycle fix.
- Gate 4 remains open only for full real-book workflow validation: import → Research/HITL → translate → interrupt/resume → QA/edit/TM → export → relaunch persistence.
- See [`WINDOWS_RELEASE.md`](WINDOWS_RELEASE.md) for the authoritative Windows release procedure and [`progress.md`](progress.md) for the latest evidence.

## Project documents

- [`MASTER_PLAN.md`](MASTER_PLAN.md) — source of truth cho product direction, target architecture, roadmap và junior guardrails.
- [`Architect.md`](Architect.md) — kiến trúc và migration map.
- [`Plan.md`](Plan.md) — kế hoạch lịch sử ban đầu; không còn là roadmap điều hành chính.
- [`progress.md`](progress.md) — progress log lịch sử, không phải specification.

## License

MIT © 2026 Trương Công Định (SlncTrZ)
