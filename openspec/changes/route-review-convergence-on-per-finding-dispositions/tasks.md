# Tasks: Route review convergence on per-finding dispositions

> Change ID: `route-review-convergence-on-per-finding-dispositions`

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

- [ ] Add `skills/autopilot/scripts/convergence_disposition.py`: guarded
      `system_one_decisions` import, `_DISPOSITION_CRITERIA`, `classify_round()`
      (one `decide()` call per round, degrades to `{}` on any unavailability),
      `replay_dispatch_counts()` (pure, fixture-driven).
- [ ] Wire `classify_round()` into `convergence_loop.converge()` at step 2k,
      before payload construction: park `defer_to_followup` /
      `reject_out_of_scope` / `needs_human` items via the existing
      `park_item(..., reason=...)`, and only build payloads / call
      `fix_callback` / `mark_addressed` for `fix_now` items. Leave the
      stall check (2j) and the raw `blocking` list used for escalation
      summaries untouched.
- [ ] Unit tests for `convergence_disposition.py`: each disposition routes
      to the right ledger call, unavailability defaults every item to
      `fix_now`, `replay_dispatch_counts()` shows fewer dispatches than the
      old rule for the same terminal blocking count.
- [ ] Integration test in `test_convergence_loop.py`: a round with a mix of
      dispositions dispatches `fix_callback` only for `fix_now` items, and
      the full existing suite passes unchanged (system_one_decisions
      unavailable in CI -> every item defaults to `fix_now`).
- [ ] Update documentation and roadmap completion bookkeeping.
- [ ] Review and merge.
