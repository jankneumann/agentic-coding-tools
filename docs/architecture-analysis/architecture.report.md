# Architecture Report

**agent-coordinator** — Multi-agent coordination MCP server

Generated: 2026-09-26T00:40:41+00:00  
Git SHA: `31b8a93dd9cdc41c9bf8c82d67ec096c0b4b39b0`

## System Overview

*Data sources: [architecture.graph.json](architecture.graph.json), [architecture.summary.json](architecture.summary.json), [python_analysis.json](python_analysis.json)*

This is a **Python MCP server** with 87 modules exposing **107 MCP endpoints** (94 tools, 11 resources, 2 prompts), backed by **35 Postgres tables**. The codebase contains 1286 functions (513 async) and 307 classes.

| Metric | Count |
|--------|-------|
| Total nodes | 2199 |
| Total edges | 1370 |
| Python modules | 87 |
| Functions | 1286 (513 async) |
| Classes | 307 |
| Mcp Endpoints | 107 |
| DB tables | 35 |
| Python nodes | 1680 |
| Sql nodes | 519 |

## Module Responsibility Map

*Data sources: [python_analysis.json](python_analysis.json), [architecture.graph.json](architecture.graph.json)*

| Module | Layer | Role | In / Out |
|--------|-------|------|----------|
| `agents_config` | Foundation | Load and validate ``agents.yaml``. | 26 / 12 |
| `approval` | Service | Parse a datetime value from various formats. | 14 / 2 |
| `assurance` | Service | — | 0 / 0 |
| `audit` | Foundation | Get the global audit service instance. | 56 / 6 |
| `audit_triage` | Service | Read the optional sidecar JSON, falling back to the module default. | 2 / 1 |
| `axi_output` | Service | Detect truncation precisely via the limit+1 fetch pattern. | 11 / 0 |
| `cloudflare_access` | Service | Add the Cloudflare Access middleware to ``app`` when enabled. | 2 / 0 |
| `code_search` | Foundation | Return whether semantic code search is explicitly enabled. | 11 / 4 |
| `code_search_authorization` | Service | Intersect caller narrowing with a server-owned grant or reject safely. | 5 / 0 |
| `code_search_runtime` | Foundation | Read the default-off gate without importing optional search packages. | 22 / 3 |
| `config` | Foundation | Resolve COORDINATOR_WORKDIR_ROOT — repo root when unset. | 80 / 3 |
| `coordination_api` | Entry | Expose the installed snapshot for request attribution and health. | 4 / 233 |
| `coordination_cli` | Service | Bridge async service calls to synchronous CLI. | 0 / 42 |
| `coordination_mcp` | Entry | Own direct-search resources in the same loop that serves MCP calls. | 0 / 171 |
| `db` | Foundation | Factory: returns the appropriate DatabaseClient based on config. | 53 / 5 |
| `db_postgres` | Service | Parse an ISO-8601 timestamp if `val` looks like one. | 2 / 1 |
| `discovery` | Service | Get the global discovery service instance. | 16 / 8 |
| `docker_manager` | Service | Return ``True`` if the ``colima`` binary is on PATH. | 0 / 0 |
| `event_bus` | Foundation | Classify event urgency based on type. | 15 / 0 |
| `event_stream` | Service | Return COORDINATOR_SSE_SIGNING_KEY, or None if unset. | 8 / 4 |
| `feature_flags` | Service | Convert a change-id into a canonical flag name. | 1 / 0 |
| `feature_registry` | Foundation | Get the global feature registry service instance. | 24 / 8 |
| `git_adapter` | Service | Raise InvalidRefNameError if ref_name does not match SPECULATIVE_REF_PATTERN. | 2 / 0 |
| `github_classifier` | Service | Provides: _load_classifier | 1 / 0 |
| `github_coordination` | Service | Get the global GitHub coordination service instance. | 0 / 4 |
| `github_openspec_fetcher` | Service | Extract the first H1 heading from proposal.md text. | 2 / 0 |
| `github_prs_api` | Service | Parse GITHUB_REPOS env var.  Returns None on validation error. | 3 / 1 |
| `guardrails` | Foundation | Reset cached metric instruments (for testing). | 13 / 10 |
| `handoffs` | Foundation | Get the global handoff service instance. | 11 / 9 |
| `help_service` | Foundation | Return a compact overview of all capability groups. | 15 / 0 |
| `http_proxy` | Service | Validate URL against SSRF allowlist. | 61 / 4 |
| `isolation_contract` | Service | Validate a present value and name its provenance on failure. | 4 / 0 |
| `issue_service` | Foundation | Render a PostgREST array literal for the ``cs`` (contains) operator. | 22 / 5 |
| `kanban_viz_files` | Service | Locate a change's directory whether it is active or archived. | 5 / 5 |
| `langfuse_middleware` | Service | Extract agent identity from the request API key. | 1 / 7 |
| `langfuse_tracing` | Service | Initialize the Langfuse client from configuration. | 7 / 2 |
| `locks` | Foundation | Lazy-init metric instruments. Returns None tuple when disabled. | 21 / 18 |
| `memory` | Foundation | Get the global memory service instance. | 11 / 8 |
| `merge_queue` | Foundation | Parse an ISO datetime string, returning None for empty/None. | 23 / 10 |
| `merge_train` | Foundation | Return the set of partition keys an entry belongs to. | 5 / 5 |
| `merge_train_service` | Service | Build a TrainEntry from a Feature's merge_queue metadata. | 13 / 11 |
| `merge_train_types` | Service | Return the set of lock-key namespaces a repo-relative path likely belongs to. | 5 / 0 |
| `merge_watcher` | Service | Provides: get_merge_watcher | 3 / 0 |
| `migrations` | Service | Return sorted list of (sequence_number, filename, path) for all migration files. | 5 / 2 |
| `model_routing` | Entry | Accept feedback without coupling callers to aggregation cadence. | 12 / 16 |
| `model_routing.api` | Foundation | Accept feedback without coupling callers to aggregation cadence. | 0 / 0 |
| `model_routing.catalog` | Service | Escape delimiters before interpolating a value into a DB filter string. | 0 / 0 |
| `model_routing.configured_catalog` | Service | — | 0 / 0 |
| `model_routing.exploration` | Service | Pick a candidate, exploiting by default and exploring within budget. | 0 / 0 |
| `model_routing.feedback` | Service | Reject non-finite or out-of-range feedback values before aggregation. | 0 / 0 |
| `model_routing.ledger` | Service | — | 0 / 0 |
| `model_routing.local_endpoints` | Service | Skip placeholder rows an endpoint has already moved past. | 0 / 0 |
| `model_routing.refresher` | Service | Mark still-available OpenRouter rows absent from this response unavailable. | 0 / 0 |
| `model_routing.resolver` | Service | Exact-join configured lanes to catalog candidates, then filter feasibility. | 0 / 0 |
| `model_routing.routing_policy` | Service | — | 0 / 0 |
| `network_policies` | Service | Get the global network policy service instance. | 2 / 4 |
| `notifications` | Service | Send an event notification. Returns True on success. | 3 / 6 |
| `notifications.base` | Service | Send an event notification. Returns True on success. | 0 / 0 |
| `notifications.gmail` | Service | Send an HTML email notification for the event. | 0 / 0 |
| `notifications.notifier` | Service | Register a notification channel. | 0 / 0 |
| `notifications.relay` | Service | Extract a notification token from an email subject line. | 0 / 0 |
| `notifications.telegram` | Service | Send an event notification as a Telegram message with Markdown formatting. | 0 / 0 |
| `notifications.templates` | Service | Escape a value for safe HTML embedding. | 0 / 0 |
| `notifications.webhook` | Service | POST JSON payload with event data to the webhook URL. | 0 / 0 |
| `openbao_identity` | Service | Refresh off the event loop until the server cancels this task. | 3 / 1 |
| `openspec_proposals_api` | Service | Return the repo root. | 4 / 7 |
| `openspec_sources` | Service | Parse OPENSPEC_SOURCES env var value into SourceDescriptors. | 5 / 1 |
| `policy_engine` | Foundation | Get the global policy engine based on configuration. | 24 / 22 |
| `policy_sync` | Service | Return the singleton PolicySyncService instance. | 0 / 0 |
| `port_allocator` | Service | Return the global ``PortAllocatorService`` singleton. | 9 / 1 |
| `profile_loader` | Service | Recursively merge *override* into a copy of *base*. | 3 / 0 |
| `profiles` | Foundation | Get the global profiles service instance. | 12 / 7 |
| `refresh_rpc_client` | Foundation | Shell out to ``affected_tests.py`` and parse the returned test list. | 6 / 0 |
| `risk_scorer` | Service | Get the global risk scorer instance. | 0 / 2 |
| `session_grants` | Service | Parse a datetime value from various formats. | 5 / 3 |
| `sse_log_redaction` | Service | Install the redaction filter on the named logger (idempotent). | 3 / 0 |
| `status` | Service | Generate an 8-character URL-safe token. | 4 / 0 |
| `sync_points` | Service | Return ``(clear, active_list)`` by reading the worktree registry. | 1 / 1 |
| `teams` | Service | Get the global crew manifest (lazy singleton). | 2 / 3 |
| `telemetry` | Foundation | Initialize OpenTelemetry providers based on environment configuration. | 21 / 0 |
| `trust_levels` | Service | — | 1 / 0 |
| `trust_resolution` | Foundation | Record a failed trust resolution; never masks the original fault. | 10 / 8 |
| `vendor_registry` | Foundation | Compatibility name for consumers that call configured entries lanes. | 3 / 7 |
| `watchdog` | Service | Read a positive interval without letting bad optional config disable watchdog. | 3 / 12 |
| `work_queue` | Foundation | Return a bounded label for queue metrics. | 20 / 36 |
| `worktrees_view` | Service | Default: parents[2] of this file = repo root. | 2 / 2 |

