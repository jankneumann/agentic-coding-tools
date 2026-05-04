# Architecture Report

Generated: 2026-05-04T01:52:13.494735+00:00  
Git SHA: `c9749ccc6c9243d3b6873770388beedb67554a7b`

## System Overview

*Data sources: [architecture.graph.json](architecture.graph.json), [architecture.summary.json](architecture.summary.json), [python_analysis.json](python_analysis.json)*

This is a **Python MCP server** with 54 modules exposing **82 MCP endpoints** (69 tools, 11 resources, 2 prompts), backed by **24 Postgres tables**. The codebase contains 827 functions (369 async) and 184 classes.

| Metric | Count |
|--------|-------|
| Total nodes | 1471 |
| Total edges | 901 |
| Python modules | 54 |
| Functions | 827 (369 async) |
| Classes | 184 |
| Mcp Endpoints | 82 |
| DB tables | 24 |
| Python nodes | 1117 |
| Sql nodes | 354 |

## Module Responsibility Map

*Data sources: [python_analysis.json](python_analysis.json), [architecture.graph.json](architecture.graph.json)*

| Module | Layer | Role | In / Out |
|--------|-------|------|----------|
| `agents_config` | Foundation | Load and validate ``agents.yaml``. | 8 / 4 |
| `approval` | Service | Parse a datetime value from various formats. | 13 / 2 |
| `assurance` | Service | — | 0 / 0 |
| `audit` | Foundation | Get the global audit service instance. | 38 / 4 |
| `config` | Foundation | Get the global configuration instance. | 66 / 2 |
| `coordination_api` | Entry | Verify the API key for write operations. | 0 / 141 |
| `coordination_cli` | Service | Bridge async service calls to synchronous CLI. | 0 / 40 |
| `coordination_mcp` | Entry | Get the current agent ID from config. | 0 / 157 |
| `db` | Foundation | Factory: returns the appropriate DatabaseClient based on config. | 43 / 4 |
| `db_postgres` | Service | Coerce a PostgREST filter string value to the appropriate Python type. | 1 / 1 |
| `discovery` | Service | Get the global discovery service instance. | 16 / 8 |
| `docker_manager` | Service | Return ``True`` if the ``colima`` binary is on PATH. | 0 / 0 |
| `event_bus` | Foundation | Classify event urgency based on type. | 13 / 0 |
| `feature_flags` | Service | Convert a change-id into a canonical flag name. | 1 / 0 |
| `feature_registry` | Foundation | Get the global feature registry service instance. | 24 / 8 |
| `git_adapter` | Service | Raise InvalidRefNameError if ref_name does not match SPECULATIVE_REF_PATTERN. | 2 / 0 |
| `github_coordination` | Service | Get the global GitHub coordination service instance. | 0 / 4 |
| `guardrails` | Foundation | Reset cached metric instruments (for testing). | 12 / 10 |
| `handoffs` | Foundation | Get the global handoff service instance. | 11 / 9 |
| `help_service` | Foundation | Return a compact overview of all capability groups. | 15 / 0 |
| `http_proxy` | Service | Validate URL against SSRF allowlist. | 56 / 1 |
| `issue_service` | Service | Get the global issue service instance. | 21 / 5 |
| `langfuse_middleware` | Service | Extract agent identity from the request API key. | 1 / 4 |
| `langfuse_tracing` | Service | Initialize the Langfuse client from configuration. | 7 / 2 |
| `locks` | Foundation | Lazy-init metric instruments. Returns None tuple when disabled. | 17 / 16 |
| `memory` | Foundation | Get the global memory service instance. | 11 / 8 |
| `merge_queue` | Foundation | Parse an ISO datetime string, returning None for empty/None. | 23 / 10 |
| `merge_train` | Foundation | Return the set of partition keys an entry belongs to. | 5 / 5 |
| `merge_train_service` | Service | Build a TrainEntry from a Feature's merge_queue metadata. | 13 / 11 |
| `merge_train_types` | Service | Return the set of lock-key namespaces a repo-relative path likely belongs to. | 5 / 0 |
| `migrations` | Service | Return sorted list of (sequence_number, filename, path) for all migration files. | 5 / 2 |
| `network_policies` | Service | Get the global network policy service instance. | 2 / 4 |
| `notifications` | Service | Send an event notification. Returns True on success. | 3 / 6 |
| `notifications.base` | Service | Send an event notification. Returns True on success. | 0 / 0 |
| `notifications.gmail` | Service | Send an HTML email notification for the event. | 0 / 0 |
| `notifications.notifier` | Service | Register a notification channel. | 0 / 0 |
| `notifications.relay` | Service | Extract a notification token from an email subject line. | 0 / 0 |
| `notifications.telegram` | Service | Send an event notification as a Telegram message with Markdown formatting. | 0 / 0 |
| `notifications.templates` | Service | Escape a value for safe HTML embedding. | 0 / 0 |
| `notifications.webhook` | Service | POST JSON payload with event data to the webhook URL. | 0 / 0 |
| `policy_engine` | Foundation | Get the global policy engine based on configuration. | 23 / 19 |
| `policy_sync` | Service | Return the singleton PolicySyncService instance. | 0 / 0 |
| `port_allocator` | Service | Return the global ``PortAllocatorService`` singleton. | 9 / 1 |
| `profile_loader` | Service | Recursively merge *override* into a copy of *base*. | 3 / 0 |
| `profiles` | Foundation | Get the global profiles service instance. | 12 / 7 |
| `refresh_rpc_client` | Foundation | Shell out to ``affected_tests.py`` and parse the returned test list. | 6 / 0 |
| `risk_scorer` | Service | Get the global risk scorer instance. | 0 / 2 |
| `session_grants` | Service | Parse a datetime value from various formats. | 5 / 3 |
| `status` | Service | Generate an 8-character URL-safe token. | 4 / 0 |
| `teams` | Service | Get the global teams configuration. | 2 / 0 |
| `telemetry` | Foundation | Initialize OpenTelemetry providers based on environment configuration. | 21 / 0 |
| `watchdog` | Service | Return the singleton WatchdogService. | 3 / 4 |
| `work_queue` | Foundation | Get the global work queue service instance. | 17 / 33 |

