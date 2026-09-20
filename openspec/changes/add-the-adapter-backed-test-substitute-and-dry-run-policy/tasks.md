# Tasks: Add the adapter-backed test substitute and dry-run policy

> Change ID: `add-the-adapter-backed-test-substitute-and-dry-run-policy`

## Tasks

### Phase 1 — `decide()`'s `dry_run` flag

- [x] 1.1 Write `tests/test_decide_dry_run.py`: `decide(..., dry_run=True)`
  returns `None` and never calls `_get_client` (a client double that raises
  `AssertionError` if constructed, same pattern `ri-02`'s budget-exceeded
  test uses); `decide(..., dry_run=False)` and `decide(...)` (omitted) both
  proceed exactly as `ri-02`'s existing behavior (parametrize over the
  extra-not-installed/key-absent/budget/success paths to prove nothing
  else changed).
  **Spec scenarios**: system-one-decisions.dry_run-short-circuits-before-any-unavailability-check,
  Omitting-dry_run-preserves-existing-behavior
  **Design decisions**: D1
  **Dependencies**: None
- [x] 1.2 Add `dry_run: bool = False` to `decide()`'s signature in
  `_core.py`; check it first, before the lazy `typesafe_sdk` import.
  **Dependencies**: 1.1
- [x] Checkpoint: run `packages/system-one-decisions/tests/test_decide_dry_run.py`
  plus the full existing suite (`test_decide_live.py`, `test_decide_event_sink.py`),
  confirm green — `ri-02`'s tests must pass unchanged since `dry_run` defaults
  to `False`.

### Phase 2 — `system_one_decisions.testing` stubs

- [x] 2.1 Write `tests/test_testing_stubs.py`: `stub_decide(monkeypatch,
  returns=None)` patches `decide` so that a caller's own code built directly
  on `decide()` runs its fallback branch when it checks for `None` (the
  only function of the two that can genuinely return `None` — design D2);
  `stub_decide_intent(monkeypatch, returns=<a Decision>)` patches
  `decide_intent` to return that exact `Decision` deterministically,
  without depending on `decide_intent`'s own always-fallback contract.
  **Spec scenarios**: system-one-decisions.A-stubbed-decide()-lets-the-callers-own-fallback-rule-run-when-it-returns-None,
  system-one-decisions.A-stubbed-decide_intent()-returns-the-caller-configured-Decision
  **Design decisions**: D2
  **Dependencies**: None (parallel to Phase 1)
- [x] 2.2 Implement `system_one_decisions/testing.py`: `stub_decide`,
  `stub_decide_intent`, both thin `monkeypatch.setattr` wrappers over the
  package's own `decide`/`decide_intent` names, exported with no new
  dependency (uses only `pytest`'s `MonkeyPatch` type for the signature,
  already a `dev`-extra dependency).
  **Dependencies**: 2.1
- [x] Checkpoint: run `test_testing_stubs.py`, confirm green; confirm
  `system_one_decisions.testing` imports with zero extras installed (no
  `typesafe_sdk`, no `system_one_adapter` needed for stubbing).

### Phase 3 — Adapter-backed behavioural tests (double opt-in, `uncalibrated` naming)

- [x] 3.1 Add `[project.optional-dependencies] test-adapter =
  ["system-one-adapter[anthropic]>=0.2,<1"]` to
  `packages/system-one-decisions/pyproject.toml`. Run `uv lock`.
  **Dependencies**: None (parallel to Phases 1-2)
- [x] 3.2 Write `tests/test_decide_adapter_uncalibrated.py`: a
  `pytest.mark.skipif` gate requiring both `ANTHROPIC_API_KEY` and
  `SYSTEM_ONE_ADAPTER_TESTS=1`; when both are set, constructs a real
  `system_one_adapter.SystemOneAdapterClient(structured_outputs=True,
  llm_answer_mode="probabilities", provider="anthropic")`, monkeypatches
  `_get_client` to return it, and calls `decide()` end-to-end against it —
  asserting the response shape matches `SystemOneResponse` (same type
  `ri-02` already handles, confirmed via introspection in design.md).
  Every test function name in this file contains `uncalibrated`.
  **Spec scenarios**: system-one-decisions.Behavioural-adapter-tests-skip-when-the-opt-in-env-is-absent,
  Every-adapter-backed-test-name-signals-uncalibrated-probabilities
  **Design decisions**: D3, D4
  **Dependencies**: 3.1, 1.2
- [x] 3.3 Write `tests/test_adapter_test_naming_guard.py`: an AST-based
  guard (same pattern as `ri-02`'s `test_no_sdk_import_outside_package.py`)
  asserting every test function in this package's `tests/` that imports
  `system_one_adapter` has `uncalibrated` in its name.
  **Spec scenarios**: system-one-decisions.Every-adapter-backed-test-name-signals-uncalibrated-probabilities
  **Dependencies**: 3.2
- [x] Checkpoint: run the full `packages/system-one-decisions/tests/` suite
  with `SYSTEM_ONE_ADAPTER_TESTS` unset, confirm the adapter test skips
  (not errors) and everything else stays green; confirm `ruff`/`mypy` clean.
  No `ANTHROPIC_API_KEY` exists in this environment, so the adapter test's
  *positive* path (an actual call against Anthropic) is unverified here —
  its skip path and the naming guard are what's directly testable, matching
  this item's own acceptance outcomes exactly.

## Non-goals (out of scope for this item)

- No migration of any existing call site.
- No `openai` provider wiring.
- No CI job sets `SYSTEM_ONE_ADAPTER_TESTS` — stays local/developer opt-in.
- `decide_intent()`'s acquisition step remains fallback-only.
