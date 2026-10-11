# Design: OpenRouter review lane for cloud workers

> Roadmap `multiplayer-collaboration`, item `ri-22`. Depends on `ri-21` (`dispatch-contract`, completed).

## Context

Cloud containers run on the Claude subscription only. The only review lane a cloud
worker can dispatch is the agent itself (served through `skills/autopilot/scripts/agent_lane.py`),
so `converge()` cannot reach `min_quorum=2`. ri-21 made that honest — the review
parks `capability_unavailable` or runs single-vendor under the temporary
`cloud-container-single-vendor-2026-10-09` entry of
`skills/parallel-infrastructure/review_quorum_policy.json`. That entry is backed by
the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`.

Most of the HTTP machinery already exists. What is missing is the wiring that would
make an OpenRouter lane count toward quorum:

| Existing piece | Location | Gap this change closes |
|---|---|---|
| `OpenAICompatAdapter` (tier 2.5), captures `generation_id` | `skills/parallel-infrastructure/scripts/openai_compat_adapter.py` | No authenticated no-op, no cost or token capture, no refusal of packets that need tools |
| Tier-2.5 discovery for `endpoint_kind in {openrouter, local}` with `base_url` | `review_dispatcher.py` `from_config_dict` / `discover_reviewers` | No agent declares an OpenRouter `base_url`, so no lane exists. There is no model-family rule and no cost policy for metered lanes |
| `--check-vendors --json` dry-probe verification (D10) | `review_dispatcher.py` `_probe_mode` | Every SDK or API lane is reported `probe_unsupported` and never verifies |
| `routing_spend_ledger` + `ROUTING_MONTHLY_CEILING_USD` | `agent-coordinator/src/model_routing/{ledger,api}.py` | Advisory only. No client writes rows (`LedgerService.record` has no caller), and nothing checks the ceiling before dispatch |
| Honest quorum guard (`verified_lanes`, `capability_unavailable`) | `skills/autopilot/scripts/convergence_loop.py` `converge()` | A lane that loses budget or auth mid-run surfaces as `quorum_lost`, not `capability_unavailable` |
| Agent-as-lane driver | `skills/autopilot/scripts/agent_lane.py` | Hard-codes `verified_lanes=[claude_code]`, so it cannot add a second lane |
| Lane ranking for `counting_lanes` | `skills/supervise/scripts/execution.py` `resolve_execution_profile.rank` | Infers the endpoint kind from `reason == probe_unsupported`, which breaks once API lanes verify |

## Goals / Non-goals

**Goals**
- In a cloud container, `converge()` reaches quorum 2 with `claude_code` plus at least one
  verified OpenRouter lane from a non-Anthropic model family.
- Lane availability comes only from the dry probe. No worker reads environment variables
  or credentials to discover lanes.
- Metered spend is recorded for every review and bounded before dispatch. A lane that is
  over budget is reported unverified, and the review parks `capability_unavailable`.
- The temporary cloud single-vendor policy is retired after the lane has been shown to
  work in cloud.

**Non-goals**
- Inline or proxy-level budget enforcement, virtual keys, a LiteLLM gateway
  (`add-coordinator-llm-gateway`).
- A general usage-accounting store, transcript ingestion, or pricing tables
  (`add-model-usage-ledger`). This change writes only to the existing `routing_spend_ledger`.
- Using OpenRouter lanes for `alternative` or `quick` modes. `OpenAICompatAdapter.can_dispatch`
  stays review-only.
- Tool use for HTTP lanes. They review the packet text only (see D6).
- The GX10 review lane, and adaptive model selection for review lanes.

## Decisions

### D1 — A lane is an endpoint-only `agents.yaml` agent, with its model in `archetypes.yaml`

The first lane is a new agent `openrouter-review`:

- `type: openrouter`, `endpoint_kind: openrouter`, `base_url: https://openrouter.ai/api/v1`
- `location: cloud`, `transport: http`, `trust_level: 1`, `capabilities: [discover]`
- `archetypes: [reviewer]`, `vendor_credentials: [openrouter]`
- no `cli` and no `sdk` block: the dispatcher builds only the tier-2.5 `OpenAICompatAdapter` for it
  (`from_config_dict` already accepts an agent whose only dispatch surface is `endpoint_kind` + `base_url`)
- no `api_key`. The lane never calls the coordinator under its own identity. Without a principal, key resolution falls back to the dispatcher's existing `OPENROUTER_API_KEY` default for `endpoint_kind: openrouter`, which works in non-OpenBao mode (cloud). On an OpenBao host the lane reports `auth_failed`. That is acceptable: hosts have CLI lanes, and D5 would not select it there. The agent schema has `additionalProperties: false`, so no agent-level `api_key_env` field is added.

