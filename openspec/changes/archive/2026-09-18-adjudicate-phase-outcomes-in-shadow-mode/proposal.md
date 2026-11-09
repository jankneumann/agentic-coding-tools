# Adjudicate phase outcomes in shadow mode

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `adjudicate-phase-outcomes-in-shadow-mode`
> Roadmap item: `ri-07`
> Effort: L
> Priority: 1

## Why

Today `phase_agent.apply_phase_outcome` records whatever outcome string a
phase sub-agent claims (`"complete"`, `"failed"`, ...) with no check that the
evidence supports it. A fixer that says `"fixed"` when it did not actually
fix anything costs a full downstream review dispatch to disprove — the
reducer (`transition()`) trusts the label the actor chose for itself.

`ri-06` proved the shadow-recording pattern for GATEKEEPER: a second,
calibrated judgment runs alongside the real decision, records its own
verdict, and never changes what the loop actually does. This item applies
the same pattern to every other phase transition — `Choice(outcome, ...)`
plus `Noul("the evidence supports the claimed outcome")` — so a future item
can flip the reducer to trust the judged label once the shadow period shows
it is trustworthy.

## What Changes

- `phase_agent.apply_phase_outcome` gains an additive adjudication step,
  architected exactly like `ri-06`'s Codex-revised `build_shadow_entry`: a
  pure function with no `LoopState` dependency, called on the real
  production path (`runner.py apply-outcome`), not only from a
  Python-level convenience wrapper. This is a deliberate repeat of `ri-06`'s
  own lesson, not a new decision.
- The adjudication call asks `Choice(outcome, expected_outcomes)` and
  `Noul(evidence_supports_outcome)` over: `expected_outcomes` (from
  `phase_agent._expected_outcomes_for_phase(phase)` — the same source
  `build-dispatch` already uses), the claimed outcome, a `git diff --stat`
  of the phase's worktree, the tail of any recorded test output, and the
  handoff record when one is available locally (see design.md's grounding —
  the coordinator has no read-by-`handoff_id` lookup, so this is the
  local-fallback JSON file, not a coordinator round-trip).
- A shared shadow-record envelope (already generalized in `ri-06` for this
  reuse) records `claimed_outcome`, `judged_outcome`, the `Choice`
  distribution, and the evidence `Noul`, appended to `state.phase_history`.
  `transition()` is never touched.
- A disagreement-attribution mechanism — which side (claimed or judged) a
  later review round's findings vindicated — ships and is tested against a
  fixture-constructed shadow period. Attributing real disagreements over a
  full sprint of production autopilot runs is out of scope for this item
  (see Non-Goals): no such sprint of shadow data exists in this repo yet.

## Impact

- **Affected specs**: `skill-workflow` (adds a shadow-adjudication
  requirement to the generic phase-outcome-application path).
- **Affected code**: `skills/autopilot/scripts/phase_agent.py` (the new
  adjudication step inside `apply_phase_outcome`), new
  `skills/autopilot/scripts/phase_outcome_shadow.py` (the adjudication
  helper, mirroring `gatekeeper_shadow.py`'s shape), new
  `skills/autopilot/scripts/phase_outcome_shadow_report.py` (the
  disagreement-attribution reporting CLI).
- **Risk**: low — every new code path is additive and defensively no-ops on
  any unavailability branch; acceptance outcomes require the claimed outcome
  and `transition()`'s behavior to stay byte-identical, proven by a replay
  test.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Cost | Shadow `decide()` calls per phase transition | Exactly 1 | Unit test on adjudication call count |
| Safety | Claimed-outcome / `transition()` divergence from today's behavior | Zero, for every phase transition | Replay test over a recorded phase sequence |
| Observability | Disagreement attribution over a fixture shadow period | Emitted by `phase_outcome_shadow_report.py` | Test against a constructed fixture (real-sprint measurement deferred) |

## Dependencies

- `ri-06` (establishes the shadow-recording architecture and the shared
  envelope this item reuses).

## Non-Goals

- Attributing real disagreements over a full sprint of production autopilot
  runs — no such data exists in this repo yet; the mechanism is tested
  against a fixture instead.
- Promoting the judged outcome to the acting one, or changing `transition()`
  — a later roadmap item's job (`ri-08` promotes GATEKEEPER; a phase-outcome
  equivalent, if warranted, is a separate future item).
- A coordinator-side lookup of a handoff record by `handoff_id` — the
  coordinator does not support this today (see design.md); this item reads
  the local-fallback file only.
- Capturing `worktree diff stat` / `test-output tail` for phases with no
  worktree or no recorded test output (e.g. `GATEKEEPER`, which `ri-06`
  already covers) — those signals are simply omitted, not fabricated.
