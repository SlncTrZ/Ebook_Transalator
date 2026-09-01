# UI Audit — Translation Workbench Migration

Status: implementation baseline for P1 UI stages A/B.

## Current component map

- `App.tsx`: global tab router + provider state.
- `Library.tsx`: import/upload/delete/select books.
- `TranslateView.tsx`: metadata review + translation start/cancel/progress + legacy export shortcut.
- `MetadataReview.tsx`: research/HITL metadata confirmation.
- `Reader.tsx`: bilingual chunk inspection.
- `GlossaryEditor.tsx`: book glossary CRUD.
- `ExportTab.tsx`: export mode/format/range.
- `Settings.tsx`: provider/model/key configuration.

## Current UX debt

1. Navigation is feature-tab centric instead of book-workflow centric.
2. Book context disappears when moving between tools.
3. Research, translation, inspection, glossary, and export feel like unrelated screens.
4. `TranslateView` duplicates an old export action already handled by `ExportTab`.
5. Chapter-range controls exist in multiple places.
6. Many inline styles prevent consistent design tokens.
7. Emoji icons are used as UI primitives.
8. Empty/error/loading states are inconsistent.
9. Sidebar consumes space without providing active-book operational context.
10. Progress metrics are separated from inspection and correction workflow.

## Target shell

```text
App rail | Book/workflow navigation | Main workspace | Inspector
                                            |
                                            +-- persistent job/status footer
```

The first implementation step keeps existing feature components but mounts them inside a workbench shell. This reduces migration risk while allowing later component-by-component replacement.

## State ownership

- App: selected book, active workspace, provider settings.
- Translation execution: backend canonical chunk state.
- Per-screen filters: local component state.
- Glossary: server-owned book data.
- Metadata/HITL: server-owned after confirmation; local draft only while editing.

## Design tokens

- Neutral dark surfaces; no pure black.
- One accent family: blue.
- Sans-serif software typography; monospace for operational numbers.
- Small radii and 1px borders; no card soup or decorative shadows.
- Motion limited to hover/active/progress transitions.
- Dense desktop-first panes with responsive collapse below 900px.
