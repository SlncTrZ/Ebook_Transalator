# Coder 2 — Job Reliability & Persistence Lane

> **Status: COMPLETED / ARCHIVED (2026-09-01).** Persisted job state machine, interrupted recovery, range-safe resume, attempt history and diagnostics were implemented and integrated. This file is retained as historical assignment evidence, not an active lane.

Project: `Ebook_Transalator`

This file is self-contained. Follow it as the authoritative assignment for this lane.

## Mission

Turn the current persisted-job model from crash-awareness into a true resumable local job system backed by canonical chunk state.

The product direction is:

```text
Local-first
+ crash-safe
+ resumable
+ deterministic state
+ human-controlled retries
```

Do not introduce distributed infrastructure for a single-user local desktop app without evidence.

---

## Ownership

You may modify:

```text
ebook_translator/db/**
tests/test_*jobs*
tests/test_*recovery*
tests/test_*progress*
tests/test_*lifecycle*
```

You may create:

```text
ebook_translator/jobs/**
```

if a dedicated job-state/orchestration domain module is justified.

You MUST NOT modify:

```text
ebook_translator/server.py
ebook_translator/models.py
ebook_translator/translator/**
ebook_translator/agent/**
frontend/**
pyproject.toml
requirements.txt
```

These are integration/shared ownership files.

If your work requires a shared-file change, do NOT make the change yourself. Record the required contract in the final handoff.

---

## Parallel-Work Rules

Another coder is working concurrently on translation context/QA/TM logic.

Therefore:

1. Do not edit files outside your ownership.
2. Do not rename/move translator or agent modules.
3. Do not perform broad refactors across project boundaries.
4. Do not reset, checkout, clean, or discard working-tree changes.
5. Assume unrelated dirty changes belong to another worker or integration owner.
6. Do not commit or push unless explicitly instructed.
7. Keep DB/job APIs narrow and explicit so integration can wire them into HTTP/service layers later.

The purpose is to prevent two coders from modifying the same files.

---

## Canonical State Contract

Per-chunk translation state remains canonical in `chunks`.

Book/job summaries may be persisted, but must not become a second competing truth source.

Never derive resume behavior from stale `books.done_chunks` or similar counters.

Conceptual rule:

```text
chunks = canonical work state
translation_jobs = orchestration/history/scope
books counters = derived snapshot only
```

Completed chunks must never be retranslated during resume unless explicitly requeued by the user.

---

# Priority 1 — Formal Job State Model

## Current

Persisted jobs exist and running jobs are marked `interrupted` on restart.

This is crash-awareness, not full lifecycle management.

## Target States

Define a clear local state machine including:

```text
pending
running
paused
cancelled
done
failed
interrupted
```

You may add another state only with a strong semantic reason.

## Required Legal Transitions

At minimum:

```text
pending → running
running → paused
paused → running
running → done
running → failed
running → cancelled
running → interrupted
interrupted → running
```

Consider whether failed jobs can explicitly retry/resume; if supported, define it rather than relying on ad-hoc status writes.

Illegal transitions must be rejected deterministically.

## Implementation Guidance

Prefer a small explicit state-machine/domain module over string comparisons spread through database methods.

Possible shape:

```text
ebook_translator/jobs/state.py
```

Do not build a generic workflow framework.

## Acceptance

- Legal transitions have tests.
- Illegal transitions have tests.
- Terminal state semantics are explicit.
- Cancellation is job-level state and does not fake chunk completion.

---

# Priority 2 — True Resume

## Current

On restart:

```text
running → interrupted
```

## Target

A resumable job must be reconstructable from persisted scope + canonical chunks.

Conceptual flow:

```text
process crash
↓
startup
↓
previous running job becomes interrupted
↓
load job scope
↓
inspect chunks in that scope
↓
keep done untouched
↓
select pending/failed retryable work according to policy
↓
resume same logical job
```

## Requirements

Resume must preserve:

- `book_id`;
- mode;
- vendor/model identity;
- chapter range;
- completed chunks;
- errors on failed chunks;
- explicit cancellation semantics.

Do not automatically resume cancelled/done jobs.

Do not retranslate `done` chunks.

Define whether failed chunks are included automatically or require retry policy. Whatever behavior is chosen must be explicit and tested.

## Required Internal Contract

Design DB/domain methods sufficient for integration owner to do something conceptually like:

```python
job = await jobs.get_resumable(job_id)
remaining = await jobs.get_remaining_chunks(job)
await jobs.mark_resumed(job_id)
```

Exact names may differ.

