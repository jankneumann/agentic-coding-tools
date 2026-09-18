# Tasks: Wire the live TypeSafe client, thresholds and telemetry

> Change ID: `wire-the-live-typesafe-client-thresholds-and-telemetry`

## Tasks

### Phase 1 — Threshold config file and loader (no SDK dependency yet)

- [x] 1.1 Create `packages/system-one-decisions/src/system_one_decisions/config/thresholds.json`
  (`schema_version: 1`, `defaults: {act_floor: 0.6, approve_floor: 0.9}`) —
  inside the importable package, not the package root, so `importlib.resources`
  can find it in a built wheel (design D3).
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.2 Write `tests/test_config_loader.py`: loading resolves
  `DEFAULT_ACT_FLOOR == 0.6` and `DEFAULT_APPROVE_FLOOR == 0.9` from the file;
  a missing file raises a clear error rather than silently defaulting (fail
  loud on a packaging mistake, not silently on a data mistake).
  **Spec scenarios**: system-one-decisions.Defaults-load-from-the-config-file
  **Dependencies**: 1.1
- [x] 1.3 Implement `_config.py`: `load_thresholds()` (cached, reads the
  packaged JSON via `importlib.resources`, not a relative filesystem path, so
  it works from an installed wheel) and module-level `DEFAULT_ACT_FLOOR`,
  `DEFAULT_APPROVE_FLOOR` constants.
  **Dependencies**: 1.2
- [x] 1.4 Update `_core.py`: `_route()`'s and `decide_intent()`'s
  `act_floor: float = 0.6` / `approve_floor: float = 0.9` become
  `act_floor: float = DEFAULT_ACT_FLOOR` / `approve_floor: float =
  DEFAULT_APPROVE_FLOOR`, importing both from `_config`.
  **Dependencies**: 1.3
