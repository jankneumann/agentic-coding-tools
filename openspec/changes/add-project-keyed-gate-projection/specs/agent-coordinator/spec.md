## ADDED Requirements

### Requirement: Gate Projection Snapshot

The system SHALL store, for each enrolled project, one snapshot of that project's pending gates, replaced as a whole by `POST /gates/projection` and removable by `DELETE /gates/projection`. Enrolled projects SHALL be those named in `GATE_PROJECTION_PROJECTS`. The snapshot SHALL NOT hold decisions, and the system SHALL NOT write to any repository.

#### Scenario: A snapshot replaces the earlier one
- **WHEN** an enrolled project posts a snapshot and then posts a second snapshot with different gates
- **THEN** the stored gates for that project SHALL be exactly those of the second snapshot

#### Scenario: A project that is not enrolled is refused
- **WHEN** a snapshot is posted for a project not named in `GATE_PROJECTION_PROJECTS`
- **THEN** the response SHALL be 403
- **AND** nothing SHALL be stored

#### Scenario: Rebuilding after deletion yields the same set
- **WHEN** a project's snapshot is deleted and the same snapshot is posted again
- **THEN** the listing SHALL return the same gate identifiers for that project as before the deletion

#### Scenario: An oversized snapshot is refused
- **WHEN** a snapshot holds more than 500 gates
- **THEN** the response SHALL be 422

### Requirement: Cross-Project Pending Gate Listing

`GET /gates/pending` SHALL return, in one response, every pending gate of every enrolled project, each with its project, gate type, subject, options, deadline and decision route, and SHALL return the status of every enrolled project. A project with no snapshot, a snapshot older than `GATE_PROJECTION_STALE_SECONDS`, or reported source errors SHALL be returned as `degraded` with a reason, and its last known gates SHALL still be listed.

#### Scenario: Gates of two projects are listed together
- **WHEN** two enrolled projects have each posted a snapshot with one gate
- **THEN** the listing SHALL contain both gates
- **AND** each SHALL carry `project`, `gate`, `subject`, `options` and `deadline`

#### Scenario: An enrolled project with no snapshot is degraded
- **WHEN** an enrolled project has posted no snapshot
- **THEN** the listing's `projects` SHALL include it with `status: degraded` and `reason: no_snapshot`

#### Scenario: A stale snapshot is degraded and still listed
- **WHEN** a project's snapshot was received longer ago than the stale window
- **THEN** the project SHALL have `status: degraded` and `reason: stale`
- **AND** its gates SHALL be listed with `project_status: degraded`

#### Scenario: Source errors degrade a project
- **WHEN** a project's snapshot reports a source error
- **THEN** the project SHALL have `status: degraded` and `reason: source_errors`

#### Scenario: No enrolment means an empty listing
- **WHEN** `GATE_PROJECTION_PROJECTS` is unset
- **THEN** the listing SHALL return no projects

#### Scenario: A gate with a pending approval takes the approval's deadline
- **WHEN** a snapshot gate's `approval_id` names a pending approval request
- **THEN** the gate SHALL be listed with `decision_route: approval_service`, options `approved` and `denied`, and the request's expiry as `deadline`

#### Scenario: A gate whose approval is already decided is not listed
- **WHEN** a snapshot gate's `approval_id` names a request that is no longer pending
- **THEN** the gate SHALL be omitted
- **AND** the project's `decided_awaiting_sync` SHALL count it

#### Scenario: A gate with no approval is routed to the repository
- **WHEN** a snapshot gate has no `approval_id`
- **THEN** the gate SHALL be listed with `decision_route: repository`, options `approved` and `rejected`, and its `answer_hint`

#### Scenario: An approval request no snapshot references is listed
- **WHEN** a pending approval request is referenced by no snapshot gate
- **THEN** the listing SHALL include it with `project` null and `source: approval_service`

### Requirement: Gate Decision Through the Approval Service

`POST /gates/decide` SHALL decide a listed gate by calling the existing approval service for the gate's approval request. It SHALL NOT store the decision anywhere else and SHALL NOT modify the projection.

#### Scenario: A decision reaches the approval request
- **WHEN** a decision is posted for a gate whose `approval_id` names a pending request
- **THEN** that approval request SHALL be decided with the given decision, decider and reason
- **AND** the stored snapshot SHALL be unchanged

#### Scenario: A repository-routed gate is refused with its answer hint
- **WHEN** a decision is posted for a gate with no pending approval request
- **THEN** the response SHALL be 409
- **AND** the response SHALL carry the gate's `answer_hint`

#### Scenario: An unknown gate is not found
- **WHEN** a decision is posted for a gate identifier absent from the project's snapshot
- **THEN** the response SHALL be 404

#### Scenario: An invalid decision is rejected
- **WHEN** a decision other than `approved` or `denied` is posted
- **THEN** the response SHALL be 422
