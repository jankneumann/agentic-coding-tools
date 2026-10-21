## Review Round 2

The packet is complete; do not explore the repo for missing artifacts.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
(empty-diff)
```

### Spec excerpts
#### specs/configuration/spec.md
## MODIFIED Requirements

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2). The provider key set SHALL be closed to the five roster keys, all five required, plus two optional keys: `local` and `openrouter`. `openrouter` holds the model aliases of the endpoint-only `openrouter-review` lane, and is not a roster vendor.

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

#### Scenario: Optional provider keys are allowed but not required

- **WHEN** a provider model map carries an `openrouter` entry or a `local` entry
- **THEN** it SHALL validate, provided the entry defines `premium`, `standard`, and `economy`
- **AND** a map without either entry SHALL also validate
- **AND** a map with any other provider key SHALL fail validation

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping


#### specs/model-routing/spec.md
## ADDED Requirements

### Requirement: Review Spend Recording Route

The coordinator SHALL expose `POST /routing/spend`, which requires the `X-API-Key` header.

The request body SHALL be validated with unknown fields forbidden. It accepts:
- required: `vendor`, `model`, `endpoint_kind`, `generation_id`;
- optional: `prompt_tokens`, `completion_tokens` (non-negative integers), `actual_usd` (a
  non-negative number), `tokens_estimated`, `work_unit_ref`, `occurred_at`.

A valid request SHALL write one `routing_spend_ledger` row through `LedgerService.record`.
`generation_id` SHALL be the idempotency key: a second request with a `generation_id` already
in the ledger SHALL return the existing row with HTTP 200 and SHALL NOT insert another row.
`GET /routing/usage` SHALL include recorded review rows in `metered_usd_used`.

#### Scenario: A review spend row is recorded
- **WHEN** an authenticated client posts `{vendor: "openrouter", model: "<publisher>/<model>", endpoint_kind: "openrouter", generation_id: "gen-abc", actual_usd: 0.0042, tokens_estimated: false}`
- **THEN** the response SHALL be HTTP 201, and the next `GET /routing/usage?window=month` SHALL
  report `metered_usd_used` increased by 0.0042

#### Scenario: Duplicate generation id is not double-counted
- **WHEN** the same body is posted twice
- **THEN** the second response SHALL be HTTP 200 and the ledger SHALL contain one `gen-abc` row

#### Scenario: Unauthenticated write is rejected
- **WHEN** the request has no `X-API-Key` header, or an invalid one
- **THEN** the response SHALL be HTTP 401 and no row SHALL be written

#### Scenario: Invalid spend is rejected
- **WHEN** the body has `actual_usd: -1`, or an unknown field `api_key`
- **THEN** the response SHALL be HTTP 422 and no row SHALL be written


#### specs/parallel-infrastructure/spec.md
## MODIFIED Requirements

### Requirement: OpenAI-Compatible Dispatcher Discovery

The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
precedence over the endpoint adapter for the same agent.

The lane id of an endpoint lane SHALL be its agent `type`. Its model family SHALL be the
publisher prefix of its primary model slug (`<publisher>/<model>`). The family of a CLI or SDK
vendor SHALL be read from `vendor_families` in `review_quorum_policy.json`.

The dispatcher SHALL skip, and SHALL NOT count toward quorum, an `openrouter` lane in either
of these cases:
- its primary model or any fallback model has publisher `anthropic`;
- its family equals the family of a lane already selected at tier 1 or tier 2. The skip
  reason SHALL be `duplicate_model_family`.

An agent with `endpoint_kind: openrouter` selected at tier 2.5 is a metered lane. Metered lanes
SHALL be selected only while the non-metered selected lanes number fewer than
`metered_lanes.fill_target`. That value defaults to the policy file's `default_min_quorum`.
Metered lanes are added in roster order until the target is reached. `--check-vendors` and
`dispatch_and_wait` SHALL apply the same selection.

`dispatch_and_wait` SHALL accept an optional `include_lanes` set. When it is given, only those
lanes SHALL be dispatched. When it is `None`, behaviour SHALL be unchanged.

#### Scenario: Endpoint-only agent is discoverable

- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint

#### Scenario: CLI retains precedence

- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
- **THEN** review discovery SHALL select the CLI tier first

#### Scenario: Anthropic-family OpenRouter lane is rejected

- **WHEN** an `openrouter` agent resolves the primary model `anthropic/<any>` or lists an
  `anthropic/` fallback
- **THEN** discovery SHALL NOT return that lane, and `--check-vendors --json` SHALL list it
  under `unverified` with reason `anthropic_family`

#### Scenario: Duplicate family is skipped

- **WHEN** `codex` is selected at tier 1, `vendor_families.codex` is `openai`, and an
  `openrouter` lane's primary model is `openai/<model>`
- **THEN** that lane SHALL be listed `unverified` with reason `duplicate_model_family` and SHALL
  NOT be dispatched

#### Scenario: Metered lane fills quorum only

- **WHEN** `fill_target` is 2, and two non-metered lanes and one verified `openrouter` lane are
  available
- **THEN** discovery SHALL return the two non-metered lanes only, and no HTTP request SHALL be
  sent to the OpenRouter endpoint during dispatch

#### Scenario: Metered lane fills a cloud roster

- **WHEN** `fill_target` is 2, `claude_code` is the only non-metered lane, and one `openrouter`
  lane verifies
- **THEN** discovery SHALL return `claude_code` and the `openrouter` lane

#### Scenario: include_lanes restricts dispatch

- **WHEN** `dispatch_and_wait` is called with `include_lanes={"openrouter"}` and `claude_code` and
  `openrouter` are both available
- **THEN** exactly one review SHALL be dispatched, to `openrouter`

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only
after a dry invocation for that mode succeeds. The dry invocation is the adapter's declared
no-op, run with a 10-second timeout:
- for a CLI lane, `<cli> --version`;
- for an `openrouter` API lane, one authenticated `GET {base_url}/key`;
- for a `local` API lane, one authenticated `GET {base_url}/models`.

An SDK lane with no authenticated no-op SHALL remain `unverified` with reason
`probe_unsupported`.

Credentials MAY be read only inside the adapter's existing credential path. The probe SHALL
NOT print, log, or return any environment value, credential, or response body. From an API
probe response it SHALL keep only the numeric budget fields (`limit`, `usage`,
`limit_remaining`).

An `openrouter` lane SHALL verify only if:
- the authenticated probe succeeds;
- at least one spend ceiling source is available: the coordinator monthly ceiling when it is
  greater than 0 and the coordinator is reachable, or the key's non-null `limit`; and
- every available source has remaining budget of at least
  `metered_lanes.review_reservation_usd`.

A `local` API lane SHALL verify when its probe succeeds; no budget rule applies to it.
An `openrouter` lane that fails any of these conditions SHALL be `unverified` with one of these reasons: `auth_failed`,
`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`, or
`spend_ceiling_unverifiable`.

With `--json` it SHALL print
`{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}], "lane_kinds": {<lane>: <endpoint_kind>}}}, "probe_command": "<argv>"}`.
It SHALL keep its existing exit codes: 0 at quorum, 2 below quorum or on probe failure. When
the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason
  `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890`,
  `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and
  `OPENROUTER_API_KEY=sk-or-test-SENTINEL-5555555555`, configures an `openrouter` lane with an
  injected transport that echoes the request headers in its response body, and runs
  `--check-vendors --json`
