# Coder 1 — Translation Intelligence Lane

> **Status: COMPLETED / ARCHIVED (2026-09-01).** Category-aware Standard prompting, bounded context engine and deterministic QA were implemented and integrated. Exact Translation Memory is implemented; fuzzy TM remains an intentionally deferred post-RC enhancement. This file is historical assignment evidence, not an active lane.

Project: `Ebook_Transalator`

This file is self-contained. Follow it as the authoritative assignment for this lane.

## Mission

Raise translation quality from chunk-level generation toward a professional long-form translation engine with reusable context, category-aware prompting, deterministic QA, and better Translation Memory retrieval.

The product direction is:

```text
Local-first
+ long-form translation
+ AI-assisted
+ human-controlled
+ source-fidelity aware
```

Do not turn this into a generic AI feature bundle.

---

## Ownership

You may modify:

```text
ebook_translator/translator/**
ebook_translator/agent/**
tests/test_*translation*
tests/test_*gateway*
tests/test_*memory*
```

You may create new modules under:

```text
ebook_translator/translator/**
ebook_translator/agent/**
```

when they clearly belong to this lane.

You MUST NOT modify:

```text
ebook_translator/server.py
ebook_translator/models.py
ebook_translator/db/**
frontend/**
pyproject.toml
requirements.txt
```

These are integration/shared ownership files.

If your work requires a shared-file change, do NOT make the change yourself. Record the required contract in the final handoff.

---

## Parallel-Work Rules

Another coder is working concurrently on job persistence/recovery.

Therefore:

1. Do not edit files outside your ownership.
2. Do not rename/move shared modules.
3. Do not perform broad refactors across project boundaries.
4. Do not reset, checkout, clean, or discard working-tree changes.
5. Assume unrelated dirty changes belong to another worker or integration owner.
6. Do not commit or push unless explicitly instructed.
7. If an interface must change, prefer backward-compatible internal adaptation and document the desired shared contract.

The purpose is to prevent two coders from modifying the same files.

---

## Current Architecture You Must Preserve

All model calls must flow through:

```text
Research / Standard / Agentic
            ↓
        LLMGateway
            ↓
      Vendor Adapter
            ↓
       Provider API
```

Forbidden:

- direct provider HTTP inside agent modules;
- hard-coded `/chat/completions` outside adapter/gateway code;
- provider-specific authentication behavior inside translation features.

Current concepts are intentionally separate:

```text
Exact response cache
!= Translation Memory
!= Glossary
!= Manual correction
```

Do not merge these concepts.

User-approved Translation Memory must outrank model response cache where applicable.

---

# Priority 1 — Context Engine

## Why

Long-form translation quality depends on context beyond the current chunk.

Current translation has glossary and prompt context but still lacks a disciplined reusable book/chapter context layer.

## Target

Introduce a reusable context builder for Standard and Agentic translation.

Conceptual target:

```text
Book metadata
Chapter context
Previous translated neighborhood
Source neighborhood
Glossary
Translation Memory suggestions
Style/category rules
Approved examples
        ↓
ContextBuilder
        ↓
Bounded structured context
        ↓
Standard + Agentic translation
```

## Requirements

The context system must:

- have deterministic budgeting;
- avoid unbounded prompt growth;
- clearly separate source neighborhood from approved translated context;
- preserve glossary exactness;
- be reusable by Standard and Agentic flows;
- degrade gracefully when optional context is unavailable;
- avoid inventing missing context.

Prefer a small explicit structure over a generic orchestration framework.

Possible module shape:

```text
ebook_translator/translator/context.py
```

Names may differ if responsibility remains clear.

## Acceptance

- Context construction is deterministic.
- Context size/budget behavior has tests.
- Standard and Agentic can consume the same context abstraction.
- Empty/missing context does not break translation.
- No provider HTTP is introduced outside gateway/adapters.

---

# Priority 2 — Category-Aware Standard Translation

## Why

Standard mode must not expose a Category control that has little or no effect on translation quality.

## Target

Category must materially affect Standard translation through prompt/style behavior.

Examples of category effects:

- literary prose tone;
- technical precision;
- business terminology;
- philosophy/conceptual wording;
- dialogue/narrative handling where relevant.

## Requirements

