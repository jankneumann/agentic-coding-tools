# Change: add-model-usage-ledger

**Status**: Draft
**Created**: 2026-09-03
**Author**: Claude (plan-feature, coordinated tier)
**Supersedes**: `usage-stats-multi-model` (archived as superseded by this change)
**Amends**: `add-adaptive-model-router` design D12 (transcript-derived records become an accepted ledger source)

## Why

The archetype catalog resolves a vendor, model, and thinking tier for every autopilot phase, but
nothing in the repo can answer "which model and thinking budget actually ran phase X, with how
many tokens, at what cost". A gap analysis on 2026-09-03 found the chain broken at every stage:

- **Intent is under-recorded.** Only the archetype *name* is persisted (loop-state, `agent_sessions`).
  The resolved model and thinking are never written per dispatch, and env-override runs record
  nothing at all.
- **Thinking is dropped at dispatch.** `POST /archetypes/resolve_for_phase` returns `thinking`, but
  `phase_agent._build_options` copies only `model`/`system_prompt`, and no CLI adapter translates
  it to a vendor flag. All three Grok tiers dispatch as identical bare `grok-4.5` calls; Codex
  frontier and premium are the same `gpt-5.6-sol` call. Review panels never receive the archetype
  model at all (`review_dispatcher.archetype_model` is a dead parameter).
- **Actual usage is never captured.** The Langfuse Stop hook reads `role` at the top level of each
  transcript line, but real Claude Code transcripts nest it under `message`, so it groups zero
  turns and emits nothing. Even a fixed hook sends model as a metadata string with no
  `usage_details`, so Langfuse could not price it. The coordinator's Langfuse middleware calls
  the v2 SDK API against the pinned v4 SDK and is silently dead. The `collect-transcripts`
  Claude adapter parses all four usage counters correctly but never sets `model`, so tokens are
  unattributable.
- **Nothing prices, stores, or surfaces.** No pricing table exists; the routing resolver's per-Mtok
  inputs are never sourced, the roadmap policy is a literal placeholder, and every evaluation
  report prints a cost of `0.0000`. The coordinator has no usage table or routes.
  `agent-metrics` reports no token or cost figures.
- **Cloud sessions lose everything.** Transcripts are written inside the ephemeral container and
  reclaimed with it. The only recovery path is a manual `claude --teleport` onto a laptop.

The raw material already exists and is free: every Claude Code assistant record carries
`message.model`, `message.usage` (input, output, cache-creation, cache-read, and thinking tokens),
and a top-level `effort`; sub-agent transcripts live at
`<project>/<session>/subagents/agent-<id>.jsonl`, keyed by the same id the dispatch receives.
Codex rollouts carry `token_count` events. During this planning session the parent ran on the
configured model while its exploration sub-agents ran on Opus 5, and no existing surface could
show that.

Why now: `add-adaptive-model-router` (21/71 tasks) explicitly deferred transcript parsing, so its
ledger only ever sees OpenAI-compatible dispatch. Without a transcript-derived ledger the router
optimises against a cost model that observes none of the Claude Code work, and the archetype
design cannot be validated at all.

## What Changes

**Execution layer (skills)**

- `collect-transcripts`: the Claude CLI adapter sets `model` and `effort` on every normalized
  assistant event and reads `output_tokens_details.thinking_tokens` and cache-tier detail into
  `TokenUsage`; the adapter discovers `subagents/agent-*.jsonl` alongside the parent session and
  stamps `agent_id`/`parent_session_id`; Grok and Pi adapters map cache tokens; Grok reads
  `total_cost_usd`. The event schema gains `model`, `effort`, `agent_id`, `parent_session_id`.
- New `usage-collector` script (in `collect-transcripts`), invoked from `Stop`, `SubagentStop`,
  and `SessionEnd` hooks: reads new transcript lines since a per-file cursor, normalizes via the
  adapters, sanitizes, and POSTs (a) compact usage records and (b) sanitized transcript events to
  the coordinator. Idempotent on `(vendor, session_id, record_hash)`. Spools locally and exits 0
  when the coordinator is unreachable.
- `autopilot`: `build_phase_dispatch_kwargs` writes a **dispatch ledger entry** per phase dispatch
  (change id, phase, archetype, intended model, intended thinking, provider, signals, override
  flag, dispatch timestamp, and, once known, the sub-agent id / transcript path) and POSTs it to
  the coordinator. Override runs record the override instead of `null`.