- **THEN** no sentinel value SHALL appear in stdout, stderr, log records, or the JSON, and no
  `env` or `printenv` subprocess SHALL have been spawned

#### Scenario: An OpenRouter lane verifies by its authenticated no-op
- **WHEN** the injected transport answers `GET /key` with HTTP 200 and `limit: 20.0`,
  `limit_remaining: 15.0`, the coordinator is unreachable, and `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be listed under `verified` for mode `review`, `lane_kinds` SHALL map
  it to `openrouter`, and no chat-completions request SHALL have been sent

#### Scenario: A rejected key is unverified
- **WHEN** the injected transport answers `GET /key` with HTTP 401
- **THEN** the lane SHALL be `unverified` with reason `auth_failed`

#### Scenario: An exhausted ceiling is unverified
- **WHEN** the coordinator reports `metered_ceiling_usd: 50.0` and `metered_usd_used: 49.5`, and
  `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_exceeded`, even if the key's
  `limit_remaining` is larger

#### Scenario: No ceiling source fails closed
- **WHEN** the coordinator is unreachable or reports `metered_ceiling_usd: 0`, and the key
  reports `limit: null`
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable`

#### Scenario: An unexpected probe response shape fails closed
- **WHEN** `GET /key` returns HTTP 200 with a body that has no `data` object
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable` unless the
  coordinator ceiling source alone verifies it

## ADDED Requirements

### Requirement: Metered Review Lane Spend Accounting

Every review that an `openrouter` lane dispatches SHALL request inline usage accounting
(`"usage": {"include": true}`). On the resulting `ReviewResult` it SHALL set:
- `generation_id`, `model_used`, `prompt_tokens`, `completion_tokens`;
- `cost_usd`, taken from the response's `usage.cost`;
- `cost_source`: `reported` when `usage.cost` is present, `estimated` when it is absent.

`converge()` SHALL write these fields into the round checkpoint's vendor index.

After each review that sent a request, `ReviewOrchestrator.dispatch_and_wait` SHALL call
`spend_recorder.record()`, which SHALL send one row to `POST /routing/spend` with:
`vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
`actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
`work_unit_ref` (`<change_id>:<phase>:round-<n>`, for example
`openrouter-review-lane:VAL_REVIEW:round-2`; the phase, not the review type, so IMPL_REVIEW and
VAL_REVIEW rows stay distinct; `converge()` supplies it in the `spend_context` it passes to
`dispatch_and_wait` when its caller gives the phase). The call SHALL happen on every dispatch path, including a host
`converge()` or `/parallel-review-*` run that selected the metered lane, not only inside
`agent_lane.py`. The result SHALL carry `spend_recorded` (the recorder's `recorded` value).

If the write fails, the record SHALL be appended to
`openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
degradation `metered_spend_unrecorded` with phase and lane. The change id SHALL come from the
`spend_context` (`change_id`, `work_unit_ref`) passed to `dispatch_and_wait`. A metered lane
dispatched without a `spend_context` SHALL NOT make an HTTP request; it SHALL return a failed
result with `error_class` `vendor_unavailable` and reason `spend_context_missing`.

