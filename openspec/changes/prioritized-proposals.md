# Proposal Prioritization Report

**Date**: 2026-02-14 13:30
**Analyzed Range**: Last 50 commits (a4d4f35..1cc4d60)
**Proposals Analyzed**: 4

## Priority Order

### 1. add-codebase-analysis-architecture — Add Codebase Analysis Architecture
- **Relevance**: Still Relevant — Proposal was just merged as PR #13 (de477f2), but this is a **proposal only** (spec, design, tasks). Zero implementation code exists. All 85 tasks remain at 0/85.
- **Readiness**: Ready — Approved proposal with design doc, 12 spec requirements, 42 scenarios, 85 tasks, and 10 design decisions. No blockers.
- **Conflicts**: **None** — Entirely new `scripts/` and `.architecture/` directories. No overlap with any coordinator proposal.
- **Scope**: Large (85 tasks) but highly parallelizable — 12 independent task groups, each scoped to separate scripts/files.
- **Recommendation**: Implement next — independent of all coordinator proposals, can run in parallel with any coordinator work.
- **Next Step**: `/implement-feature add-codebase-analysis-architecture`

### 2. complete-missing-coordination-features — Complete Missing Coordination Features (Phases 2-4)
- **Relevance**: Likely Addressed — PR #12 (97fbe66) implemented all core Phase 2-3 modules: guardrails, profiles, audit, memory, network policies, Cedar policy engine, GitHub coordination, db factory, migrations 004-010, evaluation extensions. Recent refine commits (870f389, 9bc1ade, 31bef5b) further hardened enforcement boundaries.
- **Readiness**: Needs Verification — 0/99 tasks marked complete despite code being landed. Validation report confirms tests pass (278 passed, 29 skipped).
- **Conflicts**: Overlaps heavily with both coordinator proposals.
- **Recommendation**: Verify task completion against implemented code, then archive.
- **Next Step**: `openspec archive complete-missing-coordination-features`

### 3. add-coordinator-assurance-verification — Add Coordinator Assurance and Behavioral Verification
- **Relevance**: Partially Addressed — Recent refine commits (870f389, 31bef5b, 9bc1ade) already addressed enforcement remediation tasks (1.1-1.5): policy checks enforced on MCP mutation tools, HTTP endpoints aligned, trust context propagated. However, the core **verification infrastructure** (integration tests for boundaries, property/stateful tests, differential native-vs-Cedar tests, RLS assertions, TLA+ formal models) remains unbuilt.
- **Readiness**: Partially Ready — 29 tasks total, enforcement remediation (~5 tasks) partially addressed by recent commits. Remaining ~24 tasks focused on test/verification infrastructure.
- **Conflicts**: Overlaps with dynamic-auth on `guardrails.py`, `policy_engine.py`, `audit.py`, `coordination_mcp.py`, `verification_gateway/`
- **Recommendation**: Update tasks.md to reflect enforcement work already landed, then implement remaining verification infrastructure.
- **Next Step**: `/iterate-on-plan add-coordinator-assurance-verification` (update tasks to reflect landed work, then implement)

### 4. add-dynamic-authorization — Add Dynamic Authorization Layer
- **Relevance**: Still Relevant — Delegated identity, approval gates, risk scoring, Supabase Realtime policy sync, policy versioning, and session-scoped grants are all new features not present in the codebase.
- **Readiness**: Ready — Design doc exists, 55 tasks defined, no blockers. However, depends on assurance verification being complete first for safety.
- **Conflicts**: Overlaps with assurance-verification on `policy_engine.py`, `guardrails.py`, `audit.py`, `cedar/`, `coordination_mcp.py`
- **Recommendation**: Implement after assurance verification — adding features to an already-hardened and tested codebase is safer.
- **Next Step**: `/implement-feature add-dynamic-authorization`

## Parallel Workstreams

### Stream A (start immediately — independent)
- **add-codebase-analysis-architecture**: Implement (85 tasks, all new files, zero conflict with coordinator work)

### Stream B (start immediately — lightweight)
- **complete-missing-coordination-features**: Verify and archive (no code changes needed)

### Stream C (after Stream B archived)
- **add-coordinator-assurance-verification**: Update plan, then implement remaining verification tasks (~24 tasks)

### Stream D (after Stream C completes)
- **add-dynamic-authorization**: Implement (55 tasks, new features)

### Parallelization Notes
- **Streams A and B can run in parallel** — codebase-analysis touches entirely different files from coordinator work.
- **Streams A and C can run in parallel** — same rationale, no file overlap.
- **Streams C and D must be sequential** — both modify core coordinator files.
- Within `add-codebase-analysis-architecture`, the 12 task groups (schema, Python analyzer, TS analyzer, etc.) are highly parallelizable by file scope.

## Conflict Matrix

| | codebase-analysis | complete-missing | assurance-verification | dynamic-auth |
|---|---|---|---|---|
| **codebase-analysis** | — | none | none | none |
| **complete-missing** | none | — | `coordination_mcp.py`, `work_queue.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `verification_gateway/`, `migrations/` | `coordination_mcp.py`, `guardrails.py`, `profiles.py`, `policy_engine.py`, `audit.py`, `config.py`, `cedar/`, `verification_gateway/`, `migrations/` |
| **assurance-verification** | none | *(see above)* | — | `coordination_mcp.py`, `guardrails.py`, `policy_engine.py`, `audit.py`, `verification_gateway/`, `cedar/`, `migrations/` |
| **dynamic-auth** | none | *(see above)* | *(see above)* | — |

## Proposals Needing Attention

### Likely Addressed
- **complete-missing-coordination-features**: All core modules implemented and landed. Validation report confirms 278 tests passing. The 99 tasks in `tasks.md` were never updated to reflect completion. **Action**: Archive.

### Partially Addressed
- **add-coordinator-assurance-verification**: Enforcement remediation (section 1) partially covered by recent refine commits (870f389, 31bef5b, 9bc1ade). Tasks 1.1-1.5 need re-assessment. Sections 2-6 (verification infrastructure) remain fully unaddressed. **Action**: Update plan, then implement.

### Still Relevant
- **add-codebase-analysis-architecture**: Proposal merged but zero implementation. Independent of all other proposals. **Best candidate for immediate implementation.**
- **add-dynamic-authorization**: All features remain unbuilt. Depends on assurance-verification completing first.

## Rationale for Ordering

1. **Codebase analysis first**: Zero conflicts with any other proposal. Can start immediately and run in parallel with coordinator work. Provides foundational tooling that benefits all future implementation.

2. **Archive complete-missing**: Implemented but not archived. Leaving it open creates confusion. Archiving clears the deck for focused work.

3. **Assurance verification next**: Ensures the existing safety claims hold before adding authorization complexity. Recent refine commits addressed some enforcement gaps, but verification infrastructure (property tests, differential tests, TLA+ models) is the core value of this proposal.

4. **Dynamic authorization last**: Builds on the hardened, tested foundation. Its new modules (`approval.py`, `risk_scorer.py`, `policy_sync.py`) are cleanly additive and benefit from having enforcement tests already in place.
