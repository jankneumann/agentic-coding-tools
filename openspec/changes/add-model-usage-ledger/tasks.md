# Tasks: add-model-usage-ledger

Sizes per the plan-feature Task Sizing Reference (XS ≤30m, S ≤2h, M ≤1d). No L or XL tasks.
Spec scenario IDs are `<capability>.<n>` numbered in file order within each delta spec.

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 Freeze `contracts/openapi/v1.yaml` for the `/usage/*` routes after lint [S]
  **Spec scenarios**: usage-accounting.14, usage-accounting.15, agent-coordinator.3, agent-coordinator.4, agent-coordinator.5
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: None
- [ ] 1.2 Validate `contracts/db/schema.sql` against migration conventions (IF NOT EXISTS, provenance constraints) [S]
  **Spec scenarios**: agent-coordinator.1, agent-coordinator.2
  **Contracts**: contracts/db/schema.sql
  **Design decisions**: D3, D5, D6
  **Dependencies**: None
- [ ] 1.3 Validate both event schemas (`usage-record`, `dispatch-record`) as JSON Schema 2020-12 [XS]
  **Spec scenarios**: usage-accounting.1, usage-accounting.4
  **Contracts**: contracts/events/*.schema.json
  **Dependencies**: None
- [ ] Checkpoint: run contract lint, review diff, verify scope
- [ ] 1.4 Regenerate contract types (`generated/models.py`, `generated/types.ts`) from the OpenAPI file [XS]
  **Dependencies**: 1.1, 1.3

## Phase 2 — Transcript adapters and collector (wp-adapters)

- [ ] 2.1 Write round-trip tests for the new normalized-event fields (`thinking_tokens`, `model`, `effort`, `agent_id`, `parent_session_id`) [S]
  **Spec scenarios**: harness-engineering.5
  **Contracts**: contracts/events/usage-record.schema.json
  **Dependencies**: None
- [ ] 2.2 Extend the normalized event schema (`normalize.py`, `references/event-schema.md`) with the new fields [S]
  **Dependencies**: 2.1
- [ ] 2.3 Write tests for Claude CLI adapter: sets `model`, `effort`, thinking tokens; fixture updated with real record shape [S]
  **Spec scenarios**: usage-accounting.1, usage-accounting.3, harness-engineering.5
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.4 Fix `claude_code_cli.py` to populate `model`, `effort`, `thinking_tokens`, cache detail [S]
  **Dependencies**: 2.3
- [ ] 2.5 Write tests for sidechain discovery under `subagents/agent-*.jsonl` [S]
  **Spec scenarios**: usage-accounting.7, harness-engineering.6
  **Design decisions**: D2
  **Dependencies**: 2.2
- [ ] 2.6 Implement sidechain discovery with `agent_id`/`parent_session_id` stamping [S]
  **Dependencies**: 2.5
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.7 Write tests for Grok/Pi cache-token mapping [S]
  **Spec scenarios**: harness-engineering.5
  **Dependencies**: 2.2
- [ ] 2.8 Implement Grok/Pi cache-token mapping [S]
  **Dependencies**: 2.7
- [ ] 2.8a Write tests for Grok `vendor_cost_usd` extraction [XS]
  **Spec scenarios**: harness-engineering.5
  **Dependencies**: 2.2
- [ ] 2.8b Implement Grok `vendor_cost_usd` extraction [XS]
  **Dependencies**: 2.8a
- [ ] 2.9 Write tests for sanitizer pass-through of `model`/`effort`/`usage` fields [XS]
  **Spec scenarios**: harness-engineering.8
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.10 Write tests for `usage_collector.py`: cursor advance on ack only, record_hash stability, batch shape matches contract [M]
  **Spec scenarios**: usage-accounting.2, usage-accounting.8, usage-accounting.10
  **Contracts**: contracts/openapi/v1.yaml (POST /usage/ingest)
  **Design decisions**: D3, D7
  **Dependencies**: 2.6, 2.8
- [ ] 2.11 Implement `usage_collector.py` (read since cursor → normalize → sanitize → POST) [M]
  **Dependencies**: 2.10
- [ ] 2.12 Write tests for spool write on failure, replay on next run, `USAGE_LEDGER_ENABLED=false` short-circuit, 5 s timing budget [M]
  **Spec scenarios**: usage-accounting.9, usage-accounting.10
  **Design decisions**: D7
  **Dependencies**: 2.11
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.13 Implement the collector resilience layer (spool, replay, flag gate, timing guard) in `usage_collector.py` [S]
  **Dependencies**: 2.12
- [ ] 2.14 Write tests for `--source coordinator` read path in `collect_transcripts` entry [S]
  **Spec scenarios**: harness-engineering.13
  **Dependencies**: 2.11
- [ ] 2.15 Implement `--source coordinator --since` reading `GET /usage/events` [S]
  **Dependencies**: 2.14
- [ ] 2.16 Update `collect-transcripts/SKILL.md` for the new adapter fields, flags, source [XS]
  **Dependencies**: 2.15

## Phase 3 — Coordinator ledger (wp-coordinator)

- [ ] 3.1 Write migration tests: 035 applies additively, provenance constraint rejects cost without version, CHECK accepts `validator` [S]
  **Spec scenarios**: agent-coordinator.1, agent-coordinator.2, agent-archetypes.7
  **Contracts**: contracts/db/schema.sql
  **Dependencies**: None
- [ ] 3.2 Create `database/migrations/035_model_usage_ledger.sql` from the DB contract [S]
  **Design decisions**: D3, D5, D6, D9
  **Dependencies**: 3.1
- [ ] 3.3 Write tests for `pricing.py` loader: schema validation, fail-loud on unknown vendor, exact-over-prefix, null cost with reason [S]
  **Spec scenarios**: usage-accounting.11, usage-accounting.12, usage-accounting.13, usage-accounting.14
  **Design decisions**: D5
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.4 Implement `src/pricing.py` loader [S]
  **Dependencies**: 3.3
- [ ] 3.4a Seed `agent-coordinator/pricing.yaml` (schema_version 1, version `2026.09.1`, rates for every vendor/model in `archetypes.yaml`) [S]
  **Design decisions**: D5
  **Dependencies**: 3.4
- [ ] 3.5 Write tests for `usage_ledger.py` service: ingest idempotency, dispatch upsert, by-phase join with mismatch flags, unattributed detection [M]
  **Spec scenarios**: usage-accounting.2, usage-accounting.5, usage-accounting.16, usage-accounting.17, usage-accounting.18
  **Design decisions**: D2, D3
  **Dependencies**: 3.2
- [ ] 3.6 Implement `src/usage_ledger.py` (ingest, dispatch upsert, pricing application, query builders) [M]
  **Dependencies**: 3.4, 3.5
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.7 Write API tests for `/usage/*` routes incl. 401 on ingest, 422 on unsanitized batch, filters [M]
  **Spec scenarios**: usage-accounting.14, usage-accounting.15, usage-accounting.13, agent-coordinator.3, agent-coordinator.4, agent-coordinator.5
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 3.6
- [ ] 3.8 Expose `/usage/*` routes in `coordination_api.py` [M]
  **Dependencies**: 3.7
- [ ] 3.8a Register `/usage/*` in HTTP proxy coverage [XS]
  **Dependencies**: 3.8
- [ ] 3.9 Write tests for retention job (purges events only, audits count) [S]
  **Spec scenarios**: usage-accounting.13, agent-coordinator.6
  **Design decisions**: D6
  **Dependencies**: 3.6
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.10 Implement retention job on `WatchdogService` with `USAGE_EVENT_RETENTION_DAYS` [S]
  **Dependencies**: 3.9
- [ ] 3.11 Write archetype enum parity test across `report_status.py`, the `/status/report` literal, the CHECK constraint [S]
  **Spec scenarios**: agent-archetypes.7, agent-archetypes.8
  **Design decisions**: D9
  **Dependencies**: 3.2
- [ ] 3.12 Widen the three archetype enumerations to all `archetypes.yaml` keys [XS]
  **Dependencies**: 3.11
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.13 Write tests for `resolve_archetype_for_phase`: provider-less reason, `thinking`/`tier` in endpoint response, `thinking` in audit entry [S]
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.2, agent-archetypes.4, agent-archetypes.5
  **Design decisions**: D11
  **Dependencies**: None
- [ ] 3.14 Implement `tier`, provider-less reason, audit `thinking` in the resolution function plus endpoint [S]
  **Dependencies**: 3.13
- [ ] 3.15 Write tests for `evaluation/metrics.py` pricing via `pricing.py` [S]
  **Design decisions**: D5
  **Dependencies**: 3.4
- [ ] 3.16 Price `estimated_cost_usd` in evaluation metrics from the pricing table [S]
  **Dependencies**: 3.15
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.17 Update Dockerfile COPY list plus smoke-import module list for `pricing.py`, `usage_ledger.py` [XS]
  **Dependencies**: 3.8
- [ ] 3.18 Accept optional `cli.thinking_flag` (argv template list) in the `agents.yaml` schema, with a test [S]
  **Spec scenarios**: skill-workflow.7
  **Design decisions**: D4
  **Dependencies**: None

## Phase 4 — Dispatch ledger and thinking forwarding (wp-dispatch)

- [ ] 4.1 Write tests for `coordination_bridge.try_record_dispatch` (POST, patch, failure returns None) [S]
  **Spec scenarios**: usage-accounting.4, usage-accounting.5
  **Contracts**: contracts/openapi/v1.yaml (POST /usage/dispatch), contracts/events/dispatch-record.schema.json
  **Dependencies**: None
- [ ] 4.2 Implement `try_record_dispatch` in `coordination_bridge.py` [S]
  **Dependencies**: 4.1
- [ ] 4.3 Write tests for `_build_options` copying `thinking`, plus `build_phase_dispatch_kwargs` writing a dispatch record before dispatch then patching `agent_id` after [M]
  **Spec scenarios**: skill-workflow.3, skill-workflow.4, usage-accounting.4, usage-accounting.5
  **Design decisions**: D2
  **Dependencies**: 4.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 4.4 Implement thinking copy in `_build_options` [S]
  **Dependencies**: 4.3
- [ ] 4.4a Implement dispatch-record write/patch in `build_phase_dispatch_kwargs` [M]
  **Design decisions**: D2
  **Dependencies**: 4.4
- [ ] 4.5 Write tests for the override path: resolver still called, dispatch record has `override_source="env"` [S]
  **Spec scenarios**: skill-workflow.6, usage-accounting.6
  **Dependencies**: 4.4
- [ ] 4.6 Implement override-path resolution with dispatch record [S]
  **Dependencies**: 4.5
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 4.7 Write tests for `cli.thinking_flag` template rendering in `provider_dispatch.py`, including the `thinking_not_forwarded` warning [S]
  **Spec scenarios**: skill-workflow.7, skill-workflow.8
  **Design decisions**: D4
  **Dependencies**: None
- [ ] 4.8 Implement `thinking_flag` rendering in `provider_dispatch.py` [S]
  **Dependencies**: 4.7
- [ ] 4.8a Add `cli.thinking_flag` templates to `agents.yaml` for codex, grok [XS]
  **Design decisions**: D4
  **Dependencies**: 4.8
- [ ] 4.9 Write tests for `review_dispatcher` passing `archetype_model`/`archetype_thinking` from the reviewer archetype [S]
  **Spec scenarios**: skill-workflow.9
  **Dependencies**: 4.8
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 4.10 Implement reviewer archetype resolution in `review_dispatcher.py` dispatch call [S]
  **Dependencies**: 4.9
- [ ] 4.11 Update `autopilot/SKILL.md` dispatch blocks for `thinking` plus dispatch records [XS]
  **Dependencies**: 4.4

## Phase 5 — Langfuse hook (wp-langfuse)

- [ ] 5.1 Write tests for the hook over a real-shape fixture: generations per assistant record, `usage_details`, sidechain inclusion, cursor by lines [M]
  **Spec scenarios**: observability.1, observability.2, observability.3, observability.4
  **Design decisions**: D8
  **Dependencies**: None
- [ ] 5.2 Rebuild `langfuse_hook.py` on the collect-transcripts adapter, delete `group_into_turns` [M]
  **Dependencies**: 5.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 5.3 Update `references/stop-hook.md` plus the installed-hook doc test [XS]
  **Dependencies**: 5.2

## Phase 6 — agent-metrics usage report (wp-metrics)

- [ ] 6.1 Write tests for `query_metrics.py --usage`: queries the three routes, degrades on unreachable coordinator [S]
  **Spec scenarios**: harness-engineering.4
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: None
- [ ] 6.2 Implement `--usage` (with `--change` filter) in `query_metrics.py` [S]
  **Dependencies**: 6.1
- [ ] 6.3 Write tests for `generate_dashboard.py` usage section rendering (columns, mismatch marker, estimate labels, unpriced callout) [S]
  **Spec scenarios**: harness-engineering.4
  **Dependencies**: 6.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 6.4 Implement the usage section renderer [S]
  **Dependencies**: 6.3
- [ ] 6.5 Update `agent-metrics/SKILL.md` modes plus steps [XS]
  **Dependencies**: 6.4

## Phase 7 — usage-viz app (wp-viz)

- [ ] 7.1 Scaffold `apps/usage-viz` from kanban-viz conventions (auth, SSE/poll hooks, build) [M]
  **Design decisions**: D10
  **Dependencies**: None
- [ ] 7.2 Write component tests for the four views (spend, per-change phase table with mismatch, thinking-tier comparison, ingest status) [M]
  **Contracts**: contracts/generated/types.ts
  **Dependencies**: 7.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 7.3 Implement the four views against `/usage/*` [M]
  **Dependencies**: 7.2
- [ ] 7.4 Add `docs/usage-viz/README.md`, linked from the workflow guide's Observability Frontends [XS]
  **Dependencies**: 7.3

## Phase 8 — Integration and archival (wp-integration)

- [ ] 8.1 Wire the collector into `Stop`, `SubagentStop`, `SessionEnd` in `.claude/settings.json` via `session-bootstrap` [S]
  **Spec scenarios**: usage-accounting.8, usage-accounting.11
  **Dependencies**: None
- [ ] 8.1a Document the collector hooks in `docs/cloud-session-hooks.md` [XS]
  **Dependencies**: 8.1
- [ ] 8.2 Register new test directories in `skills/pyproject.toml` testpaths or the ci.yml isolated loop; update `install-manifest.json` [XS]
  **Dependencies**: None
- [ ] 8.3 Run the full test suites in both venvs (coordinator, skills) [S]
  **Dependencies**: 8.1, 8.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 8.4 E2E: one autopilot run against a live coordinator; assert `/usage/by-phase` shows every phase with intended vs actual at ≥ 95% attribution [M]
  **Spec scenarios**: usage-accounting.16, usage-accounting.17, usage-accounting.18, usage-accounting.8
  **Dependencies**: 8.3
- [ ] 8.5 E2E: cloud-session parity check from a Claude Code web session (records arrive without teleport) [S]
  **Spec scenarios**: usage-accounting.11
  **Dependencies**: 8.3
- [ ] 8.6 Archive `usage-stats-multi-model` with superseded-by pointer [XS]
  **Design decisions**: D12
  **Dependencies**: None
- [ ] 8.7 Amend `add-adaptive-model-router/design.md` D12 with the ledger-source amendment [XS]
  **Design decisions**: D12
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 8.8 Write ADR for transcript-derived ledger placement under `docs/decisions/` [S]
  **Dependencies**: 8.4
