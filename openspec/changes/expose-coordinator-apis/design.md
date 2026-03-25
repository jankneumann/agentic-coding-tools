# Design: expose-coordinator-apis

## Context

The coordinator has 27 MCP tools and 24 HTTP endpoints, all following a consistent pattern: `@mcp.tool()` async functions delegating to service singletons (MCP), and `@app.post()` / `@app.get()` handlers with Pydantic models and auth middleware (HTTP). Two internal services — `MergeQueueService` (6 methods) and `FeatureRegistryService` (5 methods) — exist with full unit tests but no external interface. The `coordination_bridge.py` HTTP bridge probes stale endpoint variants. Skills reference these services via pseudo-code.

## Goals / Non-Goals

**Goals:**
- Expose merge queue and feature registry through all 3 interfaces (MCP, HTTP, CLI)
- Fix stale bridge endpoint probes
- Update parallel-cleanup-feature to use real APIs
- Introduce CLI as a token-efficient 3rd interface

**Non-Goals:**
- Changing merge queue or feature registry business logic
- Adding new database migrations (services already use existing tables/RPC functions)
- Replacing MCP with CLI (CLI is complementary)
- Exposing CLI as a subprocess from within skills (skills use MCP or HTTP directly)

## Decisions

### D1: CLI framework — argparse (stdlib)

Use `argparse` with subparsers for the CLI. No new dependency needed.

**Rationale:** The CLI targets AI agents, not humans with tab-completion needs. `argparse` provides `--help` generation, subcommand grouping, and is already available. `click` is a dependency (via typer/fastmcp) but adds no value over argparse for this use case.

### D2: CLI shares async service layer via `asyncio.run()`

Each CLI subcommand wraps the async service call in `asyncio.run()`. This reuses the exact same service singletons as MCP and HTTP.

```
CLI main() → argparse → subcommand handler → asyncio.run(service.method()) → print(json or table)
```

**Rationale:** Avoids duplicating any business logic. The service layer is already fully async; `asyncio.run()` is the standard stdlib bridge.

### D3: MCP tool naming — verb_noun pattern matching existing tools

New MCP tools follow the existing naming convention:
- `register_feature`, `deregister_feature`, `get_feature`, `list_active_features`, `analyze_feature_conflicts`
- `enqueue_merge`, `get_merge_queue`, `get_next_merge`, `run_pre_merge_checks`, `mark_merged`, `remove_from_merge_queue`

### D4: HTTP endpoint paths — resource-oriented REST

```
POST /features/register
POST /features/deregister
GET  /features/{feature_id}
GET  /features/active
POST /features/conflicts

POST /merge-queue/enqueue
GET  /merge-queue
GET  /merge-queue/next
POST /merge-queue/check/{feature_id}
POST /merge-queue/merged/{feature_id}
DELETE /merge-queue/{feature_id}
```

### D5: Bridge capability flags — 2 new flags

Add `CAN_FEATURE_REGISTRY` and `CAN_MERGE_QUEUE` to both `check_coordinator.py` and `coordination_bridge.py`. Probed via:
- `CAN_FEATURE_REGISTRY` → `GET /features/active`
- `CAN_MERGE_QUEUE` → `GET /merge-queue`

### D6: CLI output modes — `--json` flag

Default output: human-readable table/text. `--json` flag: JSON to stdout. Error messages always to stderr.

```bash
# Human
coordination-cli feature list
# → feature_id  title              status  priority
# → feat-123    Add auth           active  1

# Machine
coordination-cli --json feature list
# → [{"feature_id": "feat-123", "title": "Add auth", ...}]
```

## Alternatives Considered

### A1: Expose CLI via `click` or `typer`
Rejected — adds unnecessary abstraction. `argparse` subparsers provide the same structure with zero new deps. AI agents benefit from `--help` text, not rich terminal UIs.

### A2: Auto-generate MCP/HTTP from a single schema
Rejected — the existing codebase uses hand-written tools/endpoints with per-endpoint auth and policy decisions. A code generator would obscure these security-critical decisions.

### A3: Expose merge queue via work queue primitives
Rejected — merge queue has different semantics (priority ordering, pre-merge checks, conflict re-validation) that don't map cleanly to generic work queue task types.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| CLI adds maintenance surface | Low | CLI is a thin wrapper; service logic unchanged |
| New endpoints increase attack surface | Low | Same auth + policy middleware as existing endpoints |
| Bridge capability detection adds latency | Negligible | 2 new GET probes (~2ms each), parallel with existing |
| Stale bridge fix breaks existing callers | None | Callers already handle 404 gracefully via fallback chain |

## Migration Plan

1. **Phase 1** — Fix bridge (no breaking changes, callers already resilient)
2. **Phase 2** — Add MCP tools + HTTP endpoints (purely additive)
3. **Phase 3** — Add CLI entry point (new file, new pyproject.toml entry)
4. **Phase 4** — Update bridge + check_coordinator with new capability flags
5. **Phase 5** — Update parallel-cleanup-feature skill
6. **Rollback** — Revert the commit; all changes are additive
