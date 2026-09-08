# Round 2 dispositions

Quorum: 2/2 (`claude_code`, `grok`). Canonical consensus: 20 unique findings, 2 confirmed blockers, 1 disagreement.

- Confirmed blocker: `task_type=issue` was not excluded from unfiltered claims. Fixed by planning migration 037 with an enforced claim predicate and RED unfiltered-claim proof.
- Confirmed blocker: submit conflict detection did not pin the bridge envelope. Fixed by matching only `status=error`, `status_code=409`, and `response.detail` in the two safe repair cases; stale and all other errors degrade.
- Claude blocker: same-sequence ESCALATE produces `projection_generation_mismatch`. Fixed by requiring every direct `enter_escalate` phase change to increment `total_iterations` once; `projection_generation_mismatch` remains degraded.
- Claude blocker: connected SSE stops polling and transition events cannot add rows. Fixed by planning a projection-label-change event that produces a fresh change-scoped snapshot, with a connected-client test and no frontend edit.
- Grok nit: proposal retained the old absolute local-tier guarantee. Fixed to match projection-specific D10.
- Claude optionals: pinned lazy `runner.py` import and the 100-row cleanup ceiling. The maximum Autopilot generation count is 51, so the bounded repair query covers the complete projection-row history.
- Latency FYI accepted with a concrete 5-second connected-SSE and polling-fallback budget.

Unresolved blocking findings after inline revision: none known. Round 3 is the maximum and final convergence check.
