# Change Context: replace-the-gen-eval-semantic-judge-with-a-calibrated-noul

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| gen-eval-framework.1 | specs/gen-eval-framework/spec.md | `evaluate_semantic` gates on `decide()`'s noul; the LLM backend is never called on the pass path | --- | D1 | packages/gen-eval/src/gen_eval/semantic_judge.py | tests/test_semantic_eval.py::TestEvaluateSemantic::test_confident_noul_passes_with_zero_llm_calls | pass |
| gen-eval-framework.2 | specs/gen-eval-framework/spec.md | A noul below `min_confidence` triggers exactly one LLM call for reasoning prose | --- | D1 | packages/gen-eval/src/gen_eval/semantic_judge.py | tests/test_semantic_eval.py::TestEvaluateSemantic::test_low_confidence_noul_triggers_reasoning_generation | pass |
| gen-eval-framework.3 | specs/gen-eval-framework/spec.md | `decide()` returning `None`, or `system_one_decisions` being unimportable, both produce `skip` not `fail` | --- | D2 | packages/gen-eval/src/gen_eval/semantic_judge.py | tests/test_semantic_eval.py::TestEvaluateSemantic::test_decide_returns_none_produces_skip, tests/test_semantic_eval.py::TestEvaluateSemanticWithoutDecisionsExtra::test_module_unavailable_produces_skip | pass |
| gen-eval-framework.4 | specs/gen-eval-framework/spec.md | `judge=False` skips without calling `decide()` or the backend | --- | D1 | packages/gen-eval/src/gen_eval/semantic_judge.py | tests/test_semantic_eval.py::TestEvaluateSemantic::test_judge_false_skips | pass |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — `decide()` replaces the backend as the confidence source | The old self-reported LLM confidence is exactly the "brittle" pattern the parent roadmap exists to replace; `evaluate_semantic`'s signature stays stable so `evaluator.py`'s one call site needs no change | One `Noul`-shaped question (a plain `{"type": "noul", ...}` dict, never an imported `typesafe_sdk.Noul`) via `system_one_decisions.decide(state, questions, site="gen_eval.semantic_judge")`; the backend is called only from `_generate_failure_reasoning`, only on the fail path | Plain-dict questions keep the vendor SDK out of gen-eval entirely, satisfying `system-one-decisions`' own repo-wide guard test; splitting reasoning into its own helper makes the "zero LLM calls on an all-pass batch" acceptance outcome directly testable |
| D2 — Guard `system_one_decisions` import; call through the module object | `decisions` is an optional gen-eval extra; `system_one_decisions.testing.stub_decide` (`ri-03`) patches the attribute on the `system_one_decisions` module object, not a caller's pre-bound name | `system_one_decisions: ModuleType \| None` declared, then `try/except ImportError` | A `from system_one_decisions import decide` binding would silently make every `stub_decide` call in the test suite a no-op — the module's own docstring calls this out explicitly |
| D3 — Existing/adjacent tests adapted to `stub_decide`, not left as backend mocks | Running the full CI-filtered suite (not just the changed test file) surfaced two pre-existing `test_integration_extended.py` cases that drove pass/fail through the old `backend.is_available`/`run` mocks end-to-end via `Evaluator` | Both adapted to `stub_decide` a noul answer, keeping `Evaluator`'s own code untouched | The regression was real (decide() has no `TYPESAFE_API_KEY` in this env, so it silently returned `skip` where the old mocks expected `pass`/`fail`) — narrower test-file-only verification would have missed it |

## Coverage Summary

- **Requirements traced**: 4/4.
- **Tests mapped**: all 4 requirements have at least one test; `test_semantic_eval.py` has 15 tests (up from 15 in the old suite — same count, entirely rewritten around the new contract plus one new import-guard test); 2 adjacent tests in `test_integration_extended.py` adapted rather than left broken.
- **Evidence collected**: 4/4 requirements have pass evidence. Full CI-equivalent suite (`pytest -m "not e2e and not integration"`) green: 1226 passed, 2 skipped, 45 deselected. `ruff check` and `mypy` clean on `semantic_judge.py`. `packages/system-one-decisions`'s own suite (48 passed, 1 skipped), `ruff`, and `mypy` unaffected by this item's one packaging addition (see below).
- **Gaps identified**: none within this item's own (rescoped) scope.
- **Deferred items**: Cohen's-kappa measurement against a human-labelled set — see design.md Non-goals and the roadmap's own refinement history for `ri-04` (`source: user-request-do-1-defer-kappa`). `decide()`'s `event_sink` telemetry parameter is not wired.

## Cross-package packaging fix (found and fixed during implementation)

`packages/system-one-decisions` shipped without a `py.typed` marker. This
item is the package's first real cross-package consumer under `mypy --strict`
(`ri-01`-`ri-03` only exercised it from within its own test suite), and mypy
correctly refused to type-check `decide()`'s return value from
`semantic_judge.py` without one (`import-untyped`). Added the marker;
confirmed `system-one-decisions`'s own suite, `ruff`, and `mypy` are
unaffected, and no `uv.lock` needed relocking (a marker file changes no
dependency metadata).
