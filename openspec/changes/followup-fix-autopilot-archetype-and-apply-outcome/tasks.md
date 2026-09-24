# Tasks: Follow-up to fix-autopilot-archetype-and-apply-outcome

> Migrated from the parent change's section 11 ("Post-merge follow-up") during the
> 2026-09-08 archive sweep. Task numbers preserve the parent's numbering so the
> archived `tasks.md` and this file can be read side by side.

## 1. Documentation propagation

**Files**: `docs/parallel-agentic-development.md`
**Dependencies**: none — the parent is merged.

- [ ] 11.1 Update `docs/parallel-agentic-development.md` with the new dispatch-prompt
      prohibitions and the `write_capable` archetype field convention.

## 2. Deferred scoping decisions

**Dependencies**: 11.2 wants empirical evidence from autopilot runs since the parent
merged; do not decide it from first principles alone.

- [ ] 11.2 Decide whether structural enforcement of the `loop-state.json` contract
      (filesystem permissions, git hooks) warrants its own change, given whether
      Layer B+C prompt enforcement has proven insufficient empirically. Record the
      decision either way; open a successor proposal only if the answer is yes.
- [ ] 11.3 Decide whether harness-silent-no-op detection warrants its own change.
      Context: `memory/feedback_harness_worktree_silent_noop.md`, and the parent
      proposal's "Out of Scope" section.