**Layers**: Entry = exposes MCP endpoints; Service = domain logic; Foundation = imported by 3+ modules (config, db, audit).

## Dependency Layers

*Data source: [python_analysis.json](python_analysis.json)*

```
┌─────────────────────────────────────────────────┐
│  ENTRY       coordination_api, coordination_mcp, model_routing│
│             ↓ imports ↓                          │
│  SERVICE     approval, assurance, audit_triage, axi_output│
│              cloudflare_access, code_search_authorization, coordination_cli, db_postgres│
│              discovery, docker_manager, event_stream, feature_flags│
│              git_adapter, github_classifier, github_coordination, github_openspec_fetcher│
│              github_prs_api, http_proxy, isolation_contract, kanban_viz_files│
│              langfuse_middleware, langfuse_tracing, merge_train_service, merge_train_types│
│              merge_watcher, migrations, model_routing.catalog, model_routing.configured_catalog│
│              model_routing.exploration, model_routing.feedback, model_routing.ledger, model_routing.local_endpoints│
│              model_routing.refresher, model_routing.resolver, model_routing.routing_policy, network_policies│
│              notifications, notifications.base, notifications.gmail, notifications.notifier│
│              notifications.relay, notifications.telegram, notifications.templates, notifications.webhook│
│              openbao_identity, openspec_proposals_api, openspec_sources, policy_sync│
│              port_allocator, profile_loader, risk_scorer, session_grants│
│              sse_log_redaction, status, sync_points, teams│
│              trust_levels, watchdog, worktrees_view│
│             ↓ imports ↓                          │
│  FOUNDATION  agents_config, audit, code_search, code_search_runtime, config, db, event_bus, feature_registry, guardrails, handoffs, help_service, issue_service, locks, memory, merge_queue, merge_train, model_routing.api, policy_engine, profiles, refresh_rpc_client, telemetry, trust_resolution, vendor_registry, work_queue│
└─────────────────────────────────────────────────┘
```

**Single points of failure** — changes to these modules ripple widely:

- `config` — imported by 24 modules
- `db` — imported by 24 modules
- `audit` — imported by 17 modules
- `agents_config` — imported by 9 modules
- `policy_engine` — imported by 6 modules
- `telemetry` — imported by 6 modules
- `feature_registry` — imported by 5 modules
- `code_search` — imported by 4 modules
- `event_bus` — imported by 4 modules
- `guardrails` — imported by 4 modules
- `profiles` — imported by 4 modules
- `code_search_runtime` — imported by 3 modules
- `handoffs` — imported by 3 modules
- `help_service` — imported by 3 modules
- `issue_service` — imported by 3 modules
- `locks` — imported by 3 modules
- `memory` — imported by 3 modules
- `merge_queue` — imported by 3 modules
- `merge_train` — imported by 3 modules
- `model_routing.api` — imported by 3 modules
- `refresh_rpc_client` — imported by 3 modules
- `trust_resolution` — imported by 3 modules
- `vendor_registry` — imported by 3 modules
- `work_queue` — imported by 3 modules

## Entry Points

*Data sources: [architecture.graph.json](architecture.graph.json), [python_analysis.json](python_analysis.json)*

### Resources (11)

| Endpoint | Description |
|----------|-------------|
| `audit://recent` | Recent audit log entries. |
| `features://active` | Active features in the registry with their resource claims and priorities. |
| `gen-eval://coverage` | Gen-eval scenario coverage summary by category. |
| `gen-eval://report` | Latest gen-eval report summary. |
| `guardrails://patterns` | Active guardrail patterns for destructive operation detection. |
| `handoffs://recent` | Recent handoff documents from agent sessions. |
| `locks://current` | All currently active file locks. |
| `memories://recent` | Recent episodic memories across all agents. |
| `merge-queue://pending` | Features queued for merge with their status and priority. |
| `profiles://current` | Current agent's profile and permissions. |
| `work://pending` | Tasks waiting to be claimed from the work queue. |

### Prompts (2)

| Endpoint | Description |
|----------|-------------|
| `coordinate_file_edit` | Template for safely editing a file with coordination. |
| `start_work_session` | Template for starting a coordinated work session. |

### Other (94)