#### Scenario: A metered lane without spend context is not dispatched
- **WHEN** `dispatch_and_wait` is called with no `spend_context` and the selection includes the
  `openrouter` lane
- **THEN** no HTTP request SHALL be made for that lane, and its result SHALL have `error_class`
  `vendor_unavailable` and reason `spend_context_missing`

`spend_recorder.py replay --change-id <id>` SHALL post the spooled rows. Replay SHALL skip a
`generation_id` the ledger already holds, and SHALL remove each row it delivers.

Each time `dispatch_and_wait` is about to dispatch a metered lane (once per review round, on
every dispatch path), the remaining budget SHALL be re-checked with the same rule the probe
uses. A lane below `review_reservation_usd` SHALL NOT be dispatched
for that round and SHALL be reported as a failed result with `error_class` `vendor_unavailable`
and reason `spend_ceiling_exceeded`.

#### Scenario: A later round finds the ceiling exhausted
- **WHEN** the coordinator ceiling had budget at probe time, and before round 2 its remaining
  budget is below `review_reservation_usd`
- **THEN** round 2 SHALL NOT dispatch the `openrouter` lane, and SHALL record it as
  `vendor_unavailable` with reason `spend_ceiling_exceeded`

#### Scenario: A review is recorded against the ledger
- **WHEN** an `openrouter` review returns `id: gen-abc`, `usage: {prompt_tokens: 1200, completion_tokens: 300, cost: 0.0042}`, and the coordinator accepts the write
- **THEN** the ledger SHALL contain one row with `generation_id: gen-abc`, `actual_usd: 0.0042`,
  and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
  the same generation id, model and cost

#### Scenario: A host-path metered review is recorded
- **WHEN** a host with one non-metered lane runs `converge()` with `ReviewOrchestrator`, the fill
  rule selects the `openrouter` lane, and its review returns `id: gen-host`
- **THEN** `spend_recorder.record()` SHALL have been called once for `gen-host`, and the result's
  `spend_recorded` SHALL be true when the coordinator accepts the write

#### Scenario: Missing cost is labelled estimated
- **WHEN** the response has token usage but no `usage.cost`
- **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
  `tokens_estimated: true`

#### Scenario: Coordinator unavailable spools the record
- **WHEN** `POST /routing/spend` fails

[spec excerpt truncated]


#### specs/skill-workflow/spec.md
## MODIFIED Requirements

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase
whose verified lanes from `execution_profile` are fewer than
`review_requirements.min_quorum[phase]` SHALL record
`park(kind=capability_unavailable, phase, missing_lanes)` and stop. It SHALL NOT run the review
with a lower quorum.

A standalone run (no launch marker) SHALL keep disabling CLI review below quorum. It SHALL
record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one
lane reviewed.

During `converge()`, a round can end with fewer successful results than `min_quorum`.
`missing_lanes` SHALL be the round's verified lanes minus the lanes that returned a successful
result. When `missing_lanes` is non-empty and every lane in it has a recorded failure whose
`error_class` is `vendor_unavailable` or `auth_required`, `converge()` SHALL return
`reason="capability_unavailable"` with `missing_lanes` naming those lanes. A verified lane with
no result at all SHALL NOT satisfy this condition. This
covers an exhausted budget, HTTP 402, a revoked key, or `packet_requires_tools`. Any other
quorum loss SHALL remain `reason="quorum_lost"`.


