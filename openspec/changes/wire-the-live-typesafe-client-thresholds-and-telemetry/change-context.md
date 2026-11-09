# Change Context: wire-the-live-typesafe-client-thresholds-and-telemetry

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| system-one-decisions.8 | specs/system-one-decisions/spec.md | `decide()` declares a "live" extra and imports the vendor SDK nowhere else | --- | D1, D4 | packages/system-one-decisions/pyproject.toml, packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_no_sdk_import_outside_package.py, tests/test_package_import.py, tests/test_decide_live.py::test_extra_not_installed_returns_none | pass 8a7ed410 |
| system-one-decisions.9 | specs/system-one-decisions/spec.md | `decide()` returns `None`, never raises, on any of four unavailability branches | --- | D1 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_live.py (all 6 tests) | pass 8a7ed410 |
| system-one-decisions.10 | specs/system-one-decisions/spec.md | `decide()` accepts an optional `event_sink`, invoked once per completed call | --- | D2 | packages/system-one-decisions/src/system_one_decisions/_core.py | tests/test_decide_event_sink.py (all 6 tests) | pass 8a7ed410 |
| system-one-decisions.11 | specs/system-one-decisions/spec.md | Threshold defaults resolve from a package-owned data file, never a literal | --- | D3 | packages/system-one-decisions/src/system_one_decisions/{_config.py,config/thresholds.json,_core.py} | tests/test_config_loader.py, tests/test_no_threshold_literals.py | pass 8f8a37e2 |

(Requirement numbers continue from `ri-01`'s matrix, which numbered its own
seven requirements 1-7 in `add-the-shared-system-one-decision-helper-fallback-only/change-context.md`.)

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Four ordered unavailability branches | Every branch must return bare `None`, never raise, matching `ri-01`'s contract exactly | `decide()`'s lazy `import typesafe_sdk`, key check, token estimate, then `except typesafe_sdk.TypeSafeError` around the call, in that order | Checking cheapest/most-common failure first (extra not installed) avoids constructing a client or estimating tokens needlessly |
| D2 — `decide()` gains the same `event_sink` `decide_intent()` already has | Avoids adding a `langfuse` dependency to the package; the "existing Langfuse hook" the original assessment named doesn't actually apply to `decide()` call sites (plan-findings.md #2) | `event_sink: Callable[[dict[str, Any]], None] \| None = None` parameter, invoked once on the success path only | Consistent single telemetry seam across both entry points; caller decides whether/how it reaches Langfuse |
| D3 — Threshold config: package-owned JSON, not `architecture.config.yaml` | That file is scoped to the architecture-report generator and has no threshold concept (plan-findings.md #1); YAML would require adding `pyyaml`, violating `ri-01`'s still-active "no required dependencies" requirement | `src/system_one_decisions/config/thresholds.json` + `_config.py` loader via `importlib.resources`, cached | Only design consistent with both the real target convention (`context-eval`'s own data file) and the zero-required-dependencies constraint |
| D4 — Lazy, cached client construction | `ri-01`'s "no vendor SDK import at module load time" guarantee must survive this item | Module-level `_get_client()` with `functools.lru_cache(maxsize=1)`, called only after the extra-not-installed and key-absent checks pass | Keeps the import lazy while avoiding a new client per call |
| D5 — Test doubles use real SDK types | A hand-rolled fake response shape could silently drift from the real one | Tests import `typesafe_sdk` directly (added to the `dev` extra) to construct real `Choice`/`SystemOneResponse`/`Usage`/`ChoiceAnswer`/`NoulAnswer`/exception instances | "Inside the package" is not a violation of the single-import constraint, which is about runtime code reachable from other packages |

## Coverage Summary

- **Requirements traced**: 4/4 (this item's own; 7/7 from `ri-01` remain unaffected — no existing requirement's behavior changed)
- **Tests mapped**: all 4 requirements have at least one test; 13 new tests added this item (36 total in the package, up from 23)
- **Evidence collected**: 4/4 requirements have pass evidence — `test_config_loader.py`/`test_no_threshold_literals.py` at `8f8a37e2` (Phase 1); `test_decide_live.py`/`test_decide_event_sink.py`/`test_no_sdk_import_outside_package.py`/`test_package_import.py` at `8a7ed410` (Phases 2-3)
- **Gaps identified**: the real live-API success path (an actual network call against `typesafe.ai` with a real `TYPESAFE_API_KEY`) is not exercised anywhere — no credential exists in this environment or in CI. Every success-path assertion runs against a monkeypatched client built from real SDK response types (design D5), which is the same verification depth `ri-01` used for its own unavailable-client-environment testing (no docker daemon there either). This is not a deferred item — the acceptance outcomes only require the four failure branches and the telemetry shape, both fully covered.
- **Deferred items**: `decide_intent()`'s acquisition step remains fallback-only — `ri-03`'s explicit job, per design.md's non-goals.