**Layers**: Entry = exposes MCP endpoints; Service = domain logic; Foundation = imported by 3+ modules (config, db, audit).

## Dependency Layers

*Data source: [python_analysis.json](python_analysis.json)*

```
┌─────────────────────────────────────────────────┐
│  ENTRY       coordination_api, coordination_mcp  │
│             ↓ imports ↓                          │
│  SERVICE     approval, assurance, coordination_cli, db_postgres│
│              discovery, docker_manager, feature_flags, git_adapter│
│              github_coordination, http_proxy, issue_service, langfuse_middleware│
│              langfuse_tracing, merge_train_service, merge_train_types, migrations│
│              network_policies, notifications, notifications.base, notifications.gmail│
│              notifications.notifier, notifications.relay, notifications.telegram, notifications.templates│
│              notifications.webhook, policy_sync, port_allocator, profile_loader│
│              risk_scorer, session_grants, status, teams│
│              watchdog                            │
│             ↓ imports ↓                          │
│  FOUNDATION  agents_config, audit, config, db, event_bus, feature_registry, guardrails, handoffs, help_service, locks, memory, merge_queue, merge_train, policy_engine, profiles, refresh_rpc_client, telemetry, work_queue│
└─────────────────────────────────────────────────┘
```

**Single points of failure** — changes to these modules ripple widely:

- `config` — imported by 22 modules
- `db` — imported by 20 modules
- `audit` — imported by 13 modules
- `policy_engine` — imported by 6 modules
- `telemetry` — imported by 6 modules
- `feature_registry` — imported by 5 modules
- `guardrails` — imported by 4 modules
- `profiles` — imported by 4 modules
- `refresh_rpc_client` — imported by 3 modules
- `merge_queue` — imported by 3 modules
- `agents_config` — imported by 3 modules
- `locks` — imported by 3 modules
- `memory` — imported by 3 modules
- `event_bus` — imported by 3 modules
- `merge_train` — imported by 3 modules
- `handoffs` — imported by 3 modules
- `work_queue` — imported by 3 modules
- `help_service` — imported by 3 modules

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

