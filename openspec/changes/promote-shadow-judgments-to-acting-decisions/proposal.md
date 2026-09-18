# Promote shadow judgments to acting decisions

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `promote-shadow-judgments-to-acting-decisions`
> Effort: M
> Priority: 2

## Summary

Using the shadow-period measurements, flip both sites to act: the gate outcome is computed from the calibrated scores with operator-set thresholds, and phase-outcome adjudication applies the switch rule (agreement above act_floor proceeds; disagreement lets the judged label win above approve_floor, otherwise escalate with both labels in the evidence). Retire the premium-tier gatekeeper dispatch.

## Dependencies

- `ri-06`
- `ri-07`

## Acceptance Outcomes

- Promotion is gated on the recorded shadow disagreement rate and vindication split, both cited in the change's rationale with the thresholds chosen from them.
- A test asserts that claimed/judged disagreement below approve_floor transitions to escalate with both labels present in the escalation evidence.
- The premium-tier GATEKEEPER archetype dispatch is removed from the autopilot run path and complexity_gate.default_gate_verdict remains the headless fallback, covered by a headless-run test.
- Per-run judged-call cost for a reference autopilot run is recorded and is under one cent.
- Every promoted decision reaching a report carries evidence_class "judgment" and its probability; no deterministic gate is bypassed, asserted by the scope-safety floor tests.

## Rationale

This is the item that realises the proposal's two headline returns: the largest per-run cost saving (a premium-tier read-only judge replaced by a sub-cent call) and the largest correctness gain (a fixer's self-report no longer trusted). Keeping it separate from the shadow items makes the flip an explicit, evidence-gated decision rather than a side effect.
