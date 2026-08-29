# skill-workflow — delta

## MODIFIED Requirements

### Requirement: Session Handoff Hooks

Creative lifecycle skills (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`, `/supervise`) SHALL use handoff hooks when `CAN_HANDOFF=true`. Host-side handoff writers (`coordination_bridge.try_handoff_write`, `PhaseRecord.to_handoff_payload()`, the SessionEnd and PreCompact hooks) SHALL pass an optional `supervisor_record` key through unchanged when the caller supplies one, and SHALL omit it otherwise. The local-fallback envelope schema (`handoff-local-fallback.schema.json`) SHALL accept the optional key.

#### Scenario: Read handoff context at skill start
- **WHEN** a lifecycle skill starts
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL read recent handoffs and incorporate relevant context

#### Scenario: Write handoff summary at completion
- **WHEN** a lifecycle skill completes
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL write a handoff summary with completed work, in-progress items, decisions, and next steps

#### Scenario: Handoff capability unavailable
- **WHEN** `CAN_HANDOFF=false`
- **THEN** the skill SHALL proceed without handoff operations

#### Scenario: Bridge passes the supervisor record through
- **WHEN** `try_handoff_write(content={"supervisor_record": {...}, ...})` is called
- **THEN** the `POST /handoffs/write` body SHALL contain the `supervisor_record` object unchanged
- **AND** when `content` has no `supervisor_record` key the body SHALL NOT contain one

#### Scenario: PhaseRecord carries the record without changing existing payloads
- **WHEN** a `PhaseRecord` with `supervisor_record=None` calls `to_handoff_payload()`
- **THEN** the payload SHALL equal the pre-change payload key-for-key
- **WHEN** `supervisor_record` is set
- **THEN** `to_handoff_payload()` → `from_handoff_payload()` SHALL preserve it byte-identically

#### Scenario: Compaction and session end do not drop the record
- **WHEN** the PreCompact hook or the SessionEnd hook builds its `/handoffs/write` body from the latest phase record
- **AND** that record carries a `supervisor_record`
- **THEN** the body SHALL include it
- **AND** when none is present the body SHALL be identical to today's

#### Scenario: Local fallback file validates with the record present
- **WHEN** `write_both()` falls back to `openspec/changes/<id>/handoffs/<phase-slug>-<N>.json` for a record carrying `supervisor_record`
- **THEN** the written file SHALL validate against `handoff-local-fallback.schema.json`