Its model comes from a new provider `openrouter` in `agent-coordinator/archetypes.yaml`. The
`premium` tier is the review model; the `standard` and `economy` tiers are its fallbacks,
which `_derived_tier_fallbacks` already reads. Lane id = `agent.type` = `openrouter`. This is
the vendor string in `ReviewResult`, in the checkpoint index, in `execution_profile.lanes`,
and in ConsensusSynthesizer attribution.

More lanes are added the same way, each with its own `type` and provider key. Lane ids must be
unique because `converge()` keys checkpointed results by `vendor`.

`location: cloud` needs a matching cost tier. Today the only `routing.yaml` tier carrying
`endpoint_kind: openrouter` is `metered-api` with `location: local`, so
`RoutingPolicy.cost_tier("cloud", "openrouter")` returns `None` and `select_model` would exclude
the agent. Group 2 therefore appends a tier `metered-api-cloud` (`location: cloud`,
`endpoint_kinds: [openrouter]`) after `metered-api`. It is the last rung, so it never outranks a
subscription tier, and the supervisor's `_tier_order()` (which reads only `endpoint_kinds`, first
index wins) is unchanged. A group-2 test asserts `cost_tier("cloud", "openrouter")` is not `None`.

*Alternatives considered*
- Add `base_url` to `pi-local` and reuse the `pi` provider. Rejected: it couples the pi
  harness's identity, credential principal and CLI-precedence rules to an HTTP reviewer, and a
  `location: local` agent would serve a cloud lane.
- Keep a separate lane file under `skills/parallel-infrastructure/`. Rejected: it would be a
  second roster, which the principal registry rule forbids, and the coordinator's
  `/agents/dispatch-configs` would not see it.

### D2 — Model-family diversity rule

A lane counts toward quorum only if it adds a model family:

- The family of an OpenRouter lane is the publisher prefix of its primary model slug
  (`<publisher>/<model>`).
- The family of a CLI or SDK vendor comes from a new `vendor_families` map in
  `review_quorum_policy.json`, for example `claude_code → anthropic`, `codex → openai`,
  `antigravity → google`, `grok → xai`.

Config load rejects an OpenRouter lane whose primary model or any fallback model has publisher
`anthropic` (the agent is skipped with a logged reason). `discover_reviewers` skips a tier-2.5
lane whose family is already contributed by a lane selected at tier 1 or 2, and records the
reason `duplicate_model_family`. An Anthropic-family lane is reported with the reason
`anthropic_family`. Both reasons appear in the `unverified` list of `--check-vendors --json`.

A vendor missing from `vendor_families` has unknown family and is never treated as a duplicate.

**Selection is two-pass.** Today `discover_reviewers` makes one pass over `sorted(all_vendors)`,
so a tier-2.5 lane such as `openrouter` would be decided before tier-1/2 vendors that sort after
it (for example `pi`). The family rule (D2) and the fill rule (D5) both read the complete
non-metered selection, so discovery becomes:

1. Pass 1 selects every tier-1 (CLI) and tier-2 (SDK) lane exactly as today.
2. Pass 2 walks the remaining tier-2.5 candidates in `agents.yaml` roster order (the insertion
   order of `openai_adapters`, not the sorted vendor order). It applies the Anthropic rule, the
   duplicate-family rule against the pass-1 set, and then the fill rule (D5).

Tests cover a non-metered vendor that sorts after the metered lane.

*Trade-off accepted:* fallback models may belong to a different family from the primary
model. The family check uses the primary model only, and `model_used` is recorded so audits
can see what actually ran. This is preferred over forbidding cross-family fallbacks, which
would make a single capacity error fatal to the lane.

### D3 — Authenticated dry probe for API lanes

`OpenAICompatAdapter.probe(api_key, transport, timeout=10)` makes one authenticated request
that costs nothing:

- `openrouter`: `GET {base_url}/key`, which returns the key's `limit`, `usage` and `limit_remaining`
- `local`: `GET {base_url}/models`

It returns `ProbeResult(ok, reason, budget)`. `reason` is one of `None`, `auth_failed`,
`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`,
`spend_ceiling_unverifiable`. `budget` holds numeric fields only.

The response body is parsed in memory, and only the numeric budget fields are kept. Nothing
from the response or the key is printed, logged, or returned.