#### Scenario: A lane that returns nothing is not a capability loss
- **WHEN** a PLAN_REVIEW round has verified lanes `claude_code` and `openrouter`, `claude_code`
  succeeds, and `openrouter` returns neither a result nor a recorded failure
- **THEN** `converge()` SHALL return `reason="quorum_lost"`, not `capability_unavailable`

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming
  the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL
  return `parked/capability_unavailable`

#### Scenario: A single-lane review under a quorum-1 policy is recorded
- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy
  data, and exactly one review lane dispatches because the others failed to dispatch
- **THEN** the review SHALL run, and `degradations` SHALL contain a `single_vendor_review` entry
  for `PLAN_REVIEW` whose detail names the vendor
- **AND** the child SHALL NOT have read environment variables or credentials to decide that only
  one lane exists

#### Scenario: GATEKEEPER review scheduling on the host-driven path
- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one
  `review_skipped` entry for `PLAN_REVIEW`

#### Scenario: Budget exhausted mid-run parks instead of losing quorum
- **WHEN** `min_quorum` is 2, round 1 succeeds with `claude_code` and `openrouter`, and in round 2
  `openrouter` fails with HTTP 402 (`error_class=vendor_unavailable`)
- **THEN** `converge()` SHALL return `reason="capability_unavailable"` with
  `missing_lanes == ["openrouter"]`, and SHALL NOT return `quorum_lost`

#### Scenario: A malformed review still loses quorum
- **WHEN** `min_quorum` is 2 and a round's `openrouter` result fails with
  `error_class=unknown` ("Review output was not valid review-findings JSON")
- **THEN** `converge()` SHALL return `reason="quorum_lost"`

## ADDED Requirements

### Requirement: Composite Agent-Lane Review

`agent_lane.py converge` SHALL accept `--verified-lanes` (repeatable). A dispatched child SHALL
take the values from its launch marker's `execution_profile.lanes.review`. A standalone run
SHALL take them from the `--check-vendors --json` output and SHALL NOT read environment
variables or credentials.

It SHALL resolve the quorum policy with `verified_review_lanes` equal to the number of
verified lanes, and SHALL pass those lanes to `converge()` as `verified_lanes`.

Each round SHALL:
- dispatch the `claude_code` handshake lane;
- in parallel, dispatch `ReviewOrchestrator.dispatch_and_wait(include_lanes=<verified lanes except claude_code>)`;
- return both results to `converge()`.

Every lane's findings SHALL be written to the round checkpoint under its own lane id, and
ConsensusSynthesizer SHALL attribute consensus findings to those lane ids.

After each run, `agent_lane.py` SHALL write `ConvergenceResult.consensus` (including
`quorum_received`) under `openspec/changes/<change-id>/reviews/`, with one file per phase:
- `consensus-plan.json` for `PLAN_REVIEW`;
- `consensus-impl-review.json` for `IMPL_REVIEW`;
- `consensus-val-review.json` for `VAL_REVIEW`.

The two implementation phases share `review_type: implementation`, so the file is named by phase
and neither run overwrites the other. `converge()` itself SHALL NOT be required to write these
files.

The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
`single_vendor_review` degradation only when exactly one lane reviewed.

#### Scenario: Cloud plan review reaches quorum two
- **WHEN** `agent_lane.py converge --phase PLAN_REVIEW --verified-lanes claude_code --verified-lanes openrouter`
  runs against a fixture change, with an injected OpenRouter transport that returns
  schema-valid findings and an agent handshake that writes schema-valid findings
- **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
  findings files for both `claude_code` and `openrouter`, `consensus` SHALL report
  `quorum_received: 2`, and `reviews/consensus-plan.json` SHALL contain the same consensus

#### Scenario: Findings carry vendor attribution
- **WHEN** both lanes report a finding at the same file and line range
- **THEN** the consensus finding SHALL list both `claude_code` and `openrouter` in its vendor
  attribution, and the review ledger entry SHALL preserve both lane ids

#### Scenario: Only the agent lane verified
- **WHEN** `--verified-lanes claude_code` is the only lane and no active policy lowers the quorum
- **THEN** `converge()` SHALL return `capability_unavailable` with `missing_lanes` naming the
  counting lanes not verified, and no handshake file SHALL be written

### Requirement: Cloud Single-Vendor Policy Retirement

