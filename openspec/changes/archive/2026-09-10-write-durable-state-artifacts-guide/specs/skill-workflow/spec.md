## ADDED Requirements

### Requirement: Canonical durable state-artifact inventory

The repository SHALL provide one canonical guide that documents the five durable orchestration artifact classes: per-change loop state, roadmap checkpoint state, roadmap learning entries, phase records, and handoff documents. For each class, the guide SHALL state its path, holder/scope, canonical writer, authority, consumers, and missing or stale behavior.

#### Scenario: All durable classes are discoverable

- **WHEN** a contributor opens the durable state-artifacts guide
- **THEN** all five artifact classes SHALL be named with their exact repository or coordinator path
- **AND** every class SHALL identify its holder, writer, authority, consumers, and missing/stale behavior

#### Scenario: Advisory state conflicts with authoritative state

- **WHEN** a handoff, phase record, learning entry, or queue projection conflicts with a valid loop-state or roadmap checkpoint record for the same scope
- **THEN** the authoritative record SHALL win
- **AND** the conflict SHALL be reported rather than silently merged

### Requirement: Deterministic fresh-session rehydration

The guide SHALL distinguish bootstrap discovery from canonical verification and SHALL define this ordered rehydration sequence for a fresh supervisor session: bootstrap locator, roadmap definition, roadmap execution state, change execution state, learning context, phase history, handoff context, and projection rebuild. The learning-context stage SHALL use a bounded recent-learning window without making its numeric bound part of this documentation contract.

#### Scenario: Fresh supervisor session resumes active work

- **WHEN** a fresh supervisor session receives a supervisor handoff or tracked mirror
- **THEN** it SHALL use that artifact only to locate candidate active roadmaps and changes
- **AND** it SHALL verify roadmap checkpoints before per-change loop state
- **AND** it SHALL load learnings, phase records, and bounded handoff context only after authoritative state
- **AND** it SHALL rebuild coordinator and queue projections only after advisory context has been reconciled with authoritative state

#### Scenario: Never-started roadmap has no checkpoint

- **WHEN** a roadmap definition exists but no locator or advisory record claims prior execution progress
- **AND** its canonical checkpoint does not yet exist
- **THEN** rehydration SHALL treat the roadmap as never started rather than degraded
- **AND** it SHALL NOT synthesize a checkpoint from the roadmap definition or advisory context

#### Scenario: Canonical state is missing

- **WHEN** a bootstrap handoff names an active roadmap or change whose canonical checkpoint or loop-state artifact is missing
- **THEN** rehydration SHALL report a degraded or inconsistent state
- **AND** it SHALL NOT reconstruct authoritative phase state from the handoff, learning log, phase record, or queue

### Requirement: Workflow skill documentation references the canonical guide

The canonical `autopilot`, `autopilot-roadmap`, `session-log`, `supervise`, `implement-feature`, and `validate-feature` skill sources SHALL carry the repository-relative `docs/guides/state-artifacts.md` reference for shared ownership and replay semantics while retaining their phase-specific commands and gate rules.

#### Scenario: Relevant skill documentation is audited

- **WHEN** the focused state-artifact documentation test inspects the relevant canonical skill sources
- **THEN** each of the six named sources SHALL reference `docs/guides/state-artifacts.md`
- **AND** the supervise rehydration section SHALL follow the guide's ordered canonical verification sequence

#### Scenario: Runtime skill mirrors are installed

- **WHEN** the canonical changed skills are installed into `.agents` and `.claude`
- **THEN** each changed mirror SHALL be byte-identical to its canonical `skills/` source

