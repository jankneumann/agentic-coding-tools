# Publish the supervisor-worker dispatch contract

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `dispatch-contract`
> Effort: L
> Priority: 1

## Why

The first `/supervise execute` run of `multiplayer-collaboration` (2026-10-05/06)
dispatched four workers (ri-01, ri-02, ri-05, ri-20) and none reached
implementation. Every stall traced to the supervisor-worker boundary, which has no
published contract: the dispatch request and result exist only as three hand-kept
validators (`execution.py` `_validate_result`, `orchestrator.py`
`_validate_dispatch_result`, and an inline copy inside `checkpoint.schema.json`) plus
test fixtures. Each worker prompt restated the result shape by hand, and every
behaviour the prompt left out was decided by the worker. The observed failures:

1. A gate parked under a missing posture stayed parked after the operator adopted a
   posture with `auto` for it, because the child's `pending_gate` is never
   re-evaluated and nothing says whether the child's or the supervisor's record is
   authoritative.
2. Workers probed credentials (`env | grep ...`) to discover vendors, hit `ask`
   permission rules, and sat in `REQUIRES_ACTION` for hours with no way to report it.
3. Plan review silently ran below quorum because `--check-vendors` reported a vendor
   whose CLI was not installed; degradations appeared only in prose.
4. A child parked as `pending_gate/escalate_resume`, which the supervisor had no
   answer path for, deadlocking execution.

Landing the roadmap branch (PR #662) exposed three more defects, all caused by
host-local, run-local execution state reaching a shared ref: raw launch tokens in a
tracked `checkpoint.json` (flagged by gitleaks), absolute worktree paths that no
other host can reconcile, and a repository-global `auto` posture for
`proposal_approval` that also covers standalone autopilot runs no roadmap approval
authorized.

Queue-dispatched work (`team-work-queue`, `owner-routed-escalation`,
`queue-dispatch-owner-acceptance`) is built on this boundary, so it must be fixed
first.

## What Changes

- **Published schemas.** Add `openspec/schemas/dispatch-request.schema.json` and
  `dispatch-result.schema.json` (`schema_version` 2) as the only definition of the
  boundary. A new `skills/shared/dispatch_contract.py` loads and validates them;
  `execution.py`, `orchestrator.py` and `checkpoint.schema.json` (via `$ref`) consume
  that single definition, and their hand-written field sets are deleted. Version-1
  documents remain readable (D1).
- **Code-emitted results.** `runner.py emit-result <change-id> --dispatch-id ...
  --generation ...` derives the result, including its evidence digest, from
  `loop-state.json` using a normative mapping (D4) and writes it to
  `openspec/changes/<id>/dispatch-results/<dispatch-slug>-g<N>.json`.
- **Gate provenance and posture re-evaluation.** Every gate-decision record carries
  `provenance` (`posture` with `posture_digest`, or `human` with `approval_ref`). On
  resume, a posture-derived block whose digest differs from the current posture is
  re-evaluated; a human decision is never overridden. The supervisor answers a child
  only through a typed `gate_answer` in the resume request, applied by
  `runner.py gate-answer --approval-ref`.
- **Execution profile, review requirements, degradations.** The request carries a
  supervisor-resolved `execution_profile` (verified lanes per mode, location,
  isolation, sanctioned probe command) and `review_requirements` (quorum per phase,
  counting lanes). `review_dispatcher.py --check-vendors` reports a lane only when a
  dry invocation proves it dispatchable. The result carries
  `degradations[]` with an enumerated code set.
- **New parked kinds.** `permission_blocked` and `capability_unavailable` are recorded
  in loop state by `runner.py park`, emitted by `emit-result`, and routed by the
  supervisor to the operator as one deduplicated escalation each.
- **Closure contract test.** A test enumerates every `(outcome, parked.kind, gate)`
  the result schema permits and fails if the supervisor has no answer or resume path;
  `ExecutionAdapter.apply` refuses an unroutable result at apply time.
- **Landable dispatch state.** `checkpoint.json` stores `launch_digest`
  (`sha256:<hex>`) instead of the raw token, and tokens are minted per launch
  generation (D6). Isolation is recorded as `{mode, worktree_ref, branch, host_id}`
  so another host can rebind or reinitialize an attempt (D7). A legacy reader
  migrates raw tokens and absolute paths on load.
- **Scoped auto dispositions.** `auto` for `proposal_approval` and `replan_required`
  applies only to a dispatch whose launch marker carries a valid
  `roadmap_approval_ref`; otherwise the gate uses its declared `unscoped` fallback,
  `block` by default (D8).
- **Merged narrow fix.** `openspec/supervise-pending-escalate-answer` (6e6e9a6) is
  merged into this branch, not re-implemented, and covered by the closure test.

## Non-Goals

- Automatic re-routing of a `capability_unavailable` review to another lane (for
  example the GX10 review queue). This change makes the park answerable by the
  operator; automatic re-routing is a follow-up item.
- Changing how results travel between sessions beyond writing the committed result
  file. The cross-session message still carries a pointer; no new transport service.
- Rendering degradations in the supervise digest. They are persisted in the checkpoint
  and returned by `apply`; the digest is out of scope.
- Editing `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`, its
  `checkpoint.json`, `openspec/supervise/*`, or `.supervised-dispatch/`. The raw tokens
  already in the roadmap branch's history are not rewritten here (see design Open
  Questions).
