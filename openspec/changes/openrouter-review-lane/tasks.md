# Tasks: OpenRouter review lane for cloud workers

> Change ID: `openrouter-review-lane`. Design decisions are referenced as D1–D9 (`design.md`).
> Tests come first within each group (TDD). Each numbered task is sized for a single commit.
> Each group lists **Files** (write scope) and **Depends** (blocking groups). Groups whose
> write scopes do not overlap can run in parallel.

## Dependency graph

```
1 (adapter) ──┐
              ├─> 3 (dispatcher discovery/probe) ──┬─> 5 (convergence) ──┐
2 (roster) ───┘                                    ├─> 6 (supervisor)  ──┼─> 7 (cloud E2E + retirement)
4 (spend route + recorder) ────────────────────────┴───────────────────────┘
```

Groups 1, 2 and 4 are independent, so up to 3 can run in parallel. Groups 5 and 6 run in
parallel after group 3. Group 7 runs last. Sequential chain length is 4.

## 1. OpenAI-compatible adapter: probe, cost capture, packet refusal

**Files:** `skills/parallel-infrastructure/scripts/openai_compat_adapter.py`,
`skills/parallel-infrastructure/scripts/review_dispatcher.py` (only the `ReviewResult`
dataclass fields and the shared ingest helper extracted in 1.7),
`skills/tests/parallel-infrastructure/test_openai_compat_adapter.py`
**Depends:** none
**Specs:** parallel-infrastructure "Dispatchable Vendor Verification" (probe part),
"Metered Review Lane Spend Accounting" (capture part), "Tool-less Lane Packet Refusal"
(including "Fast empty HTTP review does not count"); acceptance outcome 4

- [ ] 1.1 Write the failing tests, all using an injected transport:
  - `probe()` for `openrouter` sends `GET {base_url}/key`, and for `local` sends `GET /models`.
  - 200 → `ok` with numeric budget fields.
  - 401 → `auth_failed`; timeout → `probe_timeout`; connection error → `endpoint_unreachable`.
  - A body with no `data` → budget `None`.
  - Sentinel test: a transport that echoes the headers leaks nothing into the result, the
    logs, or the exception text.
- [ ] 1.2 Implement `ProbeResult` and `OpenAICompatAdapter.probe(api_key, transport, timeout=10)`.
  Add a GET-capable transport alongside the existing POST transport, using the default SSL
  context (so `SSL_CERT_FILE` is honoured). Cite the OpenRouter docs URLs for `/key` in a
  comment (source-driven-development).
- [ ] 1.3 Write the failing tests for cost capture:
  - The request body includes `usage: {include: true}`.
  - The response fields `usage.prompt_tokens`, `usage.completion_tokens` and `usage.cost` map
    to the new `ReviewResult` fields.
  - Without a cost, `cost_source == "estimated"`.
- [ ] 1.4 Add the optional `ReviewResult` fields `prompt_tokens`, `completion_tokens`,
  `cost_usd` and `cost_source`, all defaulting to `None`, and implement the capture in
  `dispatch()`.
- [ ] 1.5 Write a failing test: `dispatch(..., tools_overflow=True)` returns
  `packet_requires_tools` / `vendor_unavailable` with zero transport calls. Then implement the
  `tools_overflow` keyword (default False).
- [ ] 1.6 Write failing tests: HTTP findings go through the same ingest pipeline as CLI findings.
  Today `OpenAICompatAdapter.dispatch` only calls `CliVendorAdapter._parse_findings`. The tests,
  each using an injected transport, cover:
  - a fast `{"findings": []}` (under `empty_findings_min_seconds()`) → `success=False`,
    `error="empty_findings_too_fast"`;
  - a schema-invalid payload → `success=False`, `error_class=unknown`;
  - a placeholder-only payload → `success=False`, `error="non_substantive_placeholder"`;
  - a valid payload → findings coerced (`coerce_findings_payload`), stamped
    `evidence_class: judgment` (`stamp_judgment_ingest`), and line-resolved against the packet diff,
    exactly as on the CLI path.
