# Change Context: add-mcp-http-proxy-transport

## Requirement Traceability Matrix

| Requirement | Scenario | Contract Ref | Design Decision | Files Changed | Tests | Evidence |
|-------------|----------|--------------|-----------------|---------------|-------|----------|
| HTTP Proxy Transport | STARTUP-1 (DB selected when available) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy_startup.py::test_startup_prefers_db | --- |
| HTTP Proxy Transport | STARTUP-2 (HTTP fallback when DB down) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy_startup.py::test_startup_http_fallback | --- |
| HTTP Proxy Transport | STARTUP-3 (neither available) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy_startup.py::test_startup_both_unavailable | --- |
| HTTP Proxy Transport | STARTUP-4 (fixed at startup) | --- | D1 | agent-coordinator/src/coordination_mcp.py | test_http_proxy_startup.py::test_transport_fixed_after_startup | --- |
| HTTP Proxy Tool Coverage | PROXY-1 (routes to HTTP) | --- | D2, D3 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_routes_to_http | --- |
| HTTP Proxy Tool Coverage | PROXY-2 (agent identity injection) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_injects_agent_identity | --- |
| HTTP Proxy Tool Coverage | PROXY-3 (HTTP errors) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_maps_http_errors | --- |
| HTTP Proxy Tool Coverage | PROXY-4 (timeout) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_handles_timeout | --- |
| HTTP Proxy Tool Coverage | PROXY-5 (auth failure) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_handles_401 | --- |
| HTTP Proxy Tool Coverage | PROXY-6 (network errors) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_handles_connection_error | --- |
| HTTP Proxy Tool Coverage | PROXY-7 (SSRF validation) | --- | D2 | agent-coordinator/src/http_proxy.py | test_http_proxy.py::test_proxy_validates_url | --- |
| Complete HTTP API Coverage | HTTP-1 (discovery endpoints) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_discovery_endpoints | --- |
| Complete HTTP API Coverage | HTTP-1a (unauthorized) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_discovery_requires_auth | --- |
| Complete HTTP API Coverage | HTTP-2 (gen-eval endpoints) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_gen_eval_endpoints | --- |
| Complete HTTP API Coverage | HTTP-3 (issue search/ready/blocked) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_issue_search_ready_blocked | --- |
| Complete HTTP API Coverage | HTTP-3a (empty search) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_issue_search_empty | --- |
| Complete HTTP API Coverage | HTTP-4 (get_task) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_get_task | --- |
| Complete HTTP API Coverage | HTTP-4a (not found) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_get_task_not_found | --- |
| Complete HTTP API Coverage | HTTP-5 (permission request) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_permission_request | --- |
| Complete HTTP API Coverage | HTTP-6 (approval submit/check) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_approval_endpoints | --- |
| Complete HTTP API Coverage | HTTP-6a (approval not found) | --- | D4 | agent-coordinator/src/coordination_api.py | test_coordination_api_new.py::test_approval_not_found | --- |
| MCP Resources in Proxy Mode | Resources unavailable | --- | D6 | agent-coordinator/src/coordination_mcp.py | test_http_proxy_startup.py::test_resources_unavailable_in_proxy_mode | --- |

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
- Requirements with tests: 4 / 4 (all implemented)
- Total new tests: 73 (31 http_proxy + 15 new endpoints + 22 existing API + 5 iteration regression tests)
- Files changed:
  - `agent-coordinator/src/http_proxy.py` (new, ~1060 LOC)
  - `agent-coordinator/src/coordination_api.py` (+692 LOC — 14 new endpoints, 10 new Pydantic models)
  - `agent-coordinator/src/coordination_mcp.py` (+343 LOC — startup probe, 53 tool handlers, 11 resource guards)
  - `agent-coordinator/tests/test_http_proxy.py` (new, ~660 LOC)
  - `agent-coordinator/tests/test_coordination_api_new_endpoints.py` (new, ~220 LOC)
  - `agent-coordinator/CLAUDE.md` (+8 LOC env var docs)
  - `skills/setup-coordinator/SKILL.md` (+3 LOC HTTP proxy fallback note)
- Evidence status: implemented + 2 refinement iterations applied
- Known pre-existing failures (unrelated to this change):
  - `test_docker_manager.py::test_auto_falls_back_to_podman` (env-dependent)
  - `test_handoffs.py::test_write_handoff_db_error` (stale assertion; fix commit `1760e44` already on main)