| Endpoint | Description |
|----------|-------------|
| `/agents/dispatch-configs` | Get CLI dispatch configs for agents with cli sections. |
| `/agents/{agent_id}/kick` | Clear a stale agent's worktree-registry entry and mark session disconnected. |
| `/approvals/pending` | List pending approval requests. |
| `/approvals/request` | Submit a human-in-the-loop approval request. |
| `/approvals/{request_id}` | Check the status of an approval request. |
| `/approvals/{request_id}/decide` | Approve or deny an approval request. |
| `/archetypes/resolve_for_phase` | Resolve archetype + model + system_prompt for an autopilot phase. |
| `/audit` | Query audit trail entries. |
| `/discovery/agents` | Discover agents with optional capability/status filters. |
| `/discovery/cleanup` | Clean up stale agent sessions and release their locks. |
| `/discovery/heartbeat` | Send a heartbeat for an agent session. |
| `/discovery/register` | Register an agent session for discovery. |
| `/events/auth` | Mint a short-lived JWT for the SSE auth handshake. |
| `/events/work` | SSE stream of work-queue transitions and audit events. |
| `/features/active` | List all active features ordered by merge priority. |
| `/features/conflicts` | Analyze resource conflicts between a candidate and active features. |
| `/features/deregister` | Deregister a feature (mark completed/cancelled). |
| `/features/register` | Register a feature with resource claims. |
| `/features/{feature_id}` | Get details of a specific feature. |
| `/gen-eval/create` | Generate a scaffold scenario YAML from a description. |
| `/gen-eval/run` | Run gen-eval testing against the coordinator's interfaces. |
| `/gen-eval/scenarios` | List gen-eval scenarios, optionally filtered by category or interface. |
| `/gen-eval/validate` | Validate a gen-eval scenario YAML document. |
| `/github/prs` | List open pull requests across configured repos. |
| `/guardrails/check` | Check an operation for destructive patterns. |
| `/handoffs/read` | Read previous handoff documents for session continuity. |
| `/handoffs/write` | Write a handoff document for session continuity. |
| `/health` | Human-facing health summary without affecting platform liveness. |
| `/help` | Compact overview of all coordinator capabilities. |
| `/help/{topic}` | Detailed help for a specific capability group. |
| `/issues/blocked` | List issues blocked by unresolved dependencies. Read-only, no auth. |
| `/issues/close` | Close one or more issues. |
| `/issues/comment` | Add a comment to an issue. |
| `/issues/create` | Create a new issue. |
| `/issues/list` | List issues with optional filters. |
| `/issues/ready` | List issues with no unresolved dependencies (ready to work on). |
| `/issues/search` | Search issues by text matching in title and description. |
| `/issues/update` | Update an issue. |
| `/issues/{issue_id}` | Get full issue details. |
| `/issues/{issue_id}/labels` | Add or remove labels on a work_queue row (drag-to-Ready interaction). |
| `/kanban-viz/audit` | Append a UI audit event (coordinator-owned, design D10). |
| `/kanban-viz/saved-views/{slug}` | Write a saved-view JSON file (coordinator-owned, design D10). |
| `/live` | Cheap liveness probe for container platforms. |
| `/locks` | List active locks held by the authenticated agent. |
| `/locks/acquire` | Acquire a file lock. Cloud agents call this before modifying files. |
| `/locks/release` | Release a file lock. |
| `/locks/release-by-agent` | Idempotently release active locks held by the authenticated agent. |
| `/locks/status/{path:path}` | Check lock status for a file. Read-only, no API key required. |
| `/locks/{path:path}` | Force-release a lock regardless of holder (destructive-write). |
| `/memory/query` | Query relevant memories for a task. |
| `/memory/store` | Store an episodic memory. |
| `/merge-queue` | Get all features in the merge queue. |
| `/merge-queue/check/{feature_id}` | Run pre-merge validation checks on a feature. |
| `/merge-queue/enqueue` | Add a feature to the merge queue. |
| `/merge-queue/merged/{feature_id}` | Mark a feature as merged and deregister it. |
| `/merge-queue/next` | Get the highest-priority feature ready to merge. |
| `/merge-queue/{feature_id}` | Remove a feature from the merge queue without merging. |
| `/merge-train/affected-tests` | Compute the test subset for a given set of changed files (R9). |
| `/merge-train/compose` | Compose a new speculative merge train from the current queue. |
| `/merge-train/eject` | Eject a feature from its current merge train. |
| `/merge-train/metrics` | Return aggregated merge throughput metrics from the audit log. |
| `/merge-train/report-result` | Record the result of speculative CI verification. |
| `/merge-train/status/{train_id}` | Return every entry currently belonging to ``train_id``. |
| `/notifications/status` | Get event bus and notification system status. |
| `/notifications/test` | Send a test notification through the event bus. |
| `/openspec/proposals` | List OpenSpec proposals (non-archive) with implementation state. |
| `/permissions/request` | Request a session-scoped permission grant. |
| `/policies/{policy_name}/rollback` | Rollback a Cedar policy to a previous version. |
| `/policies/{policy_name}/versions` | List version history for a Cedar policy. |
| `/policy/check` | Check if an operation is authorized by the policy engine. |
| `/policy/validate` | Validate Cedar policy text against the schema. |
| `/ports/allocate` | Allocate a block of ports for a session. |
| `/ports/release` | Release a port allocation for a session. |
| `/ports/status` | List all active port allocations. Read-only, no API key required. |
| `/profiles/me` | Get the calling agent's profile. |
| `/ready` | Readiness probe that verifies required dependencies. |
| `/routing/catalog` |  |
| `/routing/decisions/{decision_id}` |  |
| `/routing/feedback` |  |
| `/routing/select_model` |  |
| `/routing/usage` |  |
| `/search/code` |  |
| `/search/code/status` |  |
| `/status/report` | Accept status reports from agent hooks (Stop/SubagentStop). |
| `/sync-points/status` | Return the blocker state of the three sync-point skills. |
| `/vendors` |  |
| `/vendors/{agent_id}/availability` |  |
| `/vendors/{agent_id}/rate-limit-observations` |  |
| `/work/claim` | Claim a task from the work queue. |
| `/work/complete` | Mark a task as completed. |
| `/work/get` | Get a specific task by ID. |
| `/work/reconcile` |  |
| `/work/submit` | Submit new work to the queue. |
| `/worktrees/active` | Return active worktree entries from .git-worktrees/.registry.json. |

## Architecture Health

*Data source: [architecture.diagnostics.json](architecture.diagnostics.json)*

**3283 findings** across 5 categories:

### Orphan — 1467

1467 symbols are unreachable from any entrypoint — may be dead code or missing wiring.

- '__init__' is unreachable from any entrypoint or test
- 'agents_config' is unreachable from any entrypoint or test
- 'PollConfig' is unreachable from any entrypoint or test
- 'ModeConfig' is unreachable from any entrypoint or test
- 'CliConfig' is unreachable from any entrypoint or test
- ... and 1462 more

### Pattern Consistency — 9

9 unclassified findings.

- 'IF' uses PascalCase but most columns use snake_case
- 'IF' uses PascalCase but most columns use snake_case
- 'IF' uses PascalCase but most columns use snake_case
- 'IF' uses PascalCase but most columns use snake_case
- 'IF' uses PascalCase but most columns use snake_case
- ... and 4 more

### Reachability — 107

107 entrypoints have downstream dependencies but no DB writes or side effects.

Breakdown: 99 info, 8 warning.

- Entrypoint 'acquire_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'release_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'check_lock_status' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'list_locks_by_agent' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'release_locks_by_agent' has downstream dependencies but none touch a DB or produce side effects
- ... and 102 more

### Test Coverage — 1593

1593 functions lack test references — consider adding tests for critical paths.

- Function 'PollConfig' has no corresponding test references
- Function 'ModeConfig' has no corresponding test references
- Function 'CliConfig' has no corresponding test references
- Function 'SdkConfig' has no corresponding test references
- Function 'AgentEntry' has no corresponding test references
- ... and 1588 more

### Disconnected Flow (expected) — 107

107 MCP routes have no frontend callers — expected (clients are AI agents).

- Backend route 'acquire_lock' has no frontend callers
- Backend route 'release_lock' has no frontend callers
- Backend route 'check_lock_status' has no frontend callers
- Backend route 'list_locks_by_agent' has no frontend callers
- Backend route 'release_locks_by_agent' has no frontend callers
- ... and 102 more

## High-Impact Nodes

*Data sources: [high_impact_nodes.json](high_impact_nodes.json), [parallel_zones.json](parallel_zones.json)*

140 nodes with >= 5 transitive dependents. Changes to these ripple through the codebase — test thoroughly.

