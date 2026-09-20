# Tasks: Run the GATEKEEPER as a scored decision in shadow mode

> Change ID: `run-the-gatekeeper-as-a-scored-decision-in-shadow-mode`

## Tasks

### Phase 1 — Config-sourced thresholds and the candidate-verdict function (D3)

- [x] 1.1 Create `skills/autopilot/scripts/gatekeeper_shadow.py` with
  `DEFAULT_RISK_ESCALATE_LEVEL`, `DEFAULT_RISK_REVIEW_LEVEL`,
  `DEFAULT_VERIFIABILITY_ESCALATE_LEVEL`, `DEFAULT_VERIFIABILITY_REVIEW_LEVEL`
  and a `ShadowThresholds` dataclass.
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.2 `load_shadow_thresholds()` reads the optional sidecar
  `skills/autopilot/scripts/gatekeeper-shadow.json` (default layer only, no
  project-override layer per D3's Non-goal), falling back to the module
  constants when the file is absent or fails to parse.
  **Dependencies**: 1.1
- [x] 1.3 `compute_candidate_verdict(risk_score, verifiability_score, thresholds)`
  — pure function implementing D3's three-branch threshold logic.
  **Design decisions**: D3
  **Dependencies**: 1.1
- [x] Checkpoint: unit tests for `compute_candidate_verdict` covering all
  three branches plus both boundary-inclusive comparisons (`>=`/`<=`).

### Phase 2 — Shadow judgment call and record shape (D1, D2, D4, D5)

- [x] 2.1 `_work_packages_summary(change_dir)` — reads `work-packages.yaml`
  when present, returns `{"package_count", "package_ids", "has_dependencies"}`
  or `None` when absent.
  **Design decisions**: D5
  **Dependencies**: None
- [x] 2.2 `record_shadow_judgment(state, *, phase, acting_outcome,
  judged_outcome, judgment)` — appends the shared shadow envelope (D4) to
  `state.phase_history`.
  **Design decisions**: D4
  **Dependencies**: None
- [x] 2.3 `_shadow_gatekeeper_judgment(state, change_dir, *, acting_verdict)`
  in `gatekeeper_shadow.py` — builds the state payload (D5), the three
  questions (D2), calls `system_one_decisions.decide(...)` (guarded import,
  module-level `system_one_decisions: ModuleType | None`, looked up as
  `system_one_decisions.decide(...)` at call time per the established
  stubbing rule), and on a usable answer set calls
  `compute_candidate_verdict` then `record_shadow_judgment`. Returns
  early (no side effect) on `None` or a malformed answer set.
  **Design decisions**: D1, D2, D5
  **Dependencies**: 1.3, 2.1, 2.2
- [x] 2.4 Wire `_phase_gatekeeper` to call `_shadow_gatekeeper_judgment` once,
  after computing `outcome` and before `return outcome`, passing the
  already-decided `outcome` as `acting_verdict`. No other line of
  `_phase_gatekeeper` changes.
  **Design decisions**: D1
  **Dependencies**: 2.3
- [x] 2.5 Thread `change_dir` through `_run_phase`'s GATEKEEPER dispatch line
  (D6): `_phase_gatekeeper(state, gatekeeper_fn, gates, change_dir=change_dir)`,
  with `change_dir: Path | None = None` defaulting on `_phase_gatekeeper`
  itself so every existing direct-helper call site keeps working unmodified.
  **Design decisions**: D6
  **Dependencies**: 2.4
- [x] Checkpoint: ran the full `skills/autopilot` test suite, confirmed every
  pre-existing GATEKEEPER test (`test_gatekeeper_degraded.py`, and
  `test_autopilot.py`'s GATEKEEPER section) passes unmodified.

### Phase 3 — Fixture replay, safety proof, and reporting script

- [x] 3.1 `TestGatekeeperShadowFixtureReplay` — replays the two real recorded
  `gate_signals` profiles from `openspec/changes/add-visual-code-explainer/loop-state.json`
  and `openspec/changes/archive/2026-09-13-fix-audit-choices-range-ledger-path/loop-state.json`
  through `_phase_gatekeeper` with a stubbed `system_one_decisions.decide`
  whose `Score` answers would compute a *different* candidate verdict than
  the recorded acting verdict, and asserts: (a) the returned outcome and
  `state.gate_verdict` are byte-identical to the recorded acting verdict for
  each fixture, (b) exactly one `"GATEKEEPER_SHADOW"` `phase_history` entry
  is appended per run, (c) that entry's `judged_outcome` is the
  intentionally-different candidate, proving the shadow judgment never
  leaks into the acting decision.
  **Spec scenarios**: skill-workflow.gatekeeper-shadow-record-per-run,
  skill-workflow.gatekeeper-acting-verdict-unchanged
  **Dependencies**: 2.5
- [x] 3.2 Unavailability tests: `system_one_decisions` module missing,
  `decide()` returning `None`, and a malformed answer set (missing key) each
  leave `state.phase_history` with zero `"GATEKEEPER_SHADOW"` entries and the
  acting verdict unaffected.
  **Spec scenarios**: skill-workflow.gatekeeper-shadow-unavailable-degrades-silently
  **Dependencies**: 2.5
- [x] 3.3 Call-count test: one GATEKEEPER run with a usable shadow judge
  calls `system_one_decisions.decide` exactly once (the three questions are
  batched into a single call, D2).
  **Dependencies**: 2.5
- [x] 3.4 `skills/autopilot/scripts/gatekeeper_shadow_report.py` — CLI
  accepting one or more `loop-state.json` paths (or a glob), extracting every
  `"GATEKEEPER_SHADOW"` entry, printing the disagreement rate and a
  per-outcome-pair breakdown. Unit-tested directly (no LLM calls, satisfies
  the host-assisted invariant).
  **Design decisions**: D7
  **Dependencies**: 3.1
- [x] 3.5 `--force` and scope-safety-floor regression: run the existing
  `test_force_skips_gatekeeper` and `test_force_bypasses_scope_safety_floor_in_init`
  unmodified and confirm they still pass (no shadow entry is recorded when
  `--force` skips GATEKEEPER entirely, since `_phase_gatekeeper` is never
  called).
  **Dependencies**: 2.5
- [x] Checkpoint: ran the full `skills/autopilot` suite plus the new shadow
  tests, `ruff check` clean, confirmed `test_host_assisted_invariant.py`
  still passes with the new reporting script present.

### Phase 4 — Codex-review revision (PR #591)

- [x] 4.1 Extracted `build_shadow_entry(gate_signals, change_dir, *,
  acting_verdict) -> dict | None` as a pure function with no `LoopState`
  dependency; `shadow_gatekeeper_judgment` is now a thin wrapper over it.
  **Design decisions**: D1
  **Dependencies**: None
- [x] 4.2 Wired `phase_agent.apply_phase_outcome` to call
  `build_shadow_entry` and append the result to its own raw-dict
  `phase_history` on the non-replay path, when `phase == "GATEKEEPER"`; new
  `change_dir` parameter threaded from `runner.py`'s `_cmd_apply_outcome`
  (P1 -- the real host-driven GATEKEEPER dispatch protocol never calls
  `_phase_gatekeeper` at all).
  **Design decisions**: D1
  **Dependencies**: 4.1
- [x] 4.3 Moved the shadow call in `_phase_gatekeeper` from immediately
  before `return outcome` to immediately after `state.gate_verdict =
  outcome`, so the escalation approval gate's BLOCKED early return
  (`gates.park(...)`) can no longer skip it (P2).
  **Design decisions**: D1
  **Dependencies**: None
- [x] 4.4 `load_shadow_thresholds` now validates `isinstance(raw, dict)` and
  wraps each field's `float(...)` coercion so a malformed sidecar degrades
  to defaults instead of raising into a real GATEKEEPER phase exception
  (P2).
  **Design decisions**: D3
  **Dependencies**: None
- [x] 4.5 Regression tests: `test_shadow_entry_recorded_even_when_escalation_gate_parks`,
  `TestLoadShadowThresholdsMalformedSidecar` (3 tests), and
  `TestApplyPhaseOutcomeShadowWiring` (4 tests, including a replay test
  proving no duplicate entry and no extra `decide()` call).
  **Dependencies**: 4.1, 4.2, 4.3, 4.4
- [x] Checkpoint: ran the full `skills/autopilot` + `skills/tests/autopilot`
  suite (643 passed, same 2 pre-existing unrelated failures), `ruff check`
  clean, both invariant tests (`test_host_assisted_invariant.py`,
  `test_no_sdk_import_outside_package.py`) still pass.

## Non-goals (out of scope for this item)

- Promoting the shadow verdict to the acting decision (`ri-08`).
- Retiring the premium-tier `gatekeeper_fn` dispatch (`ri-08`).
- A project-override config layer for shadow thresholds beyond one
  default-plus-sidecar file.
- Vindication attribution for a later review round (`ri-07`'s own shadow
  record, not this item's).
