# Change: expose-coordinator-apis

## Why

The merge queue and feature registry services exist internally (`merge_queue.py`, `feature_registry.py`) but are not exposed through any external interface — MCP, HTTP, or CLI. This means `parallel-cleanup-feature` references non-existent `merge_queue.*` pseudo-APIs that produce 404 errors, and no agent can register features or coordinate merge ordering. Additionally, `coordination_bridge.py` probes stale endpoint variants (`/handoff/write`, `/handoffs/latest`) that don't match the actual API, generating spurious 404s during capability detection. Finally, the project lacks a CLI interface, which would be more token-efficient than MCP for frontier models that can parse `--help` output and structured JSON responses.

## What Changes

### Fix: Stale coordination_bridge.py endpoints
- Remove `/handoff/write` (singular) probe — only `/handoffs/write` exists
- Remove `/handoffs/latest` probe — only `POST /handoffs/read` exists
- Remove `/handoff/read` (singular) probe — only `/handoffs/read` exists
- Clean up `_HANDOFF_WRITE_ENDPOINTS` and `_HANDOFF_READ_ENDPOINTS` to single correct entries

### Add: Feature Registry MCP tools + HTTP endpoints
- `register_feature(feature_id, resource_claims, title, agent_id, branch_name, merge_priority, metadata)` — register a feature with resource claims
- `deregister_feature(feature_id, status)` — mark feature completed/cancelled
- `get_feature(feature_id)` — fetch single feature by ID
- `list_active_features()` — list all active features ordered by merge priority
- `analyze_feature_conflicts(candidate_feature_id, candidate_claims)` — detect resource overlaps with active features

### Add: Merge Queue MCP tools + HTTP endpoints
- `enqueue_merge(feature_id, pr_url)` — add feature to merge queue
- `get_merge_queue()` — list all queued features in priority order
- `get_next_merge()` — find the next READY feature to merge
- `run_pre_merge_checks(feature_id)` — validate feature is active, no conflicts, in queue
- `mark_merged(feature_id)` — deregister feature after successful merge
- `remove_from_merge_queue(feature_id)` — remove without merging

### Add: coordination-cli entry point
- New `coordination-cli` command with subcommands mirroring all coordinator capabilities
- Global `--json` flag for machine-readable output (default: human-readable tables)
- Detailed `--help` on every subcommand for token-efficient agent consumption
- Subcommand groups: `lock`, `work`, `handoff`, `memory`, `feature`, `merge-queue`, `health`, `guardrails`, `policy`, `audit`, `ports`, `approval`
- Reuses the same service layer as MCP and HTTP — no logic duplication

### Add: Bridge functions for new capabilities
- `try_register_feature(...)` and `try_deregister_feature(...)` in coordination_bridge.py
- `try_enqueue_merge(...)`, `try_pre_merge_checks(...)`, `try_mark_merged(...)` in coordination_bridge.py
- New capability flags: `CAN_FEATURE_REGISTRY`, `CAN_MERGE_QUEUE`

### Fix: parallel-cleanup-feature/SKILL.md
- Replace pseudo-code `merge_queue.enqueue()` with actual MCP tool `enqueue_merge` / HTTP `POST /merge-queue/enqueue`
- Replace `merge_queue.run_pre_merge_checks()` with `run_pre_merge_checks` tool / HTTP endpoint
- Replace `merge_queue.mark_merged()` with `mark_merged` tool / HTTP endpoint
- Replace `merge_queue.get_next_to_merge()` with `get_next_merge` tool / HTTP endpoint
- Add `register_feature` / `deregister_feature` references where appropriate

## Impact

### Affected Specs
- **agent-coordinator** — adds 11 new MCP tools, 11 new HTTP endpoints, 1 new CLI entry point
- **skill-workflow** — parallel-cleanup-feature skill updated to use real APIs
- **merge-pull-requests** — may benefit from merge queue integration

### Architecture Layers
- **Coordination** — primary: new tools/endpoints expose existing service layer
- **Execution** — skills updated to call real coordinator APIs
- **Trust** — new endpoints use existing auth + policy enforcement

### Code Touchpoints
- `agent-coordinator/src/coordination_mcp.py` — add 11 MCP tools
- `agent-coordinator/src/coordination_api.py` — add 11 HTTP endpoints
- `agent-coordinator/src/coordination_cli.py` — new file, CLI entry point
- `agent-coordinator/pyproject.toml` — add `coordination-cli` entry point
- `scripts/coordination_bridge.py` — fix stale endpoints, add 5 bridge functions, add 2 capability flags
- `skills/parallel-cleanup-feature/SKILL.md` — replace pseudo-code with real API calls
- `skills/parallel-plan-feature/scripts/check_coordinator.py` (and copies) — add new capability probes

### Rollback Plan
All additions are purely additive. The bridge fix removes stale endpoint variants but the multi-endpoint fallback pattern means existing callers already handle 404s gracefully. No rollback needed for additive MCP tools/HTTP endpoints.
