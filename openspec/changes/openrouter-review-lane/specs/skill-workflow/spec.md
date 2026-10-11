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

The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
`single_vendor_review` degradation only when exactly one lane reviewed.

#### Scenario: Cloud plan review reaches quorum two
- **WHEN** `agent_lane.py converge --phase PLAN_REVIEW --verified-lanes claude_code --verified-lanes openrouter`
  runs against a fixture change, with an injected OpenRouter transport that returns
  schema-valid findings and an agent handshake that writes schema-valid findings
- **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
  findings files for both `claude_code` and `openrouter`, and `consensus` SHALL report
  `quorum_received: 2`

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
