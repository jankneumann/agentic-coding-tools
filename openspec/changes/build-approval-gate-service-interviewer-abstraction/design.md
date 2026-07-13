# Design: Approval Gate Service (Interviewer Abstraction)

## Context

Phase 1 of the always-on-automation proposal sequences three bricks: (1) the trust
posture *contract* (ri-04, delivered), (2) the approval gate *service* that consumes
it (ri-05, this change), and (3) encoding the gates in `autopilot.py` (ri-06). This
change is (2): a small host-side library that turns a resolved posture disposition
into an executed decision at a workflow gate.

The shape is taken from attractor's **Interviewer** abstraction — auto-approve /
queue / callback / console with a timeout and a default choice — collapsed onto this
repo's existing coordinator surface:

- Approval queue: `request_approval` / `check_approval`
  (`agent-coordinator/src/coordination_mcp.py:1648`, `coordination_api.py:2650`,
  `src/approval.py`) with a `pending | approved | denied | expired` status vocabulary.
- Reply-to-approve notifications: `agent-coordinator/src/notifications/`, `status.py`.
- Audit log: `agent-coordinator/src/audit.py`.
- HTTP fallback transport: `skills/coordination-bridge/scripts/coordination_bridge.py`.

Two invariants from the proponent proposal dominate every decision below:
**fail closed, notify always** and **audit every unattended decision**.

Prior art we align with:
- `skills/shared/trust_posture.py` (ri-04): a small, side-effect-free shared helper with
  a fail-closed default and frozen-dataclass results. Same shape and same `skills/shared`
  home, so the two compose without a package boundary.
- ri-01's **injectable runners**: dependencies (clock, sleep, coordinator, audit,
  posture loader) are constructor-injected so tests are deterministic and offline.
- `coordination_bridge`'s "degrade to `skipped` when the coordinator is unavailable"
  transport contract — our fail-closed degradation is the enforcing analogue.

## Key Design Decisions

### D1: `evaluate(gate, context) -> ApprovalDecision` as the single entry point

