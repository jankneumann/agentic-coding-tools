# Tasks: add-mcp-http-proxy-transport

## Phase 1: Add Missing HTTP Endpoints

- [ ] 1.1 Write tests for new HTTP endpoints — discovery, gen-eval, issues, work, permissions, approvals
  **Spec scenarios**: agent-coordinator.HTTP-1 (discovery endpoints), agent-coordinator.HTTP-2 (gen-eval endpoints), agent-coordinator.HTTP-3 (issue search/ready/blocked), agent-coordinator.HTTP-4 (get_task), agent-coordinator.HTTP-5 (request_permission), agent-coordinator.HTTP-6 (approval submit/check)
  **Design decisions**: D4 (new HTTP endpoints)
  **Dependencies**: None

- [ ] 1.2 Add Pydantic request/response models for new endpoints
  **Dependencies**: None

- [ ] 1.3 Add discovery HTTP endpoints to `coordination_api.py` — POST /discovery/register, GET /discovery/agents, POST /discovery/heartbeat, POST /discovery/cleanup
  **Dependencies**: 1.1, 1.2

- [ ] 1.4 Add gen-eval HTTP endpoints to `coordination_api.py` — GET /gen-eval/scenarios, POST /gen-eval/validate, POST /gen-eval/create, POST /gen-eval/run
  **Dependencies**: 1.1, 1.2

- [ ] 1.5 Add remaining HTTP endpoints — POST /issues/search, POST /issues/ready, GET /issues/blocked, GET /work/task/{task_id}, POST /permissions/request, POST /approvals/request, GET /approvals/{request_id}
  **Dependencies**: 1.1, 1.2

- [ ] 1.6 Run existing test suite + new endpoint tests, fix regressions
  **Dependencies**: 1.3, 1.4, 1.5

## Phase 2: HTTP Proxy Module

- [ ] 2.1 Write tests for `http_proxy.py` — client init, agent identity injection, response normalization, error handling, timeout behavior
  **Spec scenarios**: agent-coordinator.PROXY-1 (proxy routes to HTTP), agent-coordinator.PROXY-2 (agent identity injection), agent-coordinator.PROXY-3 (error mapping), agent-coordinator.PROXY-4 (timeout handling)
  **Design decisions**: D2 (HTTP proxy module)
  **Dependencies**: 1.6

- [ ] 2.2 Create `src/http_proxy.py` — HttpProxyConfig, httpx client setup, base request/response helpers
  **Dependencies**: 2.1

- [ ] 2.3 Add proxy functions for lock tools (acquire_lock, release_lock, check_locks)
  **Dependencies**: 2.2

- [ ] 2.4 Add proxy functions for work queue tools (get_work, complete_work, submit_work, get_task)
  **Dependencies**: 2.2

- [ ] 2.5 Add proxy functions for handoff tools (write_handoff, read_handoff)
  **Dependencies**: 2.2

- [ ] 2.6 Add proxy functions for memory tools (remember, recall)
  **Dependencies**: 2.2

- [ ] 2.7 Add proxy functions for issue tools (issue_create, issue_list, issue_show, issue_update, issue_close, issue_comment, issue_search, issue_ready, issue_blocked)
  **Dependencies**: 2.2

- [ ] 2.8 Add proxy functions for discovery tools (register_session, discover_agents, heartbeat, cleanup_dead_agents)
  **Dependencies**: 2.2

- [ ] 2.9 Add proxy functions for guardrails, profiles, audit tools (check_guardrails, get_my_profile, get_agent_dispatch_configs, query_audit)
  **Dependencies**: 2.2

- [ ] 2.10 Add proxy functions for policy tools (check_policy, validate_cedar_policy, list_policy_versions, request_permission)
  **Dependencies**: 2.2

- [ ] 2.11 Add proxy functions for approval tools (request_approval, check_approval)
  **Dependencies**: 2.2

- [ ] 2.12 Add proxy functions for port allocation tools (allocate_ports, release_ports, ports_status)
  **Dependencies**: 2.2

- [ ] 2.13 Add proxy functions for feature registry tools (register_feature, deregister_feature, get_feature, list_active_features, analyze_feature_conflicts)
  **Dependencies**: 2.2

- [ ] 2.14 Add proxy functions for merge queue tools (enqueue_merge, get_merge_queue, get_next_merge, run_pre_merge_checks, mark_merged, remove_from_merge_queue)
  **Dependencies**: 2.2

- [ ] 2.15 Add proxy functions for status and gen-eval tools (report_status, list_scenarios, validate_scenario, create_scenario, run_gen_eval)
  **Dependencies**: 2.2

- [ ] 2.16 Run proxy module tests, verify all 48 tools have proxy functions
  **Dependencies**: 2.3 through 2.15

## Phase 3: Startup Probe and Tool Handler Integration

- [ ] 3.1 Write tests for startup transport selection — DB available, HTTP available, both available (DB wins), neither available
  **Spec scenarios**: agent-coordinator.STARTUP-1 (DB preferred), agent-coordinator.STARTUP-2 (HTTP fallback), agent-coordinator.STARTUP-3 (neither available)
  **Design decisions**: D1 (startup transport selection)
  **Dependencies**: 2.16

- [ ] 3.2 Implement startup probe in `coordination_mcp.py` main() — asyncpg connect probe + HTTP health probe, transport selection logic
  **Dependencies**: 3.1

- [ ] 3.3 Add transport routing to all tool handlers in `coordination_mcp.py` — `if _transport == "http": return await http_proxy.proxy_*(...)` branch
  **Dependencies**: 3.2

- [ ] 3.4 Handle MCP resources in proxy mode — return "unavailable in proxy mode" message
  **Dependencies**: 3.2
  **Design decisions**: D6 (resources in proxy mode)

- [ ] 3.5 Run full test suite (unit + new proxy + startup tests), run ruff + mypy
  **Dependencies**: 3.3, 3.4

## Phase 4: Configuration and Documentation

- [ ] 4.1 Update `setup-coordinator` skill to include COORDINATION_API_URL and COORDINATION_API_KEY in MCP env config
  **Dependencies**: 3.5
  **Design decisions**: D5 (MCP config update)

- [ ] 4.2 Update `check_coordinator.py` to report proxy mode status when MCP server is in HTTP transport
  **Dependencies**: 3.5

- [ ] 4.3 Deploy updated `coordination_api.py` to Railway with new endpoints
  **Dependencies**: 1.6

- [ ] 4.4 Update agent-coordinator CLAUDE.md with proxy mode documentation
  **Dependencies**: 3.5
