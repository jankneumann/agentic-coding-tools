# Tasks: Follow-up to fix-compact-hook-phase-boundary-detection

> Migrated from the parent change's task 6.3 during the 2026-09-08 archive sweep.
> Task number preserves the parent's numbering.

## 1. Conditional lessons-learned entry

**Files**: `docs/lessons-learned.md`
**Dependencies**: none — the parent is merged.

- [ ] 6.3 Determine whether the compact-hook gate semantics have surfaced as a
      recurring debugging touchstone since the parent merged. Evidence to check:
      session logs and handoffs mentioning premature `/compact`, and any repeat of
      the three false-positive classes (sub-agent in flight, stale-mtime touch,
      sibling-worktree handoff).
- [ ] 6.3a If recurring: add the `docs/lessons-learned.md` entry.
- [ ] 6.3b If not recurring: record the negative finding here and close the change
      without touching the doc.