### Other (69)

| Endpoint | Description |
|----------|-------------|
| `/agents/dispatch-configs` | Get CLI dispatch configs for agents with cli sections. |
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
| `/features/active` | List all active features ordered by merge priority. |
| `/features/conflicts` | Analyze resource conflicts between a candidate and active features. |
| `/features/deregister` | Deregister a feature (mark completed/cancelled). |
| `/features/register` | Register a feature with resource claims. |
| `/features/{feature_id}` | Get details of a specific feature. |
| `/gen-eval/create` | Generate a scaffold scenario YAML from a description. |
| `/gen-eval/run` | Run gen-eval testing against the coordinator's interfaces. |
| `/gen-eval/scenarios` | List gen-eval scenarios, optionally filtered by category or interface. |
| `/gen-eval/validate` | Validate a gen-eval scenario YAML document. |
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
| `/live` | Cheap liveness probe for container platforms. |
| `/locks/acquire` | Acquire a file lock. Cloud agents call this before modifying files. |
| `/locks/release` | Release a file lock. |
| `/locks/status/{file_path:path}` | Check lock status for a file. Read-only, no API key required. |
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
| `/merge-train/report-result` | Record the result of speculative CI verification. |
| `/merge-train/status/{train_id}` | Return every entry currently belonging to ``train_id``. |
| `/notifications/status` | Get event bus and notification system status. |
| `/notifications/test` | Send a test notification through the event bus. |
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
| `/status/report` | Accept status reports from agent hooks (Stop/SubagentStop). |
| `/work/claim` | Claim a task from the work queue. |
| `/work/complete` | Mark a task as completed. |
| `/work/get` | Get a specific task by ID. |
| `/work/submit` | Submit new work to the queue. |

## Architecture Health

*Data source: [architecture.diagnostics.json](architecture.diagnostics.json)*

**2123 findings** across 5 categories:

### Orphan — 946

946 symbols are unreachable from any entrypoint — may be dead code or missing wiring.

- '__init__' is unreachable from any entrypoint or test
- 'agents_config' is unreachable from any entrypoint or test
- 'approval' is unreachable from any entrypoint or test
- 'assurance' is unreachable from any entrypoint or test
- 'audit' is unreachable from any entrypoint or test
- ... and 941 more

### Pattern Consistency — 2

2 unclassified findings.

- 'IF' uses PascalCase but most columns use snake_case
- 'IF' uses PascalCase but most columns use snake_case

### Reachability — 82

82 entrypoints have downstream dependencies but no DB writes or side effects.

Breakdown: 76 info, 6 warning.

- Entrypoint 'acquire_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'release_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'check_lock_status' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'store_memory' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'query_memories' has downstream dependencies but none touch a DB or produce side effects
- ... and 77 more

### Test Coverage — 1011

1011 functions lack test references — consider adding tests for critical paths.

- Function 'PollConfig' has no corresponding test references
- Function 'ModeConfig' has no corresponding test references
- Function 'CliConfig' has no corresponding test references
- Function 'SdkConfig' has no corresponding test references
- Function 'AgentEntry' has no corresponding test references
- ... and 1006 more

### Disconnected Flow (expected) — 82

82 MCP routes have no frontend callers — expected for an MCP server (clients are AI agents, not browsers).

- Backend route 'notifications_status' has no frontend callers
- Backend route 'discovery_heartbeat' has no frontend callers
- Backend route 'list_pending_approvals' has no frontend callers
- Backend route 'get_merge_queue_endpoint' has no frontend callers
- Backend route 'check_approval_endpoint' has no frontend callers
- ... and 77 more

## High-Impact Nodes