`_probe_mode` calls this for `dispatch_tier == "openai"` lanes in place of
`probe_unsupported`. The key is resolved through the existing `ApiKeyResolver` path, which the
Dispatchable Vendor Verification requirement already allows.

The JSON report gains an additive per-mode `lane_kinds: {lane: endpoint_kind}` map. The supervisor uses it for ranking (D8).

### D4 — Spend: bounded before dispatch, recorded after it

**Bounded.** The probe (D3) also checks the budget. It reads up to two ceiling sources:

1. The coordinator ceiling: `GET /routing/usage?window=month`. It counts when
   `metered_ceiling_usd > 0` and the coordinator is reachable. Remaining budget is
   `metered_ceiling_usd − metered_usd_used`.
2. The OpenRouter key's own credit `limit`, from the probe response. It counts when the limit
   is not null. Remaining budget is `limit_remaining`.

How the probe decides:

- **Verified:** at least one source is available, and every available source has remaining
  budget of at least `review_reservation_usd`.
- **`spend_ceiling_exceeded`:** an available source has less than that left.
- **`spend_ceiling_unverifiable`:** no source is available (fail closed).

`review_reservation_usd` is a single number in `review_quorum_policy.json` under
`metered_lanes.review_reservation_usd`. The default is `1.00`. That is roughly one
full-packet review round on a premium model, and it can be tuned as data.

An unverified lane is left out of `execution_profile.lanes.review`. A dispatched child then
parks `capability_unavailable` through the existing Honest Review Quorum path. It never drops
to single-vendor review on its own.

**Recorded.** Each request sets `"usage": {"include": true}`, so OpenRouter returns
`usage.cost`. The adapter adds `prompt_tokens`, `completion_tokens`, `cost_usd` and
`cost_source` (`reported`, or `estimated` when the response has no cost) to `ReviewResult`.

A new `skills/parallel-infrastructure/scripts/spend_recorder.py` writes one row per review:

- It posts to a new authenticated `POST /routing/spend` that calls the existing
  `LedgerService.record`.
- The row holds `vendor` = lane id, `model` = `model_used`, `endpoint_kind = openrouter`,
  `generation_id`, the token counts, `actual_usd`, `tokens_estimated` (true when `cost_source`
  is `estimated`), and `work_unit_ref = <change_id>:<phase|review_type>:round-<n>`.

The same fields always go into the round checkpoint's vendor index, which is durable on the
branch.

If the coordinator write fails, the record is appended to
`openspec/changes/<id>/reviews/spend-spool.jsonl`, and the worker records the degradation
`metered_spend_unrecorded` (a new closed code). `spend_recorder.py replay --change-id <id>`
posts the spooled rows idempotently, keyed by `generation_id`. The supervisor runs it during
`apply`.

The key's credit limit bounds spend while rows sit in the spool.

*Alternatives considered*
- Fail the review when the ledger write fails. Rejected: the coordinator is known to be
  partly unreachable from cloud workers (`coordinator_projection_forbidden`), and the key
  limit already bounds spend.
- Wait for `add-model-usage-ledger`. Rejected: it is a draft with a much larger scope, and the
  roadmap names the *existing* ceiling.

### D5 — Metered lanes fill quorum, they do not add to it

An agent with `endpoint_kind: openrouter` that is selected at tier 2.5 is a metered lane.
`discover_reviewers` includes metered lanes only while the non-metered lanes it has selected
number fewer than `metered_lanes.fill_target`. `fill_target` defaults to the policy file's
`default_min_quorum`, which is 2. Metered lanes are added in `agents.yaml` roster order, during
pass 2 of the two-pass selection (D2), until the target is reached.

A host with two CLI lanes therefore pays nothing. A cloud container with only `claude_code`
gets exactly one metered lane.

This is a property of the roster that `--check-vendors` and `dispatch_and_wait` both apply, so
the profile and the dispatch always agree.

*Alternative considered:* always dispatch every configured lane (more reviewers). Rejected:
every host review would start paying OpenRouter. The operator can raise `fill_target`.

### D6 — HTTP lanes refuse packets that need tools

HTTP lanes cannot read files. The `pi --no-tools` incident shows that a reviewer which cannot
see the artifacts but still returns `{"findings": []}` manufactures false consensus.

When the round's packet metadata has `tools_overflow: true`, `OpenAICompatAdapter.dispatch`
returns `success=False`, `error_class=UNAVAILABLE`, `error="packet_requires_tools"` and makes
no HTTP call. The existing Empty Or Blinded Review Is Not Success floor still applies to HTTP
lanes.