Because `server.py` is shared/integration-owned, do not wire routes/background tasks yourself.

## Acceptance

Tests simulate:

1. job starts;
2. some chunks complete;
3. process/database reconnect occurs;
4. job becomes interrupted;
5. resume plan contains only remaining retryable work;
6. completed chunks remain untouched;
7. job can reach final correct state.

---

# Priority 3 — Range-Safe Resume

Range jobs must remain bounded to their persisted chapter scope.

Example:

```text
job scope = chapters 4–7
```

Resume must never pick pending chunks from chapters 1–3 or 8+.

## Acceptance

Tests must cover:

- full-book resume;
- one-chapter resume;
- multi-chapter range resume;
- pending chunks outside job range are ignored.

---

# Priority 4 — Retry / Attempt Metadata

The workbench needs diagnosis, not just success/failure.

Evaluate minimal useful persistence for attempts, for example:

```text
attempt_count
last_error
last_attempt_at
```

Do not add fields merely because they are common in enterprise queues.

Persist only what materially helps:

- recovery;
- failure diagnosis;
- retry policy;
- job history.

If schema changes are introduced, migration of existing SQLite databases must remain safe and idempotent.

## Acceptance

- Existing databases open successfully.
- New fields/defaults are deterministic.
- Retry metadata updates correctly.
- No impossible state is created when a retry fails again.

---

# Priority 5 — Per-Job Diagnostics Foundation

Current runtime diagnostics are mostly process/global.

Prepare persisted job-level information useful for later UI/API integration.

Useful metrics may include:

```text
scope total chunks
attempted chunks
done
failed
remaining
retry count
created/started/finished timestamps
duration where derivable
```

Do NOT invent:

- token counts unavailable from providers;
- fake monetary cost;
- fake latency;
- cache/TM counts unless real integration data exists.

If translation-layer metrics need to be written into jobs, define the integration contract instead of editing translator modules.

---

# Priority 6 — Recovery Queries and Integrity

Add narrow database/domain operations needed for safe orchestration.

Examples:

```text
latest resumable job for book
list interrupted jobs
job progress scoped to chapter range
remaining retryable chunk IDs for job
transition job atomically
```

Where state mutation depends on current state, use transaction/conditional update semantics so two callers cannot silently perform conflicting transitions.

This is still a local application, but correctness matters.

---

# Existing Logic to Reuse

Inspect before changing:

```text
ebook_translator/db/database.py
tests/test_jobs_and_recovery.py
tests/test_progress_state.py
tests/test_translation_lifecycle.py
```

Preserve the existing canonical chunk-progress principle.

Do not replace SQLite/aiosqlite.

---

# Non-Goals

Do NOT implement in this lane:

- translation prompting/context;
- QA engine;
- Translation Memory ranking;
- provider adapters;
- HTTP routes;
- frontend UI;
- Tauri packaging;
- Redis/Celery/Kafka;
- distributed workers;
- Cover AI.

No external queue is required unless measured evidence later proves local SQLite execution insufficient.

---

# Testing Requirements

At completion run at least:

```text
relevant jobs/recovery/progress/lifecycle tests
full pytest suite if available
python compileall
git diff --check
```

Do not repair unrelated test failures by modifying files outside your ownership.

If a full-suite failure is caused by an expected shared integration change, document it precisely.

---

# Required Recovery Test Matrix

Must include at least:

```text
running job interrupted by restart
interrupted job resume plan
done chunks excluded from resume
failed/pending behavior matches retry policy
range scope preserved
cancelled job cannot auto-resume
done job cannot resume
illegal job transition rejected
legacy DB migration remains valid
```

---

# Evidence Required Before DONE

Your final handoff must contain exactly these sections:

```text
1. What changed
2. Files changed
3. Tests added/updated
4. Test results
5. Shared contracts required
6. Known limitations
7. Recommended integration step
```

For shared contracts, specify exact desired behavior, for example:

```text
Needed shared contract:
- file: ebook_translator/server.py
- behavior: resume interrupted job by ID
- internal method to call: ...
- expected success/error semantics: ...
```

Do not modify the shared file yourself.

---

# Definition of Done for Coder 2

This lane is complete only when:

- job lifecycle has an explicit tested state machine;
- interrupted jobs can produce a deterministic resume plan from persisted job scope + canonical chunk state;
- completed chunks are excluded from resume;
- range jobs remain range-safe;
- retry/attempt persistence is sufficient for diagnosis and recovery;
- DB migration is safe for existing databases;
- no files outside ownership were modified;
- all required shared integration contracts are clearly documented.