*Data sources: [high_impact_nodes.json](high_impact_nodes.json), [parallel_zones.json](parallel_zones.json)*

64 nodes with >= 5 transitive dependents. Changes to these ripple through the codebase — test thoroughly.

| Node | Dependents | Risk |
|------|------------|------|
| `config.get_config` | 171 | Critical — affects 171 downstream functions (28 modules affected) |
| `http_proxy.get_client` | 107 | Critical — affects 107 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy._error_response` | 107 | Critical — affects 107 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy._request` | 106 | Critical — affects 106 downstream functions (modules: coordination_mcp, http_proxy) |
| `http_proxy._agent_identity` | 72 | Critical — affects 72 downstream functions (modules: coordination_mcp, http_proxy) |
| `policy_engine.get_policy_engine` | 43 | Critical — affects 43 downstream functions (6 modules affected) |
| `coordination_api.resolve_identity` | 30 | Critical — affects 30 downstream functions (modules: coordination_api) |
| `config` | 28 | Critical — affects 28 downstream functions (28 modules affected) |
| `coordination_api.authorize_operation` | 27 | Critical — affects 27 downstream functions (modules: coordination_api) |
| `coordination_cli._print_dict` | 27 | Critical — affects 27 downstream functions (modules: coordination_cli) |
| `coordination_cli._output` | 26 | Critical — affects 26 downstream functions (modules: coordination_cli) |
| `audit.get_audit_service` | 25 | Critical — affects 25 downstream functions (13 modules affected) |
| `coordination_cli._run` | 25 | Critical — affects 25 downstream functions (modules: coordination_cli) |
| `db.create_db_client` | 24 | Critical — affects 24 downstream functions (22 modules affected) |
| `db_postgres` | 23 | Critical — affects 23 downstream functions (23 modules affected) |
| `db.get_db` | 23 | Critical — affects 23 downstream functions (21 modules affected) |
| `db` | 22 | Critical — affects 22 downstream functions (22 modules affected) |
| `merge_queue.get_merge_queue_service` | 20 | Critical — affects 20 downstream functions (modules: coordination_api, coordination_cli, coordination_mcp) |
| `feature_registry.get_feature_registry_service` | 19 | High — test `feature_registry` changes thoroughly (5 modules affected) |
| `issue_service.get_issue_service` | 19 | High — test `issue_service` changes thoroughly (modules: coordination_api, coordination_mcp) |
| `profile_loader.interpolate` | 17 | High — test `profile_loader` changes thoroughly (6 modules affected) |
| `profile_loader._load_secrets_file` | 16 | High — test `profile_loader` changes thoroughly (6 modules affected) |
| `teams.TeamsConfig.validate` | 16 | High — test `teams` changes thoroughly (6 modules affected) |
| `audit` | 14 | High — test `audit` changes thoroughly (14 modules affected) |
| `work_queue.get_work_queue_service` | 14 | High — test `work_queue` changes thoroughly (modules: coordination_api, coordination_cli, coordination_mcp) |
| `profiles.get_profiles_service` | 13 | High — test `profiles` changes thoroughly (modules: coordination_api, coordination_mcp, policy_engine, work_queue) |
| `agents_config._default_agents_path` | 12 | High — test `agents_config` changes thoroughly (5 modules affected) |
| `agents_config._default_secrets_path` | 12 | High — test `agents_config` changes thoroughly (5 modules affected) |
| `agents_config.load_agents_config._parse_mode` | 12 | High — test `agents_config` changes thoroughly (5 modules affected) |
| `agents_config.load_agents_config` | 11 | High — test `agents_config` changes thoroughly (5 modules affected) |
| ... | | 34 more |

## Code Health Indicators

*Data source: [python_analysis.json](python_analysis.json)*

### Quick Stats

| Indicator | Value |
|-----------|-------|
| Async ratio | 369/827 (45%) |
| Docstring coverage | 639/827 (77%) |
| Dead code candidates | 425 |

### Hot Functions

Functions called by the most other functions — changes here have wide blast radius:

