# Tasks: Replace the gen-eval semantic judge with a calibrated Noul

> Change ID: `replace-the-gen-eval-semantic-judge-with-a-calibrated-noul`

## Tasks

### Phase 1 — Rewrite `evaluate_semantic` around `decide()`

- [ ] 1.1 Write `tests/test_semantic_eval.py` cases for the new contract using
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
- [ ] 1.2 Rewrite `evaluate_semantic` in `semantic_judge.py` per design D1:
  build `state`/`questions`, call `system_one_decisions.decide(...,
  site="gen_eval.semantic_judge")`, gate on the returned noul, call the
  backend only on the fail path for reasoning text via the existing prompt
  and `_parse_verdict`. Guard the `system_one_decisions` import per D2.
  **Dependencies**: 1.1
- [ ] 1.3 Write a test asserting `semantic_judge` imports successfully with
  `system_one_decisions` absent (uninstalled `decisions` extra) and every
  evaluation skips in that state.
  **Spec scenarios**: gen-eval-framework.An-unavailable-decision-helper-still-produces-skip-not-fail
  **Design decisions**: D2
  **Dependencies**: 1.2
- [ ] Checkpoint: run `packages/gen-eval/tests/test_semantic_eval.py`,
  confirm green; confirm `TestParseVerdict`'s existing cases pass byte-for-byte
  unmodified (D1: `_parse_verdict` itself is untouched); confirm `ruff`/`mypy`
  clean for `semantic_judge.py`.

## Non-goals (out of scope for this item)

- Cohen's-kappa measurement against a human-labelled set (deferred; see
  design.md Non-goals and the roadmap's own refinement history for `ri-04`).
- Wiring `decide()`'s `event_sink` parameter.
- Any change to `gen-eval-framework`'s existing `use_llm_judgment`/
  `claude --print` mechanism.
- Any change to `_parse_verdict`'s own signature or its existing unit tests.
