# Encode autopilot gates and goal gate in code

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `encode-autopilot-gates-and-goal-gate-in-code`
> Effort: L
> Priority: 1

## Summary

Move the prose gates into autopilot.py — PLAN proposal approval, SUBMIT_PR to DONE merge handoff, ESCALATE resume, and roadmap replan_required with an automated /plan-roadmap replan path — and add an attractor-style goal-gate check that refuses DONE unless VALIDATE/VAL_REVIEW phase records show pass status.

## Dependencies

- `ri-01`
- `ri-02`
- `ri-05`

## Acceptance Outcomes

- Grep of skills/autopilot/SKILL.md finds no gate whose only enforcement is prose.
- An unattended run with an auto-everything posture reaches SUBMIT_PR without interaction; with the default posture it parks exactly where it does today.
- A run whose VALIDATE record is missing or failed cannot reach DONE.
- replan_required re-invokes /plan-roadmap in replan mode when the posture allows.

## Rationale

Human gates living only in SKILL.md text is the primary blocker to unattended operation; validation success must become structurally required at loop exit, not just sequentially prior.
