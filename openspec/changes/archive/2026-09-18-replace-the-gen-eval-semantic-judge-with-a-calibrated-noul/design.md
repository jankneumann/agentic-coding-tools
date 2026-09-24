# Design: Replace the gen-eval semantic judge with a calibrated Noul

> Change ID: `replace-the-gen-eval-semantic-judge-with-a-calibrated-noul`
> Roadmap item: `ri-04` of `roadmap-jev-system-one-integration-assessment`

## Context

`gen_eval.semantic_judge.evaluate_semantic` (packages/gen-eval/src/gen_eval/semantic_judge.py)
today asks an `LLMBackend` (CLIBackend/SDKBackend/AdaptiveBackend) to return
free-text JSON `{pass, confidence, reasoning}` for a criteria/actual_output
pair, then thresholds the model's own self-reported `confidence` against
`SemanticBlock.min_confidence`. That self-reported confidence is exactly what
`ri-01`'s original proposal calls out as "brittle": nothing calibrates it, and
a verbose LLM prompt is paid on every single evaluation, pass or fail.

This is the first item that gives `system_one_decisions.decide()` (built and
merged in `ri-01`-`ri-03`) a real production call site: gen-eval's own
semantic judge, invoked as a library call inside pytest-executed evaluation
runs, not a standalone CLI script — so it is not the "call-site migration"
`ri-03`'s own reconciled description deferred to `ri-09`+; that phrase refers
specifically to a `--dry-run`-flagged consumer *script*, which gen-eval's
judge is not.

## Non-goals

- **Cohen's-kappa validation.** The original scaffold acceptance outcome
  required scoring a 40-item human-labelled set from
  `calibrate-llm-judge-against-human-labels` and reporting kappa >= 0.7. That
  change is an unimplemented scaffold on a different roadmap
  (`skill-rightsizing`), itself blocked on that roadmap's own `ri-05` — the
  dataset does not exist. Deferred per user decision; see the roadmap's own
  refinement history for `ri-04` (`source: user-request-do-1-defer-kappa`).
- **`event_sink` telemetry wiring.** `decide()` supports an optional
  `event_sink` callback (site/latency/usage/probabilities). gen-eval has no
  existing telemetry sink convention to wire it into; adding one is a
  separate concern from replacing the judge's confidence source.
- **Migrating `use_llm_judgment`/`claude --print`.** `gen-eval-framework`'s
  existing "LLM judgment is opt-in" requirement describes an unrelated,
  orthogonal mechanism (a `use_llm_judgment` scenario/step flag driving a CLI
  judge for ambiguous structural verdicts). This item touches only
  `SemanticBlock`/`evaluate_semantic`.

## Decisions

### D1 — `decide()` replaces the backend as the confidence source; the backend becomes reasoning-only

`evaluate_semantic`'s signature is unchanged:
`evaluate_semantic(backend, semantic, actual_output, step_id) -> SemanticVerdict`.
Internally:

1. `judge=False` still returns `skip` immediately (unchanged).
2. Build `state = {"criteria": criteria_text, "actual_output": actual_output}`
   (the same `criteria_text` fallback the old prompt used) and
   `questions = {"satisfies": {"type": "noul", "instructions": "The actual output satisfies the criteria"}}`
   — a **plain dict**, not an imported `typesafe_sdk.Noul(...)` instance.
   Confirmed by reading the installed SDK directly: `typesafe_sdk._core.questions.normalize_questions`
   accepts either a real `Noul`/`Choice`/`Score` object *or* a dict with a
   non-empty string `"type"` key (the `NoulModel`/`ChoiceModel`/`ScoreModel`
   TypedDict wire form) — so a caller never needs to import the vendor SDK's
   question classes at all. This also keeps `semantic_judge.py` compliant
   with `packages/system-one-decisions/tests/test_no_sdk_import_outside_package.py`,
   a repo-wide (`git ls-files`-scanned) guard from `ri-02` asserting
   `typesafe_sdk` is imported nowhere outside `packages/system-one-decisions/` —
   gen-eval must reach `decide()` without ever importing the SDK it wraps.