| Function | Callers |
|----------|---------|
| `http_proxy._request` | 53 |
| `config.get_config` | 44 |
| `http_proxy.get_config` | 44 |
| `http_proxy._agent_identity` | 36 |
| `coordination_api.resolve_identity` | 30 |
| `coordination_api.authorize_operation` | 27 |
| `coordination_cli._output` | 26 |
| `audit.get_audit_service` | 25 |
| `coordination_cli._run` | 25 |
| `git_adapter.SubprocessGitAdapter._run` | 25 |

### Dead Code Candidates

425 functions are unreachable from entrypoints via static analysis. Some may be used dynamically (e.g., classmethods, test helpers).

- **agents_config** (7): `get_mcp_env`, `reset_agents_config`, `get_agent_isolation`, `get_phase_mapping`, `reset_archetypes_config`, `compose_prompt`, ... (+1)
- **approval** (8): `db`, `submit_request`, `check_request`, `decide_request`, `expire_stale_requests`, `list_pending`, ... (+2)
- **audit** (6): `from_dict`, `db`, `log_operation`, `_insert_audit_entry`, `query`, `timed`
- **config** (5): `is_enabled`, `create_client`, `from_env`, `from_env`, `reset_config`
- **coordination_api** (4): `verify_api_key`, `create_coordination_api`, `lifespan`, `main`
- **coordination_cli** (27): `cmd_health`, `cmd_feature_register`, `cmd_feature_deregister`, `cmd_feature_show`, `cmd_feature_list`, `cmd_feature_conflicts`, ... (+21)
- **coordination_mcp** (60): `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`, ... (+54)
- **db** (17): `rpc`, `query`, `insert`, `update`, `delete`, `close`, ... (+11)
- **db_postgres** (7): `_get_pool`, `rpc`, `query`, `insert`, `update`, `delete`, ... (+1)
- **discovery** (5): `db`, `register`, `discover`, `heartbeat`, `cleanup_dead_agents`
- **docker_manager** (2): `start_container`, `wait_for_healthy`
- **event_bus** (13): `to_json`, `running`, `failed`, `on_event`, `start`, `stop`, ... (+7)
- **feature_flags** (15): `is_enabled`, `to_yaml_dict`, `load`, `_load_unlocked`, `_get_registry`, `resolve_flag`, ... (+9)
- **feature_registry** (6): `db`, `register`, `deregister`, `get_feature`, `get_active_features`, `analyze_conflicts`
- **git_adapter** (11): `create_speculative_ref`, `delete_speculative_refs`, `fast_forward_main`, `get_changed_files`, `list_speculative_refs`, `_ensure_git_version`, ... (+5)
- **github_coordination** (9): `from_dict`, `db`, `parse_lock_labels`, `parse_branch`, `sync_label_locks`, `sync_branch_tracking`, ... (+3)
- **guardrails** (5): `reset_guardrail_instruments`, `from_dict`, `db`, `_load_patterns`, `check_operation`
- **handoffs** (4): `db`, `write`, `read`, `get_recent`
- **help_service** (1): `_register`
- **http_proxy** (1): `shutdown_client`
- **issue_service** (12): `to_dict`, `to_dict`, `db`, `create`, `list_issues`, `show`, ... (+6)
- **langfuse_middleware** (1): `dispatch`
- **langfuse_tracing** (4): `create_span`, `end_span`, `trace_operation`, `reset_langfuse`
- **locks** (7): `is_valid_lock_key`, `db`, `acquire`, `release`, `check`, `extend`, ... (+1)
- **memory** (3): `db`, `remember`, `recall`
- **merge_queue** (8): `db`, `registry`, `enqueue`, `get_queue`, `get_next_to_merge`, `run_pre_merge_checks`, ... (+2)
- **merge_train** (6): `validate_post_speculation_claims`, `reset_blocked_entry`, `reset_abandoned_entry`, `execute_wave_merge`, `cleanup_orphaned_speculative_refs`, `gc_aged_speculative_refs`
- **merge_train_service** (20): `db`, `registry`, `git_adapter`, `refresh_client`, `_load_entries`, `_save_entry`, ... (+14)
- **merge_train_types** (5): `is_terminal`, `to_metadata_dict`, `all_passed`, `all_entries`, `total_entry_count`
- **network_policies** (2): `db`, `check_domain`
- **notifications** (38): `send`, `test`, `supports_reply`, `send`, `test`, `supports_reply`, ... (+32)
- **policy_engine** (25): `db`, `check_operation`, `_do_check_operation`, `check_network_access`, `list_policy_versions`, `rollback_policy`, ... (+19)
- **policy_sync** (13): `start`, `stop`, `on_policy_change`, `running`, `on_policy_change`, `start`, ... (+7)
- **port_allocator** (6): `env_snippet`, `allocate`, `release`, `status`, `_cleanup_expired`, `reset_port_allocator`
- **profile_loader** (2): `resolve_dynamic_dsn`, `_replace`
- **profiles** (5): `from_dict`, `db`, `get_profile`, `check_operation`, `_log_denial`
- **refresh_rpc_client** (4): `is_graph_stale`, `trigger_refresh`, `get_refresh_status`, `_invoke`
- **risk_scorer** (10): `db`, `compute_score`, `get_violation_count`, `_trust_factor`, `_operation_factor`, `_resource_factor`, ... (+4)
- **session_grants** (7): `db`, `request_grant`, `get_active_grants`, `has_grant`, `revoke_grants`, `_row_to_grant`, ... (+1)
- **status** (1): `cleanup_expired_tokens`
- **teams** (5): `from_dict`, `get_agent`, `get_agents_with_capability`, `get_teams_config`, `reset_teams_config`
- **telemetry** (4): `set_attribute`, `set_status`, `record_exception`, `reset_telemetry`
- **watchdog** (14): `db`, `running`, `start`, `stop`, `run_once`, `_loop`, ... (+8)
- **work_queue** (10): `db`, `_resolve_trust_level`, `claim`, `complete`, `submit`, `get_pending`, ... (+4)