- [ ] 1.7 Factor the CLI ingest steps (coerce → validate → judgment stamp → line resolve →
  placeholder check → empty-findings floor) out of `CliVendorAdapter` into a shared helper in
  `review_dispatcher.py`. Call it from both adapters. CLI behaviour must not change: the existing
  `test_fast_empty_findings_are_unsuccessful` and the related ingest tests stay green.

## 2. Lane roster

**Files:** `agent-coordinator/agents.yaml`, `agent-coordinator/archetypes.yaml`,
`agent-coordinator/routing.yaml` (append the `metered-api-cloud` tier only),
`agent-coordinator/tests/test_agents_config.py`, `agent-coordinator/tests/test_archetypes_yaml.py`
(add tests only)
**Depends:** none
**Specs:** parallel-infrastructure "OpenAI-Compatible Dispatcher Discovery"

- [ ] 2.1 Write failing tests:
  - `openrouter-review` loads with `endpoint_kind: openrouter`, a `base_url`, no `cli`/`sdk`,
    `archetypes: [reviewer]`, and `vendor_credentials: [openrouter]`.
  - `get_dispatch_configs()` emits it.
  - The `openrouter` provider resolves `premium`, `standard` and `economy` slugs, none with
    publisher `anthropic`.
  - `RoutingPolicy.cost_tier("cloud", "openrouter")` is not `None` (design D1), and
    `cost_tier("local", "openrouter")` still returns `metered-api`.
- [ ] 2.2 Add the agent entry (design D1), the `openrouter` provider tier map, and the
  `metered-api-cloud` tier (`location: cloud`, `endpoint_kinds: [openrouter]`), appended last to
  `routing.yaml` `cost_policy.tiers`. Choose the
  premium slug from the live OpenRouter model catalog: it must be non-Anthropic and preferably
  a family not served by a host CLI. Record the catalog URL and the date in a YAML comment.
- [ ] 2.3 Run the registry projection tests (`test_registry_projection.py`,
  `test_vendor_registry.py`, profile sync) and fix any projection assumption that every agent
  carries a CLI or SDK block.

## 3. Dispatcher discovery, probe wiring, family and fill rules

**Files:** `skills/parallel-infrastructure/scripts/review_dispatcher.py` (excluding the
`ReviewResult` dataclass, which group 1 owns), `skills/parallel-infrastructure/review_quorum_policy.json`
(add `vendor_families` and `metered_lanes` only; do not touch `policies`),
`skills/parallel-infrastructure/scripts/review_packet.py` (the tool-less packet builder only),
`skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`,
`skills/parallel-infrastructure/scripts/tests/test_review_packet.py`,
`skills/parallel-infrastructure/tests/test_check_vendors_api_lane.py` (new)
**Depends:** 1, 2 (the roster is needed only for the integration test in 3.9; tests 3.1–3.8 use inline config dicts)
**Specs:** parallel-infrastructure "OpenAI-Compatible Dispatcher Discovery" (MODIFIED),
"Dispatchable Vendor Verification" (MODIFIED), "Tool-less Lane Packet Refusal"

- [ ] 3.1 Write failing tests for the family rule:
  - An `anthropic/` primary or fallback → `unverified` with reason `anthropic_family`.
  - `codex` at tier 1 plus an `openai/` OpenRouter lane → `duplicate_model_family`.
  - A vendor missing from `vendor_families` is never a duplicate.
  - Two-pass order (design D2): a non-metered vendor that sorts after `openrouter` (for example
    `pi`, mapped to `openai`) still makes an `openai/` OpenRouter lane a `duplicate_model_family`.
- [ ] 3.2 Add `vendor_families` and `metered_lanes {fill_target, review_reservation_usd}` to
  `review_quorum_policy.json`, plus a loader. Implement the family rule in
  `from_config_dict` / `discover_reviewers` (design D2).
- [ ] 3.3 Write failing tests for the fill rule. With `fill_target` 2:
  - two non-metered lanes → no metered lane is selected;
  - one non-metered lane → exactly one metered lane is selected.
  
  Also test that `dispatch_and_wait(include_lanes=...)` restricts dispatch.