3. Call `system_one_decisions.decide(state, questions, site="gen_eval.semantic_judge")`.
4. If `decide()` returns `None` — either because `system_one_decisions` isn't
   importable at all (optional `decisions` extra not installed) or because
   `decide()` itself hit one of its own unavailability branches — return the
   module's existing `skip` verdict (reusing the existing "LLM backend
   unavailable" message shape, generalized to "decision helper unavailable").
   The old `backend.is_available()` check is removed; unavailability is now
   detected by `decide()`'s own `None` return, which already covers every
   case the old check covered plus the new ones.
5. Otherwise read `answers["satisfies"].noul` (a `float` in `[0, 1]`, per the
   real SDK's `NoulAnswer` shape) as `confidence`.
6. If `confidence >= min_confidence`: return `pass` directly. **The LLM
   backend is never called on this path** — this is what makes the
   all-pass/zero-LLM-calls acceptance outcome true.
7. If `confidence < min_confidence`: call the existing `backend.run(prompt,
   system=_JUDGE_SYSTEM)` with the same prompt-building logic as today, parse
   its response with the existing `_parse_verdict` machinery (unchanged,
   still independently unit-tested), and take only its `.reasoning` string.
   Return `fail` with `confidence` from step 5 (the noul value, not
   whatever confidence the backend's own JSON reports) and that `reasoning`.
   If the backend call itself raises, catch it exactly as today and fall
   back to a generic reasoning string — never let a reasoning-generation
   failure turn a `fail` into a `skip` (the pass/fail decision already
   happened in step 5/6, independent of the backend).

`_parse_verdict(raw, min_confidence)` keeps its existing signature and its own
existing unit tests (`TestParseVerdict`) untouched — it's reused verbatim as
a text-parsing helper, just no longer the source of the pass/fail decision
inside `evaluate_semantic`.

### D2 — Guard the optional `system_one_decisions` import, and call it through the module object

`gen-eval`'s `decisions` extra (already declared in `pyproject.toml` from
earlier roadmap scaffolding) makes `system_one_decisions` optional. At module
load, `try: import system_one_decisions except ImportError:
system_one_decisions = None` — the same degrade-gracefully shape every other
optional extra in this repository follows. `evaluate_semantic` checks `if
system_one_decisions is None` and calls `system_one_decisions.decide(...)`
through the module object, never `from system_one_decisions import decide`.
This is required, not stylistic: `system_one_decisions.testing.stub_decide`
(`ri-03`) patches the `decide` attribute on the `system_one_decisions` module
object itself, and its own docstring calls out exactly this gotcha — a
pre-bound `from x import y` reference keeps pointing at the original
function after the patch is applied. Binding to a local name at import time
would silently make every test in Phase 1 stub nothing.

### D3 — Existing tests are adapted with `system_one_decisions.testing.stub_decide`, not left as pure backend mocks

`ri-03` built `system_one_decisions.testing.stub_decide(monkeypatch, *,
returns)` for exactly this situation: a caller of `decide()` that needs a
deterministic answer dict in tests without a real client. `test_semantic_eval.py`'s
`TestEvaluateSemantic` cases are rewritten to `stub_decide` a `{"satisfies":
NoulAnswer-shaped mapping}` return (a plain dict matching `decide()`'s real
return shape — `decide()` returns `response.answers` unchanged, so a stub
only needs to mimic that mapping, not construct a real SDK object) instead of
mocking `backend.is_available`/`backend.run` for the pass/fail path. The
mocked `backend` remains in every test, now asserted on for reasoning-call
*count* (zero on the pass path, one on the fail path) rather than for driving
the verdict.

## Open questions (resolved)

- ~~Which capability do these requirements finally belong to?~~ →
  `gen-eval-framework` (the existing capability documenting gen-eval's
  evaluation behavior). No merged capability spec exists yet for
  `SemanticBlock`/`semantic_judge` specifically — this item's `ADDED
  Requirements` are new, real spec text for existing code, not aspirational.
- ~~What are the non-goals for this item?~~ → see Non-goals above.
- ~~Which decisions here need recording before implementation starts?~~ →
  D1-D3 above.
