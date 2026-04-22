# Proposal Prioritization Report

**Date**: 2026-04-22
**Analyzed Range**: `HEAD~50..HEAD` (50 commits)
**Proposals Analyzed**: 11 active entries (6 in-flight + 5 marked ✓ Complete pending archive)

## Executive Summary

- **7 of 11 proposals can be archived now** — 5 are already marked ✓ Complete; 2 (`replace-beads-with-builtin-tracker`, `tech-debt-analysis`) are effectively implemented but not archived.
- **1 proposal has code-reality drift** (`specialized-workflow-agents`) — `archetypes.yaml` + migration `021_agent_requirements.sql` are committed and 5 skills reference `archetype=` parameters, yet `tasks.md` shows 0/29 complete. Needs status reconciliation before any other action.
- **3 proposals are fresh and relevant** (`add-decision-index`, `add-prototyping-stage`, `harness-engineering-features`). Only one (`add-decision-index`) is safely parallelizable with current in-flight state.

## Priority Order

### 1. `replace-beads-with-builtin-tracker` — Replace Beads with Built-in Coordinator Issue Tracker
- **Relevance**: Likely Addressed — `issue_service.py` exists, migration `017_issue_tracking.sql` landed, commits `196101d chore: remove beads and update docs post-merge` and `b6cd6f5 fix(coordinator): bundle migrations in Docker image, fix issue_create 500` indicate completed + hot-fixed. `.beads/` is empty.
- **Readiness**: N/A — work is done; tasks.md shows 13/17, with the remaining 4 explicitly labeled "deferred to post-merge" and appearing complete in history.
- **Conflicts**: None
- **Recommendation**: Verify migration + issue MCP tools, mark final tasks complete, archive.
- **Next Step**: `/openspec-archive-change replace-beads-with-builtin-tracker` (after checking tasks 4.2–4.5 one by one — especially docs cleanup)

### 2. `tech-debt-analysis` — Tech Debt Analysis Skill
- **Relevance**: Likely Addressed — `proposal.md` itself declares `Status: Implemented`, `skills/tech-debt-analysis/` exists with SKILL.md, scripts, and tests (88 unit tests per proposal).
- **Readiness**: N/A — no `tasks.md`, no `design.md`, no `work-packages.yaml`. Proposal pre-dates the current 5-skill workflow. Specs + proposal only.
- **Conflicts**: None
- **Recommendation**: Verify spec delta matches shipped skill, then archive. May need to backfill `tasks.md` for archival hygiene if the archive tooling requires it.
- **Next Step**: `openspec validate tech-debt-analysis --strict` followed by `/openspec-archive-change tech-debt-analysis`

### 3. Batch Archive — 5 Proposals Marked ✓ Complete
These are flagged complete by `openspec list` but still sit in `openspec/changes/` rather than `openspec/changes/archive/`:
- `speculative-merge-trains` (11d ago)
- `cli-help-discovery` (11d ago)
- `cloudflare-domain-setup` (12d ago)
- `vendor-ux-enhancements` (19d ago)
- `interactive-plan-feature` (19d ago)

- **Relevance**: Likely Addressed
- **Readiness**: N/A
- **Conflicts**: None
- **Recommendation**: Bulk archive.
- **Next Step**: `/openspec-bulk-archive-change speculative-merge-trains,cli-help-discovery,cloudflare-domain-setup,vendor-ux-enhancements,interactive-plan-feature`

### 4. `specialized-workflow-agents` — Specialized Workflow Agents (Archetypes)
- **Relevance**: Needs Refinement — **tasks.md says 0/29 but implementation is landing**. Concrete evidence:
  - `agent-coordinator/archetypes.yaml` exists
  - `agent-coordinator/database/migrations/021_agent_requirements.sql` exists (comment explicitly tags it "Phase 3 of specialized-workflow-agents")
  - `skills/plan-feature/SKILL.md`, `implement-feature/SKILL.md`, `iterate-on-plan/SKILL.md`, `iterate-on-implementation/SKILL.md`, `fix-scrub/SKILL.md` all reference `archetype=` or `model=` parameters
  - Migration `022_add_missing_profile_operations.sql` also recent
