# Add trust posture contract file

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `add-trust-posture-contract-file`
> Effort: M
> Priority: 1

## Summary

Adopt the symphony trust-posture-binding item as a repo-owned TRUST_POSTURE.md with typed YAML front matter declaring auto, notify_with_timeout, or block per gate, plus timeout and default action, hot-reloadable.

## Dependencies

- None

## Acceptance Outcomes

- Contract file is schema-validated; unknown gate names or dispositions fail validation.
- All eight enumerated gates (GATEKEEPER escalation, proposal approval, plan-review convergence failure, validation failure, ESCALATE resume, replan_required, PR creation, merge) are representable.
- With no contract file present, behavior is byte-identical to today (every gate is block).

## Rationale

Gates become machine-readable policy objects instead of prose; every later unattended behavior (gate encoding, sync windows, auto-merge ceilings) reads its authorization from this contract.
