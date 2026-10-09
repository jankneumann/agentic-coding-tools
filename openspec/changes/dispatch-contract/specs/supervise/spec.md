## ADDED Requirements

### Requirement: Dispatch Result Closure

For every `(outcome class, parked.kind, parked.gate)` combination that `dispatch-result.schema.json` permits, the supervisor SHALL have exactly one answer or resume path, declared in a single table `gate_router.ANSWER_PATHS`. A contract test SHALL derive the permitted combinations from the schema itself (not from a hand-written list) and SHALL fail when any combination lacks an entry or an entry names a combination the schema forbids. The table SHALL include the `pending_gate` / `escalate_resume` path merged from `openspec/supervise-pending-escalate-answer`.

#### Scenario: Every permitted combination has a path
- **WHEN** the closure test enumerates the schema's `parked` `oneOf` branches and their `kind` / `gate` enums, plus the `success`, `failed:*`, and `vendor_limit:*` outcome classes
- **THEN** each combination SHALL map to an entry in `ANSWER_PATHS`, and the test SHALL report the full list of missing combinations when any is absent

#### Scenario: Adding a kind without a path fails the test
- **WHEN** a test fixture copy of the result schema adds a parked kind `example_kind` with no `ANSWER_PATHS` entry and the closure check runs against that copy
- **THEN** the check SHALL fail naming `("parked", "example_kind", null)`

#### Scenario: pending_gate with escalate_resume is answerable
- **WHEN** a child returns `parked/pending_gate` with `gate: escalate_resume`
- **THEN** `resolve_parked` SHALL evaluate `escalate_resume` for that dispatch generation and, on `proceed`, resume it

### Requirement: Typed Gate Answers With Provenance

Every gate-decision record the router writes SHALL carry `provenance`, either `{source: "posture", posture_digest}` or `{source: "human", approval_ref}`. When resolving a parked attempt, the router SHALL re-evaluate a prior `posture`-provenance block whose `posture_digest` differs from the current posture digest, and SHALL treat a `human`-provenance decision as final for its subject. A resume request SHALL carry the decision to the child only as `gate_answer: {gate, decision, approval_ref}`; the supervisor SHALL NOT write any file in a child worktree other than the launch marker.

#### Scenario: A posture-derived block clears after a posture change
- **GIVEN** an attempt parked `pending_gate/proposal_approval` whose supervisor record has `resolution: posture_block` and `provenance.posture_digest` D1
- **WHEN** the operator changes `TRUST_POSTURE.md` so `proposal_approval` is `auto` (digest D2) and `resolve_parked` runs for the attempt, whose persisted `roadmap_approval_ref` was verified at prepare
- **THEN** a new `proceed` record with `provenance: {source: posture, posture_digest: D2}` SHALL be written and the attempt SHALL be resumed with `gate_answer.decision: approved`
- **AND** the child applying that answer SHALL leave `PLAN` without parking again

#### Scenario: A human rejection survives a posture change
- **GIVEN** a prior record for the same subject with `resolution: console_rejected` and `provenance.source: human`
- **WHEN** the posture changes the gate to `auto` and `resolve_parked` runs
- **THEN** no new record SHALL be written, the attempt SHALL stay parked, and the router SHALL return the existing blocked entry

#### Scenario: An unchanged posture does not re-evaluate
- **WHEN** `resolve_parked` runs for a `posture_block` record whose `posture_digest` equals the current digest
- **THEN** the prior record SHALL be reused and no approval SHALL be filed

#### Scenario: A prose-only posture edit is not a posture change
- **WHEN** only the Markdown body of `TRUST_POSTURE.md` changes and its front matter is unchanged
- **THEN** the posture digest SHALL be unchanged

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve an `execution_profile` (verified lanes per mode `review`, `alternative`, `quick`; `location`; isolation mode; and `probe_command`, the only probe a worker may run) by invoking `review_dispatcher.py --check-vendors --json`, and `review_requirements` (`min_quorum` per review phase, default 2 and overridable by router context `review_min_quorum`, and `counting_lanes` ordered by the `cost_policy.tiers` ladder of `agent-coordinator/routing.yaml`), and SHALL place both in every request. The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's `degradations` on the checkpoint attempt and SHALL return them in its summary.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty `execution_profile.lanes.review`, `execution_profile.probe_command`, and `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL list only the verified lanes, so the child parks `capability_unavailable` at its first review phase

#### Scenario: The per-environment quorum is resolved from data
- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1 that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one review lane verifies
- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its sunset condition
- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL stay 2

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value SHALL both contain that entry unchanged

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key variables for vendor discovery

### Requirement: Single Escalation Per Capability Park

The router SHALL map `permission_blocked` and `capability_unavailable` parks to an `escalate_resume` subject keyed by a dedupe fingerprint — `sha256(tool, rule, classifier_reason)` for `permission_blocked`, `sha256(phase, sorted(missing_lanes))` for `capability_unavailable` — and SHALL project exactly one `pending_gates` entry per fingerprint listing every parked dispatch that shares it. One `proceed` answer SHALL resume each listed attempt through its own generation-checked compare-and-swap. The stored redacted command SHALL be the output of `sanitize_session_log.sanitize()` (secret-pattern and high-entropy redaction) truncated to 256 characters.

#### Scenario: Three workers blocked on one rule produce one escalation
- **WHEN** three attempts park `permission_blocked` with tool `Bash`, rule `Bash(env *)`, and the same classifier reason
- **THEN** the supervisor record SHALL contain one `pending_gates` entry whose dispatch list has all three IDs

#### Scenario: One answer resumes every attempt in the entry
- **WHEN** the operator answers that entry `approved`
- **THEN** each of the three attempts SHALL be resumed once with a distinct new generation, and an attempt whose generation changed since projection SHALL be skipped and reported, not resumed

#### Scenario: Different missing lanes are separate escalations
- **WHEN** one attempt parks `capability_unavailable` missing `{codex}` and another missing `{codex, gemini}` for the same phase
- **THEN** two `pending_gates` entries SHALL exist

#### Scenario: A secret in the blocked command is redacted
- **WHEN** a `permission_blocked` park reports command `curl -H "Authorization: Bearer abc123..."`
- **THEN** the persisted command SHALL not contain `abc123` and SHALL contain a `[REDACTED:` marker
