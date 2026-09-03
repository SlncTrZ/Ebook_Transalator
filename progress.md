# Progress Report — 2026-09-01

## Trạng thái

Ebook Translator đã đạt trạng thái **v1.0 candidate / internal beta**. Core architecture, translation workflows, recovery, QA, source-preserving export, workbench UI và Windows desktop packaging đều đã được triển khai và có regression evidence.

Việc còn lại trước `v1.0-rc1` là **full packaged pipeline validation bằng sách thật**, không phải mở rộng feature.

## Hoàn thành

### Core translation

- [x] Explicit Standard / Agentic routing.
- [x] Unified LLM Gateway cho Standard, Agentic và Research.
- [x] Multi-vendor adapters: OpenAI-compatible, Anthropic, Gemini, Ollama.
- [x] Editable API Base URL for every provider, including remote Ollama hosts such as `http://192.168.1.x:11434`.
- [x] Live provider model discovery only; no hard-coded model fallback or cached model-list bypass.
- [x] Category-aware prompting.
- [x] Bounded neighboring translation context.
- [x] Book-scoped glossary.
- [x] Exact context-aware cache.
- [x] User-approved Translation Memory tách riêng khỏi cache/manual correction.
- [x] Transient-only retry policy; permanent provider errors fail fast.

### Parser / chunk identity

- [x] EPUB + TXT parsing.
- [x] UTF-8/BOM/confidence-gated encoding handling.
- [x] CJK chapter/sentence splitting.
- [x] Stable `paragraph_idx` + `segment_idx` cho oversized paragraphs.
- [x] Exporter reconstruct segments đúng paragraph identity.

### QA / HITL

- [x] Research + metadata HITL.
- [x] User feedback / optional web verification.
- [x] Deterministic QA structured issues.
- [x] Glossary violation, missing translation, number mismatch, residue/identical text, length anomaly checks.
- [x] Reader manual correction.
- [x] Explicit save-to-Translation-Memory action.
- [x] Chunk requeue.

### Job reliability

- [x] Persisted translation job state machine.
- [x] Interrupted-job recovery after restart.
- [x] Range-safe resume.
- [x] Resume same logical job.
- [x] Completed chunks excluded from resume.
- [x] Per-chunk attempt history.
- [x] Job diagnostics.
- [x] Credentials not persisted in jobs.

### EPUB fidelity

- [x] Source-preserving EPUB patching.
- [x] Preserve CSS/assets/images/package/spine/TOC/navigation resources.
- [x] Preserve non-document archive entries.
- [x] XML-aware XHTML parsing in exporter.
- [x] Complex generated release corpus round-trip test.

### Frontend workbench

- [x] Library → Translate → Inspect → Glossary → Export → Settings workflow.
- [x] Dense desktop workbench redesign using Design Taste guardrails.
- [x] Truthful chunk progress.
- [x] QA surfaced in Reader/Inspect.
- [x] API key session-only.
- [x] Backend startup GET retry for desktop startup race.

### Automated validation

- [x] Backend regression suite: **85 passing tests**.
- [x] Complex EPUB release-corpus test.
- [x] 2,500-chunk progress/resume stress test.
- [x] TypeScript compile PASS.
- [x] Frontend production build PASS on Node 22/24 stable.
- [x] Production npm audit (`--omit=dev`): 0 vulnerabilities at verified checkpoint.
- [x] Python sidecar build + standalone smoke PASS.

## Windows desktop release evidence — 2026-09-01

Authoritative host:

```text
truon@192.168.1.171
H:\Develop\Ebook_Transalator
x86_64-pc-windows-msvc
```

Verified:

- [x] Node 24.18.0.
- [x] Python 3.12.0.
- [x] rustc 1.98.0 / cargo 1.98.0 MSVC.
- [x] Visual C++ Build Tools + Windows SDK usable.
- [x] WebView2 Runtime installed.
- [x] `cargo check --locked` PASS.
- [x] Tauri release compile PASS.
- [x] NSIS installer build PASS.
- [x] Silent NSIS install PASS (`exit 0`).
- [x] Installed desktop app launches.
- [x] Packaged backend returns HTTP 200 from `/api/vendors`.
- [x] Sidecar lifecycle bug discovered and fixed.
- [x] After desktop exit: backend process count 0, port 8080 listener count 0.

Lifecycle fix commit:

```text
02e86bc fix: terminate desktop sidecar on app exit
```

Tauri manifest normalization commit:

```text
178578a chore: normalize tauri manifest features
```

Local-state ignore commit:

```text
4d78c38 chore: ignore local assistant state
```

## Full pipeline validation còn lại

Ngày test tiếp theo chỉ cần chạy trên **packaged Windows app**, không cần thêm feature trước.

Checklist:

```text
1. Install latest NSIS build.
2. Launch packaged app.
3. Import 1 TXT thật.
4. Import 1 EPUB thật có CSS/images/TOC.
5. Run Research/HITL.
6. Run Standard translation on a small chapter range.
7. Optionally run Agentic on a small range.
8. Interrupt an active job and close app.
9. Relaunch and resume the same job.
10. Confirm completed chunks are not translated twice.
11. Inspect deterministic QA.
12. Manually correct one chunk.
13. Save one approved correction to Translation Memory.
14. Export TXT.
15. Export EPUB and reopen it.
16. Confirm assets/TOC/layout resources still exist.
17. Relaunch and confirm books/jobs/state persist.
18. If all pass: record evidence and tag v1.0-rc1.
```

## Không block v1.0

Các mục sau để sau release candidate:

- server.py → service-layer refactor;
- fuzzy Translation Memory candidate ranking;
- chapter summaries / entity registry / approved-example context;
- deeper deterministic QA;
- inline-markup preservation improvements inside translated EPUB paragraphs;
- MSI packaging after NSIS;
- Cover AI / OCR / audiobook / chat-with-book / vector DB.

## Kết luận

Ngày 2026-09-01 kết thúc ở trạng thái:

```text
Core implementation       DONE
Automated regression      PASS
Frontend production build PASS
Windows Gate 2            PASS
Gate 4 basic lifecycle    PASS
Full real-book pipeline   PENDING USER VALIDATION
```

Không nên viết thêm feature trước khi full pipeline test hoàn tất.