- [ ] 3.4 Implement the two-pass selection (design D2): pass 1 for tier 1/2, pass 2 for tier-2.5
  candidates in `agents.yaml` roster order. Then implement the metered fill selection (design D5)
  and the `include_lanes` filter. Add a fill-rule test where the non-metered lane sorts after the
  metered one.
- [ ] 3.5 Write failing tests for `_probe_mode` on API lanes, using an injected probe and an
  injected coordinator-usage function:
  - verified when the key limit leaves enough budget;
  - `spend_ceiling_exceeded` when the coordinator has too little budget left;
  - `spend_ceiling_unverifiable` when there is no ceiling source;
  - `auth_failed` passes through;
  - `lane_kinds` is present for every lane;
  - no chat-completions call is made.
- [ ] 3.6 Implement the API-lane probe in `_probe_mode`. Resolve the key via `ApiKeyResolver`,
  fetch coordinator usage through an injectable `GET /routing/usage` client (which fails soft
  to "source unavailable"), apply the budget rule (design D4), and emit `lane_kinds`. Keep
  `probe_unsupported` for SDK lanes.
- [ ] 3.7 Extend the existing credential-sentinel test to cover `OPENROUTER_API_KEY` and an
  OpenRouter lane with an echoing transport.
- [ ] 3.8 Write a failing test, then implement: `dispatch_and_wait` reads `tools_overflow` from
  the packet sidecar next to `packet_path` and passes it to OpenAI-compatible adapters.
- [ ] 3.8a Write failing tests, then implement in `review_packet.py`: a `build_toolless_packet`
  (design D6) and its `review-packet.toolless.meta.json` sidecar. Tests:
  - For `review_type="plan"`, a branch whose full diff overflows `BUDGET_CHARS` yields a tool-less
    packet with `tools_overflow: false` that contains the full `proposal.md`, `design.md`,
    `tasks.md` and spec deltas.
  - For `implementation`, the dropped files appear in `coverage.skipped`.
  - `dispatch_and_wait` passes the tool-less body and flag to OpenAI-compatible adapters, and the
    primary body to CLI lanes.
- [ ] 3.9 Integration test: with the repository's `agents.yaml`, an injected transport and no
  `pi`/`codex` binaries on `PATH`, `--check-vendors --json` lists `openrouter` as verified and
  maps it to `openrouter` in `lane_kinds`.

## 4. Spend recording route and client

**Files:** `agent-coordinator/src/model_routing/api.py`, `agent-coordinator/src/model_routing/ledger.py`
(an idempotent lookup only), `agent-coordinator/tests/model_routing/test_spend_route.py` (new),
`skills/parallel-infrastructure/scripts/spend_recorder.py` (new),
`skills/tests/parallel-infrastructure/test_spend_recorder.py` (new)
**Depends:** none (the interface is the request body in the model-routing spec)
**Specs:** model-routing "Review Spend Recording Route"; parallel-infrastructure "Metered
Review Lane Spend Accounting" (record, spool and replay part)

- [ ] 4.1 Write failing route tests: 201 on insert, 200 on a duplicate `generation_id`, 401
  without a key, 422 on a negative `actual_usd` or an unknown field, and `GET /routing/usage`
  reflects the row.
- [ ] 4.2 Implement the `SpendRecordRequest` Pydantic model (`extra="forbid"`), the
  `POST /routing/spend` route, and `LedgerService.find_by_generation_id`. No database
  migration is needed because `generation_id` already exists.
- [ ] 4.3 Write failing client tests:
  - `record()` posts the row.
  - On a connection error or 403 it appends to `reviews/spend-spool.jsonl` and returns
    `recorded=False`.
  - `replay --change-id` is idempotent and empties the spool.
  - No API key value appears in the spool.