- [x] 1.5 Write `tests/test_no_threshold_literals.py`: an AST-based guard
  (stronger than a plain grep — walks `_core.py`'s function defs and checks
  each `act_floor`/`approve_floor` keyword-only parameter's default node
  isn't a bare `ast.Constant`) asserting no bare float literal used in an
  `act_floor`/`approve_floor` position.
  **Spec scenarios**: system-one-decisions.No-threshold-literal-in-scoring-logic
  **Design decisions**: D3
  **Dependencies**: 1.4
- [x] Checkpoint: ran `uv run pytest tests/` inside
  `packages/system-one-decisions/` (23 passed) — `ri-01`'s existing
  route/decide_intent tests pass unchanged since their literal `0.6`/`0.9`
  defaults became named constants of the same value. `ruff check` (only the
  one issue in this item's own new test file, fixed) and `mypy` both clean.

### Phase 2 — `live` extra and lazy client construction

- [x] 2.1 Add `[project.optional-dependencies] live = ["typesafe-sdk>=0.7,<1"]`
  to `packages/system-one-decisions/pyproject.toml` (also added to `dev`,
  since the test suite constructs real SDK types — design D5). Ran `uv lock`
  in `packages/system-one-decisions/`.
  **Spec scenarios**: system-one-decisions.Fallback-only-install-succeeds-without-the-live-extra
  **Dependencies**: None (parallel to Phase 1)
- [x] 2.2 Write `tests/test_no_sdk_import_outside_package.py`: an AST-based
  guard over `git ls-files '*.py'` (not a hand-maintained exclusion list —
  scoping to git-tracked files excludes `.venv`/`node_modules`/
  `.git-worktrees` for free, and survives new vendor directories appearing)
  asserting no file outside `packages/system-one-decisions/` imports
  `typesafe_sdk`.
  **Spec scenarios**: system-one-decisions.No-other-package-or-skill-imports-the-vendor-SDK
  **Dependencies**: 2.1
- [x] 2.3 Write `tests/test_decide_live.py` covering, in order: extra not
  installed (`monkeypatch.setitem(sys.modules, "typesafe_sdk", None)` to
  force the `ImportError` branch deterministically, since `typesafe_sdk` is
  genuinely importable in this dev/test environment via the `dev` extra);
  key absent (`monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)`); token
  budget exceeded (a synthetic 200K-char `state`, asserted via a client
  double that raises `AssertionError` if constructed, proving no network
  attempt); network/API failure, parametrized over
  `typesafe_sdk.TypeSafeAPIConnectionError` and
  `typesafe_sdk.TypeSafeAuthenticationError` (constructed with its real
  `status`/`body`/`headers` signature) raised from a monkeypatched client's
  `system_one()` — plus one success-path test proving `decide()` returns the
  real `response.answers` dict unchanged.
  **Spec scenarios**: system-one-decisions.decide()-returns-None,-never-raises,-on-any-of-four-unavailability-branches
  (all four scenarios)
  **Design decisions**: D1, D4
  **Dependencies**: 2.2
- [x] 2.4 Implemented `decide()`'s real body in `_core.py` per design D1/D4:
  lazy `import typesafe_sdk` inside the function, the four ordered checks,
  `_get_client()` with `functools.lru_cache(maxsize=1)`, `client.system_one(
  state=state, questions=questions)`, returning `response.answers` on
  success. Token estimate uses the ~4-chars/token heuristic (same formula as
  `skills/autopilot/scripts/token_budget_check.py::_estimate_tokens`,
  reimplemented locally, no cross-package import) over
  `json.dumps(state, default=str)` plus the longest question's `repr()`.
  **Dependencies**: 2.3
- [x] Checkpoint: `test_decide_live.py` and `test_no_sdk_import_outside_package.py`
  green. Confirmed a fresh scratch-venv `pip install` with zero extras still
  succeeds and `decide(...)` returns `None` (no `TYPESAFE_API_KEY` in that
  venv, extra not installed) without raising — the live extra is truly
  optional. Also caught and fixed a real test-isolation bug in `ri-01`'s own
  `test_no_vendor_sdk_imported_at_load_time`: it asserted against this
  process's `sys.modules`, which sibling test files in this phase now
  legitimately populate with `typesafe_sdk` (design D5) — rewrote it to run
  in a subprocess, the only way to check what the assertion actually means.

### Phase 3 — `event_sink` telemetry on `decide()`

- [x] 3.1 Write `tests/test_decide_event_sink.py`: a completed call against a
  monkeypatched client (returning a real `SystemOneResponse` built from real
  `Usage`/`ChoiceAnswer`/`NoulAnswer` instances) invokes a supplied
  `event_sink` exactly once with `site`, `latency_ms`, `usage_input_tokens`,
  `probabilities` matching the mocked response (including the `{"noul": ...}`
  shape for a `NoulAnswer`); each of the four unavailability branches from
  Phase 2, parametrized, invokes `event_sink` zero times; omitting
  `event_sink` on a completed call is safe.
  **Spec scenarios**: system-one-decisions.decide()-accepts-an-optional-event_sink,-invoked-once-per-completed-call
  (all three scenarios)
  **Design decisions**: D2
  **Dependencies**: 2.4
- [x] 3.2 Added the `event_sink: Callable[[dict[str, Any]], None] | None = None`
  parameter to `decide()`'s signature; latency measured with
  `time.monotonic()` around the `client.system_one(...)` call; record dict
  built per D2, handling both `ChoiceAnswer`/`ScoreAnswer`'s `probabilities`
  and `NoulAnswer`'s scalar `noul` field via `hasattr`; `event_sink` invoked
  once on success only. (Implemented together with 2.4 in the same edit,
  since both live in `decide()`'s single control-flow body — tested
  separately per the task split above.)
  **Dependencies**: 3.1
- [x] Checkpoint: full `packages/system-one-decisions/tests/` suite green
  (36 passed); `ruff check` and `mypy` both clean. Cumulative diff reviewed
  against `design.md`'s D1-D5. `decide_intent()`'s own tests
  (`test_decide_intent.py`, `test_route.py`) pass byte-for-byte unchanged —
  this item does not touch its acquisition step.

## Non-goals (out of scope for this item)

- `decide_intent()`'s acquisition step stays "always fallback" — `ri-03`'s job
  to wire it to this item's new live path via the adapter-backed test
  substitute.
- No migration of any existing call site.
- No `langfuse` dependency added to this package.
- No public `Choice`/`Noul`/`Score` re-export — no caller constructs a
  question yet.
