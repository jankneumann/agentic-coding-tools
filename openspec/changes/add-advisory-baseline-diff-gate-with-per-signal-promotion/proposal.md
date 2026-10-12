# Add advisory baseline-diff gate with per-signal promotion

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `add-advisory-baseline-diff-gate-with-per-signal-promotion`
> Effort: M
> Priority: 4

## Summary

Compare the PR head's signal snapshot with the base branch's last green snapshot and flag any deviation beyond the declared tolerance even when every test passes. The gate starts advisory, and each signal is promoted to blocking individually once its false-positive rate is measured.

## Dependencies

- `ri-07`

## Acceptance Outcomes

- validate-feature attaches the diff against the base branch's last green snapshot to its report.
- A seeded change that doubles an RPC count with all tests green is flagged by the gate.
- Each signal has a recorded mode (advisory/blocking) and a measured false-positive rate, and setting a signal to blocking without a recorded rate is rejected.

## Rationale

This is automated canary analysis for agent PRs, which replaces pass/fail-only verification with signal parity. The advisory-first constraint requires per-signal mode tracking and false-positive measurement before anything blocks.