- **Readiness**: Partial — code reality is ahead of the plan document.
- **Conflicts**:
  - With `add-prototyping-stage` on `skills/iterate-on-plan/SKILL.md` (prototyping adds `--prototype-context`; archetypes change `Task()` model/archetype params)
  - With `harness-engineering-features` on `agent-coordinator/src/work_queue.py`
- **Recommendation**: **Do not replan — reconcile.** Run `/openspec-verify-change specialized-workflow-agents` to diff spec ↔ code, update `tasks.md` checkboxes to match committed work, then either ship the remainder or archive if already done.
- **Next Step**: `/openspec-verify-change specialized-workflow-agents`

### 5. `add-decision-index` — Per-Capability Decision Index (skill-workflow + software-factory-tooling)
- **Relevance**: Still Relevant — target files (`docs/decisions/`, `decision_index.py`, `backfill_decision_tags.py`) do not exist. Clean greenfield.
- **Readiness**: Ready — 0/25 tasks; well-structured proposal with design, tasks, specs, work-packages all present.
- **Conflicts**: None. Touches `skills/session-log/SKILL.md`, `skills/explore-feature/scripts/`, `Makefile`, `.github/workflows/ci.yml`, `docs/decisions/**`. No overlap with any other active proposal's file set.
- **Recommendation**: **Top pick for new implementation work.** Independent, moderate scope, well-scoped TDD task list.
- **Next Step**: `/implement-feature add-decision-index`

### 6. `add-prototyping-stage` — Prototyping Stage Between Plan and Implement
- **Relevance**: Still Relevant — `skills/prototype-feature/` does not exist, `VariantDescriptor` schema not in `parallel-infrastructure/`.
- **Readiness**: Ready — 0/41 tasks; comprehensive 8-phase TDD plan with contracts, design decisions referenced by task, and work-packages.yaml.
- **Conflicts**:
  - With `specialized-workflow-agents` on `skills/iterate-on-plan/SKILL.md` (both modify the skill; archetypes change `Task()` params while prototyping adds `--prototype-context`)
  - With `harness-engineering-features` on `CLAUDE.md` (both edit the workflow diagram) and `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` (prototyping adds `VariantDescriptor`; harness extends convergence loop)
