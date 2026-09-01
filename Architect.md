# Kiến trúc Hệ thống: Ebook Translator

> Tài liệu này mô tả **target architecture** và migration direction. Trạng thái implementation thực tế phải được đối chiếu với `README.md` và `MASTER_PLAN.md`. Nếu có xung đột, `MASTER_PLAN.md` là source of truth.

## Current → Target Gap (2026-08-31)

| Area | Current | Target |
|---|---|---|
| LLM calls | Standard dùng adapter; Agentic/Research còn gọi OpenAI-compatible HTTP trực tiếp | Một LLM Gateway duy nhất cho mọi workflow |
| Orchestration | FastAPI `server.py` đang giữ nhiều workflow logic | Service/orchestration layer tách khỏi transport |
| Progress | books counters + chunk COUNT + AgentContext cùng tồn tại | Một canonical job/chunk state model |
| Agentic routing | Frontend/backend contract còn lệch | Explicit Standard/Agentic job commands |
| EPUB export | Rebuild EPUB mới từ translated chunks | Preserve source spine/TOC/CSS/assets/metadata |
| Recovery | Cache/resume theo chunk có nền tảng, background crash recovery chưa đầy đủ | Crash-safe persisted job recovery |
| UI | Nhiều tab CRUD/flow rời rạc | Translation Workbench: navigator + bilingual workspace + inspector |

## Sơ đồ Luồng (Target Core)

```
[Input File] → [Parser] → [Chunker] → [Cache Check] ──→ [AI Translate] → [Writer] → [Export]
                   │            │           │                                      │
                   │            │           ├── Hash match → [Skip] ───────────────┤
                   │            │           │                                      │
                   │            │           └── [Retry (3x, backoff)] ────────────┤
                   │            │                                                  │
              [Lỗi DRM]   [Quá dài → split câu]                                [.epub mới]
              → báo lỗi
```

## Cấu trúc Layer (Target)

### 1. Data Layer (SQLite — WAL mode)

```python
"""Database schema — Core tables only."""
books:    id, file_path, title, author, source_lang, target_lang, category, status
chunks:   id, book_id, chapter_idx, paragraph_idx, content_hash, original_text,
          translated_text, status(pending|done|failed), token_count, error_log
glossary: id, book_id, source_term, target_term, notes
cache:    id, content_hash, source_lang, target_lang, model, translated_text, created_at
```

- **Chống nghẽn:** `PRAGMA journal_mode=WAL` + `aiosqlite` lock-free read
- **Cache riêng bảng:** Tách biệt chunk data với cache, dễ xoá cache mà không ảnh hưởng dữ liệu dịch

### 2. Chunking Engine

- **Default:** 1 paragraph = 1 chunk
- **Oversize protection:** nếu paragraph > 4000 tokens → split theo `.` / `!` / `?`
- **Metadata:** mỗi chunk lưu `chapter_idx` + `paragraph_idx` → ghép lại đúng thứ tự
- **Hash:** `sha256(original_text.encode())` — dùng làm key tra cache

### 3. Translation Pipeline

Target constraint: mọi model call phải đi qua `LLM Gateway → Vendor Adapter`. Agent modules không được tự ghép provider URL hoặc hard-code `/chat/completions`.


```python
async def translate_chunk(chunk, glossary, category):
    """1 chunk → 1 API call. Có retry, có cache check."""

    # Bước 1: Check cache
    cached = await get_cached(chunk.content_hash, src, tgt, model)
    if cached:
        return cached

    # Bước 2: Build prompt (glossary inject)
    prompt = build_prompt(chunk.text, glossary, category)

    # Bước 3: Call API (retry 3x, backoff)
    for attempt in retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=16)):
        try:
            result = await ai_client.translate(prompt)
            break
        except RateLimitError:
            attempt.snooze()  # ExponentialBackoff
        except APIConnectionError:
            if attempt.retry_state.attempt_number == 3:
                chunk.status = "failed"
                await save_failed(chunk, error_log)

    # Bước 4: Save cache + chunk
    await save_cache(chunk.content_hash, result)
    chunk.translated_text = result
    chunk.status = "done"
    await save_chunk(chunk)
```

