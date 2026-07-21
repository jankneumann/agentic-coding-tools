# Change Context: enforce-skill-install-portability

## Goal

Make every skill distributed by `skills/install.sh` independently runnable in a
consumer repository that does not contain this source checkout or the
coordinator package.

## Invariants

- Canonical edits land under `skills/`; generated mirrors are updated only by
  `skills/install.sh`.
- Installed runtime dependencies resolve within the installed payload, from
  explicit consumer configuration, or through declared external tools/services.
- Optional coordinator integration may degrade explicitly, but import and help
  paths must never require private `agent-coordinator/src` modules.
- Regression tests execute the real installer into a clean temporary repository.

## Relevant Specs

- `openspec/specs/skill-workflow/spec.md`
- `openspec/specs/merge-pull-requests/spec.md`
- `openspec/specs/coordinator-kanban-viz/spec.md`
- `openspec/specs/worktree/spec.md`

## Known Concurrent Change Overlap

Active proposals may touch `install.sh`, `merge-pull-requests`,
`session-bootstrap`, `validate-feature`, or `skills/shared/`. Keep commits
task-scoped, avoid absorbing unrelated changes, and rebase before delivery.

## Validation Baseline

The synced consumer currently fails at least these probes:

1. `merge-pull-requests/scripts/discover_prs.py --help` (`src` missing)
2. importing `parallel-infrastructure/scripts/result_validator.py`
3. `autopilot/scripts/smoke_provider_dispatch.py --help` (`src.agents_config` missing)

The implementation is complete only when those probes and the manifest-declared
entry points pass from both `.claude/skills` and `.agents/skills` clean installs.
