# P0.1 Handoff — Translation Routing Repair

> Scope owner: junior implementation slice
> Governing plan: `MASTER_PLAN.md`
> Priority: P0
> Status: **COMPLETED / ARCHIVED** — explicit Standard/Agentic routing, full-book/range behavior and truthful start semantics were implemented and regression-covered before 2026-09-01. This file is retained as historical handoff evidence only.

## 1. Why

The frontend/backend routing contract for translation is currently inconsistent.

Observed failures:

- The frontend always calls `POST /api/translate/start`, including when Agentic mode is selected.
- `/api/translate/start` returns `delegated_to_agentic` for Agentic requests but does not actually start the Agentic task.
- The actual Agentic task is started by a separate endpoint: `POST /api/translate/agentic`.
- Standard translation only starts inside an `is_range` branch. With API defaults (`chapter_start=0`, `chapter_end=99999`) the endpoint can return without creating a translation task.
- Response status strings currently mix transport response status with workflow semantics and can imply work happened when no job exists.

This is a correctness bug, not a cosmetic refactor.

P0.1 must make translation command routing explicit and deterministic before any LLM gateway or job-state refactor begins.

---

## 2. Current Behavior

### Frontend

Relevant files:

```text
frontend/src/api.ts
frontend/src/components/TranslateView.tsx
```

`TranslateView` calls `startTranslate(...)` for both Standard and Agentic modes.

`startTranslate(...)` always calls:

```text
POST /api/translate/start
```

with an `agentic` boolean in the request body.

### Backend

Relevant file:

```text
ebook_translator/server.py
```

Current endpoints:

```text
POST /api/translate/start
POST /api/translate/agentic
POST /api/translate/cancel
GET  /api/translate/status/{book_id}
```

Current problem paths:

```text
Standard + explicit range
→ /translate/start
→ creates background task

Standard + API default full range
→ /translate/start
→ does not create background task

Agentic
→ /translate/start
→ returns delegated_to_agentic
→ does not call /translate/agentic
→ no Agentic task starts
```

---

## 3. Target Behavior

Routing must be unambiguous.

### Required command semantics

```text
Standard button
→ one explicit Standard start command
→ Standard background task starts

Agentic button
→ one explicit Agentic start command
→ Agentic background task starts
```

Both commands must support:

```text
full book
chapter range
```

The frontend must not rely on a backend response string that claims delegation without an actual job/task being started.

---

## 4. Preferred Repair Strategy

Prefer **explicit frontend command routing** over one overloaded endpoint with an `agentic` boolean.

Target API client surface:

```text
startStandardTranslation(...)
startAgenticTranslation(...)
```

Target endpoint use:

```text
Standard → POST /api/translate/start
Agentic  → POST /api/translate/agentic
```

The backend may retain the `agentic` field temporarily for compatibility, but new frontend code must not depend on it.

Do NOT merge the endpoints into a new generalized job API in this slice. That belongs to later orchestration/job-state work if justified.

---

## 5. Scope

### Must change

Expected files:

```text
frontend/src/api.ts
frontend/src/components/TranslateView.tsx
ebook_translator/server.py
```

Tests may require new or existing test files under:

```text
tests/
```

If project structure suggests a more appropriate integration-test location, use it.

### Allowed supporting changes

Only changes directly required to test or expose routing behavior.

Examples:

- request helper split;
- minimal response type cleanup;
- test fixtures;
- dependency injection/mocking hooks if already compatible with current architecture.

---

## 6. Existing Logic to Reuse

Do not rewrite translation execution.

Reuse:

```text
_run_translation(...)
_run_agentic_translate(...)
TranslationPipeline
AgentContext
translate_agent_with_validation(...)
_cancel_event
existing chapter filtering logic
existing status polling endpoint
```

The purpose of P0.1 is to route correctly into existing execution paths.

If existing execution contains unrelated defects, document them for later slices unless they directly block routing acceptance criteria.

---

## 7. Required Changes

### 7.1 Frontend API client

Replace ambiguous public usage of:

```text
startTranslate(..., agentic)
```

with explicit functions or an equivalently explicit command abstraction.

Preferred:

```text
startStandardTranslation(...)
startAgenticTranslation(...)
```

No duplicate request-building logic if a shared private helper can safely be reused.

### 7.2 TranslateView routing

`TranslateView` must select the correct API command based on mode.

Required behavior:

```text
agentic === false → Standard endpoint
agentic === true  → Agentic endpoint
```

Do not infer whether a task started from decorative response status text.

### 7.3 Standard full-book start

`POST /api/translate/start` must create a background Standard translation task for the default/full-book scope.

Remove the accidental requirement that `is_range` be true before task creation.

Chapter filtering may remain inside `_run_translation`.

### 7.4 Standard chapter-range start

Existing range behavior must remain functional.

Do not estimate work by chapter ratio as part of this slice unless the current code makes correct routing impossible without touching it.

Progress accuracy belongs to P0.3.

### 7.5 Agentic start

