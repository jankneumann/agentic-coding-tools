# Tasks: Add the shared system_one decision helper, fallback-only

> Change ID: `add-the-shared-system-one-decision-helper-fallback-only`

## Status

- [ ] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

### Phase 1 — Package scaffold

- [ ] 1.1 Create `packages/system-one-decisions/pyproject.toml` (`name =
  "system-one-decisions"`, `requires-python = ">=3.12"`, `dependencies = []`,
  `[project.optional-dependencies] dev = ["pytest>=7.0.0"]`), mirroring
  `packages/code-search`'s layout.
  **Design decisions**: D4 (package layout)
  **Dependencies**: None
- [ ] 1.2 Create `packages/system-one-decisions/src/system_one_decisions/__init__.py`
  and `_core.py` as empty stubs (module exists, no exports yet — the next tasks
  fill it test-first).
  **Dependencies**: 1.1

### Phase 2 — `Decision` and `_route()` (pure logic, no I/O)

- [ ] 2.1 Write `tests/test_decision.py`: frozen-instance-error on mutation,
  `evidence_class` default.
  **Spec scenarios**: system-one-decisions.Decision-is-a-frozen-dataclass (both
  scenarios)
  **Dependencies**: 1.2
- [ ] 2.2 Implement the `Decision` frozen dataclass in `_core.py`; export from
  `__init__.py`.
  **Dependencies**: 2.1
- [ ] 2.3 Write `tests/test_route.py`: below-act_floor, at-or-above-act_floor,
  irreversible-below-approve_floor, irreversible-at-or-above-approve_floor,
  boundary-equal-to-act_floor (five cases from the design's threshold table).
  **Spec scenarios**: system-one-decisions._route()-implements-confidence-based-routing
  (all five scenarios)
  **Design decisions**: D1
  **Dependencies**: 2.2
- [ ] 2.4 Implement `_route()` in `_core.py` per design decision D1. Keep it
  module-private (leading underscore, not re-exported from `__init__.py`).
  **Dependencies**: 2.3
- [ ] Checkpoint: run `pytest packages/system-one-decisions/tests/test_decision.py
  packages/system-one-decisions/tests/test_route.py`, confirm green; review the
  cumulative diff touches only `packages/system-one-decisions/**`.

### Phase 3 — `decide()` stub and `decide_intent()`

- [ ] 3.1 Write `tests/test_decide_stub.py`: `decide()` returns `None` for
  representative `state`/`questions`/`site` inputs, including empty dicts and a
  large synthetic state, and makes no network call (assert via a monkeypatched
  `socket.socket` that raises if invoked, or equivalent).
  **Spec scenarios**: system-one-decisions.decide()-is-an-unconditional-stub-with-a-stable-signature
  **Design decisions**: D3
  **Dependencies**: 2.4
- [ ] 3.2 Implement `decide()` in `_core.py` as the unconditional stub; export
  from `__init__.py`.
  **Dependencies**: 3.1
- [ ] 3.3 Write `tests/test_decide_intent.py`: always-fallback behavior with
  `degraded=True` and `evidence_class="judgment"`; fallback's own exception
  propagates unmodified; `event_sink` called exactly once with matching fields
  against a synthetic `phase_history`-shaped list; omitting `event_sink` is safe.
  **Spec scenarios**: system-one-decisions.decide_intent()-always-takes-the-fallback-branch-in-this-item
  (both scenarios), system-one-decisions.decide_intent-records-one-event-through-a-caller-supplied-sink
  (both scenarios)
  **Design decisions**: D1, D2
  **Dependencies**: 3.2
- [ ] 3.4 Implement `decide_intent()` in `_core.py` calling `_route()` internally
  (per D1, always on the "unavailable" branch in this item) and invoking
  `event_sink` when provided (per D2); export from `__init__.py`.
  **Dependencies**: 3.3
- [ ] Checkpoint: run the full `packages/system-one-decisions/tests/` suite,
  confirm green; review the cumulative diff against `design.md`'s D1–D3; verify
  no import of `typesafe_sdk` or any `skills.autopilot` module exists anywhere in
  `packages/system-one-decisions/src/`.

### Phase 4 — Consumer wiring (declare, do not migrate call sites)

- [ ] 4.1 Add `system-one-decisions` as a path dependency in
  `skills/pyproject.toml`; run `uv sync` in `skills/` and confirm `python -c
  "import system_one_decisions"` succeeds inside `skills/.venv`.
  **Spec scenarios**: system-one-decisions.The-package-is-importable-from-every-declared-consumer
  (skills-venv scenario)
  **Dependencies**: 3.4
- [ ] 4.2 Add an optional `decisions` extra to `packages/gen-eval/pyproject.toml`
  depending on `system-one-decisions`; confirm a standalone `uv pip install
  packages/gen-eval[decisions]` into an empty venv makes the import succeed.
  **Spec scenarios**: system-one-decisions.The-package-is-importable-from-every-declared-consumer
  (gen-eval scenario)
  **Dependencies**: 3.4
- [ ] 4.3 Add a path dependency on `system-one-decisions` in
  `agent-coordinator/pyproject.toml` and a `COPY packages/system-one-decisions/`
  line in `agent-coordinator/Dockerfile` beside the existing `gen-eval` and
  `code-search` copies.
  **Spec scenarios**: system-one-decisions.The-package-is-importable-from-every-declared-consumer
  (coordinator scenario)
  **Dependencies**: 3.4
- [ ] Checkpoint: run `pytest packages/system-one-decisions/`, confirm green;
  run `docker-smoke-import`'s local equivalent if available, otherwise flag for
  CI verification; confirm the diff touches only
  `packages/system-one-decisions/**`, `skills/pyproject.toml`,
  `packages/gen-eval/pyproject.toml`, `agent-coordinator/pyproject.toml`, and
  `agent-coordinator/Dockerfile`.

## Non-goals (out of scope for this item)

- No live client, no `TYPESAFE_API_KEY`, no token-budget check, no Langfuse
  telemetry (ri-02).
- No migration of any existing call site to use this helper (each Group A/B/C
  item's own job).
- No `system-one-adapter` test substitute (ri-03).
