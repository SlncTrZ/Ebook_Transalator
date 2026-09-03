# Ebook Translator — Master Plan

> Source of truth for product direction, architecture targets, implementation order, acceptance gates, and junior-agent guardrails.
>
> `progress.md` is historical evidence only. `Plan.md` is the original phased plan. When these documents disagree, this file wins.

## 1. Product North Star

Ebook Translator is not a file-in/file-out translation utility. It is a local-first **Translation Workbench** for long-form books.

Target workflow:

```text
Import
→ Parse & Understand
→ Research
→ Human Review
→ Translate
→ Inspect
→ Correct
→ Resume
→ Export
```

The product must preserve three core values:

1. **Translation quality** — category-aware style, glossary consistency, inspectable output.
2. **Operational resilience** — cache-first, resumable, crash-safe, deterministic state.
3. **Professional workflow** — the UI exposes the state of the book and translation job clearly rather than hiding complexity behind a single button.

The project must NOT regress into:

```text
Upload → Pick API → Progress Bar → Download
```

That flow may exist as a shortcut later, but it must not dictate the architecture.

---

## 2. Documentation Contract

Documentation describes two things and must label them explicitly:

- **Current** — verified in the working codebase.
- **Target** — architecture/product contract that implementation must reach.

Rules:

- Never mark a target capability as implemented without evidence.
- Never weaken the target merely because the current implementation is incomplete.
- Every material gap becomes an implementation item in this plan.
- `README.md` is user-facing truth, not aspiration.
- `Architect.md` may describe the target architecture, but must show current→target migration where the implementation differs.

---

## 3. Current Baseline — Verified 2026-09-01

### Implemented and regression-covered

- Python/FastAPI backend with SQLite + `aiosqlite` WAL persistence.
- React/TypeScript workbench frontend with Tauri v2 scaffold and Python sidecar wiring.
- EPUB and TXT import with encoding/parser hardening.
- Paragraph chunking with stable `paragraph_idx` + `segment_idx` for oversize paragraphs.
- SHA-256 content fingerprints and prompt-context fingerprints.
- Unified LLM Gateway for Standard, Agentic, and Research paths.
- Vendor adapters for OpenAI-compatible APIs, Anthropic, Gemini, and Ollama.
- Every provider exposes an editable API Base URL; the configured URL is propagated through Research, Standard, Agentic, model discovery, connection testing, and CLI execution.
- Model selection is explicit and provider-sourced: no hard-coded model fallback remains; model lists are fetched live from provider APIs (including remote Ollama `/api/tags`, Anthropic/Gemini pagination, and OpenAI-compatible `/models`).
- Category-aware Standard and Agentic prompting.
- Bounded long-form neighborhood context using canonical adjacent chunks.
- Exact response cache separated from user-approved Translation Memory.
- Research/HITL metadata confirmation with user feedback and optional web verification.
- Book-scoped glossary with exact target-term semantics.
- Deterministic QA with structured issue codes surfaced in the Reader workspace.
- Manual translation correction, explicit Translation Memory promotion, and requeue.
- Persisted translation jobs with explicit state machine, attempt history, diagnostics, interrupted recovery, and range-safe resume.
- Standard and Agentic resume wiring without persisting provider credentials.
- Source-preserving EPUB export retaining non-translated archive resources, CSS/assets, package structure, spine/TOC resources, and segmented paragraph reconstruction.
- Retry policy limited to transient network/timeout/429/5xx-style provider failures; permanent client errors fail fast.
- Desktop-oriented workbench UI using the project-local Design Taste guardrails.
- Backend regression suite verified at **85 passing tests**, including complex EPUB round-trip, 2,500-chunk resume/progress stress coverage, remote Ollama model discovery, and explicit-provider-model routing.
- Frontend TypeScript compile verified passing.

### Release blockers / not yet verified

Windows desktop packaging is no longer a blocker. Gate 2 has been verified on the authoritative Windows host (`truon@192.168.1.171`, `H:\Develop\Ebook_Transalator`): Rust MSVC, `cargo check --locked`, frontend production build, Tauri release compile, NSIS bundle, silent install, packaged launch, backend HTTP readiness, and sidecar shutdown/port release all passed.

The only remaining blocker before `v1.0-rc1` is **full packaged real-book pipeline validation**:

- import representative TXT + EPUB;
- Research/HITL;
- Standard/Agentic small-range translation;
- interrupt/relaunch/resume;
- QA/manual correction/Translation Memory promotion;
- TXT/EPUB export + reopen;
- persistence across relaunch;
- record release evidence.

