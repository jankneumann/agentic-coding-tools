# Multi-Model Usage Statistics Dashboard

## Why

Anthropic, OpenAI, and Google expose token-consumption numbers only partially
in their own UIs, and never *across* vendors. This repo already runs many
vendor agents (Claude, Codex, Gemini — local and remote, per
`agent-coordinator/agents.yaml`) against shared work, so the question
"how many tokens / how much estimated cost did each vendor and model burn?"
has no single answer today. The community tool
[`phuryn/claude-usage`](https://github.com/phuryn/claude-usage) answers it for
Claude alone by parsing the JSONL transcripts Claude Code writes under
`~/.claude/projects/` into a local SQLite DB and serving a Chart.js dashboard.

Three consequences for this repo specifically:

1. **No fleet-wide cost visibility.** `vendor_health.py` tells you a vendor is
   *reachable*; nothing tells you what it *spent*. With multi-agent DAG
   execution dispatching work across vendors, per-vendor/per-model token spend
   is the missing operational metric.

2. **SQLite would be a redundant dependency here.** `claude-usage` reaches for
   SQLite because it assumes zero backing services. This repo already runs a
   Postgres-backed coordinator (`src/db_postgres.py`, numbered migrations under
   `agent-coordinator/database/migrations/`, FastAPI surface in
   `src/coordination_api.py`). A second embedded datastore would duplicate
   schema, migration, and query machinery that Postgres already provides — and
   would keep usage data trapped per-machine, defeating fleet aggregation.

3. **The frontend pattern already exists.** `apps/kanban-viz` is a
   React + TypeScript + Vite observability surface that reads the coordinator
   API over `Authorization: Bearer` with SSE + polling fallback
   (`src/hooks/useCoordinator.ts`). A usage dashboard is the same category of
   surface and should reuse that stack rather than invent a new one.

The vendors do **not** all expose usage "in similar ways", and the proposal is
honest about that (this is the "if available in similar ways" caveat from the
request):

| Vendor | Local source | Format | Feasibility |
|--------|-------------|--------|-------------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | JSONL transcript; `usage` per assistant msg | Direct — reference implementation |
| Codex CLI | `~/.codex/sessions/**/rollout-*.jsonl` | JSONL `token_count` events (since 2025-09) | Direct — same paradigm as Claude |
| Gemini CLI | `.gemini/telemetry.log` / OTEL collector | OpenTelemetry metric `gemini_cli.token.usage` | Conditional — telemetry is **opt-in**, different paradigm |
| Antigravity | undocumented | unknown | Research stub only — no stable local-log contract confirmed |

## What Changes

A new observability surface, `apps/usage-stats/`, backed by the existing
coordinator Postgres, fed by a session-end collector, with a vendor-adapter
core so adding a vendor is adding one file.

Decisions locked with the operator during discovery:
- **Fleet-wide aggregation** — records carry `principal` / `agent_id` / `host`
  so spend sums across machines and agents, not just one laptop.
- **Session-end hook collector** — ingestion piggybacks on the existing
  session lifecycle hooks (`skills/session-bootstrap`, cloud-session-hooks)
  rather than a manual command or a new daemon.
- **Full granularity** — project path and session id are persisted (no
  redaction) so the dashboard supports per-project drill-down.

Work is organized into scope-isolated packages:

- **WP-contracts** (`openspec/changes/.../contracts/`) — DB schema for the
  `usage_records` + `usage_ingest_state` tables, the `/usage/*` OpenAPI
  surface, and generated TS/Pydantic types. Coordination boundary for the
  parallel packages.
- **WP-migration** (`agent-coordinator/database/migrations/`) — `026_usage_stats.sql`:
  `usage_records` (normalized token/cost facts + fleet dimensions) and
  `usage_ingest_state` (per-file mtime/offset watermark for incremental scans).
- **WP-collector** (`apps/usage-stats/collector/`) — stdlib-only Python:
  normalized `UsageRecord` schema, per-vendor adapters
  (`claude.py`, `codex.py`, `gemini.py`, `antigravity.py` stub), a pricing
  table seeded from `agents.yaml` model lists, and an idempotent push to the
  coordinator over the existing API/DB layer keyed on `(vendor, session_id,
  record_hash)`.
- **WP-api** (`agent-coordinator/src/`) — `/usage/summary`, `/usage/daily`,
  `/usage/by-model`, `/usage/by-vendor` FastAPI routes behind the existing
  Bearer auth, plus an SSE `usage.recorded` event reusing `coordinator_notify`.
- **WP-frontend** (`apps/usage-stats/src/`) — React + TS + Vite app mirroring
  kanban-viz: `useUsage.ts` hook (SSE + polling fallback), Chart-based
  daily/weekly/all-time rollups, per-vendor and per-model filters with
  bookmarkable URL state.
- **WP-hook** (`skills/session-bootstrap/` + `.claude`/`.codex`/`.gemini` hook
  configs) — wire collector invocation into session-end so ingestion is
  automatic.
- **WP-integration** — merge packages, run the full suite, document at
  `docs/usage-stats/README.md`.

Phasing of vendor adapters (each is additive — core never changes):
Phase 1 Claude → Phase 2 Codex → Phase 3 Gemini (with opt-in telemetry setup)
→ Phase 4 Antigravity research stub.

## Selected Approach

**Approach 2: Coordinator-backed, vendor-adapter core, kanban-viz frontend**
(selected by the operator at Gate 1). No modifications were requested. The
remaining approaches are retained below for the design record. Detailed specs,
contracts, tasks, and the work-package DAG are generated against this approach.

## Approaches Considered

### Approach 1: Port `claude-usage` as-is — standalone SQLite + stdlib server

Lift the reference tool nearly verbatim: SQLite at `~/.claude/usage.db`, a
`http.server` dashboard, add Codex/Gemini parsers later.

- **Pros**: Fastest to a working Claude dashboard; zero backing-service
  dependency; fully offline; smallest blast radius (touches nothing in
  `agent-coordinator`).
- **Cons**: Adds a redundant datastore the repo's conventions discourage;
  data trapped per-machine — **cannot** do the fleet-wide aggregation the
  operator selected; diverges from the kanban-viz frontend convention; a second
  HTTP server to operate alongside the coordinator.
- **Effort**: S

### Approach 2: Coordinator-backed, vendor-adapter core, kanban-viz frontend — **Recommended**

Reuse Postgres via a new `026_usage_stats.sql` migration, push from a
stdlib collector through the existing API, expose `/usage/*` routes, and build
the dashboard on the kanban-viz React/Vite stack. Vendor adapters sit behind a
normalized `UsageRecord` so vendors are added one file at a time.

- **Pros**: No new datastore — reuses migrations/db/API the repo already has;
  enables the selected fleet-wide aggregation; frontend consistent with
  kanban-viz (SSE refresh for free); adapter seam keeps multi-vendor growth
  cheap; pricing seeded from the existing `agents.yaml` registry so vendor/model
  lists never drift.
- **Cons**: Collector now needs network + API key (SQLite was offline); larger
  surface area (migration + API + collector + frontend); couples a local-log
  tool to coordinator availability (mitigated by a local spool-and-retry on the
  collector side).
- **Effort**: L

### Approach 3: OpenTelemetry-native — route every vendor through an OTEL collector

Lean into the fact that Gemini already emits OTEL. Stand up an OTEL collector,
write shims that translate Claude/Codex JSONL into OTEL metrics, and store/query
via an OTEL backend (or Postgres exporter).

- **Pros**: One ingestion paradigm for all vendors; aligns with Gemini's native
  model; standards-based, future-proof for any OTEL-emitting tool.
- **Cons**: Heaviest operationally (new collector service + backend); forces
  Claude/Codex (simple file parses) through a metrics pipeline that adds no
  value for them; highest time-to-first-dashboard; over-engineered for a
  4-vendor scope.
- **Effort**: L

## Recommended Approach

**Approach 2.** It is the only option that satisfies the operator's locked
decisions (fleet-wide aggregation, kanban-viz frontend, Postgres reuse) without
adding a redundant datastore or an OTEL service. Approach 1 is rejected because
SQLite cannot aggregate across machines; Approach 3 is rejected as
over-engineered for four vendors where two are trivial file parses. Gemini's
OTEL data is handled by a single adapter (`gemini.py`) that reads
`.gemini/telemetry.log`, isolating the paradigm mismatch to one file rather
than imposing it on the whole pipeline.
