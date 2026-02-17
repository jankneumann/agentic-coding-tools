# Skills Workflow

A structured feature development workflow for AI-assisted coding. Skills are reusable Claude Code slash commands that guide features from proposal through implementation to completion, with human approval gates at each stage.

## Overview

The workflow breaks feature development into discrete stages, each handled by a dedicated skill. Every stage ends at a natural approval gate where a human reviews and approves before the next stage begins. This design supports asynchronous workflows where an AI agent can do focused work, then hand off for review.

```
/plan-feature <description>                        Proposal approval gate
  /iterate-on-plan <change-id> (optional)          Refines plan before approval
/implement-feature <change-id>                     PR review gate
  /iterate-on-implementation <change-id> (optional)    Refinement complete
  /validate-feature <change-id> (optional)         Live deployment verification
/cleanup-feature <change-id>                       Done
```

Optional discovery stage before planning:

```
/explore-feature [focus-area]                      Candidate feature shortlist
```

## Step Dependencies

| Step | Depends On | Unblocks |
|---|---|---|
| `/explore-feature` (optional) | Specs + active changes + architecture artifacts | Better-scoped `/plan-feature` inputs |
| `/plan-feature` | Discovery/context | Proposal approval |
| `/iterate-on-plan` (optional) | Existing proposal | Higher-quality approved proposal |
| `/implement-feature` | Approved proposal/spec/tasks | PR review |
| `/iterate-on-implementation` (optional) | Implementation branch | Higher-confidence PR |
| `/validate-feature` (optional) | Implemented branch | Cleanup decision |
| `/cleanup-feature` | Approved PR (+ optional validation) | Archived change + synced specs |

## Artifact Flow By Step

| Step | Consumes | Produces/Updates |
|---|---|---|
| `/explore-feature` | `openspec list`, `openspec list --specs`, `docs/architecture-analysis/*`, `docs/feature-discovery/history.json` (if present) | Ranked candidate list, recommended `/plan-feature` target, `docs/feature-discovery/opportunities.json`, updated `docs/feature-discovery/history.json` |
| `/plan-feature` | Existing specs/changes, architecture context, runtime-native OpenSpec assets or CLI fallback | `openspec/changes/<id>/proposal.md`, `openspec/changes/<id>/specs/**/spec.md`, `openspec/changes/<id>/tasks.md`, optional `openspec/changes/<id>/design.md` |
| `/iterate-on-plan` | Proposal/design/tasks/spec deltas | Updated planning artifacts + `openspec/changes/<id>/plan-findings.md` |
| `/implement-feature` | Proposal/spec/design/tasks context | Code changes, updated `tasks.md`, feature branch/PR |
| `/iterate-on-implementation` | Implementation branch + OpenSpec artifacts | Fix commits + `openspec/changes/<id>/impl-findings.md` (+ spec/proposal/design corrections if drift found) |
| `/validate-feature` | Running system + spec scenarios + changed files | `openspec/changes/<id>/validation-report.md`, `openspec/changes/<id>/architecture-impact.md` |
| `/cleanup-feature` | PR state + `tasks.md` completion | Archived change (`openspec/changes/archive/...`), updated `openspec/specs/`, optional `openspec/changes/<id>/deferred-tasks.md` prior to archive |

## OpenSpec 1.0 Integration

High-level workflow skills stay stable, but their internals follow this precedence:

1. Agent-native OpenSpec assets for the active runtime
2. Direct `openspec` CLI fallback

Runtime asset locations:
- Claude: `.claude/commands/opsx/*.md`, `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml`, `.gemini/skills/openspec-*/SKILL.md`

Cross-agent mapping parity:

| Intent | Claude | Codex | Gemini |
|---|---|---|---|
| Plan (new/ff) | `new`, `ff` | `openspec-new-change`, `openspec-ff-change` | `new`, `ff` |
| Continue/findings | `continue` | `openspec-continue-change` | `continue` |
| Apply | `apply` | `openspec-apply-change` | `apply` |
| Verify | `verify` | `openspec-verify-change` | `verify` |
| Archive | `archive` | `openspec-archive-change` | `archive` |
| Sync | `sync` | `openspec-sync-specs` (alias of sync intent) | `sync` |

CLI fallback commands:
- `openspec new change`
- `openspec status --change <id>`
- `openspec instructions <artifact|apply> --change <id>`
- `openspec archive <id> --yes`

## Core Skills

### `/explore-feature`

Identifies what to build next using architecture diagnostics, active OpenSpec state, and codebase risk/opportunity signals (for example refactoring candidates, usability improvements, performance/cost opportunities).

**Method**:
- Scores opportunities with a weighted model (`impact`, `strategic-fit`, `effort`, `risk`) for reproducible ranking
- Buckets results into `quick-win` and `big-bet`
- Captures explicit `blocked-by` dependencies per candidate
- Uses recommendation history to avoid repeatedly surfacing unchanged deferred work

**Produces**:
- Ranked feature shortlist and one concrete recommendation to start with `/plan-feature`
- `docs/feature-discovery/opportunities.json` (machine-readable current ranking)
- `docs/feature-discovery/history.json` (recommendation history for future prioritization)

**Gate**: None (discovery/support step).

### `/plan-feature`