| Node | Dependents | Risk |
|------|------------|------|
| `config.get_config` | 188 | Critical — affects 188 downstream functions (32 modules affected) |
| `http_proxy._error_response` | 115 | Critical — affects 115 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy.get_client` | 115 | Critical — affects 115 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy._request` | 114 | Critical — affects 114 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy._agent_identity` | 68 | Critical — affects 68 downstream functions (modules: coordination_mcp, http_proxy) |
| `audit.get_audit_service` | 50 | Critical — affects 50 downstream functions (17 modules affected) |
| `policy_engine.get_policy_engine` | 48 | Critical — affects 48 downstream functions (6 modules affected) |
| `config` | 41 | Critical — affects 41 downstream functions (36 modules affected) |
| `teams.CrewManifest.validate` | 39 | Critical — affects 39 downstream functions (10 modules affected) |
| `db_postgres` | 36 | Critical — affects 36 downstream functions (31 modules affected) |
| `coordination_api.resolve_identity` | 35 | Critical — affects 35 downstream functions (modules: coordination_api) |
| `db` | 35 | Critical — affects 35 downstream functions (30 modules affected) |
| `coordination_api.authorize_operation` | 31 | Critical — affects 31 downstream functions (modules: coordination_api) |
| `db.create_db_client` | 31 | Critical — affects 31 downstream functions (26 modules affected) |
| `db.get_db` | 30 | Critical — affects 30 downstream functions (25 modules affected) |
| `profile_loader.interpolate` | 30 | Critical — affects 30 downstream functions (11 modules affected) |
| `coordination_cli._print_dict` | 29 | Critical — affects 29 downstream functions (modules: coordination_cli) |
| `profile_loader._load_secrets_file` | 29 | Critical — affects 29 downstream functions (11 modules affected) |
| `coordination_cli._output` | 28 | Critical — affects 28 downstream functions (modules: coordination_cli) |
| `audit` | 26 | Critical — affects 26 downstream functions (22 modules affected) |
| `audit_triage` | 26 | Critical — affects 26 downstream functions (22 modules affected) |
| `coordination_cli._run` | 26 | Critical — affects 26 downstream functions (modules: coordination_cli) |
| `agents_config._default_agents_path` | 25 | Critical — affects 25 downstream functions (10 modules affected) |
| `agents_config._default_secrets_path` | 25 | Critical — affects 25 downstream functions (10 modules affected) |
| `agents_config.load_agents_config._parse_mode` | 25 | Critical — affects 25 downstream functions (10 modules affected) |
| `agents_config.load_agents_config` | 24 | Critical — affects 24 downstream functions (10 modules affected) |
| `code_search_authorization` | 21 | Critical — affects 21 downstream functions (18 modules affected) |
| `code_search_authorization._is_normalized_relative` | 21 | Critical — affects 21 downstream functions (modules: code_search, code_search_authorization) |
| `code_search` | 20 | Critical — affects 20 downstream functions (17 modules affected) |
| `code_search_authorization.validate_safe_glob` | 20 | Critical — affects 20 downstream functions (modules: code_search, code_search_authorization) |
| ... | | 110 more |

## Code Health Indicators

*Data source: [python_analysis.json](python_analysis.json)*

### Quick Stats

| Indicator | Value |
|-----------|-------|
| Async ratio | 513/1286 (40%) |
| Docstring coverage | 828/1286 (64%) |
| Dead code candidates | 609 |

### Hot Functions

Functions called by the most other functions — changes here have wide blast radius:

| Function | Callers |
|----------|---------|
| `http_proxy._request` | 58 |
| `config.get_config` | 52 |
| `http_proxy.get_config` | 52 |
| `audit.get_audit_service` | 39 |
| `coordination_api.resolve_identity` | 35 |
| `http_proxy._agent_identity` | 34 |
| `coordination_api.authorize_operation` | 31 |
| `db.get_db` | 29 |
| `coordination_cli._run` | 26 |
| `git_adapter.SubprocessGitAdapter._run` | 26 |

### Dead Code Candidates

609 functions are unreachable from entrypoints via static analysis. Some may be used dynamically (e.g., classmethods, test helpers).

- **agents_config** (10): `mutations`, `get_mcp_env`, `reset_agents_config`, `get_agent_isolation`, `reset_archetypes_config`, `resolve_provider_model`, ... (+4)
- **approval** (8): `db`, `submit_request`, `check_request`, `decide_request`, `expire_stale_requests`, `list_pending`, ... (+2)
- **audit** (7): `from_dict`, `db`, `log_operation`, `drain`, `_insert_audit_entry`, `query`, ... (+1)
- **audit_triage** (5): `push`, `drain_all`, `load_prompt`, `drain_and_classify`, `reset_triage_buffer`
- **cloudflare_access** (4): `_signing_key`, `verify`, `_is_exempt`, `_deny`
- **code_search** (14): `validate_main_key`, `validate_patterns`, `validate_reference`, `validate_languages`, `validate_paths`, `require_non_main_index`, ... (+8)
- **code_search_authorization** (4): `allow_path_regexes`, `deny_path_regexes`, `path_regexes`, `allows`
- **code_search_runtime** (18): `validate_truth_table`, `clear`, `embed_one`, `state_counts`, `status_snapshot`, `status`, ... (+12)
- **config** (5): `is_enabled`, `create_client`, `from_env`, `from_env`, `reset_config`
- **coordination_api** (10): `validate_reset_and_scope`, `optional_api_key`, `create_coordination_api`, `lifespan`, `code_search_problem_handler`, `projection_problem_handler`, ... (+4)
- **coordination_cli** (28): `cmd_health`, `cmd_feature_register`, `cmd_feature_deregister`, `cmd_feature_show`, `cmd_feature_list`, `cmd_feature_conflicts`, ... (+22)
- **coordination_mcp** (65): `_mcp_lifespan`, `select_model_for_task`, `acquire_lock`, `release_lock`, `check_locks`, `get_work`, ... (+59)
- **db** (17): `rpc`, `query`, `insert`, `update`, `delete`, `close`, ... (+11)
- **db_postgres** (9): `_encode_jsonb_param`, `_register_jsonb_codecs`, `_get_pool`, `rpc`, `query`, `insert`, ... (+3)
- **discovery** (5): `db`, `register`, `discover`, `heartbeat`, `cleanup_dead_agents`
- **docker_manager** (2): `start_container`, `wait_for_healthy`
- **event_bus** (14): `to_json`, `running`, `failed`, `on_event`, `off_event`, `start`, ... (+8)
- **event_stream** (3): `mint_events_token`, `_on_task_event`, `_on_audit_event`
- **feature_flags** (15): `is_enabled`, `to_yaml_dict`, `load`, `_load_unlocked`, `_get_registry`, `resolve_flag`, ... (+9)
- **feature_registry** (6): `db`, `register`, `deregister`, `get_feature`, `get_active_features`, `analyze_conflicts`
- **git_adapter** (11): `create_speculative_ref`, `delete_speculative_refs`, `fast_forward_main`, `get_changed_files`, `list_speculative_refs`, `_ensure_git_version`, ... (+5)
- **github_classifier** (1): `_load_classifier`
- **github_coordination** (9): `from_dict`, `db`, `parse_lock_labels`, `parse_branch`, `sync_label_locks`, `sync_branch_tracking`, ... (+3)
- **guardrails** (5): `reset_guardrail_instruments`, `from_dict`, `db`, `_load_patterns`, `check_operation`
- **handoffs** (4): `db`, `write`, `read`, `get_recent`
- **help_service** (1): `_register`
- **http_proxy** (2): `proxy_list_locks_by_agent`, `proxy_release_locks_by_agent`
- **isolation_contract** (1): `configured_isolation_value`
- **issue_service** (12): `db`, `create`, `list_issues`, `show`, `update`, `close`, ... (+6)
- **kanban_viz_files** (2): `_change_dir`, `_load_schema`
- **langfuse_middleware** (1): `dispatch`
- **langfuse_tracing** (4): `create_span`, `end_span`, `trace_operation`, `reset_langfuse`
- **locks** (9): `is_valid_lock_key`, `db`, `acquire`, `release`, `check`, `release_by_agent`, ... (+3)
- **memory** (3): `db`, `remember`, `recall`
- **merge_queue** (8): `db`, `registry`, `enqueue`, `get_queue`, `get_next_to_merge`, `run_pre_merge_checks`, ... (+2)
- **merge_train** (6): `validate_post_speculation_claims`, `reset_blocked_entry`, `reset_abandoned_entry`, `execute_wave_merge`, `cleanup_orphaned_speculative_refs`, `gc_aged_speculative_refs`
- **merge_train_service** (20): `db`, `registry`, `git_adapter`, `refresh_client`, `_load_entries`, `_save_entry`, ... (+14)
- **merge_train_types** (5): `is_terminal`, `to_metadata_dict`, `all_passed`, `all_entries`, `total_entry_count`
- **merge_watcher** (4): `start`, `stop`, `_loop`, `_tick`
- **model_routing** (53): `validate_unique_lists`, `list_candidates`, `list_entries`, `record_decision`, `record_decision_and_audit`, `get_decision`, ... (+47)
- **network_policies** (2): `db`, `check_domain`
- **notifications** (38): `send`, `test`, `supports_reply`, `send`, `test`, `supports_reply`, ... (+32)
- **openbao_identity** (11): `ensure_session`, `read_agent_key`, `reader_factory`, `state`, `usable`, `identity_status`, ... (+5)
- **openspec_sources** (1): `warm_local_sources`
- **policy_engine** (25): `db`, `check_operation`, `_do_check_operation`, `check_network_access`, `list_policy_versions`, `rollback_policy`, ... (+19)
- **policy_sync** (13): `start`, `stop`, `on_policy_change`, `running`, `on_policy_change`, `start`, ... (+7)
- **port_allocator** (6): `env_snippet`, `allocate`, `release`, `status`, `_cleanup_expired`, `reset_port_allocator`
- **profile_loader** (2): `resolve_dynamic_dsn`, `_replace`
- **profiles** (6): `from_dict`, `db`, `invalidate_cache`, `get_profile`, `check_operation`, `_log_denial`
- **refresh_rpc_client** (4): `is_graph_stale`, `trigger_refresh`, `get_refresh_status`, `_invoke`
- **risk_scorer** (10): `db`, `compute_score`, `get_violation_count`, `_trust_factor`, `_operation_factor`, `_resource_factor`, ... (+4)
- **session_grants** (7): `db`, `request_grant`, `get_active_grants`, `has_grant`, `revoke_grants`, `_row_to_grant`, ... (+1)
- **sse_log_redaction** (3): `filter`, `_scrub`, `redact_token`
- **status** (1): `cleanup_expired_tokens`
- **sync_points** (1): `get_sync_points_status`
- **teams** (8): `can_claim`, `from_dict`, `get_role`, `vendors_for`, `validate_against`, `_claimability_errors`, ... (+2)
- **telemetry** (4): `set_attribute`, `set_status`, `record_exception`, `reset_telemetry`
- **vendor_registry** (22): `db`, `agents`, `_agent`, `list_vendors`, `list_lanes`, `get_vendor`, ... (+16)
- **watchdog** (23): `db`, `vendor_registry`, `running`, `start`, `stop`, `run_once`, ... (+17)
- **work_queue** (12): `as_input_data`, `db`, `_resolve_trust_level`, `claim`, `complete`, `submit`, ... (+6)

## Parallel Modification Zones

*Data source: [parallel_zones.json](parallel_zones.json)*

**1369 independent groups** identified. The largest interconnected group has 617 modules; 1715 modules are leaf nodes (safe to modify in isolation).

**54 high-impact modules** act as coupling points — parallel changes touching these need coordination.

### Interconnected Groups

**Group 0** (617 members spanning 59 modules): `agents_config`, `approval`, `audit`, `audit_triage`, `axi_output`, `cloudflare_access`, `code_search`, `code_search_runtime`
  ... and 51 more modules

**Group 1** (66 members spanning 60 modules): `agents_config`, `approval`, `audit`, `audit_triage`, `axi_output`, `cloudflare_access`, `code_search`, `code_search_authorization`
  ... and 52 more modules

**Group 2** (35 members spanning 2 modules): `code_search`, `code_search_authorization`

**Group 3** (18 members spanning 3 modules): `merge_train`, `merge_train_service`, `merge_train_types`

**Group 4** (14 members spanning 1 modules): `notifications`

**Group 5** (12 members spanning 1 modules): `db_postgres`

**Group 6** (9 members spanning 1 modules): `code_search_runtime`

**Group 7** (9 members spanning 1 modules): `model_routing`

**Group 8** (9 members spanning 1 modules): `vendor_registry`

**Group 9** (6 members spanning 1 modules): `docker_manager`

### Leaf Modules (1715)

1715 modules have no dependents — changes are fully isolated. 1333 of the 1369 groups are singletons.

## Architecture Diagrams

*Data source: [architecture.graph.json](architecture.graph.json)*

### Container View

```mermaid
flowchart TB
    Backend["Backend (1680 nodes)"]
    Database["Database (519 nodes)"]