- [ ] 4.4 Implement `spend_recorder.py`: `record()`, `replay()`, and a CLI. It authenticates
  with the existing coordination-bridge credentials (`COORDINATION_API_URL`/`COORDINATION_API_KEY`,
  read only inside the bridge's credential path).

## 5. Convergence: composite agent lane and honest mid-run loss

**Files:** `skills/autopilot/scripts/agent_lane.py`, `skills/autopilot/scripts/convergence_loop.py`,
`skills/autopilot/scripts/runner.py` (only to add `metered_spend_unrecorded` to
`record-degradation` choices), `openspec/schemas/dispatch-result.schema.json` (only the enum
value), `skills/tests/autopilot/test_agent_lane.py`, `skills/tests/autopilot/test_convergence_loop_capability.py` (new)
**Depends:** 3, 4
**Specs:** skill-workflow "Honest Review Quorum" (MODIFIED), "Composite Agent-Lane Review";
parallel-infrastructure "Metered Review Lane Spend Accounting" (checkpoint part)

- [ ] 5.1 Write failing tests: in round 2 the OpenRouter lane fails `vendor_unavailable` →
  `capability_unavailable` with `missing_lanes == ["openrouter"]`; an `unknown` failure →
  `quorum_lost`.
- [ ] 5.2 Implement the mid-run capability mapping in `converge()` (design D7). Write
  `generation_id`, `prompt_tokens`, `completion_tokens`, `cost_usd` and `cost_source` into the
  round checkpoint's vendor index.
- [ ] 5.3 Add `metered_spend_unrecorded` to the `Degradation.code` enum in
  `dispatch-result.schema.json` and to the `runner.py record-degradation` choices. Update the
  schema fixture test.
- [ ] 5.4 Write failing tests for the `CompositeOrchestrator`:
  - Run against a fixture change with an injected transport and a scripted handshake.
  - `converge()` receives `min_quorum=2`, the checkpoint holds both lane files, and
    `quorum_received == 2`.
  - Consensus findings attribute both lane ids.
  - `--verified-lanes claude_code` alone → `capability_unavailable` with no handshake files.
- [ ] 5.5 Implement `--verified-lanes`, `CompositeOrchestrator` (the handshake lane plus
  `ReviewOrchestrator.dispatch_and_wait(include_lanes=...)` run concurrently, with the result
  callback forwarded), and quorum-policy resolution from the verified count. After each
  metered result, call `spend_recorder.record()`. On `recorded=False`, record the
  `metered_spend_unrecorded` degradation through the result payload. Update
  `_review_body` to list the lanes.
- [ ] 5.6 Write failing tests, then implement:
  - `converge()` builds the tool-less packet (task 3.8a) when the primary packet overflows, and
    passes both paths to `dispatch_and_wait`.
  - `agent_lane.py` `result.json` carries `missing_lanes` (from `ConvergenceResult.missing_lanes`),
    `lanes` (the lane ids that returned a successful result), `quorum_received`, a per-lane
    `{model_used, generation_id, cost_usd, cost_source}` map, and `degradations` (including
    `metered_spend_unrecorded`). Task 6.4's park and degradation rules read these fields.
  - After each run, `agent_lane.py` writes `ConvergenceResult.consensus` (with `quorum_received`)
    to `openspec/changes/<id>/reviews/`, using one file per phase so the two implementation phases
    do not collide: `consensus-plan.json` (PLAN_REVIEW), `consensus-impl-review.json`
    (IMPL_REVIEW), `consensus-val-review.json` (VAL_REVIEW). This matches the skill-workflow
    "Composite Agent-Lane Review" requirement. The D9 evidence and task 7.2 cite
    `consensus-plan.json`. `converge()` itself never writes these files.

## 6. Supervisor ranking, apply-time replay, and worker protocol

**Files:** `skills/supervise/scripts/execution.py`, `skills/tests/supervise/test_execution_profile.py`,
`skills/autopilot/SKILL.md` (the review-section protocol text only)
**Depends:** 3 (the `lane_kinds` shape), 4 (the replay CLI)
**Specs:** supervise "Execution Profile and Review Requirements" (MODIFIED)

- [ ] 6.1 Write failing tests: `lane_kinds` ranks `openrouter` after `vendor-cli`; a missing
  `lane_kinds` falls back to the old inference.
- [ ] 6.2 Implement the `rank()` change in `resolve_execution_profile` (design D8).
- [ ] 6.3 Write failing tests, then implement: `ExecutionAdapter.apply` runs
  `spend_recorder.py replay` once when a `metered_spend_unrecorded` degradation is present,
  reports the replayed count, and never fails the apply on a replay error.
- [ ] 6.4 Update the autopilot `SKILL.md` review section with these rules:
  - In cloud, run `agent_lane.py converge --verified-lanes <each lane from execution_profile.lanes.review>`.
  - A `capability_unavailable` result maps to `runner.py park --kind capability_unavailable`.
  - Record the degradation `metered_spend_unrecorded` when the result reports it.
  
  Keep the env-probing guard test green.

## 7. Cloud end-to-end evidence and retirement of the temporary policy

**Files:** `openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` (new),
`skills/parallel-infrastructure/review_quorum_policy.json` (`policies` entry),
`TRUST_POSTURE.md`, `skills/autopilot/SKILL.md` (single-vendor references),
`docs/guides/` (cloud setup note), `skills/tests/parallel-infrastructure/test_quorum_policy_retirement.py` (new)
**Depends:** 1–6 merged on the feature branch
**Specs:** skill-workflow "Cloud Single-Vendor Policy Retirement"; acceptance outcome 1

- [ ] 7.1 Document the cloud setup in the guide that covers cloud environments: the
  `OPENROUTER_API_KEY` environment secret, the egress allowlist entry `openrouter.ai`,
  `SSL_CERT_FILE` for the agent proxy CA, and the ceiling sources (a coordinator
  `ROUTING_MONTHLY_CEILING_USD > 0`, or an OpenRouter key with a credit limit).
- [ ] 7.2 This step is run by the operator in a provisioned cloud container. Run `/autopilot`
  on a fixture change through PLAN_REVIEW. Write `evidence/cloud-quorum-run.md` with:
  - the `--check-vendors --json` report (verified lanes, `lane_kinds`, no secrets);
  - `min_quorum` from `review_requirements`;
  - the `consensus-plan.json` lane attribution;
  - the ledger or spool `generation_id`, model and cost.
- [ ] 7.3 Write the guard test `test_quorum_policy_retirement.py`:
  - It fails if the cloud policy entry is absent while the evidence file is missing or has no
    `generation_id`.
  - It asserts that `TRUST_POSTURE.md` has no "Review quorum in cloud containers" section.
  - It asserts that `resolve_quorum_policy(cloud_container, 1)` returns quorum 2.
- [ ] 7.4 Delete the `cloud-container-single-vendor-2026-10-09` entry and the `TRUST_POSTURE.md`
  section. Remove the cloud single-vendor guidance from `skills/autopilot/SKILL.md`. Check
  whether `posture_digest` changes, and record the result in the session log.
- [ ] 7.5 Run `skills/install.sh` to sync the runtime copies, the full `skills/` and
  `agent-coordinator` test sweeps (`pytest -m "not e2e and not integration"`), `ruff`,
  `mypy --strict` on the touched coordinator modules, and `openspec validate openrouter-review-lane --strict`.

## Traceability

| Requirement | Tasks |
|---|---|
| parallel-infrastructure: OpenAI-Compatible Dispatcher Discovery | 2.1–2.3, 3.1–3.4, 3.9 |
| parallel-infrastructure: Dispatchable Vendor Verification | 1.1–1.2, 3.5–3.7, 3.9 |
| parallel-infrastructure: Metered Review Lane Spend Accounting | 1.3–1.4, 4.3–4.4, 5.2, 5.5 |
| parallel-infrastructure: Tool-less Lane Packet Refusal | 1.5–1.7, 3.8, 3.8a, 5.6 |
| skill-workflow: Honest Review Quorum | 5.1–5.3 |
| skill-workflow: Composite Agent-Lane Review | 5.4–5.6, 6.4 |
| skill-workflow: Cloud Single-Vendor Policy Retirement | 5.6, 7.1–7.4 |
| supervise: Execution Profile and Review Requirements | 6.1–6.3 |
| model-routing: Review Spend Recording Route | 4.1–4.2 |
| Acceptance outcome 4 (schema-conformant HTTP findings, synthesized like CLI lanes) | 1.6–1.7 |
