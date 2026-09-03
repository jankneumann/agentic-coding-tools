# Validation Report — route-supervise-gates-through-the-approval-gate-service

**Phase**: VALIDATE (autopilot ri-04, roadmap-supervisor-orchestration)
**Date**: 2026-09-03
**Branch / HEAD verified**: `openspec/route-supervise-gates-through-the-approval-gate-service` @ `bf0d8cf7`
**Worktree**: `.git-worktrees/route-supervise-gates-through-the-approval-gate-service`

## Summary

All executable phases pass. No blocking findings. `deploy` and `smoke` are marked
`skipped` (not applicable — this is a skills-library change, not a deployable
service). Recommend `outcome: passed`.

| Phase    | Result  | Notes |
|----------|---------|-------|
| spec     | PASS    | `openspec validate ... --strict` valid |
| evidence | PASS    | 1,065 tests passed, 0 failed, 0 errors across three suites |
| deploy   | SKIPPED | no deployable artifact — skills-library change |
| smoke    | SKIPPED | no runtime service to smoke-test |
| security | PASS    | targeted read pass over the approval/trust boundary — no bypass, fail-open, unaudited-proceed, or replay/forgery path found |
| e2e      | PASS    | covered by `test_gate_router_e2e.py` / `test_supervised_dispatch_e2e.py` in the evidence run, plus the manual Acceptance-Outcome-1 walk already recorded in `session-log.md` (Implement phase) |

## 1. Spec validation

```
$ openspec validate route-supervise-gates-through-the-approval-gate-service --strict
Change 'route-supervise-gates-through-the-approval-gate-service' is valid
```

## 2. Evidence — full test suites

Three suites run exactly as specified, from the change's own worktree:

```
$ skills/.venv/bin/python -m pytest skills/shared/tests skills/tests/supervise -q
341 passed in 14.42s

$ cd skills && uv run pytest tests/autopilot tests/autopilot-roadmap tests/roadmap-runtime -q
598 passed, 2 warnings in 12.77s
  (warnings: one PytestUnknownMarkWarning for `pytest.mark.integration`, one
  StarletteDeprecationWarning for httpx in fastapi.testclient — both pre-existing,
  neither related to this change)

$ cd skills && uv run pytest autopilot/tests tests/ci_coverage -q
126 passed in 2.51s
```

**Total: 1,065 passed / 0 failed / 0 errors.**

(Note: the literal paths given for the third suite, `autopilot/tests tests/ci_coverage`,
resolve only from `skills/` as cwd — `skills/autopilot/tests` and
`skills/tests/ci_coverage` — mirroring how suite 2 was invoked. Confirmed no stray
`autopilot/tests` or `tests/ci_coverage` directory exists elsewhere in the tree.)

## 3. Security read pass

Scope: `skills/shared/approval_gate.py`, `skills/supervise/scripts/gate_router.py`,
`skills/supervise/scripts/execution.py` — the trust/approval boundary this change's
entire purpose is to route every supervise gate through.

### 3.1 Privilege bypass / single-seam invariant

- `gate_router.py`'s own docstring states every gate the supervise skill raises goes
  through exactly one of four entry points (`evaluate`, `answer`, `resolve_parked`,
  `require_approval_ref`), and that invariant is enforced structurally by an AST scan
  (`test_gate_router.py::test_only_gate_router_imports_approval_gate`).
- Confirmed independently: `grep -rn "approval_gate\|ApprovalGate\|build_default_gate\|check_filed" skills/supervise/scripts` (excluding tests and `gate_router.py` itself)
  returns **no matches** — no other production module under
  `skills/supervise/scripts/` imports the gate service directly.
