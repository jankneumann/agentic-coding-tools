# Make expedite fail closed on missing validation

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `make-expedite-fail-closed-on-missing-validation`
> Effort: S
> Priority: 1

## Summary

Change expedite so a deployable change with no validation-report.md reports BLOCKED instead of a `skip` that rolls up to READY, reusing the `gate_logic` non-deployable / validation-exempt rules that pre_merge_gate already applies.

## Dependencies

- None

## Acceptance Outcomes

- expedite returns BLOCKED for a deployable change with no validation report, and READY remains reachable for a change that gate_logic declares validation-exempt.
- A test asserts the expedite SKILL table and the code's status mapping agree, and fails if either drifts.
- An explicit, recorded operator override for the missing report exists and appears in the expedite output.

## Rationale

expedite.py:101-105 turns a missing report into READY, contradicting the SKILL table's 'run /validate-feature first'; this is the clearest instance of absence treated as a pass and is cheap to close.
