# Build Approval Gate Service (Interviewer Abstraction)

> Parent roadmap: `roadmap-always-on-agent-automation` (item ri-05)
> Change ID: `build-approval-gate-service-interviewer-abstraction`
> Effort: M
> Priority: 1

## Why

ri-04 (`add-trust-posture-contract-file`) made the human gates *readable*: a
repo-owned `TRUST_POSTURE.md` declares, per gate, a machine-readable disposition
(`auto`, `notify_with_timeout`, `block`) that `skills/shared/trust_posture.py`
resolves. But reading a disposition is not enforcing it. Nothing yet *acts* on the
posture — files an approval, notifies a human, waits, and applies a default on
timeout. Without that actor the posture is inert and the gates stay prose.

The always-on-automation proposal (`docs/proposals/always-on-agent-automation.md`,
Phase 1, "Approval Gate Service (Interviewer Abstraction)") specifies exactly this
brick, modeled on attractor's pluggable **Interviewer** interface (auto-approve /
queue / callback / console with a timeout and a default choice). It is deliberately
*composition, not new services*: the coordinator already has the approval queue
(`request_approval` / `check_approval`), reply-to-approve notifications, and an audit
log. This change wires them into one reusable primitive.

This is the middle brick of Phase 1. ri-04 is the contract; this (ri-05) is the
service that consumes it; ri-06 (encode gates in `autopilot.py`) is the consumer that
calls this service at each real gate. Shipping the service as a standalone,
fully-tested library lets ri-06 land as a thin set of call sites.

## What Changes

### New library: `skills/shared/approval_gate.py`

An `ApprovalGate` "interviewer" whose single entry point,
`evaluate(gate, context) -> ApprovalDecision`, resolves one workflow gate:

- **`auto`** → record an audit entry and return a PROCEED decision immediately; the
  coordinator is never contacted.
- **`notify_with_timeout`** → file a coordinator approval (`request_approval`), push a
  reply-to-approve notification, then poll `check_approval` until the human resolves it
  (approved → PROCEED; denied → BLOCKED) or `timeout_seconds` elapses; on timeout apply
  the gate's `default_action` (`proceed` → PROCEED, `block` → BLOCKED). Server-side
  `expired` status is treated identically to a local timeout.
- **`block`** → return a BLOCKED decision that *parks* the caller. The library never
  hangs and never blocks on a human; the orchestrator persists loop state and stops.
- **Coordinator unreachable at any step** (filing, notifying, or polling) → degrade to
  BLOCKED (**fail closed**), never guess.

Every decision — auto, approved, denied, defaulted, parked, or degraded — is recorded
through an injected audit sink with the posture disposition that authorized it.

### Injection seams (deterministic, host-assisted)

- `CoordinatorClient` protocol (`request_approval` / `push_notification` /
  `check_approval`), raising `CoordinatorUnavailable` on transport failure.
- `AuditSink` protocol (`record`).
- Injectable `clock`, `sleep`, `poll_interval_seconds`, and `posture_loader` — mirroring
  ri-01's injectable-runner pattern — so tests drive the full state machine with a fake
  clock and fake client (no real sleeping, no real network).
- Production defaults `BridgeCoordinatorClient` / `BridgeAuditSink` wire the coordinator
  HTTP bridge (`skills/coordination-bridge`); `build_default_gate(...)` assembles them.

### Result type

`ApprovalDecision` frozen dataclass: `outcome` (PROCEED | BLOCKED), `resolution`
(the specific path), authorizing `disposition`, `gate`, `reason`, optional
`approval_id`, applied `default_action`, and `posture_present`.

### New capability spec

Adds an `approval-gate` capability (see *Out of scope* / design D8 for why a new
capability rather than extending `trust-posture`).

## Out of scope

- **Encoding gates in `autopilot.py` / SKILL.md (ri-06).** The call sites — PLAN
  proposal approval, SUBMIT_PR→DONE merge handoff, ESCALATE resume, `replan_required`,
  and the DONE goal-gate — are the next change. This change ships the *primitive* they
  call, not the wiring.
- **The trust posture contract and loader (ri-04).** Already delivered; consumed here.
- **Adding approval/audit helper endpoints to the coordinator.** The service uses the
  existing `/approvals/request`, `/approvals/{id}`, and notification surfaces via the
  bridge. No coordinator-side changes.
- **New notification channels or reply-to-approve token machinery.** Already exist
  (`agent-coordinator/src/notifications/`, `status.py`).
- **Scheduled sync windows / auto-merge ceilings (Phase 3)** and the **trajectory
  harness (Phase 4)** — separate changes that may consume this primitive later.

## Success Criteria

- `openspec validate build-approval-gate-service-interviewer-abstraction --strict`
  passes.
- All four disposition paths are covered by tests: `auto` proceeds + audits; `notify`
  resolved-approved proceeds; `notify` resolved-rejected blocks; `notify` timeout
  applies `default_action` (both `proceed` and `block` variants); `block` parks without
  hanging.
- Coordinator-unreachable at each notify step (file / notify / poll) degrades to
  BLOCKED, covered by tests.
- Every path writes exactly one audit record carrying the authorizing disposition,
  asserted by tests including the unreachable path.
- The library makes no direct LLM API calls (host-assisted invariant).
- `skills/shared/approval_gate.py` is mirrored into `.claude/skills/shared/` and
  `.agents/skills/shared/`.