## Parallel Modification Zones

*Data source: [parallel_zones.json](parallel_zones.json)*

**958 independent groups** identified. The largest interconnected group has 409 modules; 1220 modules are leaf nodes (safe to modify in isolation).

**32 high-impact modules** act as coupling points — parallel changes touching these need coordination.

### Interconnected Groups

**Group 0** (409 members spanning 39 modules): `agents_config`, `approval`, `audit`, `config`, `coordination_api`, `coordination_cli`, `coordination_mcp`, `db`
  ... and 31 more modules

**Group 1** (38 members spanning 38 modules): `agents_config`, `approval`, `audit`, `config`, `coordination_api`, `coordination_cli`, `coordination_mcp`, `db`
  ... and 30 more modules

**Group 2** (18 members spanning 3 modules): `merge_train`, `merge_train_service`, `merge_train_types`

**Group 3** (14 members spanning 1 modules): `notifications`

**Group 4** (9 members spanning 1 modules): `db_postgres`

**Group 5** (7 members spanning 5 modules): `approval`, `locks`, `merge_queue`, `merge_train_service`, `session_grants`

**Group 6** (6 members spanning 1 modules): `docker_manager`

**Group 7** (6 members spanning 1 modules): `git_adapter`

**Group 8** (5 members spanning 4 modules): `discovery`, `feature_registry`, `issue_service`, `work_queue`

**Group 9** (3 members spanning 1 modules): `merge_train`

### Leaf Modules (1220)

1220 modules have no dependents — changes are fully isolated. 941 of the 958 groups are singletons.

## Architecture Diagrams

*Data source: [architecture.graph.json](architecture.graph.json)*

### Container View

```mermaid
flowchart TB
    Backend["Backend (1117 nodes)"]
    Database["Database (354 nodes)"]
```

### Backend Components

