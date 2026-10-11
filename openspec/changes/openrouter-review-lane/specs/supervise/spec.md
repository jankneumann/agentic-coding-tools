## MODIFIED Requirements

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve two values by invoking
`review_dispatcher.py --check-vendors --json`, and SHALL place both in every request:

- **`execution_profile`**: verified lanes per mode (`review`, `alternative`, `quick`);
  `location`; isolation mode; and `probe_command`, the only probe a worker may run.
- **`review_requirements`**: `min_quorum` per review phase, and `counting_lanes`.
  - `min_quorum` defaults to 2 and can be overridden by the router context
    `review_min_quorum`.
  - `counting_lanes` are ordered by the `cost_policy.tiers` ladder of
    `agent-coordinator/routing.yaml`. Each lane's endpoint kind is read from the report's
    `lane_kinds`. The kind is inferred from the `probe_unsupported` reason only when
    `lane_kinds` is absent.

The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables
or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's
`degradations` on the checkpoint attempt and SHALL return them in its summary. When the result
carries a `metered_spend_unrecorded` degradation, `apply` SHALL run
`spend_recorder.py replay --change-id <id>` once, and SHALL report the replay outcome in its
summary without failing the apply.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty
  `execution_profile.lanes.review`, `execution_profile.probe_command`, and
  `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying
  an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe
  failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL
  list only the verified lanes, so the child parks `capability_unavailable` at its first review
  phase

#### Scenario: The per-environment quorum is resolved from data
- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1
  that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one
  review lane verifies
- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase,
  and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its
  sunset condition
- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL
  stay 2

#### Scenario: A verified OpenRouter lane is ranked as metered
- **WHEN** the report's `review.verified` is `["claude_code", "openrouter"]` with
  `lane_kinds: {"claude_code": "vendor-cli", "openrouter": "openrouter"}`, and the routing ladder is
  `[vendor-cli, vendor-sdk, openrouter]`
- **THEN** `counting_lanes` SHALL be `["claude_code", "openrouter"]`, and `min_quorum` SHALL be 2
  for each review phase

#### Scenario: A report without lane_kinds still ranks
- **WHEN** the report has no `lane_kinds` key
- **THEN** ranking SHALL use the previous `probe_unsupported` inference and `prepare` SHALL succeed

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries
  `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value
  SHALL both contain that entry unchanged

#### Scenario: Unrecorded spend is replayed on apply
- **WHEN** a result carries a `metered_spend_unrecorded` degradation and the coordinator accepts
  the replay
- **THEN** `apply` SHALL return a summary with the replayed row count, and the degradation SHALL
  remain on the checkpoint attempt

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key
  variables for vendor discovery