### Remaining architecture / product maturity debt

- `server.py` is still too large and owns orchestration that should eventually move into service modules.
- Translation Memory retrieval is exact-match-first; fuzzy candidate ranking is still a target enhancement.
- Context is neighborhood-aware but does not yet include full chapter summaries/entity registry/approved-example retrieval.
- Metrics are useful for local diagnosis but not yet a complete per-job token/cost/performance model where provider usage data is available.
- Legacy books imported before `segment_idx` existed cannot be safely auto-repaired if they already contain paragraph-index collisions; re-import is the safe migration path for that edge case.

---

## 4. Non-Negotiable Architecture

### 4.1 One LLM Gateway

All model calls must pass through one vendor-agnostic abstraction.

Target:

```text
Research Agent ─┐
Translate Agent ├─→ LLM Gateway → Vendor Adapter → Provider API
Validation AI* ─┘
```

`*` Deterministic validation remains preferred. AI validation is optional and must never silently replace deterministic checks.

Forbidden:

- Vendor-specific HTTP calls inside agent modules.
- Hard-coded `/chat/completions` outside the adapter/gateway layer.
- Separate authentication/base URL behavior per feature.

Acceptance:

- The same provider/model configuration works for Standard and Agentic modes where the provider supports required capabilities.
- Adapter contract tests cover OpenAI-compatible, Anthropic, Gemini, and Ollama request shapes.

### 4.2 One Translation Job State Model

`chunks` is the canonical source of truth for per-unit translation state.

Book/job summaries must be derived transactionally or via aggregate query.

Target state model:

```text
pending → running → done
                  ↘ failed → queued/retry
cancelled is job-level state, not fake chunk completion
```

Do not maintain counters that can drift unless they are transactionally guaranteed.

### 4.3 Explicit Orchestration Layer

Move workflow control out of HTTP handlers.

Target modules:

```text
ebook_translator/
├── services/
│   ├── import_service.py
│   ├── research_service.py
│   ├── translation_service.py
│   ├── job_service.py
│   └── export_service.py
├── translator/
│   ├── gateway.py
│   ├── adapters.py
│   ├── prompts.py
│   └── validation.py
└── server.py       # transport only
```

Names may change, responsibility may not.

### 4.4 Crash-Safe Resume

A process restart must not corrupt book/job state or force completed chunks to be translated again.

Required behavior:

- Completed chunks remain reusable.
- Failed chunks retain error reason and attempt metadata.
- Running chunks on unclean shutdown are recoverable to a retryable state.
- Cache writes and chunk completion cannot produce an impossible state.

### 4.5 EPUB Fidelity

The target is not merely “produce a valid EPUB.”

For EPUB input, export should preserve or deliberately transform:

- spine/order;
- TOC/navigation;
- stylesheets;
- images/assets;
- chapter structure;
- metadata;
- non-translated resources.

Translated text should replace or accompany the source content without rebuilding the book into a generic chapter shell unless the user explicitly selects a simplified export mode.

---

## 5. Implementation Roadmap

## P0 — Make the Core Truthful and Correct

### P0.1 Fix translation routing

Goal: Standard and Agentic actions always start the intended job.

Scope:

- Remove ambiguous `/translate/start` behavior.
- Define explicit Standard vs Agentic command semantics.
- Ensure default full-book range starts correctly.
- Remove response statuses that imply work was delegated when no job exists.

Acceptance:

- Full book Standard starts.
- Chapter-range Standard starts.
- Full book Agentic starts.
- Chapter-range Agentic starts.
- Cancel behaves predictably for each.
- Integration tests prove all five cases.

### P0.2 Unify LLM gateway

Goal: eliminate feature-specific provider HTTP logic.

Acceptance:

- Research uses gateway.
- Standard Translate uses gateway.
- Agentic Translate uses gateway.
- Provider/model/base URL/API-key semantics come from one configuration path.
- No agent code constructs provider API URLs.

### P0.3 Normalize job/progress state

Goal: one source of truth.

Acceptance:

- No stale `done_chunks`/`failed_chunks` UI.
- Status endpoint and UI report the same counts.
- Range translation progress is based on the selected job scope, not guessed ratios.
- Restart reconciliation is deterministic.

### P0.4 Contract tests

Minimum end-to-end backend tests:

