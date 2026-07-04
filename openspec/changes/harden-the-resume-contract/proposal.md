# Harden the resume contract

> Parent roadmap: `repo-improvement`
> Change ID: `harden-the-resume-contract`
> Effort: S
> Priority: 2

## Summary

Formalize and test that any fresh session can resume a loop via /autopilot <change-id> --resume and /autopilot-roadmap <workspace> --resume with zero conversational context, adding resume-freshness checks that reconcile or escalate when the branch or checkpoint has moved.

## Dependencies

- None

## Acceptance Outcomes

- A scripted kill-resume test matrix passes for every autopilot phase and roadmap orchestrator step.
- Resume after external branch movement (e.g. a human merge) reconciles or escalates instead of blindly continuing.

## Rationale

Scheduled continuation (ri-08) is only safe if resume from loop-state.json and checkpoint.json is a tested contract rather than a best-effort behavior; this small item unblocks the durability arc.
