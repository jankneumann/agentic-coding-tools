# Change Context: run-the-gatekeeper-as-a-scored-decision-in-shadow-mode

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | A shadow record per gatekeeper run appends judged verdict, both score distributions and the acting verdict | --- | D1, D2, D4 | skills/autopilot/scripts/{autopilot.py,gatekeeper_shadow.py} | tests/test_gatekeeper_shadow.py::TestShadowGatekeeperJudgment::test_records_one_entry_with_both_distributions_and_acting_verdict | pass |
| skill-workflow.2 | specs/skill-workflow/spec.md | The acting verdict is byte-identical to today's for every run in the shadow period | --- | D1 | skills/autopilot/scripts/autopilot.py | tests/test_gatekeeper_shadow.py::TestPhaseGatekeeperShadowIsolation::test_shadow_disagreement_does_not_change_acting_verdict, ::TestGatekeeperShadowFixtureReplay (both fixtures) | pass |
| skill-workflow.3 | specs/skill-workflow/spec.md | The code-computed verdict is derived from the two Score distributions with thresholds read from config | --- | D3 | skills/autopilot/scripts/gatekeeper_shadow.py | tests/test_gatekeeper_shadow.py::TestComputeCandidateVerdict (6 tests) | pass |
| skill-workflow.4 | specs/skill-workflow/spec.md | The GATEKEEPER shadow judgment degrades silently on unavailability | --- | D1 | skills/autopilot/scripts/gatekeeper_shadow.py | tests/test_gatekeeper_shadow.py::TestShadowGatekeeperJudgment::{test_no_change_dir_records_nothing, test_decide_returns_none_records_nothing, test_malformed_answers_record_nothing, test_module_unavailable_records_nothing} | pass |
| skill-workflow.5 | specs/skill-workflow/spec.md | A reporting script emits the GATEKEEPER disagreement rate over the shadow period's runs | --- | D7 | skills/autopilot/scripts/gatekeeper_shadow_report.py | tests/test_gatekeeper_shadow.py::TestGatekeeperShadowReport (3 tests) | pass |
| skill-workflow.6 | specs/skill-workflow/spec.md | --force and the scope-safety floor are untouched | --- | D1, D6 | skills/autopilot/scripts/autopilot.py | existing test_gatekeeper_degraded.py and test_autopilot.py GATEKEEPER/force suites (unmodified) | pass |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Shadow call inside `_phase_gatekeeper`, strictly additive | The acceptance outcomes require the acting verdict to stay byte-identical; the safest way to guarantee that is to compute it first, unmodified, then append an observational record | One new line before `return outcome` in `_phase_gatekeeper`; `shadow_gatekeeper_judgment` never returns a value `_phase_gatekeeper` reads | Makes "shadow never leaks into acting" a structural property, not a discipline to remember |
| D2 — Question shape (2 Scores + 1 Choice, batched) | The item's own description names exactly these three questions over exactly this state | One `decide()` call per GATEKEEPER run with all three questions | Matches the acceptance outcome literally; keeps shadow cost to one call per run |
| D3 — Thresholds read from config | Mirrors `ri-05`'s `review_rules.py` precedent for exactly this problem ("thresholds read from config," not a literal) | `gatekeeper_shadow.py`'s `ShadowThresholds` + `load_shadow_thresholds()` (default constants + optional sidecar JSON) | Consistency with the one precedent this codebase already established; avoids a bare literal a future review would flag the same way `MATCH_THRESHOLD` was |
| D4 — Shared shadow-record envelope | `ri-07` lands its own shadow record for a different phase transition; a shared envelope shape avoids two incompatible conventions | `record_shadow_judgment(state, *, phase, acting_outcome, judged_outcome, judgment)`, envelope keys fixed, `judgment` payload free-form per caller | Confirmed safe: every existing `phase_history` consumer filters by exact `phase` match, so a new synthetic phase name is inert |
| D5 — Work-packages summary, not a raw dump | The acceptance outcome says "summary," and `decide()`'s own token budget check already degrades gracefully for anything too large | `_work_packages_summary(change_dir)` returns a compact profile; `proposal.md`/`tasks.md` text passed raw, relying on `decide()`'s existing budget check | No new truncation logic to get wrong; mirrors `complexity_gate.gather_signals()`'s own "profile, not dump" philosophy |
| D6 — `change_dir` threading | The shadow judge's state payload needs the plan artifacts, which only `change_dir` can resolve | `_run_phase`'s GATEKEEPER dispatch line passes `change_dir=change_dir`; `_phase_gatekeeper` gains a keyword-only `change_dir: Path | None = None` | Every existing direct-helper call site (`test_gatekeeper_degraded.py`) keeps working unmodified because the default is `None`, which also fully disables the shadow path |
| D7 — Deterministic reporting script | The autopilot host-assisted invariant forbids any direct LLM API call from `skills/autopilot/scripts/` | `gatekeeper_shadow_report.py` reads recorded `loop-state.json` files and computes the disagreement rate with pure arithmetic | Matches `replanner.py`/`policy.py`'s existing precedent for deterministic, non-LLM reporting logic in this package |

## Coverage Summary

- **Requirements traced**: 6/6.
- **Tests mapped**: all 6 requirements have at least one test; 20 new tests
  added in `test_gatekeeper_shadow.py`.
- **Evidence collected**: 6/6 requirements have pass evidence. Full
  `skills/autopilot` + `skills/tests/autopilot` suite: 635 passed (20 new),
  plus the 2 pre-existing, unrelated `local`-provider health-probe failures
  confirmed present on `main` before this change (verified by stashing this
  change's diff and re-running the same two tests). `ruff check` clean.
  `test_host_assisted_invariant.py` and
  `test_no_sdk_import_outside_package.py` both pass.
- **Gaps identified**: none.
- **Deferred items**: promoting the shadow verdict to the acting decision
  and retiring the premium-tier dispatch (`ri-08`); vindication attribution
  for a later review round (`ri-07`'s own shadow record).