The temporary cloud single-vendor policy SHALL be retired only after an evidence file
`openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` records a cloud-container
autopilot run on a fixture change. The run must show:
- `PLAN_REVIEW` with `min_quorum=2`;
- a `consensus-plan.json` attributing findings or confirmations to `claude_code` and to an
  `openrouter` lane;
- a ledger or spool row carrying that review's `generation_id`.

Retirement SHALL:
- delete the `cloud-container-single-vendor-2026-10-09` entry from
  `review_quorum_policy.json`, keeping the `policies` array and its `sunset` field as the
  mechanism for future exceptions;
- delete the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`;
- update `skills/autopilot/SKILL.md` so that no instruction tells a cloud worker to accept
  single-vendor review.

#### Scenario: Retirement restores quorum two in cloud
- **WHEN** the policy entry has been deleted and `resolve_quorum_policy(environment="cloud_container", verified_review_lanes=1)` is called
- **THEN** `min_quorum` SHALL be 2 for each review phase and `policy_id` SHALL be null

#### Scenario: Retirement is blocked without evidence
- **WHEN** a guard test finds `review_quorum_policy.json` without the cloud entry but no
  `evidence/cloud-quorum-run.md` in this change, or an evidence file missing a `generation_id`
- **THEN** the test SHALL fail

#### Scenario: No prose exception remains
- **WHEN** a guard test scans `TRUST_POSTURE.md` after retirement
- **THEN** it SHALL find no section titled "Review quorum in cloud containers"


#### specs/supervise/spec.md
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


### Open ledger items
- [22] A metered request that OpenRouter accepted but that then failed client-side (read timeout, connection reset, or a 'timed out' error that classifies as UNKNOWN) comes back with models_attempted set and no generation_id. _dispatch_metered then skips recording and leaves spend_recorded=None. The result is no ledger row, no spool entry, and no metered_spend_unrecorded degradation. Spend that may have been billed goes uncounted silently, and later budget rechecks use a total that is too low. The same gap applies to TRANSIENT 500/503 falls-through to the fallback model within one round.
- [23] When the response has no usage.cost, row_from_review_result sends actual_usd=None (dropped by exclude_none). The server's LedgerService._ledger_row then computes _token_cost with no rates and gets 0.0 (float(rate or 0.0)). The stored row says tokens_estimated=true and actual_usd=0, so the coordinator ceiling, metered_usd_used and spooled_total_usd all count that call as free.
- [24] The _oneshot_spend_context docstring says archived changes are included, but an output dir of openspec/changes/archive/2026-10-21-<id>/reviews gives change_id='2026-10-21-<id>'. The consequences are a wrong work_unit_ref, and spend_recorder's _change_dir finding neither a live nor an archive (*-<id>) match. Spooling would then create a stray openspec/changes/2026-10-21-<id>/reviews/spend-spool.jsonl tree.
- [25] _extract_content calls choices[0].get(...) without checking that choices[0] is a dict. A malformed or proxy-mangled 200 response, such as choices: ["..."] or [null], raises AttributeError. The exception escapes dispatch instead of becoming a classified ReviewResult failure, so the lane crashes rather than degrading cleanly.
- [26] LedgerService.find_by_generation_id has no callers now that POST /routing/spend uses record_once, which calls the atomic record_spend_once RPC from migration 046. It is dead code, and it invites a reintroduction of the non-atomic read-then-insert dedupe.
- [27] The duplicate_model_family check in select_reviewers looks only at the primary adapter.model. Fallback models go through the anthropic-family rejection in from_config_dict but not through the duplicate-family check. A fallback from a family already served (for example openai/...) could therefore be dispatched after a CAPACITY fallback, which would defeat D2 independence. The current archetypes.yaml fallbacks are all qwen, so this does not happen today.
- [28] can_dispatch no longer checks for api_key_env. A pi/CLI lane with OPENROUTER_API_KEY unset is now counted as available, and passes --check-vendors through 'pi --version'. It can therefore fill a fill_target slot and then fail with AUTH at dispatch time. This matches design D1 (honest dispatch-time auth failure, classified as capability_unavailable), so it is not a defect; it is noted here as a behaviour change.
- [29] CompositeOrchestrator gives the inner ReviewOrchestrator include_lanes=others and caller_vendors=(LANE,) but no exclude_vendor. Inner selection can count the claude_code CLI toward fill_target before include_lanes filters it out. On the intended cloud path (claude_code is the only CLI) countable stays at 1, so the metered lane is still selected and the behaviour is correct. Passing exclude_vendor=LANE would make this explicit.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

Hunt only in the attached last-fix diff. Re-verify open ledger items. Do not re-open retired or parked items.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 2. Focus on remaining issues.