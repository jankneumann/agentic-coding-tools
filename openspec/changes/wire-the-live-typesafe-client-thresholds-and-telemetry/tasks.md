# Tasks: Wire the live TypeSafe client, thresholds and telemetry

> Change ID: `wire-the-live-typesafe-client-thresholds-and-telemetry`

## Tasks

### Phase 1 — Threshold config file and loader (no SDK dependency yet)

- [ ] 1.1 Create `packages/system-one-decisions/src/system_one_decisions/config/thresholds.json`
  (`schema_version: 1`, `defaults: {act_floor: 0.6, approve_floor: 0.9}`) —
  inside the importable package, not the package root, so `importlib.resources`
  can find it in a built wheel (design D3).
  **Design decisions**: D3
  **Dependencies**: None
- [ ] 1.2 Write `tests/test_config_loader.py`: loading resolves
  `DEFAULT_ACT_FLOOR == 0.6` and `DEFAULT_APPROVE_FLOOR == 0.9` from the file;
  a missing file raises a clear error rather than silently defaulting (fail
  loud on a packaging mistake, not silently on a data mistake).
  **Spec scenarios**: system-one-decisions.Defaults-load-from-the-config-file
  **Dependencies**: 1.1
- [ ] 1.3 Implement `_config.py`: `load_thresholds()` (cached, reads the
  packaged YAML via `importlib.resources`, not a relative filesystem path, so
  it works from an installed wheel) and module-level `DEFAULT_ACT_FLOOR`,
  `DEFAULT_APPROVE_FLOOR` constants.
  **Dependencies**: 1.2
- [ ] 1.4 Update `_core.py`: `_route()`'s and `decide_intent()`'s
  `act_floor: float = 0.6` / `approve_floor: float = 0.9` become
  `act_floor: float = DEFAULT_ACT_FLOOR` / `approve_floor: float =
  DEFAULT_APPROVE_FLOOR`, importing both from `_config`.
  **Dependencies**: 1.3
- [ ] 1.5 Write `tests/test_no_threshold_literals.py`: greps
  `src/system_one_decisions/*.py` (excluding `_config.py`) for a bare float
  literal used in an `act_floor`/`approve_floor` position; asserts none found.
  **Spec scenarios**: system-one-decisions.No-threshold-literal-in-scoring-logic
  **Design decisions**: D3
  **Dependencies**: 1.4
- [ ] Checkpoint: run `pytest packages/system-one-decisions/tests/
  test_config_loader.py packages/system-one-decisions/tests/
  test_no_threshold_literals.py packages/system-one-decisions/tests/test_route.py
  packages/system-one-decisions/tests/test_decide_intent.py`, confirm green —
  `ri-01`'s existing route/decide_intent tests must still pass unchanged since
  their literal `0.6`/`0.9` defaults become named constants of the same value.

### Phase 2 — `live` extra and lazy client construction

- [ ] 2.1 Add `[project.optional-dependencies] live = ["typesafe-sdk>=0.7,<1"]`
  to `packages/system-one-decisions/pyproject.toml`. Run `uv lock` in
  `packages/system-one-decisions/`.
  **Spec scenarios**: system-one-decisions.Fallback-only-install-succeeds-without-the-live-extra
  **Dependencies**: None (parallel to Phase 1)
- [ ] 2.2 Write `tests/test_no_sdk_import_outside_package.py`: a grep-style
  guard scanning every `.py` file in the repository (excluding
  `packages/system-one-decisions/`) for `typesafe_sdk` import statements;
  asserts none found. Include the repo's own `.git-worktrees/` and
  `.venv`/`node_modules` directories in the exclusion list (generated/vendor
  content, not source).
  **Spec scenarios**: system-one-decisions.No-other-package-or-skill-imports-the-vendor-SDK
  **Dependencies**: 2.1
