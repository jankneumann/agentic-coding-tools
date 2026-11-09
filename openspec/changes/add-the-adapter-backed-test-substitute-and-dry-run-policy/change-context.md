# Change Context: add-the-adapter-backed-test-substitute-and-dry-run-policy

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| system-one-decisions.12 | specs/system-one-decisions/spec.md | `decide()` accepts a `dry_run` flag that guarantees zero client construction | --- | D1 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_dry_run.py (all 4 tests) | pass |
| system-one-decisions.13 | specs/system-one-decisions/spec.md | `system_one_decisions.testing` provides reusable stubs for `decide`/`decide_intent` | --- | D2 | packages/system-one-decisions/src/system_one_decisions/testing.py | tests/test_testing_stubs.py (all 3 tests) | pass |
| system-one-decisions.14 | specs/system-one-decisions/spec.md | Adapter-backed behavioural tests are double-gated and named `uncalibrated` | --- | D3, D4 | packages/system-one-decisions/pyproject.toml, tests/test_decide_adapter_uncalibrated.py, tests/test_adapter_test_naming_guard.py | tests/test_decide_adapter_uncalibrated.py (skips correctly), tests/test_adapter_test_naming_guard.py | pass |

(Requirement numbers continue from `ri-02`'s matrix, which numbered 8-11.)

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — `decide()` gains an explicit `dry_run` parameter | The scaffold's acceptance outcome presumed a `system_one`-consuming script already exists to test `--dry-run` against; none does yet (plan-findings.md #1) | `dry_run: bool = False`, checked first, before the lazy `typesafe_sdk` import | Establishes the enforcement point now; a future script's own `--dry-run` flag just threads into this parameter |
| D2 — `system_one_decisions.testing` submodule, not a new package | Avoids duplicating the package's own import-boundary work; no `pytest11` plugin precedent exists in this repo to imitate (plan-findings.md #3) | `testing.py`: `stub_decide`/`stub_decide_intent`, plain `monkeypatch.setattr` wrappers | Simplest thing that gives every future call-site migration the reusable behavior the acceptance outcome asks for |
| D3 — Double opt-in gate for adapter-backed behavioural tests | A key merely being present in the environment must not be enough to start spending money on a normally-skipped suite (plan-findings.md #4) | `pytest.mark.skipif` requiring both `ANTHROPIC_API_KEY` and `SYSTEM_ONE_ADAPTER_TESTS=1` | Explicit double opt-in, not implicit key-presence detection |
| D4 — Adapter is a drop-in client, no `_core.py` branch logic needed | Confirmed via direct introspection of the real `system-one-adapter` v0.2.0 package: `SystemOneAdapterClient.system_one()` returns the literal same `SystemOneResponse` type `typesafe_sdk` does, and shares the same `TypeSafeError` exception hierarchy | `_get_client` monkeypatched to return a real `SystemOneAdapterClient` in the one behavioural test; `decide()`'s branch logic from `ri-02` is untouched | Duck typing already gives this for free — no design work needed beyond D1's `dry_run` |

## Coverage Summary

- **Requirements traced**: 3/3 (this item's own; `ri-01`'s 7 and `ri-02`'s 4 remain unaffected)
- **Tests mapped**: all 3 requirements have at least one test; 12 new tests added (45 passed + 1 correctly-skipped in the full suite, up from 37)
- **Evidence collected**: 3/3 requirements have pass evidence. `ruff check` and `mypy` clean on every file this item touched.
- **Gaps identified**: the adapter-backed behavioural test's *positive* path (an actual call against Anthropic) is unverified in this environment — no `ANTHROPIC_API_KEY` exists here. Confirmed directly (not just via the test) that the double-gate correctly skips when either env var alone is set, and when both are absent. This is not a deferred item — the acceptance outcomes ask for the tests to exist and skip correctly, both fully verified.
- **Deferred items**: none. `decide_intent()`'s acquisition step remains fallback-only per design.md's non-goals — `ri-04` onward is where consumers start migrating.

## Lockfile propagation (found and fixed during implementation)

The new `test-adapter` extra changed `system-one-decisions`' package metadata,
staling `packages/gen-eval/uv.lock` and `agent-coordinator/uv.lock` (same class
of drift `ri-01`/`ri-02` each hit once). Additionally caught that
`skills/uv.lock` had been stale since `ri-02`'s `dev`/`live` extras — `test-skills`'s
CI job never actually syncs `skills/` itself (it syncs `agent-coordinator` and
runs specific skill tests against that venv), so the staleness never surfaced
as a failure. Relocked all three; verified each consumer's real install command
(`uv sync --all-extras` for gen-eval and skills, the coordinator's exact
`uv sync --locked --all-extras --no-dev --no-install-project`) still succeeds.
