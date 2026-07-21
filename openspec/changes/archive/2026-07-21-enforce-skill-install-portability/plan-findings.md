# Plan Review Findings

## Review 1 — Specification and overlap

- The existing `skill-workflow` capability already defines cross-repository
  portability and sibling-relative infrastructure. This change modifies that
  capability instead of creating a competing capability.
- `coordinator-kanban-viz` currently encodes the reversed classifier dependency;
  its delta explicitly changes ownership to the shipped boundary.
- Concurrent active changes overlap installer, validation, session bootstrap,
  and merge-skill files. Work packages isolate those surfaces and require a
  pre-delivery rebase/conflict check.

Verdict: proceed after adding explicit work-package locks and impacted specs.

## Review 2 — Runtime architecture

- A blanket ban on `parents[2]` would reject valid sibling discovery. Static
  analysis must detect escapes outside the installed root, not syntax alone.
- `setup-coordinator` remains distributable: HTTP mode uses the public bridge;
  source-admin behavior requires an explicit configured coordinator directory.
- Smoke tests should not import every Python file because optional dependencies
  and module side effects exist. The manifest declares safe import/help probes,
  while compilation and static closure checks cover the remaining payload.
- Plain prose mentioning coordinator internals is not a violation. Executable
  snippets, local links, imports, hooks, and subprocess code are.

Verdict: proceed with the manifest-driven dynamic/static split reflected in D5.

## Resolution

All blocking observations are incorporated into `design.md`, `tasks.md`, and
`work-packages.yaml`. No unresolved P0/P1 plan finding remains.
