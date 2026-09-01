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

## 3. Current Baseline — Verified 2026-08-31

### Implemented

- Python/FastAPI backend.
- React/TypeScript frontend with Tauri project scaffold.
- EPUB and TXT parsing.
- Paragraph-level chunking with oversize splitting.
- SHA-256 content fingerprinting.
- SQLite + `aiosqlite` with WAL mode.
- Cache table keyed by content hash + source + target + model.
- Standard translation pipeline with retry.
- Vendor adapter layer for OpenAI-compatible APIs, Anthropic, Gemini, and Ollama.
- Research Agent + metadata/glossary proposal.
- HITL metadata confirmation.
- Deterministic glossary validation.
- Reader and export screens.
- TXT and generated EPUB export.

### Partial / inconsistent

- Agentic translation wiring.
- Multi-vendor support inside Agentic/Research LLM calls.
- Translation progress/state consistency.
- Chapter-range semantics.
- Frontend/backend API contracts.
- EPUB fidelity to original structure/CSS/assets.
- Crash recovery for background jobs.
- Test coverage for complete workflows.
- Desktop packaging/release pipeline.

### Known architecture debt

- `server.py` owns too much orchestration.
- Standard and Agentic paths do not share one LLM invocation abstraction.
- Progress exists in multiple mutable representations.
- Frontend contains overlapping translation/export paths.
- Some documentation claims exceed working behavior.

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

## 10. Immediate Parallel Execution Plan — Two Coders

The earlier P0 sequencing has been completed far enough that the next high-value work can run in two parallel lanes with strict file ownership.

The project should now use **two coder lanes plus one later integration gate**.

### 10.1 Coder 1 — Translation Intelligence

Authoritative handoff file:

```text
CODER_1_TRANSLATION_INTELLIGENCE.md
```

Primary ownership:

```text
ebook_translator/translator/**
ebook_translator/agent/**
translation/gateway/memory tests
```

Mission:

```text
Context Engine
→ Category-aware Standard prompting
→ Deterministic QA
→ Translation Memory fuzzy-ranking foundation
```

This coder MUST NOT modify:

```text
ebook_translator/server.py
ebook_translator/models.py
ebook_translator/db/**
frontend/**
pyproject.toml
requirements.txt
```

### 10.2 Coder 2 — Job Reliability & Persistence

Authoritative handoff file:

```text
CODER_2_JOB_RELIABILITY.md
```

Primary ownership:

```text
ebook_translator/db/**
ebook_translator/jobs/** if created
job/recovery/progress/lifecycle tests
```

Mission:

```text
Formal Job State Machine
→ True Resume
→ Range-safe recovery
→ Retry/attempt metadata
→ Per-job diagnostics foundation
```

This coder MUST NOT modify:

```text
ebook_translator/server.py
ebook_translator/models.py
ebook_translator/translator/**
ebook_translator/agent/**
frontend/**
pyproject.toml
requirements.txt
```

### 10.3 Shared / Integration-Only Files

The two coders must not edit these files concurrently:

```text
ebook_translator/server.py
ebook_translator/models.py
frontend/src/api.ts
pyproject.toml
requirements.txt
```

When either lane requires changes in shared files, the coder must return an explicit integration contract rather than editing the shared file.

Integration contract must specify:

```text
file
required endpoint/model/method
input
output
state/error semantics
reason
```

The integration owner applies shared-file changes only after both lanes complete or reach a clean review boundary.

### 10.4 Parallel Safety Rules

For both coders:

1. Ownership boundaries are mandatory, not advisory.
2. Do not reset, checkout, clean, or discard unrelated working-tree changes.
3. Do not broad-refactor outside the assigned domain.
4. Do not commit or push unless explicitly instructed.
5. Do not modify a shared file merely because doing so is easier locally.
6. Add tests inside the lane's owned test scope.
7. Report required cross-lane contracts explicitly.
8. Full-suite failures caused by missing shared integration must be documented rather than patched by violating ownership.

### 10.5 Integration Gate After Both Coders

After both handoffs are returned, perform one controlled integration pass over shared files.

Expected integration work may include:

```text
server.py route/service wiring
models.py contract additions
frontend/src/api.ts API contract updates
shared dependency/version updates only if proven necessary
full regression suite
```

Do not merge the two lanes by allowing both coders to independently modify orchestration hotspots.

### 10.6 Required Handoff Format

Each coder must return:

```text
1. What changed
2. Files changed
3. Tests added/updated
4. Test results
5. Shared contracts required
6. Known limitations
7. Recommended integration step
```

The two dedicated handoff files contain the complete acceptance criteria and non-goals for each lane.
