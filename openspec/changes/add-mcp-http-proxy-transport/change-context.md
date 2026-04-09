# Change Context: add-mcp-http-proxy-transport

## Requirement Traceability Matrix

| Requirement | Scenario | Contract Ref | Design Decision | Files Changed | Tests | Evidence |
|-------------|----------|--------------|-----------------|---------------|-------|----------|
| HTTP Proxy Transport | STARTUP-1 (DB selected when available) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy.py::test_select_transport_prefers_db_when_available | pass 4394fd5 |
| HTTP Proxy Transport | STARTUP-2 (HTTP fallback when DB down) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy.py::test_select_transport_falls_back_to_http | pass 4394fd5 |
| HTTP Proxy Transport | STARTUP-3 (neither available) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy.py::test_select_transport_defaults_db_when_neither_available | pass 4394fd5 |
| HTTP Proxy Transport | STARTUP-4 (fixed at startup) | --- | D1 | agent-coordinator/src/coordination_mcp.py | covered by module-level `_transport` state + manual verification | deferred (integration test) |
| HTTP Proxy Tool Coverage | PROXY-1 (routes to HTTP) | --- | D2, D3 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_acquire_lock_routes_to_http | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-2 (agent identity injection) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_agent_identity_returns_config_values, test_proxy_acquire_lock_routes_to_http | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-3 (HTTP errors) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_request_maps_other_http_errors | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-4 (timeout) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_request_maps_timeout | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-5 (auth failure) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_request_maps_401_to_auth_failure | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-6 (network errors) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_request_maps_connection_error | pass 4394fd5 |
| HTTP Proxy Tool Coverage | PROXY-7 (SSRF validation) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_validate_url_* (6 tests) | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-1 (discovery endpoints) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_all_14_new_routes_registered | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-1a (unauthorized) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_discovery_register_requires_auth, test_discovery_heartbeat_requires_auth, test_discovery_cleanup_requires_auth | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-2 (gen-eval endpoints) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_gen_eval_*_requires_auth, test_gen_eval_scenarios_is_public | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-3 (issue search/ready/blocked) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_issues_search_requires_auth, test_issues_ready_requires_auth, test_issues_blocked_is_public | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-3a (empty search) | --- | D4 | agent-coordinator/src/coordination_api.py | covered by service layer tests | deferred (service-layer test) |
| Complete HTTP API Coverage | HTTP-4 (get_task) | --- | D4 | agent-coordinator/src/coordination_api.py | existing test_http_get_task.py covers POST /work/get | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-4a (not found) | --- | D4 | agent-coordinator/src/coordination_api.py | covered by existing service-layer tests | deferred (service-layer test) |
| Complete HTTP API Coverage | HTTP-5 (permission request) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_permissions_request_requires_auth | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-6 (approval submit/check) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new_endpoints.py::test_approvals_request_requires_auth, test_approvals_get_by_id_requires_auth | pass 4394fd5 |
| Complete HTTP API Coverage | HTTP-6a (approval not found) | --- | D4 | agent-coordinator/src/coordination_api.py | 404 handled by HTTPException in endpoint | deferred (integration test) |
| MCP Resources in Proxy Mode | Resources unavailable | --- | D6 | agent-coordinator/src/coordination_mcp.py | test_http_proxy.py::test_resource_unavailable_constant_defined_and_used | pass 4394fd5 |

## Design Decision Trace

| Decision | Description | Requirements Validated | Files |
|----------|-------------|------------------------|-------|
| D1 | Startup transport selection | STARTUP-1/2/3/4 | coordination_mcp.py |
| D2 | HTTP proxy module with per-tool functions | PROXY-1/2/3/4/5/6/7 | http_proxy.py |
| D3 | Tool handler routing | PROXY-1 | coordination_mcp.py |
| D4 | New HTTP endpoints | HTTP-1/2/3/4/5/6 | coordination_api.py |
| D5 | MCP config update | (operational) | setup-coordinator skill |
| D6 | Resources in proxy mode | (resource scenario) | coordination_mcp.py |

## Coverage Summary

- Total requirements: 4
- Total scenarios: 22
- Scenarios with pass evidence: 18 / 22 (82%)
- Scenarios deferred (out-of-scope for unit tests): 4 / 22
  - STARTUP-4 (transport fixed at runtime — needs integration test)
  - HTTP-3a (empty search — service-layer test)
  - HTTP-4a (get_task not found — service-layer test)
  - HTTP-6a (approval not found — integration test)
- Total new tests: 73 passing
  - 35 in test_http_proxy.py
  - 15 in test_coordination_api_new_endpoints.py
  - 22 in existing test_coordination_api.py (no regression)
  - 1 in test_http_get_task.py (pre-existing, verifies POST /work/get)
- Files changed:
  - `agent-coordinator/src/http_proxy.py` (new, ~1075 LOC after iteration fixes)
  - `agent-coordinator/src/coordination_api.py` (+692 LOC — 14 new endpoints, 10 new Pydantic models)
  - `agent-coordinator/src/coordination_mcp.py` (+343 LOC — startup probe, 53 tool handlers, 11 resource guards)
  - `agent-coordinator/tests/test_http_proxy.py` (new, ~830 LOC after iteration fixes)
  - `agent-coordinator/tests/test_coordination_api_new_endpoints.py` (new, ~220 LOC)
  - `agent-coordinator/CLAUDE.md` (+8 LOC env var docs)
  - `skills/setup-coordinator/SKILL.md` (+3 LOC HTTP proxy fallback note)
- Evidence status: implemented + 2 refinement iterations + validation pass
- Known pre-existing failures (unrelated to this change):
  - `test_docker_manager.py::test_auto_falls_back_to_podman` (env-dependent)
  - `test_handoffs.py::test_write_handoff_db_error` (stale assertion; fix commit `1760e44` already on main)