- New trust-posture gates. The new parked kinds resolve through the existing
  `escalate_resume` gate.

## Acceptance Outcomes

1. dispatch-request and dispatch-result schemas exist under openspec/schemas and
   execution.py and orchestrator.py validate against them with existing fixtures
   passing.
2. runner.py emit-result produces a schema-valid result for every terminal and parked
   loop-state shape, verified end to end.
3. A closure contract test fails when any schema-permitted parked kind/gate
   combination lacks a supervisor answer or resume path.
4. A posture-derived gate block clears on resume after a posture change while a human
   rejection does not.
5. execution_profile, review_requirements, and degradations[] are carried end to end,
   and permission_blocked and capability_unavailable parks are routed to the operator
   as single escalations.
6. checkpoint.json stores no raw launch token (only a digest that child_start
   verifies) and the default secret-scan passes on a committed checkpoint with live
   attempts and no allowlist entry.
7. A checkpoint with live attempts committed on one host can be reconciled on another
   host, which rebinds or reinitializes attempts instead of failing on absolute
   isolation paths.
8. An auto disposition for proposal_approval or replan_required proceeds only for a
   dispatch carrying a valid roadmap_approval_ref; a standalone autopilot run without
   one is gated by its non-auto fallback.

"End to end" in outcomes 2 and 5 means: supervisor request -> child launch marker ->
child `loop-state.json` -> `emit-result` file -> `ExecutionAdapter.apply` ->
checkpoint attempt record and `apply` return value.

## Impact

Affected specs (deltas under `specs/`):

| Capability | Change |
|---|---|
| `roadmap-orchestration` | MODIFIED Durable Delegated Attempt Ledger, Outcome-Only Resume Contract; ADDED Published Dispatch Contract Schemas, Launch Token Digest, Host-Portable Attempt Isolation |
| `supervise` | ADDED Dispatch Result Closure, Typed Gate Answers With Provenance, Execution Profile and Review Requirements, Single Escalation Per Capability Park |
| `skill-workflow` | ADDED Code-Emitted Dispatch Result, Loop State Parks and Degradations, Gate Authority and Re-Evaluation on Resume, Honest Review Quorum |
| `trust-posture` | ADDED Roadmap-Approval-Scoped Auto Dispositions |
| `parallel-infrastructure` | ADDED Dispatchable Vendor Verification |

Affected code:

- `openspec/schemas/`: new `dispatch-request.schema.json`, `dispatch-result.schema.json`;
  edited `checkpoint.schema.json`, `gate-decision.schema.json`,
  `gate-request.schema.json`, `trust-posture.schema.json`; mirrors in
  `skills/roadmap-runtime/install_assets/openspec/schemas/`.
- `skills/shared/`: new `dispatch_contract.py`; `trust_posture.py` (digest, `unscoped`
  fallback), `approval_gate.py` (provenance, scoped auto).
- `skills/autopilot/scripts/`: `runner.py` (`emit-result`, `park`,
  `record-degradation`, `gate-answer --approval-ref`, gate-check re-evaluation),
  `autopilot.py` (LoopState v6), `convergence_loop.py` (quorum park).
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`--check-vendors --json`).
- `skills/roadmap-runtime/scripts/models.py`, `checkpoint.py` (attempt shape, legacy
  migration).
- `skills/autopilot-roadmap/scripts/orchestrator.py` (prepare, validation via contract).
- `skills/supervise/scripts/execution.py`, `gate_router.py`, `skills/supervise/SKILL.md`,
  `skills/autopilot/SKILL.md` (worker protocol: emit-result, park, no env probing).
- Tests under `skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure}/`.

Compatibility: v1 results and legacy checkpoints keep loading (D1, D6, D7). Loop
state moves to `schema_version` 6 with defaulted new fields. In-flight workers on
`multiplayer-collaboration` that still return v1 results are accepted until their
attempts resolve.

## Sources of Truth

- `openspec/roadmaps/multiplayer-collaboration/supervisor-worker-contract.md` (Issues
  1-4, cross-cutting transport, and the PR #662 addendum).
- Roadmap item `ri-21` in `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`.

## Constraints

- Existing `openspec/roadmaps/*/checkpoint.json` files (including the archived
  `2026-09-26-roadmap-supervisor-orchestration` one) must keep loading; a test covers
  raw tokens and absolute isolation paths.
- The narrow fix on `openspec/supervise-pending-escalate-answer` is merged, not
  re-implemented (task 1.1).
- Out of scope for edits: `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`,
  its `checkpoint.json`, `openspec/supervise/*`, `.supervised-dispatch/`.