**Decision**: One public method resolves one gate and returns a value object. It never
raises for a *posture* outcome (block, timeout, unreachable are all returned as
decisions), only for programmer error (an unknown gate name, surfaced by the ri-04
loader's `disposition_for`).

**Why**: A gate is a decision point, not an exception site. Callers write
`if decision.proceed: ... else: park(decision)`; they never wrap the gate in
`try/except` to discover they were blocked. This is the interviewer contract: it always
answers, and the answer is data.

### D2: `ApprovalDecision` — `outcome` (coarse) + `resolution` (audit-grade)

**Decision**: Two enums. `Outcome ∈ {PROCEED, BLOCKED}` is what the caller branches on.
`Resolution ∈ {AUTO, APPROVED, REJECTED, TIMEOUT_PROCEED, TIMEOUT_BLOCK, POSTURE_BLOCK,
COORDINATOR_UNREACHABLE}` records *how* that outcome was reached. The decision also
carries the authorizing `disposition`, the `gate`, a human `reason`, the `approval_id`
(when one was filed), the applied `default_action`, and `posture_present`.

**Why**: The caller only needs proceed-or-park, so branching on a two-value enum keeps
call sites trivial and total. But the audit contract and any future operator surface
need to distinguish "proceeded because auto" from "proceeded because the timer expired
with default_action=proceed" from "proceeded because a human approved" — three very
different trust stories that collapse to the same `Outcome`. Splitting coarse outcome
from fine resolution serves both without overloading either. Frozen dataclass because a
decision is an immutable record.

### D3: The polling / timeout model

**Decision**: For `notify_with_timeout`: (1) `request_approval`, (2) `push_notification`
(best-effort), (3) poll loop — `deadline = clock() + timeout_seconds`; while
`clock() < deadline`, call `check_approval`; `approved` → PROCEED, `denied`/`rejected` →
BLOCKED, `expired` → apply default now, `pending` → `sleep(min(poll_interval,
remaining))` and loop; (4) on natural loop exit (timer expired unresolved) apply
`default_action`.

**Why**:
- **Injected `clock` + `sleep`.** `time.monotonic` / `time.sleep` in production; a fake
  clock whose `sleep` advances a counter in tests. A 30s-timeout / 5s-poll flow runs in
  microseconds and asserts exact sleep totals. This is the ri-01 injectable pattern; it
  is the only way to test a timeout deterministically without wall-clock flake.
- **`sleep(min(poll_interval, remaining))`** never oversleeps past the deadline, so the
  effective timeout is the declared `timeout_seconds`, not `timeout + poll_interval`.
- **Server `expired` == local timeout.** The coordinator ages approvals out
  independently (watchdog). If a poll observes `expired`, that is the same terminal
  condition as our local timer, so it routes through the same `default_action` branch —
  one code path, no divergence between "our clock expired" and "their clock expired".
- **`monotonic`, not wall-clock**, so a system clock adjustment mid-wait cannot shorten
  or extend the window.

### D4: Fail closed — `CoordinatorUnavailable` at any step → BLOCKED

**Decision**: The `CoordinatorClient` protocol raises `CoordinatorUnavailable` for any
*transport* failure (missing URL, unreachable, 5xx, 404-capability-absent, 401/403).
The gate catches it at each of the three notify steps and returns a BLOCKED /
`COORDINATOR_UNREACHABLE` decision immediately — no sleeping, no retry, no guessing.
This holds **even when the gate's `default_action` is `proceed`**: an unreachable
coordinator is not a timeout, it is an inability to consult the human at all, so it
fails closed regardless of the configured default.

**Why**: "Fail closed, notify always. Ambiguity parks work as blocked rather than
guessing." A `default_action=proceed` gate is a statement about *what to do when the
human doesn't answer in time* — it presupposes the request was actually filed and
visible. When the coordinator is down the request was never seen by anyone, so applying
`proceed` would be an unattended action nobody could have vetoed. Blocking is the only
safe reading. The distinction between "human said no" and "couldn't ask the human" is
exactly why the client *raises* for transport errors instead of returning a sentinel
status the poll loop might misread as a decision.

**Notification is mostly non-fatal — with one safety exception.** `push_notification`
returning `False` (no channel configured, soft no-op) does *not* fail the gate outright:
the approval is already filed and pollable, so a human can still resolve it from the
queue. Only a *raised* `CoordinatorUnavailable` from the notifier (transport genuinely
down) fails closed immediately. This reconciles "fail closed at any point" with "a
missing Telegram token shouldn't park a correctly-filed approval." **The exception:** a
`default_action=proceed` gate that *times out* with an **undelivered** notification
fails closed to block rather than proceeding — auto-proceeding when nobody was ever
notified would be an unattended action no human could have vetoed. Delivery status is
therefore carried from the notify step into the timeout default so a `proceed` default
only fires when a human was actually reachable.

### D5: `block` parks, it does not wait

**Decision**: A `block` disposition returns BLOCKED / `POSTURE_BLOCK` synchronously,
touching neither the coordinator nor the clock. The orchestrator (ri-06) persists loop
state and stops; a human resumes later out of band.

**Why**: `block` is "today's behavior" — the loop parks for a human. The library's job
is to *report* that, fast, so the orchestrator can checkpoint and exit. If `block` filed
an approval and waited, it would silently become `notify_with_timeout` with an infinite
timeout — a hang, which the deliverable explicitly forbids ("do NOT hang").

### D6: Audit on every path, best-effort, decoupled from the approval client

**Decision**: A separate injected `AuditSink.record(record)` is called exactly once per
`evaluate`, in a single `_finalize` step, on every path — auto, approved, denied,
defaulted, parked, and degraded. The record carries `gate`, `outcome`, `resolution`,
`authorizing_disposition`, `reason`, `approval_id`, `default_action`, `posture_present`,
`agent_id`, and `operation`. Sink failure is caught and logged but never crashes the
gate; the decision is still returned.

**Why**:
- **Separate seam from the coordinator client.** The coordinator-unreachable path must
  *still* audit ("every gate decision, including defaulted ones, lands in the audit
  log"). If audit rode on the same client that just failed, the unreachable path could
  not be audited. Decoupling lets the approval transport be down while the audit sink
  (a local file, a different endpoint, or an in-process `audit.log_operation`) still
  records the park. Tests assert an audit record on the unreachable path precisely
  because the seams are independent.
- **Best-effort, never fatal.** An audit write must not turn a valid PROCEED into a
  crash. The decision is the product; audit is a side record. So sink exceptions are
  swallowed (logged), and with a healthy sink — the tested and production path — the
  record is guaranteed.
- **`authorizing_disposition` is mandatory in the record**, satisfying the acceptance
  outcome "with the posture that authorized it," and `posture_present` distinguishes a
  loaded posture from the absent-file all-block default.

### D7: Default clients over the coordination bridge; no coordinator changes

**Decision**: `BridgeCoordinatorClient` and `BridgeAuditSink` wrap the existing
`coordination_bridge` transport. The approval client hits `/approvals/request`,
`/approvals/{id}`, and `/notifications/test`. The audit sink, having no host-reachable
audit-*write* route, records through the coordinator's durable memory surface
(`try_remember`, `event_type="approval_gate_decision"`, tagged `approval_gate`) — a
queryable coordinator-side record. Both import the bridge lazily from its sibling skill
dir (the `phase_agent.py` pattern) and raise/return-false-closed if it is absent.

**Why**: "Wire before building." The coordinator already exposes everything needed; this
change adds *zero* server-side surface. Reusing the bridge inherits its SSRF allowlist,
URL resolution, and timeout handling rather than re-implementing HTTP. The audit sink
uses memory because the coordinator's `audit_log` has no external write endpoint (audit
is written internally by server operations); memory is the honest host-reachable durable
record. The injectable seam means an **in-coordinator** deployment can swap in a sink
calling `audit.log_operation` directly — a one-liner — so this is a pragmatic default,
not a lock-in. `request_approval` additionally produces a genuine server-side `audit_log`
entry via `authorize_operation`, so notify-path decisions are double-recorded.

### D8: New `approval-gate` capability, not an extension of `trust-posture`

**Decision**: Add a new `approval-gate` capability spec rather than adding requirements
to `trust-posture`.

**Why**: `trust-posture` (ri-04) is the *policy contract* — a data artifact and its
side-effect-free loader; its requirements are about file format, validation, and
fail-closed resolution. This change is the *enforcement service* — a stateful actor that
talks to the coordinator, waits on humans, and applies defaults. They are different
kinds of thing (data vs. behavior) with different failure modes and different consumers.
Keeping them as separate capabilities matches the repo's granularity (loader vs. service)
and lets ri-06's gate-encoding requirements attach to `approval-gate` without entangling
the contract spec. The dependency is one-directional and explicit: `approval-gate`
consumes `trust-posture`.

### D9: No LLM calls in the library (host-assisted invariant)

**Decision**: The library only reads the posture, calls the injected coordinator client,
and records audit. No model client, no prompt, no completion — anywhere.

**Why**: This is host-assisted infrastructure. Any model-in-the-loop behavior (e.g., the
coordinator's audit-triage LLM classification) lives on the coordinator/host side. Keeping
the gate model-free makes it trivially testable, cheap, and safe to call on every gate.

## Alternatives Considered

- **Async / `await` API.** Rejected: the gate is called from the synchronous autopilot
  state machine (`autopilot.py`), and a blocking poll with an injected `sleep` is simpler
  to test and reason about than threading an event loop through the orchestrator. The
  coordinator client can wrap async transport internally if ever needed.
- **A single `CoordinatorClient` carrying audit too.** Rejected per D6: the unreachable
  path must still audit, which requires the audit seam to survive an approval-transport
  failure.
- **Returning a status string instead of a decision object.** Rejected per D2: the audit
  contract and operator surface need structured provenance (disposition, approval_id,
  default applied), which a bare enum cannot carry.
- **Retry/backoff on transient coordinator errors.** Deferred: fail-closed-to-block is
  the specified behavior, and a parked loop is cheaply resumable. Retry belongs to the
  dispatcher (Phase 2), not the gate primitive.

## Testing Strategy

`skills/shared/tests/test_approval_gate.py`: a `FakeClock` (sleep advances a counter), a
scriptable `FakeCoordinator` (status sequence + raise-on-step), and a `RecordingAudit`
drive every path deterministically and offline. Coverage: auto; block; absent-posture
block; notify approved; notify denied; notify timeout→proceed; notify timeout→block;
server-expired→default; soft-notification-failure non-fatal; coordinator-unreachable at
file / notify / poll (parametrized) → block; approval_id preserved on poll failure;
audit-in-every-path (table); audit-sink-failure-non-fatal; and the production
`BridgeCoordinatorClient` / `BridgeAuditSink` / `build_default_gate` wiring via a
monkeypatched bridge (so the default clients are exercised, not dead code).
