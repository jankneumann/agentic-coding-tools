# Tasks: Replace the gen-eval semantic judge with a calibrated Noul

> Change ID: `replace-the-gen-eval-semantic-judge-with-a-calibrated-noul`

## Tasks

### Phase 1 — Rewrite `evaluate_semantic` around `decide()`

- [x] 1.1 Write `tests/test_semantic_eval.py` cases for the new contract using
  `system_one_decisions.testing.stub_decide`: a high-noul stub produces
  `pass` with the LLM backend never called; a low-noul stub produces `fail`
  with the noul's own confidence and calls the backend exactly once for
  reasoning; a `stub_decide(returns=None)` stub produces `skip` without
  calling the backend; `judge=False` produces `skip` without calling
  `decide()` or the backend.
  **Spec scenarios**: gen-eval-framework.A-confident-noul-produces-a-pass-with-zero-LLM-calls,
  A-low-confidence-noul-triggers-reasoning-generation,
  An-unavailable-decision-helper-still-produces-skip-not-fail,
  judge=False-still-skips-without-calling-decide()-or-the-backend
  **Design decisions**: D1, D3
  **Dependencies**: None
- [x] 1.2 Rewrite `evaluate_semantic` in `semantic_judge.py` per design D1:
  build `state`/`questions` (a plain `{"type": "noul", ...}` dict, not an
  imported `typesafe_sdk.Noul` -- keeps the repo-wide vendor-SDK-import guard
  test satisfied, see design.md D1), call `system_one_decisions.decide(...,
  site="gen_eval.semantic_judge")` through the module object per D2, gate on
  the returned noul, call the backend only on the fail path for reasoning
  text via `_generate_failure_reasoning` (existing prompt + `_parse_verdict`).
  **Dependencies**: 1.1
- [x] 1.3 Write a test asserting `semantic_judge` degrades to `skip` when its
  own `system_one_decisions` module reference is unavailable (the unit-test
  equivalent of the `decisions` extra not being installed).
  **Spec scenarios**: gen-eval-framework.An-unavailable-decision-helper-still-produces-skip-not-fail
  **Design decisions**: D2
  **Dependencies**: 1.2
- [x] 1.4 Adapt the two pre-existing `test_integration_extended.py` cases
  (`test_semantic_evaluation_via_evaluator`, `test_semantic_fail_causes_step_failure`)
  that exercised the old backend-JSON-driven pass/fail path end-to-end
  through `Evaluator`, to `stub_decide` instead -- these are real regressions
  under the new contract, not covered by `test_semantic_eval.py` alone
  (found by running the full CI-filtered suite, not just the changed file's
  own tests).
  **Dependencies**: 1.2
- [x] 1.5 Add a `py.typed` marker to `packages/system-one-decisions` (it had
  none) -- required for `semantic_judge.py` to type-check `decide()`'s
  return value under `mypy --strict` from a different package; a
  cross-package packaging gap this item's own mypy gate exposed, not a
  behavior change.
  **Dependencies**: 1.2
- [x] Checkpoint: ran `packages/gen-eval/tests/test_semantic_eval.py` (15
  passed) and the full CI-equivalent suite `pytest -m "not e2e and not
  integration"` (1226 passed, 2 skipped, 45 deselected); confirmed
  `TestParseVerdict`'s existing cases pass byte-for-byte unmodified (D1:
  `_parse_verdict` itself is untouched); confirmed `ruff check` and `mypy`
  clean for `semantic_judge.py`; confirmed `packages/system-one-decisions`'s
  own suite (48 passed, 1 skipped), `ruff`, and `mypy` are unaffected by the
  `py.typed` addition.

## Non-goals (out of scope for this item)

- Cohen's-kappa measurement against a human-labelled set (deferred; see
  design.md Non-goals and the roadmap's own refinement history for `ri-04`).
- Wiring `decide()`'s `event_sink` parameter.
- Any change to `gen-eval-framework`'s existing `use_llm_judgment`/
  `claude --print` mechanism.
- Any change to `_parse_verdict`'s own signature or its existing unit tests.