1. TXT import → Standard translate mock → export TXT.
2. EPUB import → chunk order preserved.
3. Research → confirm metadata → Agentic translate mock.
4. Cache hit skips provider call.
5. Failed chunk can be retried.
6. Chapter-range job translates only selected chapters.
7. Cancelled job does not report `done`.

No P1 work starts until these gates pass.

---

## P1 — Product-Grade Translation Workbench

### P1.1 UI information architecture redesign

The UI is a workbench, not a set of disconnected CRUD tabs.

Target desktop layout:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Workspace / Book / Global Actions                                  │
├────────────────┬────────────────────────────────┬───────────────────┤
│ Book Navigator │ Translation Workspace          │ Inspector         │
│                │                                │                   │
│ Chapters       │ Original | Translation         │ Metadata          │
│ Job states     │ Inline issues / corrections    │ Glossary          │
│ Search/filter  │ Selection/context actions      │ Context / QA      │
├────────────────┴────────────────────────────────┴───────────────────┤
│ Job status · model · cache hits · tokens · latency · errors         │
└─────────────────────────────────────────────────────────────────────┘
```

Core UX rules:

- User always knows which book, chapter, job, and model are active.
- Translation state is visible at chapter and paragraph level.
- Research/HITL is a workflow stage, not a detached feature.
- Glossary editing is contextual to the current book and visible while inspecting translations.
- Failed chunks are actionable from the workspace.
- Export is a completion action with a preview of scope and fidelity mode.

### P1.2 Design system

Use the project-local skill:

```text
.agents/skills/design-taste-frontend/SKILL.md
```

It is a **visual-quality guardrail**, not a product architecture authority.

Project overrides for Ebook Translator:

- Prefer software/workbench density over landing-page theatricality.
- No perpetual animation in data-heavy translation surfaces.
- Motion intensity should default low-to-medium for daily desktop use.
- Design variance should be controlled; information hierarchy outranks novelty.
- No decorative bento layout for the core translation workspace.
- No emojis in production UI; replace with a coherent icon system.
- Avoid generic card soup; use panes, dividers, toolbars, tables/lists, and hierarchy.
- Dark mode may exist, but the app must not rely on neon/glow aesthetics.
- Loading, empty, error, disabled, retrying, cancelled, and partial-success states are mandatory.

Before adding a UI dependency, inspect `frontend/package.json` and reuse existing dependencies first.

### P1.3 Translation inspection and correction

Required capabilities:

- Per-paragraph original/translated comparison.
- Missing glossary term indicators.
- Failed/retry state.
- Manual correction.
- “Re-translate selected” with reason/context.
- Preserve edited translation from automatic overwrite unless explicitly confirmed.

### P1.4 EPUB fidelity engine

Implement source-EPUB-preserving export path.

Acceptance corpus must include:

- stylesheet-heavy EPUB;
- images;
- nested TOC;
- unusual chapter filenames;
- multilingual metadata.

### P1.5 Translation memory evolution

Current fingerprint cache is retained and expanded deliberately.

Separate concepts:

- exact-response cache;
- translation memory;
- glossary;
- user-approved manual correction.

Do not silently treat all four as the same data.

---

## P2 — Reliability and Observability

### P2.1 Job persistence

Persist job metadata:

- job ID;
- book ID;
- mode;
- provider/model;
- chapter scope;
- created/started/finished timestamps;
- status;
- error summary.

### P2.2 Metrics

Expose useful local metrics only:

- chunks/sec;
- provider latency;
- retries;
- cache hit ratio;
- tokens by job/model where available;
- failed chunk count.

Metrics must aid diagnosis, not become a vanity dashboard.

### P2.3 Background-task recovery

Replace fragile process-only task state with persisted orchestration sufficient for local desktop recovery.

No external queue is required unless evidence proves SQLite/local execution insufficient.

---

## P3 — Distribution and Optional Capabilities

### P3.1 Tauri desktop packaging

- Deterministic Python sidecar strategy.
- Windows packaging first if that is the primary operator environment.
- Clear local storage paths.
- Upgrade/migration strategy for SQLite schema.

### P3.2 Cover generation

Cover AI remains optional and must not block core product maturity.

Do not begin until P0 and P1 acceptance gates are satisfied.

---

## 6. UI Redesign Execution Plan

### Stage A — Audit before styling

Junior must inventory:

- screens/components;
- duplicated controls;
- state ownership;
- API calls embedded directly in components;
- missing interaction states;
- current CSS tokens;
- installed frontend dependencies.

Deliverable: UI map + component responsibility map. No visual rewrite yet.

### Stage B — Design tokens and shell

Establish:

- spacing scale;
- typography scale;
- neutral palette + one accent;
- borders/radii;
- icon family;
- pane sizes;
- focus/hover/active/disabled/error states.

Build the application shell before redesigning individual features.

### Stage C — Translation workspace

Implement navigator + bilingual work area + inspector first.

Do not migrate every legacy screen at once.

### Stage D — Research/HITL integration

Bring metadata research and glossary proposal into the book workflow.

### Stage E — Export and settings

Unify provider settings and export contract after core workflow is stable.

### Stage F — Legacy removal

Remove obsolete tabs/components/API wrappers only after replacement workflows have tests.

---

## 7. Junior Agent Non-Negotiables

Every junior/agent must follow these rules:

1. Read `MASTER_PLAN.md` before coding.
2. Read the relevant existing implementation before designing replacements.
3. Reuse existing logic before introducing new abstractions.
4. Do not turn TODOs/placeholders into “implemented” claims.
5. Do not fake progress, cache hits, token counts, sources, job state, or success.
6. Do not add provider-specific HTTP outside the LLM gateway/adapter layer.
7. Do not add a second way to perform the same frontend API operation.
8. Do not add a UI element without a workflow purpose.
9. Do not change target architecture merely to avoid refactoring.
10. Do not grow `server.py` into a monolithic workflow engine.
11. Do not rewrite working modules solely for style consistency.
12. Do not add Redis, Celery, Kafka, cloud databases, or other infrastructure without measured need.
13. Do not add animation libraries or UI frameworks without checking existing dependencies and explaining why reuse is insufficient.
14. Do not mark a slice complete without tests/evidence matching its acceptance criteria.
15. Preserve user-edited translations and glossary overrides unless the user explicitly chooses replacement.

---

## 8. Required Slice Template

Every implementation slice handed to a junior must contain:

```text
Title
Why
Current behavior
Target behavior
Scope
Files expected
Existing logic to reuse
Non-goals
Acceptance criteria
Required tests
Regression risks
Evidence required before DONE
```

A slice without explicit non-goals is incomplete.

---

## 9. Definition of Done

A feature is DONE only when:

- implementation exists;
- public behavior matches docs;
- tests cover its critical path;
- loading/error/empty/cancel/retry states are handled where relevant;
- no duplicate implementation remains unless explicitly justified;
- docs are updated if behavior changed;
- evidence can be shown with commands/tests/screenshots as appropriate.

“Works on my machine” is not a completion criterion.

---

## 10. Immediate Execution Plan — v1.0 Release Candidate

The earlier two-coder Translation Intelligence and Job Reliability lanes have been substantially completed and integrated. They are no longer the active execution plan.

The project is now in **release-hardening mode**. Do not expand feature scope until the release gates below are satisfied.

### 10.1 Gate 1 — Stabilize the Frontend Build Environment — VERIFIED

Verified on 2026-09-01 with Node **22.23.2**:

```text
TypeScript compile PASS
npm run build PASS
@rolldown/binding-linux-x64-gnu present
@tauri-apps/cli-linux-x64-gnu present
tauri-cli 2.11.4 reachable
npm audit --omit=dev: 0 vulnerabilities
```

Host-specific note: `/mnt/pc-dev` does not permit npm to create symlinks, so `npm ci` must use `--no-bin-links` and local non-committed executable wrappers are needed under `node_modules/.bin` for npm scripts on this host. Do not change `package.json` or application source to encode this filesystem workaround.

### 10.2 Gate 2 — Windows Rust / Tauri Verification — VERIFIED

**Windows is now the authoritative desktop release environment.** Linux remains useful for backend/frontend development and automated tests, but Linux GTK/WebKit packaging is not a v1.0 blocker.

Authoritative runbook:

```text
WINDOWS_RELEASE.md
scripts/windows_release.ps1
```

Required Windows baseline:

```text
Windows 10/11
Node 22 or 24 stable
Python 3.12+
Rust stable MSVC host toolchain
Microsoft C++ Build Tools — Desktop development with C++
Microsoft Edge WebView2 Runtime
```

Primary release target:

```text
x86_64-pc-windows-msvc
NSIS installer first
MSI optional after NSIS passes
```

Verified Gate 2 evidence on 2026-09-01:

```text
Node 24.18.0
Python 3.12.0
rustc/cargo 1.98.0 x86_64-pc-windows-msvc
Visual C++ Build Tools + Windows SDK usable
WebView2 Runtime present
frontend production build PASS
Windows sidecar .exe generated
cargo check --locked PASS
Tauri NSIS bundle PASS
silent installer exit 0
packaged app launch PASS
/api/vendors HTTP 200
sidecar cleanup PASS
port 8080 released after app exit
```

A packaged smoke run exposed and then closed an orphan-sidecar bug in commit `02e86bc` (`fix: terminate desktop sidecar on app exit`). The previous Linux `glib-2.0` blocker remains host evidence only and does not block v1.0.

Verify:

- Tauri v2 shell plugin wiring compiles.
- Python sidecar is discovered with the correct target-triple filename.
- Backend starts before the UI needs it.
- App closes the sidecar cleanly.
- Port collision behavior is understandable and recoverable.
- SQLite/app data lives in a deliberate writable application location for packaged builds.
- Installer/package launches on the target OS.

Windows packaging is the first priority release target unless deployment requirements change.

### 10.3 Gate 3 — Real-World Corpus and Stress Validation — IN PROGRESS

Automated release-corpus coverage now includes:

```text
complex EPUB with CSS + image asset
nested TOC/navigation
unusual chapter filenames
multilingual metadata
source-preserving export + reopen validation
2,500-chunk progress/resume scope stress test
```

The exporter now parses source XHTML in XML-aware mode, eliminating the BeautifulSoup XML-as-HTML warning exposed by the corpus test.

Synthetic/constructed corpus tests are necessary but not enough for v1.0; representative real books still need manual release validation.

Create a local release corpus covering at minimum:

```text
EPUB with heavy CSS
EPUB with images/assets
nested TOC/navigation
unusual spine/chapter filenames
multilingual metadata
very long paragraphs / segmented chunks
UTF-8 TXT
UTF-8 BOM TXT
Windows-1252 TXT
CJK TXT with Chinese/Japanese punctuation
large book with thousands of chunks
```

Run representative workflows:

```text
Import
→ Research/HITL
→ Standard translation with mocked or controlled provider
→ Agentic translation with mocked or controlled provider
→ interrupt/restart
→ resume
→ manual correction
→ save Translation Memory
→ QA inspection
→ requeue failed/corrected chunk
→ export TXT/EPUB
→ reopen exported artifact
```

Acceptance:

- no lost completed chunks after restart;
- no out-of-range resume work;
- no paragraph mapping corruption;
- no missing EPUB assets/TOC/package resources in source-preserving export;
- no silent user-edit overwrite;
- errors remain actionable rather than becoming fake completion.

### 10.4 Gate 4 — Windows Packaged Desktop Smoke Test — BASIC LIFECYCLE VERIFIED / FULL PIPELINE PENDING

Basic packaged lifecycle is verified: NSIS install, launch, backend readiness, graceful app exit, sidecar termination, port release, and clean relaunch all passed.

What remains is the user-facing full pipeline on representative real books. Authoritative checklist lives in [`WINDOWS_RELEASE.md`](WINDOWS_RELEASE.md).

Verify end-to-end:

```text
install
launch
backend readiness
import local book
translate mocked/small real sample
inspect/edit
export
close app
relaunch
resume persisted state
uninstall / reinstall or upgrade migration check
```

Capture release evidence rather than relying on source-tree behavior.

### 10.5 Gate 5 — Tag `v1.0-rc1`

Create the release candidate only when Gates 1–4 pass.

Before tagging:

```text
backend pytest PASS
frontend TypeScript PASS
frontend production build PASS
cargo check PASS
Tauri package PASS
corpus smoke suite PASS
git diff --check PASS
working tree clean except intentional local-only config
README and MASTER_PLAN match verified behavior
```

### 10.6 Post-RC Work — Do Not Block v1.0

After `v1.0-rc1`, prioritize product maturity in this order:

1. Extract orchestration from the 1,000+ line `server.py` into explicit service modules.
2. Add local fuzzy Translation Memory candidate ranking without a vector database.
3. Expand long-form context with chapter summaries, entity registry, style memory, and approved examples.
4. Expand deterministic QA conservatively: named-entity consistency, quote/structure mismatch, untranslated residue, missing/added sentence heuristics.
5. Improve per-job observability where provider usage metadata is actually available.

Explicitly deferred unless core evidence creates a need:

```text
Cover AI
OCR
audiobook generation
chat-with-book
vector database
Redis/Celery/Kafka
cloud scheduler
additional provider breadth for its own sake
```

The release strategy is now **stabilize → verify → package → corpus-test → RC**, not add more features.