```

### Backend Components

```mermaid
flowchart TB
    __init__["__init__ (1 symbols)"]
    agents_config["agents_config (67 symbols)"]
    approval["approval (14 symbols)"]
    assurance["assurance (1 symbols)"]
    audit["audit (18 symbols)"]
    audit_triage["audit_triage (14 symbols)"]
    axi_output["axi_output (4 symbols)"]
    cloudflare_access["cloudflare_access (12 symbols)"]
    code_search["code_search (37 symbols)"]
    code_search_authorization["code_search_authorization (40 symbols)"]
    code_search_runtime["code_search_runtime (45 symbols)"]
    config["config (45 symbols)"]
    coordination_api["coordination_api (168 symbols)"]
    coordination_cli["coordination_cli (35 symbols)"]
    coordination_mcp["coordination_mcp (82 symbols)"]
    db["db (23 symbols)"]
    db_postgres["db_postgres (20 symbols)"]
    discovery["discovery (20 symbols)"]
    docker_manager["docker_manager (8 symbols)"]
    event_bus["event_bus (22 symbols)"]
    event_stream["event_stream (13 symbols)"]
    feature_flags["feature_flags (26 symbols)"]
    feature_registry["feature_registry (19 symbols)"]
    git_adapter["git_adapter (25 symbols)"]
    github_classifier["github_classifier (2 symbols)"]
    github_coordination["github_coordination (16 symbols)"]
    github_openspec_fetcher["github_openspec_fetcher (10 symbols)"]
    github_prs_api["github_prs_api (8 symbols)"]
    guardrails["guardrails (16 symbols)"]
    handoffs["handoffs (14 symbols)"]
    help_service["help_service (6 symbols)"]
    http_proxy["http_proxy (73 symbols)"]
    isolation_contract["isolation_contract (6 symbols)"]
    issue_service["issue_service (27 symbols)"]
    kanban_viz_files["kanban_viz_files (11 symbols)"]
    langfuse_middleware["langfuse_middleware (5 symbols)"]
    langfuse_tracing["langfuse_tracing (10 symbols)"]
    locks["locks (20 symbols)"]
    memory["memory (13 symbols)"]
    merge_queue["merge_queue (17 symbols)"]
    merge_train["merge_train (30 symbols)"]
    merge_train_service["merge_train_service (29 symbols)"]
    merge_train_types["merge_train_types (14 symbols)"]
    merge_watcher["merge_watcher (8 symbols)"]
    migrations["migrations (7 symbols)"]
    model_routing____init__["model_routing.__init__ (1 symbols)"]
    model_routing__api["model_routing.api (54 symbols)"]
    model_routing__catalog["model_routing.catalog (22 symbols)"]
    model_routing__configured_catalog["model_routing.configured_catalog (6 symbols)"]
    model_routing__exploration["model_routing.exploration (5 symbols)"]
    model_routing__feedback["model_routing.feedback (8 symbols)"]
    model_routing__ledger["model_routing.ledger (13 symbols)"]
    model_routing__local_endpoints["model_routing.local_endpoints (11 symbols)"]
    model_routing__refresher["model_routing.refresher (9 symbols)"]
    model_routing__resolver["model_routing.resolver (18 symbols)"]
    model_routing__routing_policy["model_routing.routing_policy (19 symbols)"]
    network_policies["network_policies (8 symbols)"]
    notifications____init__["notifications.__init__ (1 symbols)"]
    notifications__base["notifications.base (10 symbols)"]
    notifications__gmail["notifications.gmail (13 symbols)"]
    notifications__notifier["notifications.notifier (14 symbols)"]
    notifications__relay["notifications.relay (6 symbols)"]
    notifications__telegram["notifications.telegram (11 symbols)"]
    notifications__templates["notifications.templates (11 symbols)"]
    notifications__webhook["notifications.webhook (8 symbols)"]
    openbao_identity["openbao_identity (20 symbols)"]
    openspec_proposals_api["openspec_proposals_api (16 symbols)"]
    openspec_sources["openspec_sources (10 symbols)"]
    policy_engine["policy_engine (36 symbols)"]
    policy_sync["policy_sync (17 symbols)"]
    port_allocator["port_allocator (12 symbols)"]
    profile_loader["profile_loader (14 symbols)"]
    profiles["profiles (15 symbols)"]
    refresh_rpc_client["refresh_rpc_client (12 symbols)"]
    risk_scorer["risk_scorer (14 symbols)"]
    session_grants["session_grants (13 symbols)"]
    sse_log_redaction["sse_log_redaction (6 symbols)"]
    status["status (6 symbols)"]
    sync_points["sync_points (5 symbols)"]
    teams["teams (14 symbols)"]
    telemetry["telemetry (20 symbols)"]
    trust_levels["trust_levels (2 symbols)"]
    trust_resolution["trust_resolution (5 symbols)"]
    vendor_registry["vendor_registry (30 symbols)"]
    watchdog["watchdog (28 symbols)"]
    work_queue["work_queue (32 symbols)"]
    worktrees_view["worktrees_view (4 symbols)"]
    agents_config -->|"call"| audit
    agents_config -->|"call"| config
    agents_config -->|"call"| db
    agents_config -->|"call"| isolation_contract
    agents_config -->|"call, import"| model_routing__api
    agents_config -->|"call"| profile_loader
    agents_config -->|"call"| profiles
    agents_config -->|"call"| teams
    approval -->|"call, import"| db
    audit -->|"call, import"| audit_triage
    audit -->|"call, import"| config
    audit -->|"call, import"| db
    audit_triage -->|"import"| audit
    code_search -->|"call, import"| code_search_authorization
    code_search_runtime -->|"call, import"| code_search
    code_search_runtime -->|"import"| code_search_authorization
    config -->|"call"| agents_config
    config -->|"call"| code_search_runtime
    config -->|"call"| profile_loader
    coordination_api -->|"call, import"| agents_config
    coordination_api -->|"call, import"| approval
    coordination_api -->|"call, import"| audit
    coordination_api -->|"call, import"| axi_output
    coordination_api -->|"call, import"| cloudflare_access
    coordination_api -->|"call, import"| code_search
    coordination_api -->|"call, import"| code_search_runtime
    coordination_api -->|"call, import"| config
    coordination_api -->|"call, import"| db
    coordination_api -->|"call, import"| discovery
    coordination_api -->|"call, import"| event_bus
    coordination_api -->|"call, import"| event_stream
    coordination_api -->|"call, import"| feature_registry
    coordination_api -->|"call, import"| github_prs_api
    coordination_api -->|"call, import"| guardrails
    coordination_api -->|"call, import"| handoffs
    coordination_api -->|"call, import"| help_service
    coordination_api -->|"call, import"| issue_service
    coordination_api -->|"call, import"| kanban_viz_files
    coordination_api -->|"import"| langfuse_middleware
    coordination_api -->|"call, import"| langfuse_tracing
    coordination_api -->|"call, import"| locks
    coordination_api -->|"call, import"| memory
    coordination_api -->|"call, import"| merge_queue
    coordination_api -->|"import"| merge_train
    coordination_api -->|"call, import"| merge_train_service
    coordination_api -->|"call, import"| merge_watcher
    coordination_api -->|"call, import"| migrations
    coordination_api -->|"call, import"| model_routing__api
    coordination_api -->|"call, import"| notifications__notifier
    coordination_api -->|"call, import"| openbao_identity
    coordination_api -->|"call, import"| openspec_proposals_api
    coordination_api -->|"call, import"| policy_engine
    coordination_api -->|"call, import"| port_allocator
    coordination_api -->|"call, import"| profiles
    coordination_api -->|"call, import"| refresh_rpc_client
    coordination_api -->|"call, import"| session_grants
    coordination_api -->|"call, import"| sse_log_redaction
    coordination_api -->|"import"| sync_points
    coordination_api -->|"call, import"| telemetry
    coordination_api -->|"call, import"| trust_resolution
    coordination_api -->|"import"| vendor_registry
    coordination_api -->|"call, import"| watchdog
    coordination_api -->|"call, import"| work_queue
    coordination_api -->|"import"| worktrees_view
    coordination_cli -->|"call, import"| audit
    coordination_cli -->|"import"| axi_output
    coordination_cli -->|"call, import"| config
    coordination_cli -->|"call, import"| db
    coordination_cli -->|"call, import"| feature_registry
    coordination_cli -->|"call, import"| guardrails
    coordination_cli -->|"call, import"| handoffs
    coordination_cli -->|"call, import"| help_service
    coordination_cli -->|"call, import"| locks
    coordination_cli -->|"call, import"| memory
    coordination_cli -->|"call, import"| merge_queue
    coordination_cli -->|"call, import"| work_queue
    coordination_mcp -->|"call, import"| agents_config
    coordination_mcp -->|"call, import"| approval
    coordination_mcp -->|"call, import"| audit
    coordination_mcp -->|"import"| code_search
    coordination_mcp -->|"call, import"| code_search_runtime
    coordination_mcp -->|"call, import"| config
    coordination_mcp -->|"call, import"| discovery
    coordination_mcp -->|"call, import"| event_bus
    coordination_mcp -->|"call, import"| feature_registry
    coordination_mcp -->|"call, import"| guardrails
    coordination_mcp -->|"call, import"| handoffs
    coordination_mcp -->|"call, import"| help_service
    coordination_mcp -->|"call"| http_proxy
    coordination_mcp -->|"call, import"| issue_service
    coordination_mcp -->|"call, import"| locks
    coordination_mcp -->|"call, import"| memory
    coordination_mcp -->|"call, import"| merge_queue
    coordination_mcp -->|"import"| merge_train
    coordination_mcp -->|"call, import"| merge_train_service
    coordination_mcp -->|"call, import"| migrations
    coordination_mcp -->|"call, import"| model_routing__api
    coordination_mcp -->|"call, import"| policy_engine
    coordination_mcp -->|"call, import"| port_allocator
    coordination_mcp -->|"call, import"| profiles
    coordination_mcp -->|"call, import"| refresh_rpc_client
    coordination_mcp -->|"call, import"| session_grants
    coordination_mcp -->|"call, import"| telemetry
    coordination_mcp -->|"call, import"| work_queue
    db -->|"call, import"| config
    db -->|"call, import"| db_postgres
    db_postgres -->|"import"| config
    discovery -->|"call, import"| audit
    discovery -->|"call, import"| config
    discovery -->|"call, import"| db
    event_stream -->|"call"| coordination_api
    event_stream -->|"import"| event_bus
    event_stream -->|"import"| issue_service
    event_stream -->|"import"| worktrees_view
    feature_registry -->|"call, import"| audit
    feature_registry -->|"call, import"| config
    feature_registry -->|"call, import"| db
    feature_registry -->|"call"| discovery
    github_coordination -->|"call, import"| config
    github_coordination -->|"call, import"| db
    github_prs_api -->|"import"| github_classifier
    guardrails -->|"call, import"| audit
    guardrails -->|"call, import"| config
    guardrails -->|"call, import"| db
    guardrails -->|"call, import"| telemetry
    handoffs -->|"call, import"| audit
    handoffs -->|"call, import"| config
    handoffs -->|"call, import"| db
    handoffs -->|"call, import"| policy_engine
    http_proxy -->|"import"| code_search
    http_proxy -->|"call, import"| code_search_runtime
    http_proxy -->|"call"| config
    issue_service -->|"call, import"| config
    issue_service -->|"call, import"| db
    issue_service -->|"call"| discovery
    kanban_viz_files -->|"call, import"| config
    langfuse_middleware -->|"call, import"| config
    langfuse_middleware -->|"call, import"| coordination_api
    langfuse_middleware -->|"call, import"| langfuse_tracing
    langfuse_tracing -->|"call, import"| config
    locks -->|"call"| approval
    locks -->|"call, import"| audit
    locks -->|"call, import"| config
    locks -->|"call, import"| db
    locks -->|"call, import"| policy_engine
    locks -->|"call, import"| telemetry
    memory -->|"call, import"| audit
    memory -->|"call, import"| config
    memory -->|"call, import"| db
    memory -->|"call, import"| policy_engine
    merge_queue -->|"call"| approval
    merge_queue -->|"call, import"| audit
    merge_queue -->|"call, import"| db
    merge_queue -->|"call"| feature_flags
    merge_queue -->|"call, import"| feature_registry
    merge_train -->|"import"| git_adapter
    merge_train -->|"call, import"| merge_train_types
    merge_train_service -->|"call"| approval
    merge_train_service -->|"call, import"| db
    merge_train_service -->|"call, import"| feature_registry
    merge_train_service -->|"import"| git_adapter
    merge_train_service -->|"call, import"| merge_train
    merge_train_service -->|"import"| merge_train_types
    merge_train_service -->|"import"| refresh_rpc_client
    migrations -->|"call, import"| config
    model_routing__api -->|"call, import"| audit
    model_routing__api -->|"import"| http_proxy
    model_routing__api -->|"call"| model_routing__catalog
    model_routing__api -->|"call"| model_routing__exploration
    model_routing__api -->|"call"| model_routing__ledger
    model_routing__api -->|"call"| model_routing__resolver
    model_routing__api -->|"call"| model_routing__routing_policy
    model_routing__api -->|"import"| vendor_registry
    model_routing__catalog -->|"call, import"| db
    model_routing__configured_catalog -->|"call, import"| agents_config
    model_routing__configured_catalog -->|"call"| model_routing__catalog
    model_routing__ledger -->|"call, import"| db
    model_routing__ledger -->|"call"| model_routing__catalog
    model_routing__local_endpoints -->|"call, import"| agents_config
    model_routing__resolver -->|"call"| isolation_contract
    model_routing__routing_policy -->|"call, import"| agents_config
    network_policies -->|"call, import"| config
    network_policies -->|"call, import"| db
    notifications__gmail -->|"call"| db
    notifications__gmail -->|"call"| notifications__relay
    notifications__gmail -->|"call"| notifications__templates
    notifications__gmail -->|"call"| status
    notifications__notifier -->|"call"| notifications__templates
    openbao_identity -->|"import"| agents_config
    openspec_proposals_api -->|"call"| github_openspec_fetcher
    openspec_proposals_api -->|"call"| openspec_sources
    openspec_sources -->|"call"| openspec_proposals_api
    policy_engine -->|"call, import"| audit
    policy_engine -->|"call, import"| config
    policy_engine -->|"call, import"| db
    policy_engine -->|"call, import"| network_policies
    policy_engine -->|"call, import"| profiles
    policy_engine -->|"call, import"| telemetry
    policy_engine -->|"import"| trust_levels
    policy_engine -->|"call, import"| trust_resolution
    port_allocator -->|"import"| config
    profiles -->|"call, import"| audit
    profiles -->|"call, import"| config
    profiles -->|"call, import"| db
    risk_scorer -->|"call, import"| db
    session_grants -->|"call"| approval
    session_grants -->|"call, import"| db
    sync_points -->|"call"| code_search_runtime
    teams -->|"call"| agents_config
    trust_resolution -->|"call, import"| agents_config
    trust_resolution -->|"call, import"| audit
    trust_resolution -->|"call, import"| config
    trust_resolution -->|"call, import"| profiles
    vendor_registry -->|"call, import"| agents_config
    vendor_registry -->|"call, import"| db
    vendor_registry -->|"call, import"| isolation_contract
    watchdog -->|"call, import"| audit
    watchdog -->|"call, import"| db
    watchdog -->|"call, import"| event_bus
    watchdog -->|"import"| model_routing__catalog
    watchdog -->|"import"| model_routing__configured_catalog
    watchdog -->|"import"| model_routing__ledger
    watchdog -->|"import"| model_routing__local_endpoints
    watchdog -->|"import"| model_routing__refresher
    watchdog -->|"import"| vendor_registry
    work_queue -->|"call, import"| agents_config
    work_queue -->|"call, import"| audit
    work_queue -->|"call, import"| config
    work_queue -->|"call, import"| db
    work_queue -->|"call"| discovery
    work_queue -->|"call, import"| guardrails
    work_queue -->|"call"| locks
    work_queue -->|"call, import"| policy_engine
    work_queue -->|"call, import"| telemetry
    work_queue -->|"call, import"| trust_resolution
    worktrees_view -->|"call"| approval
    worktrees_view -->|"call"| code_search_runtime
