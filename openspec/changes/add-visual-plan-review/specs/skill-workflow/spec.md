# Skill Workflow — Delta for add-visual-plan-review

## ADDED Requirements

### Requirement: Visual Plan Review Artifact

The `plan-feature` skill SHALL be able to render an OpenSpec change's `proposal.md` (and the
`tasks.md` task DAG) into a self-contained, reviewable HTML artifact at
`.plan-review/<change-id>.html`. Every requirement heading and every task in the rendered artifact
SHALL carry a deterministic `data-plan-anchor` attribute derived from its slug/id, so that
annotations remain resolvable after the proposal is edited and the artifact re-rendered. The
artifact SHALL inline all CSS/JS so it can be opened directly from disk without a running server.

#### Scenario: Proposal rendered with stable anchors

- **WHEN** `plan-feature` renders a change whose `proposal.md` contains a requirement "Support
  cloud runs" and whose `tasks.md` contains task `2.1`
- **THEN** the artifact SHALL contain an element with `data-plan-anchor="support-cloud-runs"`
- **AND** an element with `data-plan-anchor="task-2-1"`
- **AND** re-rendering after an unrelated edit SHALL preserve both anchor values
- **AND** the artifact SHALL reference no external stylesheet, script, or font URL

### Requirement: Plan Annotation Capture

The plan-review server SHALL bind to `127.0.0.1` only, serve the artifact, and capture human
annotations of specific elements or text ranges. Each captured annotation SHALL be persisted to the
git-tracked artifact `openspec/changes/<change-id>/plan-annotations.json` as a record
`{uid, selector, tag, text, prompt, target, anchor, resolved}`, where `text` is truncated to 240
characters. The annotation artifact SHALL carry a header block
(`schema_version`, `generated_at`, `git_sha`, `generator`, `run_id`). The agent SHALL retrieve
queued annotations via a long-poll endpoint that does not time out under normal operation and whose
session is keyed by canonical change-id.

#### Scenario: Annotation record persisted

- **WHEN** a human annotates the element `data-plan-anchor="support-cloud-runs"` with the comment
  "this assumption is false in cloud runs"
- **THEN** a record SHALL be appended to `openspec/changes/<change-id>/plan-annotations.json`
- **AND** the record's `anchor` SHALL be `support-cloud-runs`
- **AND** the record's `prompt` SHALL be "this assumption is false in cloud runs"
- **AND** the record's `resolved` SHALL be `false`

#### Scenario: Annotation artifact carries header

- **WHEN** the first annotation for a change is persisted
- **THEN** `plan-annotations.json` SHALL contain a header with `schema_version`, an ISO-8601
  `generated_at`, a `git_sha`, `generator`, and `run_id`

#### Scenario: Long-poll returns annotations

- **WHEN** the agent is blocked on the plan-review long-poll and a human queues two annotations
- **THEN** the poll SHALL return both annotation records
- **AND** queued annotations SHALL survive a client disconnect because they are persisted on queue

### Requirement: Review Session Has an Explicit Completion Signal

The plan-review session SHALL provide an explicit human "done / continue" control in the artifact
that ends the review, and the long-poll SHALL be able to return a terminal `complete` event.
`plan-feature` SHALL leave the visual-review step only after it receives that `complete` event or an
intentional operator abort — never merely because the first batch of annotations arrived — so the
agent knows review is finished. The completion signal SHALL work in the zero-annotation case, so a
reviewer who has no feedback can end the session without the agent blocking indefinitely.

#### Scenario: Poll returns a terminal complete event

- **WHEN** the human clicks "done / continue" in the artifact
- **THEN** the long-poll SHALL return a terminal `complete` event
- **AND** `plan-feature` SHALL exit the visual-review step and proceed to `iterate-on-plan`

#### Scenario: Completing with no annotations does not block

- **WHEN** a reviewer opens the artifact, adds no annotations, and clicks "done / continue"
- **THEN** the poll SHALL return a `complete` event with an empty annotation set
- **AND** `plan-feature` SHALL proceed without having blocked indefinitely

#### Scenario: First annotation batch does not end the session

