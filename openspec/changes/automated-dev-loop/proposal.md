# Proposal: Automated Development Loop with Review Convergence

## Change ID
`automated-dev-loop`

## Why

Today the development workflow requires a human operator to invoke each skill sequentially. For simple, well-defined features this manual orchestration is overhead. The existing MVRO infrastructure handles multi-vendor coordination within individual stages — but nothing ties stages together into a self-driving loop. Automating the full plan-to-PR lifecycle for simple features frees human attention for complex architectural decisions.

## Summary

Add an automated development loop that orchestrates the full plan-review-implement-validate-PR lifecycle with multi-vendor review convergence. Given an initial OpenSpec proposal, the system repeatedly dispatches reviews to all configured coding assistants (Claude, Codex, Gemini) until no medium-or-higher-severity findings remain, then proceeds through implementation, validation, fix loops, and PR submission — stopping only at the irreversible merge step for human approval.

## Motivation

Today the development workflow requires a human operator to invoke each skill sequentially (`/plan-feature` -> `/parallel-review-plan` -> `/implement-feature` -> `/validate-feature` -> `/cleanup-feature`). For simple, well-defined features this manual orchestration is overhead. The existing MVRO infrastructure (review dispatch, consensus synthesis, integration gating) already handles multi-vendor coordination within individual stages — but nothing ties the stages together into a self-driving loop.

**Key insight**: The existing convergence gate pattern (consensus synthesis + blocking finding detection) can be generalized into a cross-stage state machine. Each stage transition becomes a gate check: "are all blocking findings resolved?" If yes, advance. If no, fix and re-review.

## Goals

1. **Fully automated simple features**: From proposal to PR with zero human intervention (except final merge approval)
2. **Multi-vendor review convergence**: Every artifact (plan, implementation, validation) reviewed by all available vendors; loop until no medium+ findings from any vendor
3. **Two implementation strategies**: Small/ambiguous packages use alternatives+synthesis; larger packages use lead+review
4. **Memory and handoff continuity**: Cross-stage insights, decisions, and lessons flow via coordinator memory and handoffs
5. **Graceful degradation**: If a vendor is unavailable, continue with reduced quorum; if coordinator is down, fall back to linear workflow
6. **Observable progress**: Each loop iteration produces structured state that can be inspected, resumed, or overridden by a human

## Non-Goals

- Replacing `/cleanup-feature` with automated merge (merge is irreversible)
- Supporting interactive/human-in-the-loop review within the loop (that's the existing manual workflow)
- Handling features that span multiple repositories
- Optimizing for cost — this prioritizes quality convergence over compute efficiency

## Approach

### New Skill: `/auto-dev-loop`

A conductor skill that orchestrates the full lifecycle as a state machine:

```
INIT → PLAN_REVIEW → PLAN_FIX → IMPLEMENT → IMPL_REVIEW → IMPL_FIX → VALIDATE → VAL_FIX → SUBMIT_PR → DONE
```

Each state has:
- **Entry action**: What to do when entering the state
- **Exit gate**: What must be true to advance
- **Max iterations**: Safety cap on fix loops
- **Fallback**: What to do if stuck (escalate to human)

### New Script: `convergence_loop.py`

A reusable review-fix convergence engine that:
1. Dispatches reviews to all available vendors (via `review_dispatcher.py`)
2. Synthesizes consensus (via `consensus_synthesizer.py`)
3. Checks exit condition: no confirmed/unconfirmed findings at medium+ severity
4. If not converged: dispatches fixes to the authoring agent, re-reviews
5. Tracks iteration count, finding trends, and convergence metrics
6. Writes handoff and memory at each iteration

### New Script: `implementation_strategy_selector.py`

Decides per work-package whether to use:
- **Alternatives + synthesis**: 3 vendors produce independent implementations, best parts merged
- **Lead + review**: One vendor implements, others review, fix loop until converged

Selection criteria: package size (LOC estimate), ambiguity level (design alternatives count), and available vendor capacity.

### New Schema: `convergence-state.schema.json`

Tracks the full loop state for resumability:
```yaml
current_phase: "IMPL_REVIEW"
iteration: 2
max_iterations: 3
findings_trend: [12, 5, 1]  # findings per round
convergence_met: false
blocking_findings: [...]
vendor_availability: {claude: true, codex: true, gemini: false}
```

### Integration with Existing Infrastructure

| Component | How It's Used |
|-----------|--------------|
| `review_dispatcher.py` | Dispatches reviews at each convergence gate |
| `consensus_synthesizer.py` | Deduplicates and classifies findings across vendors |
| `integration_orchestrator.py` | Manages implementation package completion gates |
| `dag_scheduler.py` | Schedules work packages respecting dependencies |
| Coordinator handoffs | Stage-to-stage context transfer |
| Coordinator memory | Cross-loop learning (which fix patterns work, which vendors flag which issues) |
| `agents.yaml` | Vendor discovery and CLI configuration |

## Risks

| Risk | Mitigation |
|------|-----------|
| Review oscillation (vendors disagree on fixes) | Max iteration cap (3 rounds default), escalate-to-human on cap hit |
| Severity calibration mismatch across vendors | Shared rubric in review prompt; consensus synthesis takes highest severity |
| Infinite loop on non-convergent findings | Finding trend tracking — if findings aren't decreasing, escalate after 2 flat rounds |
| Vendor unavailability mid-loop | Quorum-based: continue with 2/3; if <2, pause and alert |
| Stale context after many fix iterations | Re-read artifacts at each iteration; don't cache stale state |
| Cost explosion on complex features | Complexity gate at entry: reject features above threshold (LOC, file count, dependency depth) |

## Success Criteria

1. Simple features (< 500 LOC, single work package) complete proposal-to-PR in < 30 minutes with zero human intervention
2. Review convergence achieves zero medium+ findings within 3 rounds for 80%+ of simple features
3. Multi-vendor consensus catches at least 20% more issues than single-vendor review
4. The loop state is fully resumable — interrupting and restarting produces the same outcome
5. Memory accumulates useful cross-feature learning (fix patterns, vendor strengths)
