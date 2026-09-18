# Change Context: adjudicate-phase-outcomes-in-shadow-mode

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | A shadow record per phase transition appends claimed and judged outcomes with the evidence Noul | --- | D1, D2, D4 | skills/autopilot/scripts/{phase_agent.py,phase_outcome_shadow.py} | tests/test_phase_outcome_shadow.py::TestBuildOutcomeAdjudicationEntry::test_records_claimed_and_judged_outcome_with_evidence_noul, ::TestApplyPhaseOutcomeWiring::test_implement_outcome_gets_adjudicated | pass |
| skill-workflow.2 | specs/skill-workflow/spec.md | transition() runs on the claimed outcome unchanged | --- | D1 | skills/autopilot/scripts/phase_agent.py | tests/test_phase_outcome_shadow.py::TestApplyPhaseOutcomeWiring::test_disagreement_does_not_change_claimed_outcome_or_transition | pass |
| skill-workflow.3 | specs/skill-workflow/spec.md | The adjudication degrades silently on unavailability | --- | D3, D6 | skills/autopilot/scripts/phase_outcome_shadow.py | tests/test_phase_outcome_shadow.py::TestBuildOutcomeAdjudicationEntry::{test_module_unavailable_returns_none, test_decide_returns_none_yields_none, test_every_signal_absent_short_circuits_without_calling_decide, test_malformed_answers_return_none}, ::TestApplyPhaseOutcomeWiring::{test_no_change_dir_records_nothing, test_module_unavailable_records_nothing} | pass |
| skill-workflow.4 | specs/skill-workflow/spec.md | A replayed apply-outcome call does not duplicate the shadow entry | --- | D1 | skills/autopilot/scripts/phase_agent.py | tests/test_phase_outcome_shadow.py::TestApplyPhaseOutcomeWiring::test_replay_does_not_duplicate_entry_or_call_decide_twice | pass |
| skill-workflow.5 | specs/skill-workflow/spec.md | Disagreement attribution is exercised against a fixture shadow period | --- | D5 | skills/autopilot/scripts/phase_outcome_shadow.py | tests/test_phase_outcome_shadow.py::TestAttributeDisagreements (3 tests) | pass |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Adjudication inside `apply_phase_outcome`, on the real production path | `ri-06` discovered by review that the real host-driven dispatch protocol never calls the Python-level phase-handler function; applying that lesson from the start here rather than repeating the mistake | `build_outcome_adjudication_entry` is a pure function called directly from `apply_phase_outcome`'s non-replay path, not from any Python-level convenience wrapper | The real production path (`runner.py apply-outcome`) is the only place every phase transition genuinely executes |
| D2 — Question shape (`Choice(outcome)` + `Noul(evidence)`) | The item's own description names exactly these two questions over exactly this state | One `decide()` call per phase transition with both questions, criteria drawn from `expected_outcomes` | Matches the acceptance outcome literally; keeps shadow cost to one call per transition |
| D3 — Independently best-effort signal gathering | `git diff --stat`, a test-output artifact, and a handoff record can each be absent for unrelated reasons (no worktree yet, no validation report, no local-fallback file) | `git_diff_stat`/`test_output_tail`/`read_local_handoff` each return `None` on any failure; the adjudication call proceeds with whatever subset is available, or records nothing if all are absent | No shadow entry is better than one built on fabricated signals |
| D4 — Shared envelope reused from `ri-06` | Two independent envelope shapes for "claimed vs. judged" would be an unforced inconsistency | `phase_outcome_shadow.py` imports `gatekeeper_shadow._shadow_entry_dict`/`_answer_field`/`_choice_snapshot` directly rather than duplicating them | `ri-06`'s own design already generalized the envelope for exactly this reuse |
| D5 — Attribution mechanism now, real-sprint data later | No sprint of real autopilot shadow data exists in this repo yet — the same grounding gap `ri-04`'s kappa measurement and `ri-06`'s disagreement-rate report both had | `attribute_disagreements(entries, review_findings)` takes the review-vindication signal as an explicit argument and is tested against a constructed fixture; wiring a real reviewer-finding source is deferred | Corrected via `refine-roadmap` before implementation, following the same discipline as `ri-04`/`ri-06`'s own dataset-grounding corrections |
| D6 — No `record_degraded` reuse | `record_degraded` marks the acting GATEKEEPER decision as unchecked — a different signal from "this phase's shadow adjudication was unavailable"; reusing it would corrupt `goal_gate.py`'s own DEGRADED-entry reading for VALIDATE | Unavailability records nothing at all (D3), mirroring `ri-06`'s own precedent | The roadmap's scaffolded acceptance outcome naming `record_degraded` was corrected via `refine-roadmap` before implementation started |

## Coverage Summary

- **Requirements traced**: 5/5.
- **Tests mapped**: all 5 requirements have at least one test; 22 new tests
  in `test_phase_outcome_shadow.py`, 3 in `test_phase_outcome_shadow_report.py`,
  plus one pre-existing `ri-06` test in `test_gatekeeper_shadow.py`
  intentionally updated (`test_non_gatekeeper_phase_records_no_shadow_entry`
  → `test_non_gatekeeper_phase_records_no_gatekeeper_shadow_entry`) to
  reflect that a non-GATEKEEPER phase now legitimately gets its own,
  separate adjudication call.
- **Evidence collected**: 5/5 requirements have pass evidence. Full
  `skills/autopilot` + `skills/tests/autopilot` +
  `skills/tests/openspec_paths` suite: 2124 passed (26 new), plus the same
  2 pre-existing, unrelated `local`-provider health-probe failures already
  documented on `ri-06`'s own PR. `ruff check` clean.
  `test_host_assisted_invariant.py`, `test_no_sdk_import_outside_package.py`,
  and `test_no_test_pins_a_real_change_directory` all pass.
- **Gaps identified**: none.
- **Deferred items**: attributing real disagreements over a full sprint of
  production autopilot runs (no such data exists yet); promoting the
  judged outcome to the acting one (a later roadmap item's job, if
  warranted); unifying `phase_agent._expected_outcomes_for_phase` with
  `autopilot.TRANSITIONS` (pre-existing duplication, unrelated to this item).
