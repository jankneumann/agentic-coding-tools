## Review Round 3

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
diff --git a/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
index 433068ef..ac4bd97c 100644
--- a/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
+++ b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
@@ -192,14 +192,35 @@ degradation `metered_spend_unrecorded` with phase and lane.
 
 ### Requirement: Tool-less Lane Packet Refusal
 
-An OpenAI-compatible lane SHALL NOT review a packet whose sidecar metadata has
-`tools_overflow: true`. Its dispatch SHALL return `success=False`,
-`error_class=vendor_unavailable` and `error="packet_requires_tools"` without sending a request.
+When a round's primary review packet has `tools_overflow: true`, `converge()` SHALL also build a
+tool-less packet for OpenAI-compatible lanes, within the same `BUDGET_CHARS`, with its own sidecar
+`review-packet.toolless.meta.json`:
+- for `review_type == "plan"`, its diff SHALL be limited to `openspec/changes/<change-id>/**`,
+  and it SHALL carry the full text of `proposal.md`, `design.md`, `tasks.md` and the spec deltas;
+- for `review_type == "implementation"`, it SHALL keep the rule-group selection, drop the excluded
+  and truncated files, and list them in the sidecar as `coverage.skipped`.
+
+`dispatch_and_wait` SHALL give OpenAI-compatible lanes the tool-less packet when one exists, and
+the primary packet otherwise. CLI lanes and the `claude_code` handshake lane SHALL keep the
+primary packet.
+
+An OpenAI-compatible lane SHALL NOT review a packet it received whose sidecar has
+`tools_overflow: true`. That means the tool-less packet when one was built, otherwise the primary
+packet. Its dispatch SHALL return `success=False`, `error_class=vendor_unavailable` and
+`error="packet_requires_tools"` without sending a request.
 The Empty Or Blinded Review Is Not Success rule SHALL apply to OpenAI-compatible lanes as it
 does to CLI lanes.
 
+#### Scenario: Overflowing branch diff still reaches the HTTP lane
+- **WHEN** a plan review's primary packet has `tools_overflow: true` because the branch diff
+  exceeds `BUDGET_CHARS`, but the change's own artifacts fit, and an `openrouter` lane is selected
+- **THEN** a tool-less packet with `tools_overflow: false` SHALL be written. The `openrouter` lane
+  SHALL be dispatched with that packet's body, and the CLI and handshake lanes SHALL receive the
+  primary packet
+
 #### Scenario: Overflowing packet is refused
-- **WHEN** a round's packet metadata has `tools_overflow: true` and an `openrouter` lane is selected
+- **WHEN** the packet an `openrouter` lane would receive (the tool-less packet, or the primary
+  packet when no tool-less packet was built) has `tools_overflow: true`
 - **THEN** the lane's result SHALL be `success=False` with `error="packet_requires_tools"`, and the
   injected transport SHALL record zero requests
 
diff --git a/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md b/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
index 17fd6760..1d7463b5 100644
--- a/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
+++ b/openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md
@@ -72,6 +72,16 @@ Each round SHALL:
 Every lane's findings SHALL be written to the round checkpoint under its own lane id, and
 ConsensusSynthesizer SHALL attribute consensus findings to those lane ids.
 
+After each run, `agent_lane.py` SHALL write `ConvergenceResult.consensus` (including
+`quorum_received`) under `openspec/changes/<change-id>/reviews/`, with one file per phase:
+- `consensus-plan.json` for `PLAN_REVIEW`;
+- `consensus-impl-review.json` for `IMPL_REVIEW`;
+- `consensus-val-review.json` for `VAL_REVIEW`.
+
+The two implementation phases share `review_type: implementation`, so the file is named by phase
+and neither run overwrites the other. `converge()` itself SHALL NOT be required to write these
+files.
+
 The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
 `single_vendor_review` degradation only when exactly one lane reviewed.
 
@@ -80,8 +90,8 @@ The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It
   runs against a fixture change, with an injected OpenRouter transport that returns
   schema-valid findings and an agent handshake that writes schema-valid findings
 - **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
-  findings files for both `claude_code` and `openrouter`, and `consensus` SHALL report
-  `quorum_received: 2`
+  findings files for both `claude_code` and `openrouter`, `consensus` SHALL report
+  `quorum_received: 2`, and `reviews/consensus-plan.json` SHALL contain the same consensus
 
 #### Scenario: Findings carry vendor attribution
 - **WHEN** both lanes report a finding at the same file and line range

```

### Rule groups

#### Group 1 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
- openspec/changes/openrouter-review-lane/specs/skill-workflow/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

### Spec excerpts
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

After each review, `spend_recorder.record()` SHALL send one row to `POST /routing/spend` with:
`vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
`actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
`work_unit_ref` (`<change_id>:<review_type>:round-<n>`).

If the write fails, the record SHALL be appended to
`openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
degradation `metered_spend_unrecorded` with phase and lane.

