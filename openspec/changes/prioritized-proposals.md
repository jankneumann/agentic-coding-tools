# Proposal Prioritization Report

**Date**: 2026-02-13
**Analyzed Range**: All 42 commits
**Proposals Analyzed**: 3

## Priority Order

### 1. complete-missing-coordination-features — Complete Missing Coordination Features (Phases 2-4)
- **Relevance**: Likely Addressed — PR #12 (97fbe66) implemented guardrails, profiles, audit, memory, network policies, Cedar policy engine, GitHub coordination, db factory, migrations 004-010, and evaluation extensions. All core modules exist in the codebase.
- **Readiness**: Needs Verification — 0/99 tasks marked complete despite code being landed
- **Conflicts**: Overlaps heavily with both other proposals
- **Recommendation**: Verify implementation completeness against tasks.md, update task status, then archive
- **Next Step**: `openspec archive complete-missing-coordination-features`

### 2. add-coordinator-assurance-verification — Add Coordinator Assurance and Behavioral Verification
- **Relevance**: Still Relevant — Recent commits added the core modules this proposal wants to harden, but the verification infrastructure itself (integration tests for enforcement boundaries, property/stateful tests, differential tests, RLS assertions, TLA+ formal verification) has NOT been built
- **Readiness**: Ready (design doc exists, 22 tasks defined, no blockers)
- **Conflicts**: Overlaps with dynamic-auth on `guardrails.py`, `policy_engine.py`, `audit.py`, `coordination_mcp.py`, `verification_gateway/`
- **Recommendation**: Implement next — hardening existing code before adding new authorization features creates a safety net
- **Next Step**: `/implement-feature add-coordinator-assurance-verification`

### 3. add-dynamic-authorization — Add Dynamic Authorization Layer
- **Relevance**: Still Relevant — Delegated identity, approval gates, risk scoring, Supabase Realtime policy sync, policy versioning, and session-scoped grants are all new features not present in the codebase
- **Readiness**: Ready (design doc exists, 55 tasks defined, no blockers)
- **Conflicts**: Overlaps with assurance-verification on `policy_engine.py`, `guardrails.py`, `audit.py`, `cedar/`, `coordination_mcp.py`
- **Recommendation**: Implement after assurance verification — adding features to an already-hardened codebase is safer, and avoids needing to update assurance tests twice
- **Next Step**: `/implement-feature add-dynamic-authorization`

## Parallel Workstreams

### Stream A (start immediately)
- **complete-missing-coordination-features**: Verify and archive (lightweight — no code changes)

### Stream B (after Stream A archived)
- **add-coordinator-assurance-verification**: Implement (22 tasks, hardening focus)

### Stream C (after Stream B completes)
- **add-dynamic-authorization**: Implement (55 tasks, new features)

### Parallelization Notes
All three proposals conflict on core files (`coordination_mcp.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `config.py`, Cedar files, migrations). **They must be done sequentially.** However, within each proposal, internal tasks can be parallelized by file scope.

## Conflict Matrix

| | assurance-verification | complete-missing | dynamic-auth |
|---|---|---|---|
| **assurance-verification** | — | `coordination_mcp.py`, `work_queue.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `verification_gateway/`, `migrations/` | `coordination_mcp.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `verification_gateway/`, `cedar/`, `migrations/` |
| **complete-missing** | *(see above)* | — | `coordination_mcp.py`, `guardrails.py`, `profiles.py`, `policy_engine.py`, `audit.py`, `config.py`, `cedar/`, `verification_gateway/`, `migrations/` |
| **dynamic-auth** | *(see above)* | *(see above)* | — |

## Proposals Needing Attention

### Likely Addressed
- **complete-missing-coordination-features**: PR #12 (commit 97fbe66) landed all core Phase 2-3 modules. The 99 tasks in `tasks.md` were never updated to reflect completion. Recommended action: audit each task against implemented code, mark completed tasks, then archive the proposal.

### Still Relevant (ordered by priority)
- **add-coordinator-assurance-verification**: Focused on enforcement boundaries, property tests, differential tests, RLS assertions, and TLA+ formal verification. None of this infrastructure exists yet. Smallest scope (22 tasks) and highest value-to-effort ratio.
- **add-dynamic-authorization**: Comprehensive authorization enhancement (delegated identity, approval gates, risk scoring, policy sync). All features are opt-in/backward-compatible. Largest scope (55 tasks) but cleanly isolated new modules.

## Rationale for Ordering

1. **Archive first**: `complete-missing-coordination-features` is implemented but not archived. Leaving it open creates confusion about what work remains. Archiving clears the deck.

2. **Harden before extending**: `add-coordinator-assurance-verification` ensures the existing safety claims actually hold before adding more authorization complexity. Without assurance tests, adding dynamic authorization could mask enforcement gaps.

3. **Extend last**: `add-dynamic-authorization` builds on the hardened foundation. Its 4 new modules (`approval.py`, `risk_scorer.py`, `policy_sync.py`, `session_grants.py`) are cleanly additive and benefit from having enforcement tests already in place.