- `autopilot` / `parallel-infrastructure`: **forward `thinking` to vendor flags** at the CLI
  adapter boundary (`--model_reasoning_effort` for Codex, effort suffix/flag for Grok and
  Antigravity, `--effort` for Claude CLI where supported). `review_dispatcher` passes
  `archetype_model` from the resolved reviewer archetype.
- `langfuse` Stop hook: rebuilt on the `collect-transcripts` adapters (deleting the private
  `group_into_turns` parser) and emits `as_type="generation"` observations with `usage_details`
  and `model` so Langfuse computes cost. The coordinator-side v2 middleware is **out of scope**
  (left to `add-cross-harness-flow-display`) but the observability spec is corrected to say it
  is non-functional on the v4 SDK.
- `agent-metrics`: new `--usage` mode with a per-change, per-phase table (intended model, actual
  model, intended thinking, actual effort, thinking tokens, input/output/cache tokens, estimated
  cost with pricing version, and a **mismatch flag**), plus per-vendor/per-model totals.

**Coordination layer (coordinator)**

- Migration `035_model_usage_ledger.sql`: `usage_records`, `dispatch_records`,
  `transcript_events` (sanitized, 90-day retention), `usage_ingest_state`.
- Routes: `POST /usage/ingest`, `POST /usage/dispatch`, `GET /usage/summary`,
  `GET /usage/by-phase`, `GET /usage/by-model`, `GET /usage/mismatches`, `GET /usage/events`.
  Writes require the API key; reads follow the existing GET convention.
- Retention job on `WatchdogService`: purge `transcript_events` older than 90 days nightly;
  `usage_records` and `dispatch_records` are never purged.
- The `validator` (and `supervisor`, `documenter`) archetypes are accepted by `report_status.py`,
  the `/status/report` Pydantic literal, and the `agent_sessions` CHECK constraint, so VALIDATE
  no longer drops its archetype.

**Governance layer**

- `agent-coordinator/pricing.yaml`: versioned static table (`schema_version`, monotonic
  `version`, per `(vendor, model)` input/output/cache-read/cache-write USD per Mtok, optional
  thinking rate). Loader validates with jsonschema and fails loud on unknown vendors. Every cost
  figure carries `pricing_version` and `estimated: true`. Unknown models yield `cost_usd = null`
  with reason `no_price`, never a silent zero.
- `evaluation/metrics.py` prices `estimated_cost_usd` from the same table so evaluation reports
  stop printing `0.0000`.

**Observability surface**

- `apps/usage-viz`: React + TypeScript + Vite app copied from `kanban-viz` conventions (Bearer
  auth, SSE/poll fallback) with four views: spend by vendor/model, per-change phase table with
  mismatch highlighting, thinking-tier comparison, and cloud-session ingest status.

**Planning hygiene**

- Archive `usage-stats-multi-model` with a superseded-by pointer to this change.
- Amend `add-adaptive-model-router/design.md` D12 so `usage_records` is an accepted source for the
  router's spend ledger and posteriors (feedback job reads it).

No **BREAKING** changes: all migrations are additive; the Langfuse hook's observation shape changes
from `agent` turns to `generation` observations, which is a new-data-only change with no
downstream consumer today.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|---|---|---|---|
| Attribution completeness | Autopilot phase dispatches with a matching `usage_records` row joined via `dispatch_records` | ≥ 95% over one full autopilot run | VALIDATE (e2e autopilot run + `/usage/by-phase`) |
| Ingest latency | Time from `Stop` hook firing to row visible via `GET /usage/summary` | p95 ≤ 60 s | VALIDATE (integration test with live coordinator) |
| Idempotency | Duplicate rows after re-running the collector on an unchanged transcript | 0 | IMPLEMENT (unit) + VALIDATE (integration) |
| Hook overhead | Wall-clock of the `Stop` collector for ≤ 500 new transcript lines | p95 ≤ 5 s; hard timeout 30 s; never non-zero exit | IMPLEMENT (unit timing test) |
| Resilience | Behaviour with coordinator unreachable | Exit 0, records spooled to `~/.claude/state/usage-spool/`, replayed on next hook | VALIDATE (integration, coordinator stopped) |
| Cost provenance | Cost figures without `pricing_version` and `estimated` flag | 0 (NOT NULL constraints) | IMPLEMENT (migration test) |
| Secret hygiene | Unredacted secrets in stored `transcript_events` across the sanitizer corpus | 0 | IMPLEMENT (sanitizer test corpus) |
| Retention | `transcript_events` rows older than 90 days after the nightly job | 0; `usage_records` row count unchanged | VALIDATE (integration with clock skew) |
| Compatibility | Existing skills with the collector disabled (`USAGE_LEDGER_ENABLED=false`) | All existing tests pass unchanged | CI |