`spend_recorder.py replay --change-id <id>` SHALL post the spooled rows. Replay SHALL skip a
`generation_id` the ledger already holds, and SHALL remove each row it delivers.

#### Scenario: A review is recorded against the ledger
- **WHEN** an `openrouter` review returns `id: gen-abc`, `usage: {prompt_tokens: 1200, completion_tokens: 300, cost: 0.0042}`, and the coordinator accepts the write
- **THEN** the ledger SHALL contain one row with `generation_id: gen-abc`, `actual_usd: 0.0042`,
  and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
  the same generation id, model and cost

#### Scenario: Missing cost is labelled estimated
- **WHEN** the response has token usage but no `usage.cost`
- **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
  `tokens_estimated: true`

#### Scenario: Coordinator unavailable spools the record
- **WHEN** `POST /routing/spend` fails with a connection error or HTTP 403
- **THEN** the review result SHALL be unchanged, one line SHALL be appended to
  `reviews/spend-spool.jsonl`, and a `metered_spend_unrecorded` degradation SHALL be recorded

#### Scenario: Replay is idempotent
- **WHEN** `replay` runs twice over a spool holding `gen-abc`, and the first run succeeds
- **THEN** the ledger SHALL hold exactly one `gen-abc` row and the spool SHALL be empty

### Requirement: Tool-less Lane Packet Refusal

When a round's primary review packet has `tools_overflow: true`, `converge()` SHALL also build a
tool-less packet for OpenAI-compatible lanes, within the same `BUDGET_CHARS`, with its own sidecar
`review-packet.toolless.meta.json`:
- for `review_type == "plan"`, its diff SHALL be limited to `openspec/changes/<change-id>/**`,
  and it SHALL carry the full text of `proposal.md`, `design.md`, `tasks.md` and the spec deltas;
- for `review_type == "implementation"`, it SHALL keep the rule-group selection, drop the excluded
  and truncated files, and list them in the sidecar as `coverage.skipped`.

`dispatch_and_wait` SHALL give OpenAI-compatible lanes the tool-less packet when one exists, and
the primary packet otherwise. CLI lanes and the `claude_code` handshake lane SHALL keep the
primary packet.

An OpenAI-compatible lane SHALL NOT review a packet it received whose sidecar has
`tools_overflow: true`. That means the tool-less packet when one was built, otherwise the primary
packet. Its dispatch SHALL return `success=False`, `error_class=vendor_unavailable` and
`error="packet_requires_tools"` without sending a request.
The Empty Or Blinded Review Is Not Success rule SHALL apply to OpenAI-compatible lanes as it
does to CLI lanes.

#### Scenario: Overflowing branch diff still reaches the HTTP lane
- **WHEN** a plan review's primary packet has `tools_overflow: true` because the branch diff
  exceeds `BUDGET_CHARS`, but the change's own artifacts fit, and an `openrouter` lane is selected
- **THEN** a tool-less packet with `tools_overflow: false` SHALL be written. The `openrouter` lane
  SHALL be dispatched with that packet's body, and the CLI and handshake lanes SHALL receive the
  primary packet

#### Scenario: Overflowing packet is refused
- **WHEN** the packet an `openrouter` lane would receive (the tool-less packet, or the primary
  pac

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

During `converge()`, a round can end with fewer successful results than `min_quorum`. When
every failed lane's `error_class` is `vendor_unavailable` or `auth_required`, `converge()`
SHALL return `reason="capability_unavailable"` with `missing_lanes` naming those lanes. This
covers an exhausted budget, HTTP 402, a revoked key, or `packet_requires_tools`. Any other
quorum loss SHALL remain `reason="quorum_lost"`.

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
- [3] The mid-run mapping fires when 'every failed lane's error_class is UNAVAILABLE or AUTH'. A verified lane can also produce no ReviewResult at all: it is filtered at dispatch by the family or fill rule, not discovered in the worker environment, or dispatch_and_wait returns [] when job_count == 0. In that case the failed set is empty, the condition is vacuously true, and converge() returns capability_unavailable with missing_lanes == [].
- [7] D4 checks the budget only in the probe, which the supervisor runs once per batch against a $1.00 reservation. A dispatched child can then run up to 3 rounds in each of 3 review phases with packets of roughly 80k tokens, and every concurrently dispatched child sees the same remaining budget. When the coordinator ceiling is the only source (key limit null), nothing stops an overrun, so 'bounded before dispatch' does not hold.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

Hunt only in the attached last-fix diff. Re-verify open ledger items. Do not re-open retired or parked items.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 3. Focus on remaining issues.