# Run the GATEKEEPER as a scored decision in shadow mode

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `run-the-gatekeeper-as-a-scored-decision-in-shadow-mode`
> Effort: L
> Priority: 1

## Summary

Add shadow-mode recording to the autopilot loop and use it for _phase_gatekeeper: alongside the existing premium-tier judge, ask Score(verifiability, 4 levels), Score(risk, 4 levels) and Choice(verdict, {proceed, proceed_with_review, escalate}) over gate_signals plus proposal.md, tasks.md and the work-packages summary, compute a candidate verdict in code from the two scores, and log it beside the acting verdict without acting on it.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A shadow record per gatekeeper run appends judged verdict, both score distributions and the acting verdict to loop-state.json phase_history, asserted against a fixture run.
- The acting verdict is byte-identical to today's for every run in the shadow period, proven by a replay test over recorded gate_signals.
- The code-computed verdict is derived from the two Score distributions with thresholds read from config; the Choice verdict is recorded only as a cross-check.
- A reporting script emits the GATEKEEPER disagreement rate over the shadow period's runs.
- --force and the scope-safety floor are untouched, covered by existing autopilot tests passing unmodified.

## Rationale

Pilot step 3 and the cleanest fit in the repo: the rubric is already two named dimensions and the gate outcome should be computed in code rather than asserted by the judge, the pattern add-orchestrator-adjudication-review-gate prefers. Shadow mode buys the disagreement measurement before any behaviour change, and this item also lands the shadow plumbing C1 reuses.
