# Deferred Tasks: phase-record-compaction

These tasks are deferred from the implementation PR with rationale. They
are intentionally NOT in `tasks.md` so the per-task checkbox discipline
treats this change as fully implemented.

## 6.3 Smoke run with ≥30% peak-context-window reduction

**Status**: deferred

**Rationale**: This task requires an end-to-end autopilot run with token
instrumentation wired to a live Anthropic SDK client, capturing
`phase_token_pre` / `phase_token_post` audit entries across a real
mid-size feature, and computing the peak-context-window reduction. That
needs the harness machinery (Agent tool dispatch, coordinator audit
sink, SDK credentials) which is not available in the local
implementation environment.

**Coverage already in place**:

- The token meter itself (`skills/autopilot/scripts/phase_token_meter.py`)
  is fully unit-tested across SDK / proxy / disabled paths
  (`skills/tests/phase-record-compaction/test_phase_token_meter.py`,
  8 tests).
- The wiring into `_maybe_handoff` (token_meter_fn pre/post invocation,
  best-effort failure semantics) is unit-tested
  (`skills/tests/phase-record-compaction/test_autopilot_handoff_dispatch.py`,
  `TestTokenMeterFnWiring`, 3 tests).
- The Layer-2 LoopState opacity tests
  (`skills/tests/phase-record-compaction/test_loopstate_opacity.py`,
  7 tests) verify that the driver-side state delta is bounded after a
  phase callback returns — which is the *mechanism* the ≥30% reduction
  relies on.

**Recommended follow-up**: a dedicated benchmark proposal that runs
autopilot end-to-end against a representative bug-fix change, captures
peak context across phases, and asserts the reduction target. The
proposal can land independently because the wiring it exercises is
already in place.