### 4. Error Recovery

Current implementation mới đạt một phần target này. Đặc biệt, process/background-task crash recovery và reconciliation của job state vẫn là hạng mục P1/P2 trong `MASTER_PLAN.md`.


| Loại lỗi | Hành vi |
|---|---|
| **429 Rate Limit** | Backoff 1s → 4s → 16s. Sau 3 lần → skip + log |
| **5xx Server Error** | Như trên |
| **Connection Timeout** | Retry với timeout=60s. Lần 3 fail → skip |
| **DRM file** | Báo lỗi rõ "File có DRM, không parse được" |
| **Encoding (.txt)** | Thử utf-8 → fallback chardet → fallback cp1252. Vẫn fail → báo lỗi |
| **Mất điện giữa chừng** | Chạy lại → check DB: chunk `done` → skip. Chỉ dịch `pending` + `failed` |

### 5. Caching Policy (Fingerprinting)

Exact-response cache hiện tại là nền tảng, nhưng target architecture tách rõ **cache**, **translation memory**, **glossary**, và **manual correction**; không được gộp các semantic khác nhau chỉ vì cùng giúp tái sử dụng bản dịch.


```
Key:   sha256(original_text + source_lang + target_lang + model)
TTL:   ∞ (vĩnh viễn) — chỉ xoá khi anh clear cache tay
Scope: Per-book? Không — global. Cùng 1 paragraph ở 2 cuốn sách khác nhau = dùng chung cache
```

- **Cache-first:** Luôn check cache trước khi gọi API
- **Write-through:** Sau mỗi translate success → ghi cache ngay
- **Invalidate:** Nếu đổi model → key khác → cache cũ không ảnh hưởng

---

## Tech Stack

Tech stack hiện tại được giữ theo nguyên tắc reuse-first. Không thêm Redis/Celery/Kafka/cloud database nếu chưa có bằng chứng SQLite/local orchestration không đáp ứng Scalability thực tế của desktop workload.


| Layer | Công nghệ | Lý do |
|---|---|---|
| **Ngôn ngữ** | Python 3.12+ | Hệ sinh thái NLP + AI mạnh |
| **Database** | SQLite + aiosqlite | Embedded, zero config, WAL chống lock |
| **Parser EPUB** | ebooklib + BeautifulSoup | Chuẩn, bảo trì tốt |
| **Parser TXT** | chardet | Auto-detect encoding |
| **AI Client** | httpx (async) + tenacity | Async call + retry pattern |
| **Cache** | hash (sha256) + bảng SQLite | Không cần Redis, đủ nhanh cho local |
| **Export** | ebooklib | Current: TXT + generated EPUB; Target P1: preserve source EPUB spine/TOC/CSS/assets/metadata |
| **Frontend** | Tauri 2.x + React (TS) | Desktop workbench; packaging vẫn chưa hoàn tất |
| **Error Handling** | tenacity + logging | Retry exponential backoff |
| **Token Tracking** | tiktoken (OpenAI) | Đếm token trước khi gửi, tránh oversize |

---

## UI Architecture Target

Core product surface không được trở thành SaaS dashboard/card soup. Target là desktop workbench:

```text
Book Navigator | Original / Translation Workspace | Inspector
---------------------------------------------------------------
Job status · model · cache hits · tokens · latency · errors
```

Design implementation phải đọc `.agents/skills/design-taste-frontend/SKILL.md`, nhưng project-specific workflow rules trong `MASTER_PLAN.md` override các decorative/landing-page biases của skill.

## So sánh trước và sau Audit

| Hạng mục | Cũ (bloated) | Mới (Ngon-Bổ-Rẻ) |
|---|---|---|
| Cover AI | Phase 1 | Phase 4 (tuỳ chọn) |
| Web Search + HITL | Phase 2 | Phase 3 (tuỳ chọn) |
| Cache | Không có | Phase 1 — bắt buộc |
| Error recovery | Không có | Phase 1 — bắt buộc |
| Chunking | Không rõ | Paragraph, có oversize split |
| Frontend | Electron (nặng) | Tauri (nhẹ) |
| Guideline | AI-generated, thiếu thực tế | Audit-driven, tập trung vào core value |
