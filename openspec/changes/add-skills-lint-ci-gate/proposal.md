# Gate skills/ on ruff in CI

## Why

`skills/` holds **265 non-test Python files** (plus 365 test files) across 39 skills with
`scripts/` directories. `agent-coordinator/src` holds 73. CI lints and type-checks the 73
and ignores the 265: the `test-infra-skills` job exists but runs only `pytest`.

The cost of that gap is not hypothetical. A single lint pass over the tree found:

- `skills/use-railway/scripts/enable-pg-stats.py:149` calling `run_railway_command`, which
  was never imported — a guaranteed `NameError` on the "restart the service" path, firing
  *after* `shared_preload_libraries` has already been altered, leaving a production
  database reconfigured but never restarted. The function exists in `dal.py:108` with a
  matching signature; it was simply missing from the import list beside its four siblings.
- `refresh-architecture/scripts/tests/test_pipeline_integration.py:352` calling
  `pytest.skip()` without importing `pytest`, so the skip path itself raises.
- `improve-harness/scripts/analyze_failures.py:390` computing a merged, deduplicated
  finding set and then ranking the raw input instead — silently discarding every
  `scan_session_logs()` result from the tool's output.
- `use-railway/scripts/pg-extensions.py:79` shadowing the imported `info()` logger with a
  loop variable.

None of these are style. All were invisible to CI.

## What Changes

- Clean the tree to zero `ruff` findings under an explicit rule set.
- Add `ruff` to `skills/pyproject.toml` and regenerate `uv.lock`.
- Add a blocking `Lint (ruff)` step to the existing `test-infra-skills` job, ordered
  before the install/test steps so a style break fails in seconds.
- Declare `[tool.ruff.lint] select` **explicitly** and ignore `E402` tree-wide.

## Approaches Considered

### Approach A — Fix the tree, then gate blocking *(Selected)*

Auto-fix what is mechanical, hand-fix the rest, configure the genuinely-not-debt rule
away, then turn on a blocking gate against a green baseline.

**Pros**: green baseline; the gate means what it says; found four real bugs on the way.
**Cons**: one large mechanical diff (235 auto-fixes across 135 files).
**Effort**: M

### Approach B — Diff-scoped gate

Lint only files changed in the PR.

**Pros**: green on day one, zero cleanup, blocks all new debt.
**Cons**: the existing bugs — including the production-database `NameError` — stay on main
indefinitely, and the baseline never improves.
**Effort**: S

### Approach C — Gate now with a baseline allowlist

Add the current violations to `per-file-ignores` wholesale and ratchet down later.

**Pros**: fastest to land.
**Cons**: bakes 415 exemptions into config; in practice such allowlists become permanent,
and it would have suppressed the four real bugs rather than surfacing them.
**Effort**: S

### Selected Approach

**Approach A**, chosen by the operator. The bug discoveries validate the choice: B and C
would both have left the `enable-pg-stats.py` `NameError` on main.

## Impact

- **Affected specs**: `harness-engineering` (CI quality gates).
- **Affected code**: 140 files touched by lint fixes; `skills/pyproject.toml`,
  `skills/uv.lock`, `.github/workflows/ci.yml`.
- **Behaviour**: unchanged. Test suite is identical before and after — 1143 passed,
  55 skipped — at every step.

## Out of Scope

- **`mypy` over `skills/`.** It cannot simply be switched on: a naive run aborts because
  `skills/tests/agent-coordinator/` carries an `__init__.py` under a hyphenated (invalid)
  package name, and the flat-import layout needs `MYPYPATH=<skill>/scripts` per skill.
  Separate change.
- **Broadening `select` toward `["E", "F", "I", "N", "W", "UP"]`** to match
  agent-coordinator. That is ~1500 findings and should be done a family at a time.
- **Fixing the `analyze_failures.py` ranking bug**, which changes that tool's output and
  needs its own change. It is marked in place rather than deleted.
- The 18 pre-existing pytest collection errors under `skills/tests/` from module-name
  collisions (`models`, `registry`, `checkpoint` defined in several `skills/*/scripts/`).
