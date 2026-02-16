# Proposal Prioritization Report

**Date**: 2026-02-16
**Analyzed Range**: HEAD~50..HEAD (50 commits)
**Proposals Analyzed**: 3

## Priority Order

### 1. complete-missing-coordination-features — Complete Missing Coordination Features (Phases 2-4)
- **Relevance**: Likely Addressed — extensive overlap with existing code
- **Readiness**: N/A (needs verification before further action)
- **Conflicts**: Heavy overlap with #2 and #3 (same `agent-coordinator/src/` files)
- **Scope**: Very Large (99 tasks across 13 groups)
- **Recommendation**: Verify and partially archive. Code audit shows most Phase 2-3 features already exist:
  - **Already implemented**: `src/guardrails.py` (281 LOC), `src/profiles.py` (228 LOC), `src/audit.py` (193 LOC), `src/memory.py` (204 LOC), `src/network_policies.py` (90 LOC), `src/policy_engine.py` (525 LOC), `src/github_coordination.py` (333 LOC), `src/db.py` (285 LOC), `src/db_postgres.py` (244 LOC)
  - **Already implemented**: Migrations 004-010, Cedar schema + default policies, all unit tests (15 test files)
  - **Potentially remaining**: Documentation updates (task group 11), some audit integration hooks (task group 10), verification executor completions (task group 8)
  - Run `/iterate-on-plan complete-missing-coordination-features` to reconcile tasks against actual implementation, then archive completed groups and migrate remaining tasks.
- **Next Step**: `/iterate-on-plan complete-missing-coordination-features`

### 2. add-coordinator-assurance-verification — Coordinator Assurance and Behavioral Verification
- **Relevance**: Needs Verification — some enforcement work done in commits `870f389` and `97fbe66`
- **Readiness**: Blocked (explicitly depends on `complete-missing-coordination-features` per task D1)
- **Conflicts**: Overlaps with #1 on `src/coordination_mcp.py`, `src/work_queue.py`, `src/guardrails.py`, `src/policy_engine.py`, `src/audit.py`; overlaps with #3 on policy engine and Cedar files
- **Scope**: Medium (29 tasks across 6 groups)
- **Recommendation**: Defer until #1 is verified/archived. Recent commits (`870f389` "enforce policy at lock/work write boundaries", `97fbe66` "address PR review — guardrails, audit RLS, profile naming") partially address enforcement remediation (task group 1). Core value is verification infrastructure (property tests, differential tests, TLA+ models) — sections 4-5. Re-assess after #1 reconciliation.
- **Next Step**: Wait for #1 reconciliation, then `/iterate-on-plan add-coordinator-assurance-verification`

### 3. add-dynamic-authorization — Dynamic Authorization Layer
- **Relevance**: Still Relevant — no existing implementation of delegated identity, approval gates, risk scoring, or realtime policy sync
- **Readiness**: Blocked (depends on base capability surfaces from `complete-missing-coordination-features`)
- **Conflicts**: Overlaps with #2 on `src/policy_engine.py`, `src/guardrails.py`, `cedar/` files; overlaps with #1 on `src/coordination_mcp.py`, `src/config.py`
- **Scope**: Large (55 tasks across 8 groups)
- **Recommendation**: Defer. Most advanced proposal (delegated identity, approval gates, risk scoring, realtime policy sync, policy versioning, session grants). All dependencies must land first. Well-structured and ready for implementation once #1 and #2 are resolved.
- **Next Step**: Wait for #1 and #2, then `/implement-feature add-dynamic-authorization`

## Parallel Workstreams

### Stream A (start immediately)
- **complete-missing-coordination-features**: Verify implementation status, archive completed tasks, migrate remaining work

### Stream B (after Stream A)
- **add-coordinator-assurance-verification**: Update plan to reflect landed enforcement work, implement remaining verification infrastructure

### Stream C (after Stream B)
- **add-dynamic-authorization**: Implement new authorization features on hardened, tested foundation

### Parallelization Notes
- **Streams A and B must be sequential** — assurance work depends on reconciliation in `complete-missing-coordination-features`
- **Streams B and C must be sequential** — both modify core coordinator and policy files

## Conflict Matrix

| | complete-missing | assurance-verification | dynamic-authorization |
|---|---|---|---|
| **complete-missing** | — | `coordination_mcp.py`, `work_queue.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `verification_gateway/` | `coordination_mcp.py`, `config.py`, `policy_engine.py`, `cedar/` |
| **assurance-verification** | *(see above)* | — | `policy_engine.py`, `guardrails.py`, `cedar/` |
| **dynamic-authorization** | *(see above)* | *(see above)* | — |

## Proposals Needing Attention

### Likely Addressed
- **complete-missing-coordination-features**: All 13 task groups (0-12) have corresponding implemented code, migrations, and tests. The 0/99 task checkbox status is misleading — the work was done across multiple PRs (#7, #12, and others) without updating the task file. **Action**: Reconcile tasks against implementation, archive completed work, migrate genuine gaps.

### Needs Verification
- **add-coordinator-assurance-verification**: Commits `870f389` and `97fbe66` address enforcement remediation (task group 1). Verify whether remaining assurance tasks (formal verification, property tests, differential tests) are still desired given the project's current priorities.

## Changes Since Last Prioritization (2026-02-14)

- **add-codebase-analysis-architecture**: Fully implemented and archived as `2026-02-14-add-codebase-analysis-architecture` and `2026-02-16-refactor-analysis-architecture`. Removed from active proposals.
- **add-report-config**: Implemented and archived as `2026-02-16-add-report-config`; this covered the architecture report configuration script/file capability.
- Overall active proposal count reduced from 4 to 3.