- [ ] 2.3 Write `tests/test_decide_live.py` covering, in order: extra not
  installed (skip this specific case if `typesafe_sdk` happens to be
  importable in the test environment, since it's genuinely present there —
  assert the *logic path* instead by monkeypatching `sys.modules["typesafe_sdk"]
  = None` to force the `ImportError` branch deterministically); key absent
  (`monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)`); token budget
  exceeded (a synthetic `state` whose serialized form exceeds 32,000
  estimated tokens); network/API failure (a monkeypatched client whose
  `system_one()` raises `typesafe_sdk.TypeSafeAPIConnectionError` and, in a
  second case, `typesafe_sdk.TypeSafeAuthenticationError`) — one test per
  branch, each asserting `decide(...)` returns `None` without raising.
  **Spec scenarios**: system-one-decisions.decide()-returns-None,-never-raises,-on-any-of-four-unavailability-branches
  (all four scenarios)
  **Design decisions**: D1, D4
  **Dependencies**: 2.2
- [ ] 2.4 Implement `decide()`'s real body in `_core.py` per design D1/D4:
  lazy `import typesafe_sdk` inside the function, the four ordered checks,
  `_get_client()` with `functools.lru_cache(maxsize=1)`, `client.system_one(
  state=state, questions=questions)`, returning `response.answers` on success.
  Use the ~4-chars/token heuristic (same formula as
  `skills/autopilot/scripts/token_budget_check.py::_estimate_tokens`,
  reimplemented locally — no cross-package import, to keep
  `packages/system-one-decisions` dependency-free of `skills/`) over
  `json.dumps(state, default=str)` plus the longest question's `repr()`.
  **Dependencies**: 2.3
- [ ] Checkpoint: run `packages/system-one-decisions/tests/test_decide_live.py`
  and `test_no_sdk_import_outside_package.py`, confirm green. Confirm
  `uv sync` (no extras) in a scratch venv still succeeds and `import
  system_one_decisions` still raises nothing, proving the live extra is truly
  optional.

### Phase 3 — `event_sink` telemetry on `decide()`

- [ ] 3.1 Write `tests/test_decide_event_sink.py`: a completed call against a
  monkeypatched client (returning a real `SystemOneResponse` built from real
  `Usage`/`ChoiceAnswer`/`NoulAnswer` instances) invokes a supplied
  `event_sink` exactly once with `site`, `latency_ms`, `usage_input_tokens`,
  `probabilities` matching the mocked response; each of the four
  unavailability branches from Phase 2 invokes `event_sink` zero times;
  omitting `event_sink` on a completed call is safe.
  **Spec scenarios**: system-one-decisions.decide()-accepts-an-optional-event_sink,-invoked-once-per-completed-call
  (all three scenarios)
  **Design decisions**: D2
  **Dependencies**: 2.4
- [ ] 3.2 Add the `event_sink: Callable[[dict[str, Any]], None] | None = None`
  parameter to `decide()`'s signature; measure latency with
  `time.monotonic()` around the `client.system_one(...)` call; build the
  record dict per D2 (handling both `ChoiceAnswer`/`ScoreAnswer`'s
  `probabilities` and `NoulAnswer`'s scalar `noul` field); invoke
  `event_sink` once on success only.
  **Dependencies**: 3.1
- [ ] Checkpoint: run the full `packages/system-one-decisions/tests/` suite,
  confirm green; review the cumulative diff against `design.md`'s D1-D5;
  confirm `decide_intent()`'s behavior is byte-for-byte unchanged from `ri-01`
  (same tests, same assertions) — this item does not touch its acquisition
  step.

## Non-goals (out of scope for this item)

- `decide_intent()`'s acquisition step stays "always fallback" — `ri-03`'s job
  to wire it to this item's new live path via the adapter-backed test
  substitute.
- No migration of any existing call site.
- No `langfuse` dependency added to this package.
- No public `Choice`/`Noul`/`Score` re-export — no caller constructs a
  question yet.