## Approaches Considered

### Selected Approach

**Approach A** was selected at Gate 1 on 2026-09-03 with no modifications. Discovery decisions
that bind the detailed artifacts:

- Supersede `usage-stats-multi-model`; amend the router's D12 so transcript-derived records feed
  its ledger.
- Store sanitized transcript events centrally, not only usage rows; 90-day retention for events,
  usage and dispatch rows kept indefinitely.
- Fix the Langfuse Stop hook (adapter-based parsing, `usage_details`); leave the coordinator's
  v2-era middleware to `add-cross-harness-flow-display`.
- Surface in `agent-metrics --usage` first and also scaffold `apps/usage-viz`.
- Pricing is a hand-maintained versioned YAML; OpenRouter refresh stays in the router change.
- Acceptance check: after one autopilot run, the per-phase table shows intended vs actual model,
  thinking, tokens, and estimated cost, and flags every mismatch.

### Approach A: Transcript-derived ledger pushed from hooks into the coordinator — **Recommended**

Hooks inside every session (local or cloud) parse the vendor transcripts with the existing
`collect-transcripts` adapters and push compact usage records, dispatch records, and sanitized
events to the coordinator over HTTP. The coordinator is the system of record; pricing is a
versioned YAML; `agent-metrics` and a new `usage-viz` app read the coordinator API. Langfuse is
fed from the same normalized events as a secondary view.

- **Pros**
  - Covers every vendor whose CLI writes a transcript (Claude Code, Codex, Grok, Pi) with one
    normalizer that already exists and has tests.
  - The only path that works for cloud sessions: the container already reaches the coordinator
    for status hooks, and nothing else survives container reclaim.
  - Captures the *actual* model and effort per sub-agent, which is the verification the
    archetype design needs. Intended-vs-actual is a join, not an inference.
  - Feeds the router's posteriors and the arbitrage cost ledger from real observations, closing
    the "nothing populates `cost_observed_usd`" gap.
  - Works offline and with the Langfuse MCP credentials broken (as they are today).
- **Cons**
  - Transcript formats are vendor-private and can drift; the adapters must fail soft and the
    schema version must be stamped.
  - Cost is an estimate from a hand-maintained table, never an invoice.
  - Largest surface area: adapters, hooks, migration, routes, report, app.
- **Effort**: L (decomposed into seven M-or-smaller packages; see design)

### Approach B: Claude Code native OpenTelemetry export into the existing OTel stack

Enable Claude Code's built-in telemetry (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, OTLP exporter) and
point it at the coordinator's existing OpenTelemetry/Prometheus stack from
`add-otel-observability`. Claude Code emits token and cost metrics per model itself; a Grafana or
Prometheus query becomes the report.

- **Pros**
  - Zero transcript parsing; Claude Code computes cost with its own price table.
  - Reuses infrastructure that already exists in the coordinator.
  - Smallest implementation: configuration plus dashboards.
- **Cons**
  - Claude Code only. Codex, Grok, Pi, and local models are invisible, which defeats the
    cross-vendor question.
  - Metrics carry session and model attributes but no phase, change id, or sub-agent id, so
    intended-vs-actual per phase is not reconstructible; attribution would rely on resource
    attributes set per process, which sub-agents share with their parent.
  - No transcript events, so no central deep analysis for cloud sessions.
  - Requires an OTLP collector reachable from cloud containers, which the network policy does
    not currently allow.
- **Effort**: S

### Approach C: Langfuse as the system of record

Fix the Stop hook to emit generation observations with usage details, tag traces with change id
and phase at emit time, rely on Langfuse's built-in model pricing for cost, and have
`agent-metrics` query the Langfuse API. Dispatch intent is stored as trace metadata.

- **Pros**
  - Pricing and a UI come for free; per-generation cost is computed server-side.
  - Session and trace grouping already model the conversation shape well.
  - Aligns with `add-cross-harness-flow-display`.
