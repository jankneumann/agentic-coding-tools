# Approval Gate

## ADDED Requirements

### Requirement: Approval Gate Service Consumes The Trust Posture

The system SHALL provide an approval gate service at
`skills/shared/approval_gate.py` that, given a gate name and a context mapping,
consults the trust posture (via `skills/shared/trust_posture.py`'s `load_posture` and
`disposition_for`) and returns an `ApprovalDecision` describing whether the workflow
may proceed or is parked. The service SHALL read the posture fresh on each evaluation
so posture edits are observed without a restart. It SHALL expose a single evaluation
entry point that returns a decision for every posture outcome and raises only for a
gate name outside the enumerated gates. The service SHALL make no direct LLM API calls.

#### Scenario: Gate resolved against the current posture

- **WHEN** the service evaluates a gate whose posture disposition is `auto`
- **THEN** it SHALL return a decision whose outcome is proceed
- **AND** the decision SHALL carry the authorizing disposition `auto`

#### Scenario: Unknown gate name raises

- **WHEN** the service is asked to evaluate a name outside the enumerated gates
- **THEN** it SHALL raise rather than return a decision

### Requirement: Auto Disposition Proceeds Without A Human

When a gate's disposition is `auto`, the service SHALL return a proceed decision
immediately without contacting the coordinator, filing an approval, or waiting.

#### Scenario: Auto proceeds and records audit

- **WHEN** an `auto` gate is evaluated
- **THEN** the decision outcome SHALL be proceed
- **AND** the coordinator SHALL NOT be contacted
- **AND** an audit record SHALL be written carrying the `auto` disposition

### Requirement: Notify With Timeout Files An Approval And Polls To Resolution

When a gate's disposition is `notify_with_timeout`, the service SHALL file a
coordinator approval request, push a reply-to-approve notification, and poll the
approval status until a human resolves it or the gate's `timeout_seconds` elapses.
A human approval SHALL yield a proceed decision; a human denial SHALL yield a blocked
decision. The polling clock and sleep SHALL be injectable so the timeout is
deterministic and requires no real waiting. A soft notification no-op (no channel
accepted the message) SHALL NOT fail the gate, because the approval remains filed and
resolvable.

#### Scenario: Human approves within the window

- **WHEN** a `notify_with_timeout` gate is evaluated and the human approves before the timeout
- **THEN** the service SHALL return a proceed decision
- **AND** the decision SHALL carry the coordinator approval id

#### Scenario: Human denies within the window

- **WHEN** a `notify_with_timeout` gate is evaluated and the human denies before the timeout
- **THEN** the service SHALL return a blocked decision

#### Scenario: Notification channel is a soft no-op

- **WHEN** the notification push reports that no channel accepted it but the approval was filed and later resolves
- **THEN** the gate SHALL still resolve from the polled approval status rather than failing

### Requirement: Timeout Applies The Gate Default Action

The service SHALL apply the gate's `default_action` when a `notify_with_timeout`
gate's timer expires with no human resolution: `proceed` yields a proceed decision
and `block` yields a blocked decision. A coordinator-reported `expired` status
observed while polling SHALL be treated identically to a local timeout. The applied
default action SHALL be recorded on the decision.

#### Scenario: Timeout with default action proceed

- **WHEN** a `notify_with_timeout` gate with `default_action: proceed` reaches its timeout unresolved
- **THEN** the service SHALL return a proceed decision recording that the default action was applied

#### Scenario: Timeout with default action block

- **WHEN** a `notify_with_timeout` gate with `default_action: block` reaches its timeout unresolved
- **THEN** the service SHALL return a blocked decision recording that the default action was applied

#### Scenario: Server-reported expiry maps to the default action

- **WHEN** a poll observes the coordinator status `expired`
- **THEN** the service SHALL apply the gate's `default_action` as though the local timer had expired

### Requirement: Block Disposition Parks The Caller Without Hanging

When a gate's disposition is `block`, the service SHALL return a blocked decision
synchronously without contacting the coordinator and without waiting. An absent
trust posture (no contract file), which resolves every gate to `block`, SHALL
likewise return a blocked decision, and the decision SHALL indicate the posture was
not present.

#### Scenario: Block parks immediately

- **WHEN** a `block` gate is evaluated
- **THEN** the service SHALL return a blocked decision
- **AND** it SHALL neither contact the coordinator nor sleep

#### Scenario: Absent posture parks and reports not-present

- **WHEN** a gate is evaluated with no trust posture contract present
- **THEN** the service SHALL return a blocked decision
- **AND** the decision SHALL report that the posture was not present

### Requirement: Coordinator Unreachable Degrades To Block

The service SHALL degrade to a blocked decision (fail closed) when the coordinator
transport is unreachable at any step of a `notify_with_timeout` flow — filing the
approval, pushing the notification, or polling the status — and SHALL NOT wait or retry.
This SHALL hold even when the gate's `default_action` is `proceed`, because an
unreachable coordinator means the human was never consulted. The blocked decision
SHALL record that the cause was coordinator unreachability, distinct from a human
denial.

#### Scenario: Filing the approval fails

- **WHEN** `request_approval` fails with a transport error
- **THEN** the service SHALL return a blocked decision recording coordinator unreachability

#### Scenario: Polling fails mid-window

- **WHEN** an approval was filed but a later `check_approval` fails with a transport error
- **THEN** the service SHALL return a blocked decision
- **AND** the decision SHALL preserve the filed approval id

#### Scenario: Fail closed overrides a proceed default

- **WHEN** the coordinator is unreachable for a gate whose `default_action` is `proceed`
- **THEN** the service SHALL return a blocked decision rather than proceeding

### Requirement: Every Decision Is Audited With Its Authorizing Disposition

The service SHALL record exactly one audit entry for every evaluation — auto,
approved, denied, defaulted, parked, or degraded — through an injectable audit sink.
Each audit entry SHALL carry the gate, the outcome, the specific resolution, and the
trust posture disposition that authorized the decision. Audit recording SHALL be
best-effort: a failure of the audit sink SHALL be logged but SHALL NOT prevent the
decision from being returned to the caller. The audit sink SHALL be a distinct
injection seam from the coordinator client so that a decision reached while the
coordinator is unreachable is still audited.

#### Scenario: Audit written on the coordinator-unreachable path

- **WHEN** a `notify_with_timeout` gate degrades to block because the coordinator is unreachable
- **THEN** an audit record SHALL still be written carrying the `notify_with_timeout` disposition and a coordinator-unreachable resolution

#### Scenario: Audit sink failure does not crash the gate

- **WHEN** the audit sink raises while recording a decision
- **THEN** the failure SHALL be swallowed and the decision SHALL still be returned to the caller

### Requirement: Deterministic Injection Seams And Bridge-Backed Defaults

The service SHALL accept an injected coordinator client, audit sink, clock, sleep
function, poll interval, and posture loader so that tests exercise every path
deterministically with no real network and no real sleeping. The service SHALL also
provide production defaults that reach the coordinator through the existing
coordination bridge (`skills/coordination-bridge`) and a factory that assembles them.
The default coordinator client SHALL raise a coordinator-unavailable error on any
transport failure so the fail-closed degradation is triggered.

#### Scenario: Injected doubles drive the state machine

- **WHEN** the service is constructed with a fake clock, fake coordinator client, and recording audit sink
- **THEN** every disposition path SHALL be exercisable without real time passing or real network calls

#### Scenario: Bridge-backed default client fails closed on transport error

- **WHEN** the default bridge-backed coordinator client receives a transport error from the bridge
- **THEN** it SHALL raise a coordinator-unavailable error rather than returning a status