- **WHEN** the human queues one annotation but has not signalled completion
- **THEN** `plan-feature` SHALL continue waiting for further annotations or the `complete` event
- **AND** SHALL NOT exit the visual-review step after only the first batch

### Requirement: Plan-Review Server Hardens Its Local Endpoints

Binding to `127.0.0.1` alone SHALL NOT be treated as sufficient authorization, because other pages
in the user's browser can reach a localhost endpoint via cross-site requests. The server SHALL embed
a per-session random token in the generated artifact and SHALL require it on every poll and mutation
(annotation-write) request, SHALL validate the `Host` and `Origin` headers, and SHALL NOT enable
permissive CORS. Proposal and task content rendered into the artifact SHALL have raw HTML escaped or
sanitized and SHALL be served under a restrictive Content-Security-Policy, so annotation text or
proposal prose cannot inject script into the local review origin.

#### Scenario: Mutation without the session token is rejected

- **WHEN** a request to write an annotation arrives without the per-session token or with a
  mismatched `Origin`
- **THEN** the server SHALL reject it with a client error
- **AND** SHALL NOT append anything to `plan-annotations.json`

#### Scenario: Rendered proposal content cannot inject script

- **WHEN** a `proposal.md` contains a raw `<script>` tag or an annotation contains HTML
- **THEN** the rendered artifact SHALL escape or sanitize it so it is displayed as text, not executed
- **AND** the artifact SHALL be served under a restrictive Content-Security-Policy

### Requirement: Plan Review Layout Gate

The plan-review server SHALL run an open-time layout audit of the rendered artifact for horizontal
overflow, element clipping, and text overlap, emitting findings of shape
`{selector, kind, overflowPx, viewportWidth, severity}`. Findings of `error` severity SHALL mask the
human view until resolved; findings of `warning` severity SHALL render normally. The audit findings
SHALL be reported back to the agent through the same poll channel as annotations.

#### Scenario: Layout gate masks on error severity

- **WHEN** the rendered artifact overflows the viewport horizontally by 40px
- **THEN** the audit SHALL emit a finding with `kind` indicating horizontal overflow, `overflowPx`
  of 40, and `severity` of `error`
- **AND** the human view SHALL be masked until the finding is resolved
- **AND** the finding SHALL be delivered to the agent via the poll channel

### Requirement: Visual Review Is Environment-Aware and Optional

The visual-review step SHALL be opt-in (a `--visual-review` flag on `plan-feature`) and SHALL be
short-circuited automatically in headless/cloud execution as determined by
`environment_profile.detect()`. When short-circuited, the skill SHALL still write the HTML artifact
to disk and SHALL log that visual review was skipped, and SHALL NOT block on a long-poll. When
enabled and interactive, the skill SHALL wait for the review-complete signal (or an operator abort)
and then fold the **unresolved** annotations into the `iterate-on-plan` pass as element-anchored
findings, and each SHALL be marked `resolved: true` once its feedback has been applied;
`parallel-review-plan` SHALL attach `plan-annotations.json` (when present) to reviewer context. The
visual-review step SHALL run after `tasks.md` has been generated so the rendered task DAG is
populated.

#### Scenario: Visual review gate in plan-feature

- **WHEN** `plan-feature --visual-review` runs in an interactive local environment after `tasks.md`
  has been generated (plan-feature Step 6)
- **THEN** the skill SHALL render and serve the artifact and long-poll for annotations until the
  review-complete event (or an operator abort)
- **AND** on completion SHALL fold the **unresolved** annotations into the `iterate-on-plan` pass as
  element-anchored findings
- **AND** SHALL mark each folded annotation `resolved: true` after its feedback has been applied

#### Scenario: Visual review skipped when headless

- **WHEN** `plan-feature --visual-review` runs in a cloud/headless environment
- **THEN** `environment_profile.detect()` SHALL cause the interactive loop to be skipped
- **AND** the HTML artifact SHALL still be written to `.plan-review/<change-id>.html`
- **AND** the skill SHALL log that visual review was skipped and SHALL NOT block on a poll

#### Scenario: Reviewers see human annotations

- **WHEN** `parallel-review-plan` runs for a change that has a non-empty `plan-annotations.json`
- **THEN** each dispatched reviewer's context SHALL include the human annotation records