- Reuse existing prompt/category logic where possible.
- Avoid duplicating independent prompt taxonomies between Standard and Agentic.
- Category should participate in exact-cache context fingerprinting through generated messages/context.
- Glossary rules remain stronger than stylistic preference.

## Acceptance

- Tests prove different categories produce different relevant prompt context.
- Existing generic behavior remains valid for `general`.
- No UI/server changes are made in this lane.

---

# Priority 3 — Deterministic QA Engine

## Why

Professional translation workflow requires objective checks before using more expensive AI review.

## Target

Create a structured deterministic QA layer.

Priority checks:

```text
missing translation
source residue
number mismatch
glossary violation
named-entity inconsistency
quote mismatch
length anomaly
```

AI QA is optional and secondary.

## Suggested Contract

```python
qa_result = qa_engine.check(
    source=source,
    translated=translated,
    glossary=glossary,
    context=context,
)
```

Structured output should conceptually resemble:

```json
{
  "passed": false,
  "issues": [
    {
      "code": "glossary_violation",
      "severity": "warning",
      "message": "...",
      "expected": "...",
      "actual": "..."
    }
  ]
}
```

## Rules

- Stable machine-readable issue codes.
- Severity must be explicit.
- Deterministic checks must not require model calls.
- False-positive-prone checks should be conservative.
- No fake semantic confidence score.

## Acceptance

Tests cover at minimum:

- correct translation passes basic QA;
- number mismatch;
- glossary violation;
- untranslated/source residue;
- empty translation;
- benign punctuation does not create obvious false failure.

---

# Priority 4 — Translation Memory Retrieval Evolution

## Current

Translation Memory currently supports explicit exact reuse based on matching content identity/language pair.

## Target

Prepare the next retrieval layer:

```text
Exact TM match
↓
Fuzzy TM candidates
↓
Ranked suggestions
```

## Constraints

Do NOT add Redis, vector databases, external search infrastructure, or embedding services without measured evidence that local SQLite/string similarity is insufficient.

Prefer Ngon-Bổ-Rẻ:

- normalization;
- token/string similarity;
- local ranking;
- bounded candidate sets.

Do not silently auto-apply weak fuzzy matches. Fuzzy results are suggestions/context unless confidence is strong and contract explicitly allows reuse.

Because `ebook_translator/db/**` is owned by the other lane/integration, you may implement ranking/retrieval logic around provided candidates or define the persistence query contract needed, but do not modify DB files.

## Acceptance

- Exact match behavior remains unchanged.
- Fuzzy ranking logic has deterministic unit tests.
- Weak candidates are not silently treated as exact approved translation.
- Any required DB query/interface is documented for integration.

---

# Existing Logic to Reuse

Inspect before changing:

```text
ebook_translator/translator/gateway.py
ebook_translator/translator/adapters.py
ebook_translator/translator/pipeline.py
ebook_translator/translator/cache_key.py
ebook_translator/translator/metrics.py
ebook_translator/agent/pipeline.py
```

Reuse existing gateway/cache/TM concepts rather than replacing them wholesale.

---

# Non-Goals

Do NOT implement in this lane:

- job state machine;
- crash recovery/resume orchestration;
- HTTP routes;
- frontend UI;
- Tauri packaging;
- DB schema migrations;
- Cover AI;
- cloud queues;
- unrelated parser/export refactors.

---

# Testing Requirements

At completion run at least:

```text
relevant translation/agent tests
full pytest suite if available
python compileall
git diff --check
```

Do not repair unrelated test failures by modifying files outside your ownership.

If a full-suite failure is caused by an expected shared integration change, document it precisely.

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
- file: ebook_translator/db/database.py
- new method: find_translation_memory_candidates(...)
- input: ...
- output: ...
- why: ...
```

Do not modify the shared file yourself.

---

# Definition of Done for Coder 1

This lane is complete only when:

- category-aware Standard prompting is real and tested;
- context construction exists with deterministic bounds and tests;
- deterministic QA exists with structured issues and tests;
- TM fuzzy ranking foundation exists without weakening explicit/manual approval semantics;
- no provider-specific HTTP escaped the gateway/adapter boundary;
- no files outside ownership were modified;
- all required shared integration contracts are clearly documented.
