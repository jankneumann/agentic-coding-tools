# Gate drift with mirrors, hooks, and blocking CI

> Parent roadmap: `repo-improvement`
> Change ID: `gate-drift-with-mirrors-hooks-and-blocking-ci`
> Effort: M
> Priority: 1

## Summary

Add install.sh --check plus a CI job that fails when .claude/skills/ or .agents/skills/ drift from canonical skills/, wire core.hooksPath=.githooks into every bootstrap path, adopt or delete orphaned test suites, and promote continue-on-error CI steps (gen-eval mypy --strict blocking, Node job for apps/kanban-viz).

## Dependencies

- None

## Acceptance Outcomes

- Editing a mirror file or forgetting to sync skills/ fails CI via the drift job.
- A fresh clone gets active git hooks with no manual steps.
- No test file in the repo is outside CI, and gen-eval mypy --strict is a blocking step.

## Rationale

Everything later assumes the automation can be trusted; the committed skill mirrors have no drift gate, git hooks are inactive for most clones, and orphaned tests and advisory CI steps erode confidence in the quality machinery the roadmap builds on.
