## ADDED Requirements

### Requirement: Calibrated Noul-Based Semantic Judgment

`evaluate_semantic` MUST obtain its pass/fail confidence for a step by calling
`system_one_decisions.decide()` with a single `Noul` question over
`state={"criteria": ..., "actual_output": ...}` and `site="gen_eval.semantic_judge"`,
rather than parsing a confidence value out of a free-text LLM judge response.
`SemanticBlock.min_confidence` MUST gate on the returned noul value with no
change to `evaluate_semantic`'s public signature.

When `system_one_decisions.decide()` returns `None` — for any of its own
unavailability branches, or because `system_one_decisions` is not importable
at all (the optional `decisions` extra is not installed) — `evaluate_semantic`
MUST return the same `skip` verdict it already returns when the LLM backend is
unavailable, never a `fail`.

The existing LLM backend (the `LLMBackend` Protocol / `_JUDGE_SYSTEM` prompt)
MUST be invoked only to produce human-readable reasoning prose for a step
whose noul confidence is below `min_confidence`. It MUST NOT be invoked for a
step whose noul confidence meets or exceeds `min_confidence`.

#### Scenario: A confident noul produces a pass with zero LLM calls

- **WHEN** `decide()` returns a noul answer at or above `min_confidence`
- **THEN** `evaluate_semantic` returns a `pass` verdict
- **AND** the LLM backend's `run` method is never called

#### Scenario: A low-confidence noul triggers reasoning generation

- **WHEN** `decide()` returns a noul answer below `min_confidence`
- **THEN** `evaluate_semantic` returns a `fail` verdict carrying the noul-derived confidence
- **AND** the LLM backend is called exactly once to produce the verdict's `reasoning` text

#### Scenario: An unavailable decision helper still produces skip, not fail

- **WHEN** `decide()` returns `None`, or `system_one_decisions` cannot be imported
- **THEN** `evaluate_semantic` returns the same `skip` verdict it returns when the LLM backend is unavailable
- **AND** the LLM backend's `run` method is never called

#### Scenario: judge=False still skips without calling decide() or the backend

- **WHEN** `SemanticBlock.judge` is `False`
- **THEN** `evaluate_semantic` returns `skip` without calling `decide()` or the LLM backend