The packet metadata is the sidecar `build_review_packet` writes next to `packet_path`.
`dispatch_and_wait` already receives `packet_path`, and passes the `tools_overflow` flag to
the adapter.

**Refusal must stay rare.** Refusal alone would make the lane useless in practice. Plan-review
packets on long-lived branches routinely overflow: the round-1 PLAN_REVIEW packet for this change
was 320000/320000 chars with `tools_overflow: true`, because the diff against `origin/main` spans
about 420 files. To avoid this, `converge()` builds a second, tool-less packet for HTTP lanes
whenever the primary packet overflows:

- For `review_type == "plan"`, the tool-less packet's diff is limited to
  `openspec/changes/<change-id>/**`. It includes the full text of `proposal.md`, `design.md`,
  `tasks.md` and the spec deltas, all within the same `BUDGET_CHARS`. A plan review judges the plan
  artifacts, and the unrelated branch diff is not needed for that.
- For `review_type == "implementation"`, the tool-less packet keeps the existing rule-group
  selection but drops the excluded and truncated files. Its sidecar lists them as `coverage.skipped`
  (the blinded-review floor still applies).
- The tool-less packet gets its own sidecar (`review-packet.toolless.meta.json`). An HTTP lane
  refuses with `packet_requires_tools` only when this packet *also* has `tools_overflow: true`.
  The CLI and handshake lanes keep the primary packet.

A scenario covers a plan review whose full branch diff overflows: the HTTP lane receives a
tool-less packet that fits, and it is dispatched. The D9 evidence run must use a change whose
primary packet overflows, so that a small fixture cannot hide the problem.

### D7 — Composite orchestrator in `agent_lane.py`, and honest mid-run loss

`agent_lane.run_converge` gains `--verified-lanes` (repeatable). A dispatched child copies
the values from its launch marker's `execution_profile.lanes.review`. A standalone run copies
them from the `--check-vendors --json` output, which is the only allowed probe.

It builds a `CompositeOrchestrator`. Each round it:

- dispatches the `claude_code` handshake lane (unchanged), and
- runs `ReviewOrchestrator.dispatch_and_wait(..., include_lanes=<verified lanes other than claude_code>)`
  concurrently,

and returns the combined `ReviewResult` list, with the checkpoint callback forwarded.
`include_lanes` is a new optional filter on `dispatch_and_wait`; `None` keeps today's
behaviour.

The quorum policy is resolved with `verified_review_lanes = len(verified_lanes)` instead of the
literal `1`.

`claude_code` is always a verified lane inside `agent_lane`, because the running agent
serves it. That is the premise of the module today. A `--verified-lanes claude_code` value
is deduplicated.

In `converge()`, when a round has fewer successful results than `min_quorum` and every failed
lane's `error_class` is `UNAVAILABLE` or `AUTH` (budget exhausted, HTTP 402, key revoked, or
`packet_requires_tools`), it returns `reason="capability_unavailable"` with `missing_lanes` set
to the failed lanes. Any other quorum loss stays `quorum_lost`.

The autopilot SKILL already maps `capability_unavailable` to `runner.py park --kind
capability_unavailable`.

### D8 — Supervisor ranking uses `lane_kinds`

`resolve_execution_profile.rank` reads the lane's endpoint kind from the report's
`lane_kinds`. It falls back to the old `probe_unsupported` inference only when `lane_kinds` is
absent, so older reports still rank. `openrouter` sorts by its position in the
`cost_policy.tiers` ladder in `routing.yaml`.

`ExecutionProfile` in `dispatch-request.schema.json` does not change: lanes stay plain lane-id strings.

### D9 — Retiring the temporary policy needs evidence and is the last task

The operator runs `/autopilot` on a fixture change in a cloud container whose environment has
`OPENROUTER_API_KEY` as a secret and allows egress to `openrouter.ai`. The run is accepted
only if the evidence file `openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md`
shows all of the following:

- `PLAN_REVIEW` with `min_quorum=2`
- two attributed lanes in `reviews/consensus-plan.json`. `converge()` itself never writes this
  file (only `/parallel-review-plan` does), so `agent_lane.py` persists `ConvergenceResult.consensus`
  to `reviews/consensus-<review_type>.json` after each run (task 5.5), alongside `quorum_received`
  and the per-lane index already in `.review-cache/round-N/`
- a `routing_spend_ledger` row, or a spool row, carrying the `generation_id`

Only then does the final task:

- delete the `cloud-container-single-vendor-2026-10-09` entry,
- delete the `TRUST_POSTURE.md` section, and
- update the `single_vendor_review` references in `skills/autopilot/SKILL.md`.

