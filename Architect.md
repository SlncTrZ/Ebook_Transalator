# Kiến trúc Hệ thống: Ebook Translator

> Snapshot kiến trúc đã triển khai, cập nhật 2026-09-01. `MASTER_PLAN.md` là source of truth cho release gates và thứ tự công việc. `Plan.md` và các handoff cũ chỉ còn giá trị lịch sử.

## 1. Product Architecture

Ebook Translator là **local-first long-form translation workbench**:

```text
Import
→ Parse & Understand
→ Research / HITL
→ Translate
→ Inspect / Correct
→ Resume safely
→ Export
```

AI làm phần nặng; người dùng giữ quyền kiểm soát terminology, context, quality và final text.

## 2. Runtime Topology

```text
Tauri v2 desktop shell
        │
        ├── React/TypeScript workbench
        │
        └── Python FastAPI sidecar (127.0.0.1:8080)
                    │
                    ├── SQLite / WAL
                    ├── Parser + Chunker
                    ├── Research / HITL
                    ├── LLM Gateway
                    ├── Standard / Agentic pipelines
                    ├── QA / Translation Memory
                    └── Export engine
```

Windows `x86_64-pc-windows-msvc` là authoritative desktop release target. Linux vẫn dùng cho backend/frontend development và automated tests.

## 3. Core Layers

### 3.1 Import / Parsing

- EPUB: `ebooklib` + BeautifulSoup.
- TXT: strict UTF-8 first, BOM-aware handling, confidence-gated detection, cp1252 fallback.
- CJK chapter/sentence splitting hỗ trợ punctuation không cần whitespace.
- Upload/import có path sanitization, size limit và explicit errors.

### 3.2 Canonical Chunk Identity

Mỗi chunk có:

```text
book_id
chapter_idx
paragraph_idx
segment_idx
content_hash
original_text
translated_text
status
```

`paragraph_idx` là identity của paragraph gốc; `segment_idx` chỉ biểu diễn các segment của paragraph quá dài. Exporter phải join segments theo `paragraph_idx + segment_idx` trước khi patch EPUB.

### 3.3 SQLite State

SQLite là persistent source of truth, WAL mode, `aiosqlite`.

Các domain chính:

```text
books
chunks
glossary
translation_cache
translation_memory
translation_jobs
translation_job_attempts
```

Book counters chỉ là compatibility snapshot. Progress thật được aggregate trực tiếp từ chunks trong đúng scope chapter range.

### 3.4 LLM Gateway

Mọi model call phải đi qua:

```text
Workflow
→ LLM Gateway
→ Vendor Adapter
→ Provider
```

Standard, Agentic và Research không được hard-code provider HTTP path riêng.

Gateway hiện hỗ trợ OpenAI-compatible providers, Anthropic, Gemini và Ollama.

### 3.5 Translation Pipelines

Standard và Agentic dùng cùng các primitives:

- category-aware prompting;
- bounded neighboring context;
- glossary injection;
- Translation Memory lookup;
- exact context-aware response cache;
- transient-only retry policy;
- deterministic QA;
- persisted job lifecycle.

Cache, Translation Memory, glossary và manual correction là bốn semantics khác nhau và không được gộp.

### 3.6 Context Engine

Context hiện tại được build từ canonical neighboring chunks trong cùng chapter:

```text
previous source
previous completed translation
current source
next source
```

Context có budget hữu hạn và deterministic truncation. Chapter summary/entity registry/style memory sâu hơn là post-RC enhancement, không block v1.0.

### 3.7 Deterministic QA

QA hiện phát hiện tối thiểu:

- missing translation;
- glossary violation;
- number mismatch;
- identical/source residue;
- abnormal length ratio.

QA trả structured issue codes cho Reader/Inspect UI. Manual correction không tự động trở thành Translation Memory; promotion vào TM là action riêng.

### 3.8 Job Reliability

Persisted `translation_jobs` dùng explicit state machine:

```text
pending → running → done / failed / interrupted / paused / cancelled
```

Resume:

- giữ nguyên logical job;
- chỉ lấy `pending|failed` chunks;
- giữ đúng chapter scope;
- không dịch lại chunks `done`;
- không persist API credentials;
- có attempt history + diagnostics.

Khi process restart, running jobs trở thành `interrupted` và running attempts được đóng thành failed attempt evidence.

### 3.9 EPUB Fidelity

Nếu source là EPUB thật, exporter patch source archive thay vì rebuild từ zero:

- giữ CSS/assets/images;
- giữ package/spine/TOC/navigation resources;
- giữ non-document entries byte-for-byte;
- patch các XHTML document cần dịch;
- reconstruct segmented paragraphs trước khi patch.

Source XHTML được parse XML-aware trong exporter.

Known limitation: translated-only replacement hiện có thể làm mất inline markup bên trong chính translated paragraph. Đây là post-RC fidelity enhancement, không phải resource-loss bug.

## 4. Desktop Lifecycle

Tauri spawn Python backend bằng `tauri-plugin-shell` sidecar.

`CommandChild` được giữ trong managed app state và bị terminate khi Tauri nhận `Exit` hoặc `ExitRequested`.

Lý do: build Windows thực tế đã phát hiện sidecar orphan giữ port `8080` sau khi UI process kết thúc. Fix hiện đã verify trên packaged NSIS build:

```text
app exit
→ backend process count = 0
→ port 8080 listener count = 0
```

## 5. Desktop Storage

Default SQLite path:

```text
~/.ebook_translator/library.db
```

`ET_DB_PATH` có thể override. Credentials không được persist trong repository hoặc DB job metadata.

## 6. Frontend Architecture

Workbench shell:

```text
Library → Translate → Inspect → Glossary → Export → Settings
```

Desktop layout:

```text
Workflow rail | Active workspace | Context / runtime inspector
```

Design rules:

- dense desktop workbench, không card soup;
- one accent color;
- no purple/neon/glow;
- compact status/progress metrics;
- low motion;
- clear loading/empty/error states;
- API key session-only.

## 7. Release Architecture

Authoritative Windows release path:

```text
Node 22/24 stable
Python 3.12+
Rust stable x86_64-pc-windows-msvc
Visual C++ Build Tools
Windows SDK
WebView2
→ Python sidecar build
→ cargo check --locked
→ Tauri release build
→ NSIS installer
→ packaged smoke test
```

Verified 2026-09-01 on `truon@192.168.1.171`, repo `H:\Develop\Ebook_Transalator`:

- Node 24.18.0;
- Python 3.12.0;
- rustc/cargo 1.98.0 MSVC;
- frontend production build PASS;
- `cargo check --locked` PASS;
- NSIS build PASS;
- silent install PASS;
- packaged app launch PASS;
- packaged `/api/vendors` returns HTTP 200;
- sidecar shutdown / port release PASS after lifecycle fix.

## 8. Remaining Before v1.0-rc1

Không cần thêm feature mới.

Còn đúng release validation:

1. full packaged pipeline bằng sách thật;
2. import TXT + EPUB;
3. Research/HITL;
4. Standard và/hoặc Agentic translation sample;
5. interrupt/relaunch/resume;
6. manual correction + TM promotion;
7. QA inspection;
8. TXT/EPUB export + reopen;
9. persistence across relaunch;
10. record release evidence và tag `v1.0-rc1` nếu pass.

Sau RC mới quay lại server/service refactor, fuzzy TM, richer long-form context và deeper QA.