```mermaid
flowchart TB
    __init__["__init__ (1 symbols)"]
    agents_config["agents_config (31 symbols)"]
    approval["approval (14 symbols)"]
    assurance["assurance (1 symbols)"]
    audit["audit (17 symbols)"]
    config["config (41 symbols)"]
    coordination_api["coordination_api (121 symbols)"]
    coordination_cli["coordination_cli (33 symbols)"]
    coordination_mcp["coordination_mcp (77 symbols)"]
    db["db (23 symbols)"]
    db_postgres["db_postgres (14 symbols)"]
    discovery["discovery (20 symbols)"]
    docker_manager["docker_manager (8 symbols)"]
    event_bus["event_bus (21 symbols)"]
    feature_flags["feature_flags (26 symbols)"]
    feature_registry["feature_registry (19 symbols)"]
    git_adapter["git_adapter (25 symbols)"]
    github_coordination["github_coordination (16 symbols)"]
    guardrails["guardrails (15 symbols)"]
    handoffs["handoffs (14 symbols)"]
    help_service["help_service (6 symbols)"]
    http_proxy["http_proxy (68 symbols)"]
    issue_service["issue_service (21 symbols)"]
    langfuse_middleware["langfuse_middleware (5 symbols)"]
    langfuse_tracing["langfuse_tracing (10 symbols)"]
    locks["locks (18 symbols)"]
    memory["memory (13 symbols)"]
    merge_queue["merge_queue (17 symbols)"]
    merge_train["merge_train (30 symbols)"]
    merge_train_service["merge_train_service (29 symbols)"]
    merge_train_types["merge_train_types (14 symbols)"]
    migrations["migrations (5 symbols)"]
    network_policies["network_policies (8 symbols)"]
    notifications____init__["notifications.__init__ (1 symbols)"]
    notifications__base["notifications.base (10 symbols)"]
    notifications__gmail["notifications.gmail (13 symbols)"]
    notifications__notifier["notifications.notifier (14 symbols)"]
    notifications__relay["notifications.relay (6 symbols)"]
    notifications__telegram["notifications.telegram (11 symbols)"]
    notifications__templates["notifications.templates (11 symbols)"]
    notifications__webhook["notifications.webhook (8 symbols)"]
    policy_engine["policy_engine (36 symbols)"]
    policy_sync["policy_sync (17 symbols)"]
    port_allocator["port_allocator (12 symbols)"]
    profile_loader["profile_loader (14 symbols)"]
    profiles["profiles (14 symbols)"]
    refresh_rpc_client["refresh_rpc_client (12 symbols)"]
    risk_scorer["risk_scorer (14 symbols)"]
    session_grants["session_grants (13 symbols)"]
    status["status (6 symbols)"]
    teams["teams (10 symbols)"]
    telemetry["telemetry (20 symbols)"]
    tests__test_architecture["tests.test_architecture (52 symbols)"]
    watchdog["watchdog (18 symbols)"]
    work_queue["work_queue (24 symbols)"]
    agents_config -->|"call"| profile_loader
    agents_config -->|"call"| teams
    approval -->|"call, import"| db
    audit -->|"call, import"| config
    audit -->|"call, import"| db
    config -->|"call"| agents_config
    config -->|"call"| profile_loader
    coordination_api -->|"call, import"| agents_config
    coordination_api -->|"call, import"| approval
    coordination_api -->|"call, import"| audit
    coordination_api -->|"call, import"| config
    coordination_api -->|"call, import"| discovery
    coordination_api -->|"call, import"| event_bus
    coordination_api -->|"call, import"| feature_registry
    coordination_api -->|"call, import"| guardrails
    coordination_api -->|"call, import"| handoffs
    coordination_api -->|"call, import"| help_service
    coordination_api -->|"call, import"| issue_service
    coordination_api -->|"import"| langfuse_middleware
    coordination_api -->|"call, import"| langfuse_tracing
    coordination_api -->|"call, import"| locks
    coordination_api -->|"call, import"| memory
    coordination_api -->|"call, import"| merge_queue
    coordination_api -->|"import"| merge_train
    coordination_api -->|"call, import"| merge_train_service
    coordination_api -->|"call, import"| migrations
    coordination_api -->|"call, import"| notifications__notifier
    coordination_api -->|"call, import"| policy_engine
    coordination_api -->|"call, import"| port_allocator
    coordination_api -->|"call, import"| profiles
    coordination_api -->|"call, import"| refresh_rpc_client
    coordination_api -->|"call, import"| session_grants
    coordination_api -->|"call, import"| telemetry
    coordination_api -->|"call, import"| watchdog
    coordination_api -->|"call, import"| work_queue
    coordination_cli -->|"call, import"| audit
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
    coordination_mcp -->|"call, import"| policy_engine
    coordination_mcp -->|"call, import"| port_allocator
    coordination_mcp -->|"call, import"| profiles
    coordination_mcp -->|"call, import"| refresh_rpc_client
    coordination_mcp -->|"call, import"| session_grants
    coordination_mcp -->|"call, import"| telemetry
    coordination_mcp -->|"call, import"| work_queue
    db -->|"call, import"| config
    db -->|"import"| db_postgres
    db_postgres -->|"import"| config
    discovery -->|"call, import"| audit
    discovery -->|"call, import"| config
    discovery -->|"call, import"| db
    feature_registry -->|"call, import"| audit
    feature_registry -->|"call, import"| config
    feature_registry -->|"call, import"| db
    feature_registry -->|"call"| discovery
    github_coordination -->|"call, import"| config
    github_coordination -->|"call, import"| db
    guardrails -->|"call, import"| audit
    guardrails -->|"call, import"| config
    guardrails -->|"call, import"| db
    guardrails -->|"call, import"| telemetry
    handoffs -->|"call, import"| audit
    handoffs -->|"call, import"| config
    handoffs -->|"call, import"| db
    handoffs -->|"call, import"| policy_engine
    http_proxy -->|"call"| config
    issue_service -->|"call, import"| config
    issue_service -->|"call, import"| db
    issue_service -->|"call"| discovery
    langfuse_middleware -->|"call, import"| config
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
    network_policies -->|"call, import"| config
    network_policies -->|"call, import"| db
    notifications__gmail -->|"call"| db
    notifications__gmail -->|"call"| notifications__relay
    notifications__gmail -->|"call"| notifications__templates
    notifications__gmail -->|"call"| status
    notifications__notifier -->|"call"| notifications__templates
    policy_engine -->|"call, import"| audit
    policy_engine -->|"call, import"| config
    policy_engine -->|"call, import"| db
    policy_engine -->|"call, import"| network_policies
    policy_engine -->|"call, import"| profiles
    policy_engine -->|"call, import"| telemetry
    port_allocator -->|"import"| config
    profiles -->|"call, import"| audit
    profiles -->|"call, import"| config
    profiles -->|"call, import"| db
    risk_scorer -->|"call, import"| db
    session_grants -->|"call"| approval
    session_grants -->|"call, import"| db
    watchdog -->|"call, import"| db
    watchdog -->|"call, import"| event_bus
    work_queue -->|"call, import"| agents_config
    work_queue -->|"call, import"| audit
    work_queue -->|"call, import"| config
    work_queue -->|"call, import"| db
    work_queue -->|"call"| discovery
    work_queue -->|"call, import"| guardrails
    work_queue -->|"call"| locks
    work_queue -->|"call, import"| policy_engine
    work_queue -->|"call, import"| profiles
    work_queue -->|"call, import"| telemetry
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
    public__memory_procedural {
        TIMESTAMPTZ created_at
        TEXT description
        INT failure_count
        UUID id
        TIMESTAMPTZ last_used
        TEXT__ prerequisites
        TEXT skill_name
        JSONB steps
        INT success_count
        TIMESTAMPTZ updated_at
    }
    public__memory_working {
        TEXT agent_id
        TIMESTAMPTZ created_at
        TIMESTAMPTZ expires_at
        UUID id
        TEXT key
        TEXT session_id
        TIMESTAMPTZ updated_at
        JSONB value
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
```
