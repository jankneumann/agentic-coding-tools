# OpenRouter review lane for cloud workers

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `openrouter-review-lane`
> Effort: M
> Priority: 2

## Summary

Make API-based multi-vendor review available in cloud containers. Register OpenRouter-backed
reviewer lanes from non-Anthropic model families that:

- dispatch over HTTP through the existing OpenAI-compatible adapter,
- need no vendor CLI, and
- count toward `converge()` quorum.

Lanes are declared in the dispatch request's `execution_profile` and `review_requirements`
from ri-21. Each lane is verified by a dry invocation, not by probing credentials, and is
bounded by the existing spend ceiling. Once the lanes are in use, the temporary cloud
single-vendor review policy is retired.

## Dependencies

- `ri-21` (`dispatch-contract`, completed): execution_profile, review_requirements, the quorum
  policy data file, honest-quorum parking, and the closed degradation codes.

## Why

Cloud workers run on the Claude subscription only. Their only review lane is the agent itself,
so review either parks `capability_unavailable` or runs single-vendor under the temporary
policy in `TRUST_POSTURE.md` (operator decision 2026-10-09).

The repository already has most of an HTTP lane:

- `OpenAICompatAdapter` (tier 2.5 of the review dispatcher)
- an OpenRouter generation id on `ReviewResult`
- `routing_spend_ledger` with a monthly ceiling
- the `--check-vendors` dry-probe contract, which already names "the adapter's own
  authenticated no-op" for API lanes

None of this is wired:

- No agent declares an OpenRouter `base_url`.
- API lanes are always reported `probe_unsupported`.
- Nothing writes ledger rows or checks the ceiling.
- `agent_lane.py` hard-codes a single lane.

Wiring these pieces restores the two-vendor quorum for cloud workers at metered cost, without
waiting for the GX10 review lane. It also replaces a policy exception written in prose with a
configured lane that can be observed.

## What Changes

**Lane roster** (`agent-coordinator/agents.yaml`, `agent-coordinator/archetypes.yaml`)
- Add the endpoint-only agent `openrouter-review` (`type: openrouter`,
  `endpoint_kind: openrouter`, `base_url`, reviewer-only).
- Add a provider `openrouter` whose tier map supplies the review model and its fallbacks
  (design D1).

**Dispatcher** (`skills/parallel-infrastructure/scripts/{openai_compat_adapter,review_dispatcher}.py`, `review_quorum_policy.json`)
- An authenticated, zero-cost dry probe for API lanes (`GET /key` for OpenRouter,
  `GET /models` for local endpoints). It replaces `probe_unsupported` and also checks the
  spend budget (D3, D4).
- Per-mode `lane_kinds` in `--check-vendors --json`.
- A model-family diversity rule: no Anthropic-family lanes, and no lane whose family is
  already counted (D2).
- Metered lanes fill quorum rather than supplement it (D5).
- Cost and token capture on `ReviewResult`.
- Refusal of packets that need tools (D6).
- An `include_lanes` filter on `dispatch_and_wait`.

**Spend** (new `skills/parallel-infrastructure/scripts/spend_recorder.py`, `agent-coordinator/src/model_routing/api.py`)
- A new authenticated `POST /routing/spend` that writes `routing_spend_ledger` rows.
- When the coordinator cannot be reached, records go to a local spool with a replay command,
  and the new degradation code `metered_spend_unrecorded` is recorded (D4).

**Convergence** (`skills/autopilot/scripts/{agent_lane,convergence_loop}.py`)
- `agent_lane.py` composes the `claude_code` handshake lane with the verified HTTP lanes (D7).
- `converge()` reports a mid-run loss of lane capability as `capability_unavailable`, not
  `quorum_lost` (D7).

**Supervisor** (`skills/supervise/scripts/execution.py`, `openspec/schemas/dispatch-result.schema.json`)
- `counting_lanes` is ranked from `lane_kinds` (D8).
- The degradation enum gains the new code.

**Retirement, gated on cloud evidence** (`TRUST_POSTURE.md`, `review_quorum_policy.json`, `skills/autopilot/SKILL.md`, docs)
- Delete the temporary cloud section and the policy entry.
- Document the cloud setup: the environment secret and the egress allowlist (D9).

## Acceptance Outcomes

- In a cloud container with an OpenRouter credential provisioned as an environment secret,
  `converge()` reaches `min_quorum=2` for PLAN_REVIEW using `claude_code` plus at least one
  OpenRouter lane from a different model family, verified end to end on a fixture change.
- Lane availability is established by a dry invocation of the lane for the requested mode and
  reported in `execution_profile`. No worker reads environment variables or credentials to
  discover it, and `--check-vendors` no longer reports a lane that cannot dispatch.
- Every OpenRouter review records model, generation id and cost against the existing monthly
  spend ceiling. Exceeding the ceiling parks with `capability_unavailable` instead of silently
  dropping to single-vendor review.
- OpenRouter findings conform to `review-findings.schema.json` and are synthesized by
  ConsensusSynthesizer like CLI lanes, with vendor attribution preserved in the ledger.
- The "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md` is removed
  once the lane passes in cloud, restoring quorum 2 everywhere, and `review_requirements`
  expresses any remaining per-environment exception as data with a sunset.

## Non-goals

- Inline or proxy budget enforcement and virtual keys (`add-coordinator-llm-gateway`).
- A general usage-accounting store or pricing tables (`add-model-usage-ledger`).
- OpenRouter lanes for the `alternative` or `quick` dispatch modes, and tool use by HTTP lanes.
- The GX10 review lane, and adaptive model selection for review lanes.

## Impact

**Affected specs**

| Capability | Delta |
|---|---|
| `parallel-infrastructure` | MODIFIED: OpenAI-Compatible Dispatcher Discovery; Dispatchable Vendor Verification. ADDED: Metered Review Lane Spend Accounting; Tool-less Lane Packet Refusal |
| `skill-workflow` | MODIFIED: Honest Review Quorum. ADDED: Composite Agent-Lane Review; Cloud Single-Vendor Policy Retirement |
| `supervise` | MODIFIED: Execution Profile and Review Requirements |
| `model-routing` | ADDED: Review Spend Recording Route |

**Affected code**
- `skills/parallel-infrastructure/scripts/{openai_compat_adapter,review_dispatcher}.py` and new `spend_recorder.py`; `skills/parallel-infrastructure/review_quorum_policy.json`
- `skills/autopilot/scripts/{agent_lane,convergence_loop}.py`, `skills/autopilot/SKILL.md`
- `skills/supervise/scripts/execution.py`
- `agent-coordinator/{agents.yaml,archetypes.yaml}` and `agent-coordinator/src/model_routing/api.py`
- `openspec/schemas/dispatch-result.schema.json` (additive enum value)
- `TRUST_POSTURE.md` (section removal, last task), `docs/guides/` cloud setup notes

**Operational**
- Requires the cloud environment secret `OPENROUTER_API_KEY`, egress to `openrouter.ai`, and
  either `ROUTING_MONTHLY_CEILING_USD > 0` on the coordinator or a credit limit on the
  OpenRouter key.
- Review packets are sent to OpenRouter.

## Rationale

Restores the two-vendor review quorum for cloud workers at metered API cost instead of waiting
on the GX10 review lane, and replaces a prompt-level policy exception with a configured,
observable lane.