The mechanism for per-environment exceptions (`policies[]` with a `sunset`) stays. Any future
exception is data, never prose.

Editing the prose of `TRUST_POSTURE.md` is checked against `posture_digest`, which covers the
front-matter dispositions. If the digest also covers the body, the resulting gate
re-evaluation is expected and is recorded in the session log.

## Cross-cutting interface contracts

| Contract | Change | Compatibility |
|---|---|---|
| `ReviewResult` | adds `prompt_tokens`, `completion_tokens`, `cost_usd`, `cost_source` (all optional, default `None`) | additive, existing callers unaffected |
| `--check-vendors --json` | adds `modes.<mode>.lane_kinds`; API lanes may now be `verified` or carry the new reasons | additive; consumers ignore unknown keys |
| `review_quorum_policy.json` | adds `vendor_families` and `metered_lanes.{fill_target, review_reservation_usd}` | additive; `resolve_quorum_policy` ignores them |
| `dispatch_and_wait` | adds optional `include_lanes` | default keeps behaviour |
| `dispatch-result.schema.json` `Degradation.code` | adds enum value `metered_spend_unrecorded` | additive enum; writers older than this change never emit it |
| Coordinator HTTP | adds `POST /routing/spend` (X-API-Key auth, Pydantic `extra="forbid"`, `actual_usd >= 0`, `generation_id` idempotency) | new route |

## Security

- **Credentials:** the OpenRouter key is read only through `ApiKeyResolver`. In cloud that
  means the `OPENROUTER_API_KEY` environment secret in non-OpenBao mode; on hosts it means
  OpenBao `vendor_credentials: [openrouter]`. The probe and dispatch never log headers or
  response bodies. A sentinel test (the existing Dispatchable Vendor Verification scenario,
  extended to `OPENROUTER_API_KEY`) checks this.
- **Data egress:** packets, which hold diffs and spec excerpts, are sent to a third party
  (OpenRouter and the upstream provider). This is acceptable for this repository, which is
  public on GitHub. For any other repository it is opt-in, because the lane exists only if an
  agent with `endpoint_kind: openrouter` and `base_url` is configured.
- **New endpoint:** `POST /routing/spend` requires `X-API-Key`. Its input is validated, and it
  accepts only the fields of the ledger row.
- **Cost abuse:** the ceiling check before dispatch, plus the key's own credit limit, plus
  `fill_target`.

## Risks

| Risk | Mitigation |
|---|---|
| The cloud environment's egress policy blocks `openrouter.ai` | The probe reports `endpoint_unreachable`, the review parks honestly, and the setup doc names the allowlist entry |
| TLS through the agent proxy fails with stdlib `urllib` | The transport uses the default SSL context, which honours `SSL_CERT_FILE`; the cloud setup doc points it at the proxy CA bundle |
| OpenRouter changes the `/key` or `usage.cost` shapes | The transport is injectable and tests pin the parsed fields. The probe fails closed (`spend_ceiling_unverifiable`) on an unexpected shape |
| The model slug in the `openrouter` provider is retired | `_derived_tier_fallbacks` provides fallbacks; a slug error is classified and the next model is tried |
| `claude --version` fails inside the container, so the profile omits `claude_code` and the fill rule tries to select a second metered lane | The roster has one metered lane, so at most one is selected. `agent_lane` still counts `claude_code` (D7) |
| The supervisor runs `--check-vendors` in a different environment class than the worker, for example a host supervisor with a cloud worker | This is inherited from ri-21 (the profile is resolved by the supervisor). The worker parks honestly if the profile lists lanes it cannot dispatch, through the mid-run mapping in D7. Correcting the supervisor's environment is out of scope |
| Spool rows are never replayed | `metered_spend_unrecorded` is a visible degradation on the dispatch result, and `apply` runs replay |

## Open questions (for the operator, recorded as decisions with defaults)

1. **Ceiling when the coordinator ceiling is unset.** The default fails closed and requires
   either `ROUTING_MONTHLY_CEILING_USD > 0` or an OpenRouter key with a credit limit (D4).
   The alternative is to treat an unset ceiling as unlimited.
2. **Fill vs. supplement.** The default dispatches metered lanes only to fill quorum (D5).
   The alternative is to always dispatch them.
3. **Initial review model** for the `openrouter` provider `premium` tier. It must be a
   non-Anthropic publisher, and preferably a family not already served by a host CLI
   (codex → openai, antigravity → google, grok → xai). It is chosen at implementation from
   the live OpenRouter catalog and recorded in `archetypes.yaml` with its source URL.