- **Cons**
  - The hook cannot know the change id or phase at emit time without the dispatch ledger this
    approach is trying to avoid; attribution becomes best-effort tag inference.
  - Introduces an external dependency for the router and policy engine to read cost from; the
    MCP credentials are broken today and cloud sessions would need Langfuse secrets from
    OpenBao on every container.
  - Self-hosted Langfuse needs ClickHouse, Redis, and MinIO; Langfuse Cloud sends every prompt
    off-box, which conflicts with keeping sanitized transcripts under our own retention rules.
  - The coordinator stays blind, so the router's posteriors cannot be fed without a second
    ingestion path.
- **Effort**: M

**Recommendation rationale**: only Approach A gives per-phase intended-versus-actual attribution
across vendors and survives cloud container reclaim. Approach B's zero-parsing advantage is real,
and the design keeps the door open by recording Claude Code's own `effort` field, but its
Claude-only scope and lack of phase attribution disqualify it as the primary path. Approach C is
retained as a secondary view: the same normalized events that feed the coordinator also feed
Langfuse, so its UI benefits arrive without making it the source of truth.

## Impact

**Affected specs (delta files under `specs/`)**

| Capability | Delta | Change |
|---|---|---|
| `usage-accounting` (new) | `specs/usage-accounting/spec.md` | ADDED: usage record model, dispatch record model, transcript event store with retention, versioned pricing table, usage routes, hook-driven ingestion with spool, mismatch reporting |
| `observability` | `specs/observability/spec.md` | MODIFIED: Claude Code Session Tracing Hook parses the real transcript shape via adapters and emits generation observations with `usage_details`; middleware requirement annotated non-functional on SDK v4 |
| `agent-archetypes` | `specs/agent-archetypes/spec.md` | MODIFIED: `ResolvedArchetype` and the resolve endpoint response include `thinking`; `validator`/`supervisor`/`documenter` accepted by status reporting |
| `skill-workflow` | `specs/skill-workflow/spec.md` | MODIFIED: per-phase resolution records a dispatch ledger entry; dispatch payload forwards thinking to vendor flags; review dispatcher applies archetype model |
| `harness-engineering` | `specs/harness-engineering/spec.md` | MODIFIED: transcript mining extracts model, effort, agent id, thinking and cache tokens; sub-agent discovery; agent-metrics gains `--usage` |
| `agent-coordinator` | `specs/agent-coordinator/spec.md` | MODIFIED: HTTP API coverage lists `/usage/*`; database persistence lists the four new tables; watchdog retention job |

**Affected code**

- `skills/collect-transcripts/scripts/{normalize.py, sanitize_events.py, adapters/*.py, usage_collector.py (new)}`, `references/event-schema.md`, `SKILL.md`, tests + fixtures
- `skills/autopilot/scripts/{phase_agent.py, provider_dispatch.py}`, `skills/parallel-infrastructure/scripts/review_dispatcher.py`
- `skills/langfuse/scripts/langfuse_hook.py`, `references/stop-hook.md`
- `skills/agent-metrics/scripts/{query_metrics.py, generate_dashboard.py}`, `SKILL.md`
- `skills/session-bootstrap` hook wiring (`.claude/settings.json` Stop/SubagentStop/SessionEnd), `docs/cloud-session-hooks.md`
- `agent-coordinator/database/migrations/035_model_usage_ledger.sql`
- `agent-coordinator/src/{coordination_api.py, usage_ledger.py (new), pricing.py (new), watchdog.py}`, `agent-coordinator/pricing.yaml` (new), `scripts/report_status.py`, Dockerfile COPY + smoke list
- `agent-coordinator/evaluation/{metrics.py, backends/grok.py}`
- `apps/usage-viz/` (new)
- `openspec/changes/usage-stats-multi-model/` (archive), `openspec/changes/add-adaptive-model-router/design.md` (D12 amendment)

**Architecture layers**: Execution (hooks, adapters, dispatch flags), Coordination (ledger tables,
routes, retention), Governance (pricing versioning, retention policy, cost provenance).

**Rollback**: all changes are additive and gated by `USAGE_LEDGER_ENABLED` (hooks) and the
presence of `pricing.yaml` (pricing). Disabling the flag restores current behaviour; the
migration can stay applied with empty tables.