- `execution.py`'s `prepare()` calls `gate_router.require_approval_ref(...)` before
  any dispatch attempt is written (comment: "so a missing or stale approval never
  mutates roadmap execution state"). `resume()` likewise calls
  `require_approval_ref(...)` before the CAS transition that un-parks an attempt,
  and before `_remove_owned_marker` / field strip run. No code path in either
  function reaches `prepare_delegated_batch` / the parked→prepared transition
  without first passing that check.

### 3.2 Fail-open on coordinator errors

- `approval_gate.py` is explicitly fail-closed: every `CoordinatorUnavailable` raised
  by `request_approval`, `push_notification`, or `check_approval` (including inside
  the polling loop) is caught and degrades the decision to `BLOCKED` /
  `COORDINATOR_UNREACHABLE` via `_unreachable(...)` — never silently proceeds.
- `BridgeCoordinatorClient._require_ok` treats HTTP 5xx, 404, 401, and 403 all as
  `CoordinatorUnavailable` (auth failure is explicitly "not the human's decision →
  fail closed"), so a misconfigured/unreachable/unauthorized coordinator cannot be
  mistaken for an implicit approval.
- Timeout handling: a `default_action=proceed` gate does **not** auto-proceed if the
  approval notification was never delivered (`notified=False`) — `_apply_default`
  explicitly fails that case closed to `TIMEOUT_BLOCK` with a logged warning, so an
  unattended action nobody could have vetoed cannot auto-proceed on a timer alone.
- `gate_router._apply_prior_record`'s D4 "prior-record rule" re-checks a filed
  approval via `check_filed` before ever reusing a stale `proceed`; only an
  `outcome == "proceed"` prior record is reused unconditionally — every other prior
  state (open `posture_block`, pending, blocked-with-approval_id) is re-verified
  against the live posture or the coordinator before being trusted.

### 3.3 Proceeding without a recorded gate decision

- Every terminal path in `ApprovalGate` funnels through `_finalize()`, which
  unconditionally calls `_record_audit()` before returning the decision to the
  caller — auto, human-resolved, defaulted, blocked, and degraded decisions are all
  recorded. An audit-sink failure is swallowed (logged, not raised) by design so a
  broken sink can't crash a gate, but the attempt to record always happens on the
  code path that returns a decision; there is no early return that skips
  `_record_audit`.
- `gate_router.evaluate`/`answer` call `_project(...)` (mirror projection) **before**
  `manager.record_gate_decision(...)` (checkpoint persistence), and the code
  comments explicitly call out why: "a refusal must never follow a partial write."
  A `GateRefusalError` from `_project` (e.g., a blocked decision naming no
  `change_id`) aborts before the checkpoint record is written, so there's no
  half-recorded state — either both the mirror and the checkpoint are updated, or
  neither is (for a reused record, neither is touched, which is correct — it was
  already persisted on the prior call).

### 3.4 approval_ref reuse / forgery / replay across roadmaps

- `require_approval_ref` resolves `approval_ref` by looking up its embedded
  `decision_id` (a `uuid4`, unguessable) against `checkpoint.gate_decisions` — it is
  never trusted verbatim; a ref that doesn't resolve to a persisted record raises
  `ApprovalRefError`.
- It additionally checks: the resolved record's `gate` matches the caller's expected
  gate, `outcome == "proceed"` (a blocked/pending decision can never authorize
  anything), and — when a `dispatch_id`/`roadmap_id` is supplied — that they match
  the record's own.
- **Roadmap-fingerprint replay is explicitly closed**: for `Gate.ROADMAP_APPROVAL`,
  `require_approval_ref` recomputes `roadmap_fingerprint(roadmap)` against the
  **current** roadmap shape passed in by the caller and rejects the ref if it no
  longer matches the fingerprint stamped on the record at approval time. The
  docstring states the intent directly: "a caller that retained an old reference
  across a `refine-roadmap` or replan does not get to reuse it." `execution.py`'s
  `prepare()` always loads the roadmap fresh from `roadmap.yaml` and passes it in,
  so this check cannot be bypassed by passing a stale in-memory roadmap object.
  `resume()` deliberately passes `roadmap=None` — correct, since only
  `roadmap_approval` refs carry a fingerprint and a parked child's gate is never
  that one; `require_approval_ref` itself raises if `roadmap_approval` is requested
  without a roadmap, so this isn't a silent fingerprint skip for that gate.
- `roadmap_fingerprint()` is a deterministic sha256 over sorted
  `(item_id, change_id, sorted(depends_on), sorted(external_depends_on),
  normalized_status)` tuples — no wall-clock or ordering dependence, so it can't
  drift/flap between an authorize call and a later `prepare()` call for the same
  unchanged DAG shape (avoiding false-negative re-blocks), while still moving on any
  supersession/skip/edge change (closing the replay window on a genuine edit).

### 3.5 Other notes (non-blocking)

- `execution.py`'s `_validate_exact_evidence` independently pins worktree path,
  branch, and loop-state commit/digest for every `success`/`parked` result before
  `apply()` acts on it — a second, independent boundary alongside the approval-ref
  check, consistent with the "trust/approval boundary" framing of this change.
- No TODOs or comments in the reviewed files suggest a known-open gap in this
  change's scope. The one pre-existing `TODO` in `approval_gate.py`
  (`BridgeCoordinatorClient.push_notification`, "return True only once a dedicated
  approval-notification endpoint confirms...") is a deliberate, already-fail-closed
  conservative choice (delivery is under-reported, never over-reported), not a
  security gap.

**No privilege-bypass, fail-open, unaudited-proceed, or approval_ref replay/forgery
paths were found in the reviewed surface.**

## 4. Deploy / Smoke — skipped

This change is a skills-library / orchestration-logic change (Python modules under
`skills/shared`, `skills/supervise/scripts`) with no standalone deployable service,
container, or endpoint of its own — there is nothing to `deploy` or `smoke`-test in
the literal sense. Its runtime behavior is exercised entirely by the `evidence` suite
above plus the coordinator-integration paths already covered by
`skills/tests/supervise/test_gate_router_e2e.py` and
`skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py`.

## 5. e2e

`test_gate_router_e2e.py` and the two `test_supervised_dispatch*_e2e.py` suites
(migrated per task 2.5) are part of the `evidence` run above and passed. In addition,
the Implement phase already recorded a manual "Acceptance Outcome 1" end-to-end walk
in `session-log.md` (`## Phase: Implement — Acceptance Outcome 1 Walk`), driving a
scratch roadmap through `gate-check`/`gate-answer`/`gate-log` with an all-`auto`
posture and inspecting the resulting checkpoint sidecar record — that walk's scope
note (it does not itself drive a dispatched child to a merged PR, since that requires
a full separate `/autopilot` run against the child's own posture) still applies and is
not re-litigated here.

## Recommendation

`outcome: passed`.