- **Recommendation**: Start **after** `specialized-workflow-agents` is verified/archived, so iterate-on-plan edits don't collide.
- **Next Step**: `/implement-feature add-prototyping-stage` (sequence after #4)

### 7. `harness-engineering-features` — 7 Features from OpenAI's Harness Engineering
- **Relevance**: Still Relevant — none of the 7 features have landed. `CLAUDE.md` is currently 139 lines (not yet the ~100-line TOC target). `skills/improve-harness/` and `skills/agent-metrics/` do not exist.
- **Readiness**: Needs Planning — 21 tasks across 7 features is sparse for the scope (Feature 1 alone "agent-to-agent review loops" is substantial). Tasks lack work-packages.yaml-level granularity seen in #5 and #6. Specs exist but plan feels like a roadmap, not an implementation plan.
- **Conflicts**:
  - With `specialized-workflow-agents` on `agent-coordinator/src/work_queue.py` (session scope enforcement vs archetype routing)
  - With `add-prototyping-stage` on `CLAUDE.md` and `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
  - With `add-decision-index` indirectly (decision-index adds CI staleness check; harness adds architecture linters phase — both extend CI)
- **Recommendation**: **Split before implementing.** Consider `/plan-roadmap` to decompose into 7 sequenceable sub-proposals. At minimum, separate Features 1 & 3 (review loops, architecture enforcement) from Feature 2 (CLAUDE.md restructure) from Features 5–7 (evaluator profile, scope enforcement, metrics) — they have different conflict surfaces.
- **Next Step**: `/iterate-on-plan harness-engineering-features` OR `/plan-roadmap openspec/changes/harness-engineering-features/proposal.md`

## Parallel Workstreams

### Stream A — Start Immediately (fully independent)
- **A1**: `add-decision-index` — `/implement-feature add-decision-index`
- **A2**: Batch archive — `/openspec-bulk-archive-change speculative-merge-trains,cli-help-discovery,cloudflare-domain-setup,vendor-ux-enhancements,interactive-plan-feature` (administrative, no code conflicts)
- **A3**: Verify + archive `replace-beads-with-builtin-tracker` and `tech-debt-analysis` (sequential within A3; independent of A1)

### Stream A4 — Reconciliation Gate (do before Stream B)
- `specialized-workflow-agents`: `/openspec-verify-change` to reconcile tasks.md with code reality. Until this clears, iterate-on-plan has two pending editors (SWA and prototyping).

### Stream B — After Stream A4 reconciliation (`specialized-workflow-agents` resolved)
- **B1**: `add-prototyping-stage` — unblocked once iterate-on-plan edits from SWA are landed/confirmed

### Sequential — After B1
- `harness-engineering-features` — conflicts with both SWA (work_queue.py) and APS (CLAUDE.md, parallel-infra). Best approach: decompose via `/plan-roadmap` into sub-proposals that can be parallelized with less overlap.

## Conflict Matrix

| | decision-index | prototyping | SWA | harness | replace-beads | tech-debt |
|---|---|---|---|---|---|---|
| **decision-index** | — | none | none | CI workflow (minor) | none | none |
| **prototyping** | none | — | `iterate-on-plan/SKILL.md` | `CLAUDE.md`, `parallel-infrastructure/` | none | none |
| **SWA** | none | `iterate-on-plan/SKILL.md` | — | `work_queue.py` | none | none |
| **harness** | `.github/workflows/ci.yml` | `CLAUDE.md`, `parallel-infra/consensus_synthesizer.py` | `work_queue.py`, `memory.py` | — | none | none |
| **replace-beads** | none | none | none | none | — | none |
| **tech-debt** | none | none | none | none | none | — |

## Proposals Needing Attention

### Likely Addressed (verify and archive)
- `replace-beads-with-builtin-tracker` — all integration commits present; only post-merge cleanup tasks pending. Confirm `.beads/` removal, migration script run, and docs updated.
- `tech-debt-analysis` — skill shipped; proposal declares `Status: Implemented`. Archive workflow may need a stub `tasks.md`.
- 5 already-complete: `speculative-merge-trains`, `cli-help-discovery`, `cloudflare-domain-setup`, `vendor-ux-enhancements`, `interactive-plan-feature`.

### Needs Refinement (update plan to match code before proceeding)
- `specialized-workflow-agents` — **critical**: Phase 2 (`archetypes.yaml`) and Phase 3 (migration 021, `agent_requirements` column, skill model hints) have landed via merge-PR automation but `tasks.md` still shows 0/29. Update checkboxes via `/openspec-verify-change` before planning new work that touches the same files. Documents needing update: `tasks.md` (task status); possibly `proposal.md` "Status" line.

### Needs Decomposition
- `harness-engineering-features` — 7 features, 21 tasks, no work-packages.yaml parallelization plan. Scope + cross-cutting file list (work_queue, memory, CLAUDE.md, consensus_synthesizer, validate-feature) make it too large for one change. Run `/plan-roadmap` to decompose.

## Top Recommendation

Run these in a single session in this order:

1. `/openspec-bulk-archive-change speculative-merge-trains,cli-help-discovery,cloudflare-domain-setup,vendor-ux-enhancements,interactive-plan-feature` (5 min)
2. `/openspec-verify-change specialized-workflow-agents` then archive or finish remainder (30–60 min)
3. `/openspec-verify-change replace-beads-with-builtin-tracker` then archive (15 min)
4. Archive `tech-debt-analysis` (5 min)
5. `/implement-feature add-decision-index` — the only fresh, genuinely independent, fully-planned piece of new work

After steps 1–4, **4 proposals remain** (`add-decision-index`, `add-prototyping-stage`, `harness-engineering-features`, plus whatever's left of SWA), with a clean conflict story and `add-decision-index` ready to go.