`POST /api/translate/agentic` must remain the execution endpoint for Agentic mode in this slice.

The frontend must call it directly.

Do not make `/api/translate/start` return `delegated_to_agentic` as the primary Agentic workflow.

If backward compatibility is retained, its behavior must not misrepresent whether work was started.

### 7.6 Response contract

Use simple truthful start responses.

Acceptable shape:

```json
{
  "book_id": 123,
  "status": "started",
  "mode": "standard"
}
```

and:

```json
{
  "book_id": 123,
  "status": "started",
  "mode": "agentic"
}
```

Exact field shape may vary if existing frontend types make another minimal shape better, but:

- `status` must describe what actually happened;
- no fake delegation state;
- frontend and backend types must match.

---

## 8. Non-Goals

P0.1 MUST NOT become a broad refactor.

Do not implement:

- Unified LLM Gateway — P0.2.
- Provider adapter changes — P0.2.
- Progress/source-of-truth redesign — P0.3.
- Persisted jobs — P2.
- Retry/requeue model redesign.
- EPUB export changes.
- UI redesign.
- Settings redesign.
- Database schema changes unless absolutely unavoidable for routing tests.
- `server.py` service-layer extraction unless a tiny extraction is required to make routing testable; broad extraction belongs to later architecture slices.

Do not “clean up everything nearby.”

---

## 9. Acceptance Criteria

All must pass.

### A. Standard full book

Given:

```text
chapter_start = default/full-book start
chapter_end   = default/full-book end
mode          = standard
```

When start is requested:

- backend creates the Standard background task;
- response says work started;
- translation execution path is `_run_translation` / existing Standard pipeline.

### B. Standard chapter range

Given a valid chapter range:

- Standard background task starts;
- only selected chapter scope reaches the existing range filter;
- no Agentic path is invoked.

### C. Agentic full book

When Agentic mode is selected:

- frontend calls the Agentic endpoint;
- backend creates `_run_agentic_translate` task;
- response says work started;
- Standard pipeline is not started.

### D. Agentic chapter range

Given Agentic mode + range:

- Agentic task starts;
- supplied chapter scope reaches existing Agentic range filter.

### E. Cancel compatibility

Existing cancel request remains callable after either mode starts.

P0.1 does not need to redesign cancellation semantics, but routing changes must not break the current cancel path.

### F. No fake start states

No request may return a status equivalent to `started`, `delegated`, or `handled` unless the intended execution path was actually entered or a background task was actually scheduled.

---

## 10. Required Tests

At minimum add automated tests proving routing.

Mock external model calls. No real API keys or provider calls.

Required cases:

```text
1. standard_full_book_starts_background_task
2. standard_range_starts_background_task
3. agentic_full_book_starts_agentic_task
4. agentic_range_starts_agentic_task
5. frontend_standard_calls_standard_endpoint
6. frontend_agentic_calls_agentic_endpoint
```

If frontend test infrastructure does not exist and adding a full framework would materially expand scope:

- do not add a large frontend testing stack just for P0.1;
- instead provide backend automated tests plus static/type/build evidence for frontend routing;
- document the missing frontend test infrastructure as technical debt.

Backend tests must still be automated.

---

## 11. Regression Risks

Check specifically:

- importing an unregistered book through Standard start;
- starting an already imported book;
- `active_pipeline` behavior;
- `_cancel_event` reset behavior;
- repeated starts;
- `chapter_start` indexing: frontend is 1-based while some backend defaults are 0-based;
- polling begins after a truthful `started` response;
- Agentic code currently does not use `active_pipeline` in the same way Standard does.

Do not fix unrelated progress-counter drift in this slice. Flag it for P0.3.

---

## 12. Evidence Required Before DONE

Junior must provide all of the following:

### Code evidence

```text
git diff -- <touched files>
```

Explain each touched file in one sentence.

### Test evidence

Run the smallest relevant automated suite plus existing regression tests.

Report exact command and result.

Examples only; use actual project commands:

```text
pytest ...
npm run build
```

### Routing evidence

Show, from tests or instrumented mocks, that:

```text
Standard → Standard task
Agentic  → Agentic task
```

for both full-book and range cases.

### Scope evidence

Confirm explicitly:

- no LLM adapter refactor;
- no DB schema redesign;
- no progress-model redesign;
- no UI redesign.

---

## 13. Stop Conditions

Stop and report rather than expanding scope if any of these occurs:

- fixing routing requires changing provider APIs;
- existing test environment cannot import/start FastAPI without unrelated failures;
- a dirty-file conflict makes it unclear which existing user changes must be preserved;
- a required change would overwrite current uncommitted work without a safe merge.

Do not discard or reset existing working-tree changes.

---

## 14. Completion Definition

P0.1 is DONE when translation mode selection is boring and deterministic:

```text
click Standard → Standard starts
click Agentic  → Agentic starts
full book      → starts
chapter range  → starts
```

No hidden delegation. No endpoint ambiguity. No architecture expansion beyond routing.

After P0.1 passes review, proceed to **P0.2 Unified LLM Gateway**.
