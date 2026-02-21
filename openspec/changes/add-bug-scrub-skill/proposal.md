# Proposal: Add Bug Scrub and Fix Scrub Skills

## Why

The 5-skill feature workflow generates deferred issues at multiple points — `/iterate-on-implementation` flags "out of scope" findings, `/iterate-on-plan` flags scope overruns, and `/cleanup-feature` produces `deferred-tasks.md` for unchecked tasks. Security review reports and architecture diagnostics also surface non-blocking findings. However, there is no systematic way to **discover, aggregate, and prioritize** these deferred issues alongside code health signals (lint warnings, type errors, test failures, TODO/FIXME markers). Issues accumulate silently until they compound into larger problems.

A `/bug-scrub` + `/fix-scrub` skill pair provides a periodic health check workflow with clean separation of concerns: `/bug-scrub` diagnoses (read-only), `/fix-scrub` remediates (writes code). This bridges the gap between feature-scoped quality gates and project-wide maintenance without requiring a full OpenSpec proposal for routine code health fixes.

## What Changes

### `/bug-scrub` — Diagnostic skill (read-only)

- Add new skill `skills/bug-scrub/SKILL.md` — a diagnostic/support skill (no approval gate, like `/explore-feature` and `/refresh-architecture`)
- Add `skills/bug-scrub/scripts/` directory with Python helpers for:
  - **Signal collection**: Run pytest, ruff, mypy; scan for TODO/FIXME/HACK markers; parse security review reports; parse architecture diagnostics
  - **Deferred issue harvesting**: Scan `impl-findings.md` and `deferred-tasks.md` from active and archived OpenSpec changes for out-of-scope findings
  - **Finding aggregation**: Normalize findings from all sources into a unified schema with severity, source, affected files, and age
  - **Report generation**: Produce a structured markdown report with prioritized findings
- Add `skills/bug-scrub/scripts/models.py` with shared data models for findings (consumed by both skills)

### `/fix-scrub` — Remediation skill (writes code)

- Add new skill `skills/fix-scrub/SKILL.md` — an action skill that consumes the bug-scrub report and applies fixes
- Add `skills/fix-scrub/scripts/` directory with Python helpers for:
  - **Fix planning**: Read bug-scrub report, classify findings as auto-fixable vs agent-fixable vs manual-only, group by file scope for parallel execution
  - **Auto-fix execution**: Apply tool-native fixes (e.g., `ruff check --fix`) for auto-fixable findings
  - **Agent-fix orchestration**: For agent-fixable findings, generate Task() prompts with file scope isolation
  - **Quality verification**: Run quality checks after fixes to confirm no regressions
- Install both skills to agent config directories via existing `skills/install.sh`
- Register both skills in `docs/skills-workflow.md` as supporting skills

## Impact

### Affected Specs

| Spec | Impact |
|------|--------|
| `skill-workflow` | MODIFIED — Add requirements for bug-scrub and fix-scrub as supporting skills |

### Affected Architecture Layers

- **None directly** — these skills consume existing artifacts and apply local code fixes without modifying coordination, trust, or governance layers

### Affected Files

- `skills/bug-scrub/SKILL.md` (new)
- `skills/bug-scrub/scripts/*.py` (new)
- `skills/bug-scrub/tests/*.py` (new)
- `skills/fix-scrub/SKILL.md` (new)
- `skills/fix-scrub/scripts/*.py` (new)
- `skills/fix-scrub/tests/*.py` (new)
- `docs/skills-workflow.md` (modified — add supporting skill entries)
- `openspec/specs/skill-workflow/spec.md` (modified via spec delta)

## Non-Goals

- **Beads issue creation** — the report is the output; the user decides whether to create Beads issues from findings
- **CI integration** — these are on-demand skills, not CI jobs (though findings from CI runs are consumed as input)
- **TypeScript/Node tooling beyond openspec** — initial scope focuses on the Python ecosystem tools (pytest, ruff, mypy) plus openspec validate; TypeScript linting can be added in a follow-up
- **Fixing architecture or design-level issues** — `/fix-scrub` handles code-level fixes (lint, types, markers, deferred patches); findings requiring design changes are reported as manual-only