Creates an [OpenSpec](https://github.com/fission-ai/openspec) proposal for a new feature. The skill gathers context from existing specs and code using parallel exploration agents, then scaffolds a complete proposal with requirements, tasks, and spec deltas using runtime-native OpenSpec assets first and CLI fallback second.

**Produces**: `openspec/changes/<change-id>/` containing `proposal.md`, `tasks.md`, `design.md`, and spec deltas in `specs/`

**Gate**: Proposal approval — the human reviews the proposal before implementation begins.

### `/iterate-on-plan`

Refines an OpenSpec proposal through structured iteration. Each iteration reviews the proposal documents, identifies quality issues across seven dimensions (completeness, clarity, feasibility, scope, consistency, testability, parallelizability), implements fixes, and commits. Repeats until only low-criticality findings remain or max iterations (default: 3) are reached.

**Produces**: Iteration commits improving proposal documents, a parallelizability assessment, and a proposal readiness checklist.

**Gate**: Same as `/plan-feature` — the refined proposal still needs human approval.

### `/implement-feature`

Implements an approved proposal. Works through tasks sequentially or in parallel (for independent tasks with no file overlap), runs quality checks (pytest, mypy, ruff, openspec validate), and creates a PR. Uses runtime-native apply guidance first and `openspec instructions apply` as fallback.

**Produces**: Feature branch `openspec/<change-id>`, passing tests, and a PR ready for review.

**Gate**: PR review — the human reviews the implementation before merge.

### `/iterate-on-implementation`

Refines a feature implementation through structured iteration. Each iteration reviews the code against the proposal, identifies improvements (bugs, edge cases, workflow issues, performance, UX), implements fixes, and commits. Supports parallel fixes for findings targeting different files. Also updates OpenSpec documents if spec drift is detected.

**Produces**: Iteration commits on the feature branch with structured findings summaries.

**Gate**: Same as `/implement-feature` — the refined PR still needs human review.

### `/validate-feature`

Deploys the feature locally with DEBUG logging and runs five validation phases:

1. **Deploy** — Starts services via docker-compose
2. **Smoke** — Verifies health endpoints, auth enforcement, CORS, error sanitization, and security headers
3. **E2E** — Runs Playwright end-to-end tests (if available)
4. **Spec Compliance** — Verifies each OpenSpec scenario against the live system
5. **Log Analysis** — Scans logs for warnings, errors, stack traces, and deprecation notices

Also checks CI/CD status via GitHub CLI. Produces a structured validation report and architecture-impact artifact, persists them to the change directory, and posts report results to the PR.

**Produces**: `openspec/changes/<change-id>/validation-report.md` and a PR comment.

**Gate**: Validation results — the human decides whether to proceed to cleanup or address findings.

### `/cleanup-feature`

Merges the approved PR, migrates any open tasks (to Beads issues or a follow-up OpenSpec proposal), archives the proposal via runtime-native archive guidance or CLI fallback, and cleans up branches.

**Produces**: Merged PR, archived proposal in `openspec/changes/archive/<change-id>/`, updated specs in `openspec/specs/`.

**Gate**: None — this is the final mechanical step.

## Supporting Skills

### `/merge-pull-requests`

Triages, reviews, and merges open PRs from multiple sources: OpenSpec feature PRs, Jules automation PRs, Codex PRs, Dependabot/Renovate PRs, and manual PRs. Includes staleness detection and review comment analysis.

### `/prioritize-proposals`

Analyzes all active OpenSpec proposals against recent commit history. Produces a prioritized "what to do next" report optimized for minimal file conflicts and parallel agent work. Detects proposals that may already be addressed by recent commits or need refinement due to code drift.

### `/update-specs`

Updates OpenSpec spec files to reflect what was actually built. Used after implementation work where debugging, testing, code review, or interactive refinements revealed differences between the original spec and the final implementation.

### `/openspec-beads-worktree`

Coordinates OpenSpec proposals with Beads task tracking and isolated git worktree execution. Implements systematic spec-driven development with parallel agent coordination.

## Design Principles

### Skills map to approval gates

Each skill ends at a natural handoff point where human approval is needed. `/plan-feature` stops at proposal approval, `/implement-feature` stops at PR review. This creates clean boundaries between AI work and human oversight.

### Creative and mechanical work are separated

Planning and implementation are creative work requiring judgment. Cleanup and archival are mechanical. Separating them into different skills allows the mechanical steps to be delegated or automated with higher confidence.

### Iteration happens at both creative stages

Both proposals and implementations benefit from structured refinement. `/iterate-on-plan` catches quality issues before implementation begins, while `/iterate-on-implementation` catches bugs and edge cases before PR review. Each uses domain-specific finding types and quality checks.

### Parallel execution is first-class

Task decomposition in proposals explicitly identifies dependencies and maximizes independent work units. The `Task()` tool with `run_in_background=true` enables concurrent agents without worktrees. File scope isolation via prompts prevents merge conflicts — each agent's prompt lists exactly which files it may modify.

### All planning flows through OpenSpec

Every non-trivial feature starts with an [OpenSpec](https://github.com/fission-ai/openspec) proposal. This creates a traceable record of decisions and requirements. Spec deltas ensure specifications stay updated as features are built.

### Cross-agent parity is explicit

Generated OpenSpec assets for Claude, Codex, and Gemini must map equivalently to plan/apply/validate/archive intent. If one runtime drifts, docs and skill mappings should be corrected before rollout.

## Formal Specification

The skills workflow is formally specified with 14 requirements covering iterative refinement, structured analysis, commit conventions, documentation updates, parallel execution patterns, worktree isolation, and feature validation.

See [`openspec/specs/skill-workflow/spec.md`](../openspec/specs/skill-workflow/spec.md) for the complete specification.
