# VAL_REVIEW, round 2: route-supervise-gates-through-the-approval-gate-service

You are an independent reviewer verifying a fix pass. Round 1 of this
VAL_REVIEW (see
`openspec/changes/route-supervise-gates-through-the-approval-gate-service/reviews-val/round-1/findings-grok-implementation.json`)
found one CRITICAL and one optional gap:

1. **CRITICAL**: `ApprovalGate.check_filed` (`skills/shared/approval_gate.py`)
   still mapped a coordinator `expired` status with `notified=False` through
   `_apply_default`, returning (and auditing) a fresh `TIMEOUT_BLOCK` decision
   instead of `None`. The skill-workflow spec's "Late coordinator answer"
   scenario (`openspec/changes/route-supervise-gates-through-the-approval-gate-service/specs/skill-workflow/spec.md`,
   search "Late coordinator answer") requires `None` — the existing fail-closed
   block stands unchanged, unaudited again.
2. Optional: canonical `openspec/schemas/gate-decision.schema.json` and the
   change-local `contracts/schemas/gate-decision.schema.json` disagreed on
   `roadmap_fingerprint`/`decision_id` type strictness.

## Your job

Verify commit `b8ce3dd7` (`git show b8ce3dd7` or
`git diff bf0d8cf7..b8ce3dd7` in this repo) actually closes both, and does
not introduce a new gap:

1. Read `_interpret_status` in `skills/shared/approval_gate.py` — the
   `expired` branch should now return `None` when `not notified`, before
   ever calling `_apply_default`. Verify this covers BOTH `check_filed` (a
   later re-check — `None` means "nothing changed") AND `_notify`'s own poll
   loop (a server-side `expired` arriving mid-poll with an undelivered
   notification should read as "keep waiting", NOT resolve the loop early —
   the loop's local-timeout fallback after the deadline still calls
   `_apply_default` directly, unaffected, so a genuinely undelivered
   notification still ends in the correct fail-closed block exactly once).
2. Check `test_check_filed_expired_undelivered_stays_blocked` in
   `skills/shared/tests/test_approval_gate.py` now asserts `decision is None`
   and `audit.records == []`, matching the spec scenario exactly.
3. Check the new `test_notify_server_expired_undelivered_keeps_polling_until_local_timeout`
   test actually exercises the poll-loop path (does it fail if the `not
   notified` check were removed from `_interpret_status`?).
4. Check `skills/tests/supervise/test_gate_router.py`'s
   `test_missing_notified_on_prior_record_is_coerced_to_false_not_none` was
   correctly moved to an `approved`-status re-check (the coercion is no
   longer observable through `expired`, since `None` and `False` now
   collapse to the same `not notified` branch) rather than silently
   weakened.
5. Verify `openspec/schemas/gate-decision.schema.json` now matches
   `contracts/schemas/gate-decision.schema.json` for `roadmap_fingerprint`
   and `decision_id`.

Also do a final broad pass: is there anything else in the trust-boundary
surface (`skills/shared/approval_gate.py`, `skills/supervise/scripts/gate_router.py`,
`skills/supervise/scripts/execution.py`) where a spec scenario and the actual
code diverge, the way this one did? Round 1's other findings (accept/none)
do not need re-verification.

## Output

Write findings as a JSON array conforming to
`openspec/schemas/review-findings.schema.json` to stdout only — do not write
any file. Use the eight-axis schema and five-prefix severity from
`parallel-review-implementation`'s SKILL.md. If the fix holds and nothing new
surfaced, say so explicitly with a `none`-severity finding.