```

### Frontend Components

```mermaid
flowchart TB
    empty["No TypeScript nodes found"]
```

### Database ERD

```mermaid
erDiagram
    public__agent_profile_assignments {
        TEXT agent_id
        TIMESTAMPTZ assigned_at
        TEXT assigned_by
        UUID id
        UUID profile_id
    }
    public__agent_profiles {
        NOT_EXISTS_synced_from_registry_at_TIMESTAMPTZ IF
        TEXT agent_type
        TEXT__ allowed_operations
        TEXT__ blocked_operations
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        INT max_api_calls_per_hour
        INT max_execution_time_seconds
        INT max_file_modifications
        JSONB metadata
        TEXT name
        JSONB network_policy
        INT trust_level
        TIMESTAMPTZ updated_at
    }
    public__agent_sessions {
        NOT_EXISTS_delegated_from_TEXT IF
        TEXT agent_id
        TEXT agent_type
        TEXT__ capabilities
        TEXT current_task
        TIMESTAMPTZ ended_at
        TEXT__ files_modified
        TEXT id
        TIMESTAMPTZ last_heartbeat
        JSONB metadata
        TIMESTAMPTZ started_at
        TEXT status
        TEXT task_description
        INTEGER tasks_completed
    }
    public__approval_queue {
        TEXT agent_id
        TEXT agent_type
        JSONB context
        TIMESTAMPTZ created_at
        TIMESTAMPTZ decided_at
        TEXT decided_by
        TIMESTAMPTZ expires_at
        UUID id
        TEXT operation
        TEXT reason
        TEXT resource
        TEXT status
    }
    public__audit_log {
        NOT_EXISTS_delegated_from_TEXT IF
        TEXT agent_id
        TEXT agent_type
        TIMESTAMPTZ created_at
        INT duration_ms
        TEXT error_message
        UUID id
        TEXT operation
        JSONB parameters
        JSONB result
        BOOLEAN success
    }
    public__cedar_entities {
        JSONB attributes
        TIMESTAMPTZ created_at
        TEXT entity_id
        TEXT entity_type
        UUID id
        JSONB parents
        TIMESTAMPTZ updated_at
    }
    public__cedar_policies {
        NOT_EXISTS_policy_version_INTEGER IF
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        TEXT name
        TEXT policy_text
        INTEGER priority
        TIMESTAMPTZ updated_at
    }
    public__cedar_policies_history {
        TEXT change_type
        TIMESTAMPTZ changed_at
        TEXT changed_by
        UUID id
        UUID policy_id
        TEXT policy_name
        TEXT policy_text
        INTEGER version
    }
    public__changesets {
        TEXT agent_id
        TEXT branch_name
        JSONB changed_files
        TEXT commit_sha
        TIMESTAMPTZ created_at
        TEXT description
        UUID id
        TEXT session_id
        TEXT status
        TIMESTAMPTZ updated_at
    }
    public__code_search_index_file_attempts {
        INTEGER attempt_count
        INTEGER chunk_count
        TEXT chunk_digest
        TEXT content_digest
        TEXT eligibility_reason
        BOOLEAN eligible
        TEXT file_path
        TEXT git_blob_id
        TEXT git_entry_type
        UUID index_id
    }
    public__code_search_index_files {
        INTEGER chunk_count
        TEXT chunk_digest
        TEXT content_digest
        TEXT eligibility_reason
        BOOLEAN eligible
        TEXT file_path
        TEXT git_blob_id
        TEXT git_entry_type
        UUID index_id
    }
    public__code_search_indexes {
        code_search_indexes_natural_key CONSTRAINT
        NOT_EXISTS_policy_fingerprint_TEXT IF
        INTEGER attempt_count
        INTEGER chunk_count
        TIMESTAMPTZ completed_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ deleted_at
        TEXT embedder_model
        INTEGER embedding_dim
        UUID index_id
        TEXT last_error
        TIMESTAMPTZ lease_expires_at
        TEXT lease_owner
        UUID lease_token
        TEXT namespace_key
        TEXT namespace_kind
        TEXT repo_slug
        TIMESTAMPTZ retention_until
        TEXT source_revision
        TIMESTAMPTZ started_at
        TEXT status
        TEXT storage_key
        TIMESTAMPTZ updated_at
    }
    public__code_search_registry {
        NOT_EXISTS_canonical_index_id_UUID IF
        INTEGER chunk_count
        TIMESTAMPTZ created_at
        TEXT embedder_model
        INTEGER embedding_dim
        TEXT last_indexed_commit
        TEXT repo_root
        TEXT repo_slug
        TIMESTAMPTZ updated_at
    }
    public__feature_registry {
        TEXT branch_name
        TIMESTAMPTZ completed_at
        TEXT feature_id
        INTEGER merge_priority
        JSONB metadata
        TIMESTAMPTZ registered_at
        TEXT registered_by
        TEXT__ resource_claims
        TEXT status
        TEXT title
        TIMESTAMPTZ updated_at
    }
    public__file_locks {
        TEXT agent_type
        TIMESTAMPTZ expires_at
        TEXT file_path
        TIMESTAMPTZ locked_at
        TEXT locked_by
        JSONB metadata
        TEXT reason
        TEXT session_id
    }
    public__guardrail_violations {
        TEXT agent_id
        TEXT agent_type
        BOOLEAN blocked
        TEXT category
        JSONB context
        TIMESTAMPTZ created_at
        UUID id
        TEXT matched_text
        TEXT operation_text
        TEXT pattern_name
        INT trust_level
    }
    public__handoff_documents {
        NOT_EXISTS_supervisor_record_JSONB IF
        TEXT agent_name
        JSONB completed_work
        TIMESTAMPTZ created_at
        JSONB decisions
        UUID id
        JSONB in_progress
        JSONB next_steps
        JSONB relevant_files
        TEXT session_id
        TEXT summary
    }
    public__issue_comments {
        TEXT author
        TEXT body
        TIMESTAMPTZ created_at
        UUID id
        UUID issue_id
    }
    public__memory_episodic {
        TEXT agent_id
        TIMESTAMPTZ created_at
        JSONB details
        TEXT event_type
        UUID id
        TEXT__ lessons
        TEXT outcome
        FLOAT relevance_score
        TEXT session_id
        TEXT summary
        TEXT__ tags
    }
    public__model_catalog {
        BOOLEAN available
        TEXT base_url
        JSONB benchmark_priors
        NUMERIC_12_6_ completion_usd_per_mtok
        INTEGER context_window
        TEXT endpoint_kind
        BIGSERIAL id
        TEXT model
        NUMERIC_10_2_ p50_latency_ms
        NUMERIC_12_6_ prompt_usd_per_mtok
        NUMERIC_5_2_ quota_headroom_pct
        TIMESTAMPTZ quota_reset_at
        TEXT quota_source
        TIMESTAMPTZ refreshed_at
        BOOLEAN stale
        TEXT vendor
    }
    public__model_posteriors {
        BIGINT catalog_id
        INTEGER half_life_days
        BIGSERIAL id
        BOOLEAN low_confidence
        TEXT metric
        DOUBLE_PRECISION sample_size
        TEXT task_type
        TIMESTAMPTZ updated_at
        DOUBLE_PRECISION value
    }
    public__network_access_log {
        TEXT agent_id
        BOOLEAN allowed
        TIMESTAMPTZ created_at
        TEXT domain
        UUID id
        UUID policy_id
        TEXT reason
    }
    public__network_policies {
        TEXT action
        TIMESTAMPTZ created_at
        TEXT description
        TEXT domain_pattern
        BOOLEAN enabled
        UUID id
        INT priority
        UUID profile_id
    }
    public__notification_tokens {
        TEXT change_id
        TIMESTAMPTZ created_at
        TEXT entity_id
        TEXT event_type
        TIMESTAMPTZ expires_at
        TEXT token
        TIMESTAMPTZ used_at
    }
    public__operation_guardrails {
        TEXT category
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        INT min_trust_level
        TEXT name
        TEXT pattern
        TEXT severity
    }
    public__routing_decisions {
        JSONB alternatives
        JSONB budget_state
        TIMESTAMPTZ created_at
        UUID decision_id
        JSONB excluded
        BOOLEAN exploration
        BOOLEAN fallback
        TEXT outcome_ref
        TEXT policy_version
        JSONB request
        JSONB selected
    }
    public__routing_spend_ledger {
        NUMERIC_12_6_ actual_usd
        BIGINT completion_tokens
        NUMERIC_12_6_ counterfactual_usd
        UUID decision_id
        TEXT endpoint_kind
        BOOLEAN exploration
        TEXT generation_id
        BIGSERIAL id
        TEXT model
        TIMESTAMPTZ occurred_at
        BIGINT prompt_tokens
        BOOLEAN tokens_estimated
        TEXT vendor
        TEXT work_unit_ref
    }
    public__session_permission_grants {
        TEXT agent_id
        TEXT approved_by
        TIMESTAMPTZ expires_at
        TIMESTAMPTZ granted_at
        UUID id
        TEXT justification
        TEXT operation
        TEXT session_id
    }
    public__vendor_probe_state {
        TEXT agent_id
        JSONB metadata
        TEXT observation_id
        TIMESTAMPTZ observed_at
        TEXT reason
        TEXT source_agent_id
        TIMESTAMPTZ stale_after
        TEXT status
    }
    public__vendor_rate_limits {
        TEXT agent_id
        JSONB metadata
        TEXT model
        TEXT observation_id
        TIMESTAMPTZ observed_at
        TEXT payload_hash
        TEXT reason
        TIMESTAMPTZ reset_at
        TEXT scope
        TEXT source_agent_id
    }
    public__verification_policies {
        JSONB config
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        verification_executor executor
        TEXT file_pattern
        UUID id
        TEXT name
        INT priority
        verification_tier tier
    }
    public__verification_results {
        UUID changeset_id
        TIMESTAMPTZ completed_at
        TIMESTAMPTZ created_at
        INT duration_ms
        TEXT error_message
        verification_executor executor
        UUID id
        JSONB result
        TIMESTAMPTZ started_at
        verification_status status
        verification_tier tier
    }
    public__work_queue {
        NOT_EXISTS_labels_TEXT__ IF
        INTEGER attempt_count
        TIMESTAMPTZ claimed_at
        TEXT claimed_by
        TIMESTAMPTZ completed_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ deadline
        UUID__ depends_on
        TEXT description
        TEXT error_message
        UUID id
        JSONB input_data
        INTEGER max_attempts
        INTEGER priority
        JSONB result
        TIMESTAMPTZ started_at
        TEXT status
        TEXT task_type
    }
    public__work_queue_projection_heads {
        TEXT change_id
        TEXT phase
        INTEGER transition_sequence
        TIMESTAMPTZ updated_at
    }
    public__work_queue_projection_ownership {
        TIMESTAMPTZ created_at
        UUID task_id
    }
```
