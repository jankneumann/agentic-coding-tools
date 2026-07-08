# Tasks: Build Approval Gate Service (Interviewer Abstraction)

> Change ID: `build-approval-gate-service-interviewer-abstraction`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## 1. Design and spec

- [x] 1.1 Rewrite `proposal.md` (Why / What Changes / Out of Scope / Success Criteria)
- [x] 1.2 Write `design.md` (interviewer abstraction, polling/timeout model, fail-closed degradation, audit contract, alternatives)
- [x] 1.3 Add `specs/approval-gate/spec.md` delta (new capability, ADDED requirements + scenarios)
- [x] 1.4 Justify new `approval-gate` capability vs extending `trust-posture` (design D8)

## 2. Result types and injection seams

- [x] 2.1 Define `Outcome` (proceed/blocked) and `Resolution` (auto/approved/rejected/timeout×2/posture_block/unreachable) enums
- [x] 2.2 Define frozen `ApprovalDecision` (gate, outcome, resolution, disposition, reason, approval_id, default_action, posture_present) with `to_audit_record`
- [x] 2.3 Define `CoordinatorClient` protocol (`request_approval` / `push_notification` / `check_approval`) and `CoordinatorUnavailable`
- [x] 2.4 Define `AuditSink` protocol distinct from the coordinator client
- [x] 2.5 Make clock, sleep, poll interval, and posture loader injectable (ri-01 pattern)

## 3. Gate state machine

- [x] 3.1 `auto` → proceed immediately, no coordinator contact
- [x] 3.2 `block` → park synchronously, never hang
- [x] 3.3 `notify_with_timeout` → file approval, notify (best-effort), poll to resolution
- [x] 3.4 Timeout → apply `default_action` (proceed/block); map server `expired` to the same branch
- [x] 3.5 Fail closed: `CoordinatorUnavailable` at file/notify/poll → block, even under `default_action: proceed`
- [x] 3.6 Audit exactly once on every path via `_finalize`, best-effort, carrying the authorizing disposition

## 4. Production defaults (bridge-backed)

- [x] 4.1 `BridgeCoordinatorClient` over the coordination bridge (`/approvals/request`, `/approvals/{id}`, `/notifications/test`), raising `CoordinatorUnavailable` on transport error
- [x] 4.2 `BridgeAuditSink` recording decisions to the coordinator durable memory surface (`try_remember`)
- [x] 4.3 `build_default_gate(...)` factory wiring the defaults
- [x] 4.4 No direct LLM API calls anywhere in the library (host-assisted invariant)

## 5. Tests (`skills/shared/tests/test_approval_gate.py`)

- [x] 5.1 `auto` proceeds + audits; coordinator untouched
- [x] 5.2 `block` parks + audits, no sleep/coordinator; absent-posture parks + reports not-present
- [x] 5.3 `notify` resolved-approved proceeds; resolved-rejected blocks
- [x] 5.4 `notify` timeout → default_action proceed AND block; server `expired` → default
- [x] 5.5 Soft notification failure is non-fatal
- [x] 5.6 Coordinator-unreachable at file / notify / poll (parametrized) → block; approval_id preserved on poll failure
- [x] 5.7 Audit written in every path (table) with authorizing disposition; audit-sink failure non-fatal
- [x] 5.8 Production `BridgeCoordinatorClient` / `BridgeAuditSink` / `build_default_gate` exercised via monkeypatched bridge (no dead code)

## 6. Sync and validation

- [x] 6.1 Mirror `skills/shared/approval_gate.py` into `.claude/skills/shared/` and `.agents/skills/shared/` (cp; rsync unavailable)
- [x] 6.2 `pytest skills/shared/tests/` green (skills/.venv)
- [x] 6.3 `openspec validate build-approval-gate-service-interviewer-abstraction --strict` passes
- [ ] 6.4 Review and merge
