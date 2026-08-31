# Proposal Prioritization Report

**Run ID**: `2026-08-31-214046-8825a29`  
**Generated**: 2026-08-31 21:42:50 UTC  
**Analyzed Range**: `HEAD~50..HEAD`  
**OpenSpec Proposals Analyzed**: 62 active changes

## Executive Summary

The next implementation should be `encode-autopilot-gates-and-goal-gate-in-code`.
It is approved, priority 1, and turns the already-shipped trust-posture and approval
services into enforced runtime gates. It is also the named blocker for the
always-on dispatcher and the supervisor's gated execution work.

Two independent streams can proceed beside it: implement
`extend-handoff-document-with-supervisor-record`, and verify/archive the six active
changes whose task lists are already complete. Do not start
`add-supervisor-candidate-work-digest` until the handoff record supplies its
`back_edge` storage contract.

`iterate-traceability-sweep-over-touched-changes` is not the next executable item.
Its implementation merged in PR 435, but its final archive task is blocked by
OpenSpec 1.7.0's inability to express intentional scenario removal from a MODIFIED
requirement. Track that tooling limitation in GitHub issue
[#439](https://github.com/jankneumann/agentic-coding-tools/issues/439); do not use
`--skip-specs` to force the archive.

## Priority Order

### 1. Encode autopilot gates and goal gate in code

- **Change ID**: `encode-autopilot-gates-and-goal-gate-in-code`
- **Roadmap / Priority**: `roadmap-always-on-agent-automation:ri-06`; P1
- **Progress**: 0/39 tasks
- **Readiness**: Approved and unblocked. Its prerequisites -- archetype/apply-outcome
  fixes, compact-hook fixes, and the approval-gate service -- are complete.
- **Value**: Replaces prose-only approval, escalation, validation, PR, merge, and
  replan gates with enforced state-machine checks. It prevents DONE without current
  validation evidence.
- **Dependency leverage**: Directly unlocks the dispatcher daemon and supervisor
  roadmap ri-04.
- **Conflict surface**: Large overlap with `skills/autopilot/`, roadmap runtime,
  `plan-roadmap`, shared gate code, and their tests. Avoid concurrent implementation
  of other autopilot state-machine changes.
- **Recommendation**: Implement now.
- **Command**: `/implement-feature encode-autopilot-gates-and-goal-gate-in-code`

### 2. Extend the handoff document with the supervisor record

- **Change ID**: `extend-handoff-document-with-supervisor-record`
- **Roadmap / Priority**: `roadmap-supervisor-orchestration:ri-05`; P1
- **Progress**: 0/33 tasks
- **Readiness**: Approved; depends only on completed supervisor ri-02.
- **Value**: Makes the supervisor rehydratable by persisting active changes,
  pending gates, standing decisions, and the digest back edge through handoffs.
- **Dependency leverage**: Supplies storage required by supervisor escalation work
  and the candidate-work digest.
- **Conflict surface**: Coordinator handoff APIs, bridge/proxy contracts, session
  hooks, and `skills/supervise/`. This is mostly disjoint from priority 1 and can be
  implemented in parallel with careful contract ownership.
- **Recommendation**: Start as the second implementation stream.
- **Command**: `/implement-feature extend-handoff-document-with-supervisor-record`

### 3. Verify and archive already-complete active changes

Six active changes report every task complete:

| Change | Progress |
|---|---:|
| `rename-descriptor-model-levels` | 11/11 |
| `make-setup-coordinator-script-backed` | 41/41 |
| `inject-scoped-semantic-context-into-coding-jobs` | 40/40 |
| `derive-agent-identity-from-registry` | 24/24 |
| `add-local-model-provider-tier` | 17/17 |
| `extract-gen-eval-package` | 43/43 |

- **Readiness**: Task-complete is not proof of merge/archive readiness. Confirm each
  proposal's PR is merged, no open tasks remain outside `tasks.md`, validation is
  current, and its spec delta can archive cleanly.
- **Value**: Removes false active-work signal and reduces prioritization noise.
- **Conflict surface**: Independent if handled one change at a time; archive may
  reveal spec conflicts with newer changes.
- **Recommendation**: Run as a maintenance stream, not a blind bulk archive.
- **Command**: `/cleanup-feature <change-id> --post-merge --pr <number>` after the
  per-change verification gate passes.

### 4. Add the supervisor candidate-work digest

- **Change ID**: `add-supervisor-candidate-work-digest`
- **Roadmap / Priority**: `roadmap-supervisor-orchestration:ri-13`; P3
- **Progress**: 0/23 tasks
- **Readiness**: Approved, but not ready to start independently.
- **Dependency**: Its proposal explicitly writes digest decisions into the
  `back_edge.digested_stubs[]` contract created by the handoff-record change.
  The roadmap also declares ri-16 ordering, which should be reconciled before
  execution because ri-16 was recently reverted to incomplete.
- **Conflict surface**: `skills/supervise/`, supervisor schemas, and roadmap
  refinement integration.
- **Recommendation**: Queue immediately after priority 2, then refresh dependency
  status before implementation.

### 5. Follow up the prime-agent harness

- **Change ID**: `followup-add-prime-agent-harness`
- **Progress**: 0/33 tasks
- **Readiness**: Planned, but its early work includes empirical, operator, and
  billed validation tasks rather than a purely local implementation start.
- **Conflict surface**: Provider configuration, routing, dispatcher behavior, and
  model-tier work overlap the gate change and several active provider proposals.
- **Recommendation**: Defer until the coded gate work lands and the provider/router
  proposal set is reconciled. Then execute the evidence-gathering tasks before
  changing harness policy.

### 6. Iterate traceability sweep over touched changes

- **Change ID**: `iterate-traceability-sweep-over-touched-changes`
- **Progress**: 4/5 tasks
- **State**: Implementation merged; archive blocked.
- **Blocker**: GitHub issue #439 records the missing OpenSpec scenario-removal
  operation. The canonical spec still contains the stale scenario because the
  current CLI cannot represent its deliberate removal safely.
- **Recommendation**: Leave active and blocked. Resolve upstream/tooling semantics,
  then archive normally; do not force or skip specs.

## Parallel and Sequential Work

### Safe parallel streams

1. Implement coded autopilot/goal gates.
2. Implement the supervisor handoff record, with coordinator/handoff files owned by
   that stream.
3. Verify and archive task-complete proposals one at a time.

### Required sequence

1. Land `extend-handoff-document-with-supervisor-record`.
2. Reconcile supervisor roadmap ri-16 status and dependencies.
3. Implement `add-supervisor-candidate-work-digest`.

Keep `followup-add-prime-agent-harness` behind the gate/configuration work to avoid
designing empirical harness policy against a moving runtime.

## Near-Complete Proposals Requiring Triage

These changes have high task completion, but recent commits touched adjacent
workflow, architecture, and roadmap surfaces. Inspect validation and merge state
before assuming the remaining checkbox count is executable work:

| Change | Progress | Triage action |
|---|---:|---|
| `factory-missions-architecture-alignment` | 51/53 | Identify whether the final tasks are validation, merge, or external blockers. |
| `axi-align-coordinator-output` | 16/18 | Recheck coordinator contract drift. |
| `fix-autopilot-archetype-and-apply-outcome` | 54/59 | Reconcile proposal state with the gate proposal's declared completed prerequisite. |
| `fix-compact-hook-phase-boundary-detection` | 22/25 | Reconcile proposal state with the gate proposal's declared completed prerequisite. |
| `add-frontier-model-tier` | 11/13 | Check overlap with provider and prime-harness follow-up work. |
| `require-validating-roadmap-scaffolds` | 4/5 | Determine whether its last task is an archive/validation step. |

## Backlog Assessment

The remaining inventory contains more than forty 0%-complete proposals. Their
existence alone is not a readiness signal: many predate the last several days of
roadmap-runtime, session-log, coordinator-bridge, architecture-refresh, and
supervisor planning changes. Before scheduling them, refresh their dependency and
scope assumptions and merge or retire duplicates. Prioritize proposals that either
unlock a declared roadmap edge or remove a current operational blocker; do not use
proposal age as the deciding factor.

## Final Recommendation

Run:

```text
/implement-feature encode-autopilot-gates-and-goal-gate-in-code
```

If a second implementation stream is available, run
`/implement-feature extend-handoff-document-with-supervisor-record` concurrently.
Use a third, low-conflict maintenance stream to verify and archive the six
task-complete active changes. After the handoff record lands, implement the
candidate-work digest.
