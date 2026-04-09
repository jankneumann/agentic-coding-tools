"""HTTP proxy transport for the coordination MCP server.

When the local PostgreSQL database is unavailable at startup, the MCP server
switches to proxy mode and routes tool calls through the coordinator's HTTP
API. This module provides:

- ``HttpProxyConfig``: Configuration holder loaded from environment variables
- ``probe_*()``: Startup probes for DB reachability and HTTP API reachability
- ``init_client()`` / ``get_client()``: httpx client lifecycle management
- ``proxy_*()``: Per-tool proxy functions that map MCP tool calls to HTTP
  requests and normalize responses

Design notes (from openspec/changes/add-mcp-http-proxy-transport/design.md):

- D1: Startup probe selects transport once; fixed for process lifetime
- D2: httpx.AsyncClient with default pooling, fail-fast (no retries)
- D2: SSRF protection via URL allowlist (reuses coordination_bridge pattern)
- D5: COORDINATION_API_URL and COORDINATION_API_KEY from env
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

_log = logging.getLogger(__name__)

# =============================================================================
# SSRF allowlist
# =============================================================================

_ALLOWED_SCHEMES = {"http", "https"}
_BUILTIN_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _validate_url(url: str) -> str | None:
    """Validate URL against SSRF allowlist.

    Returns the validated URL or None if the URL is not allowed.
    Only http/https schemes targeting localhost or hosts in
    COORDINATION_ALLOWED_HOSTS are permitted.

    Matches the pattern used by skills/coordination-bridge/scripts/coordination_bridge.py
    so operators configure SSRF allowlists in one place.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    extra_hosts_raw = os.environ.get("COORDINATION_ALLOWED_HOSTS", "").strip()
    allowed = set(_BUILTIN_ALLOWED_HOSTS)
    wildcards: list[str] = []
    if extra_hosts_raw:
        for entry in extra_hosts_raw.split(","):
            entry = entry.strip().lower()
            if not entry:
                continue
            if entry.startswith("*."):
                wildcards.append(entry[1:])  # store ".domain.com"
            else:
                allowed.add(entry)

    if hostname in allowed:
        return url

    for suffix in wildcards:
        if hostname.endswith(suffix) and hostname != suffix.lstrip("."):
            return url

    return None


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class HttpProxyConfig:
    """HTTP proxy configuration loaded from environment variables."""

    base_url: str
    api_key: str | None
    agent_id: str
    agent_type: str
    timeout: float = 5.0

    @classmethod
    def from_env(cls) -> HttpProxyConfig | None:
        """Load proxy config from environment variables.

        Returns None if COORDINATION_API_URL is not set or fails validation.
        """
        base_url = os.environ.get("COORDINATION_API_URL", "").strip()
        if not base_url:
            return None

        validated = _validate_url(base_url)
        if validated is None:
            _log.warning(
                "COORDINATION_API_URL %r rejected by SSRF allowlist. "
                "Add host to COORDINATION_ALLOWED_HOSTS if trusted.",
                base_url,
            )
            return None

        return cls(
            base_url=validated.rstrip("/"),
            api_key=os.environ.get("COORDINATION_API_KEY") or None,
            agent_id=os.environ.get("AGENT_ID", "claude-code-1"),
            agent_type=os.environ.get("AGENT_TYPE", "claude_code"),
            timeout=float(os.environ.get("COORDINATION_HTTP_TIMEOUT", "5.0")),
        )


# =============================================================================
# Startup probes (D1)
# =============================================================================


async def probe_database(dsn: str, timeout_seconds: float = 2.0) -> bool:
    """Probe PostgreSQL DSN reachability.

    Returns True if a connection can be established within the timeout,
    False otherwise. Never raises.
    """
    if not dsn:
        return False
    try:
        import asyncio

        import asyncpg

        conn = await asyncio.wait_for(asyncpg.connect(dsn=dsn), timeout=timeout_seconds)
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
        return True
    except Exception as exc:  # noqa: BLE001
        _log.debug("DB probe failed: %s", exc)
        return False


async def probe_http_api(base_url: str, timeout_seconds: float = 2.0) -> bool:
    """Probe HTTP API /health endpoint.

    Returns True if the API responds 200 to GET /health within the timeout.
    """
    if not base_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(f"{base_url.rstrip('/')}/health")
            return response.status_code == 200
    except Exception as exc:  # noqa: BLE001
        _log.debug("HTTP API probe failed: %s", exc)
        return False


async def select_transport(
    dsn: str,
    http_base_url: str,
    probe_timeout_seconds: float = 2.0,
) -> str:
    """Select transport based on backend availability.

    Returns "db" if the database is reachable, "http" if only the HTTP API
    is reachable, or "db" if neither is reachable (preserving existing
    failure mode — the user sees the existing DB connection error).

    Rationale: "db" is the default fallback because it preserves the
    existing behavior when the MCP server was unable to probe anything.
    """
    if await probe_database(dsn, timeout_seconds=probe_timeout_seconds):
        return "db"
    if http_base_url and await probe_http_api(
        http_base_url, timeout_seconds=probe_timeout_seconds
    ):
        return "http"
    return "db"


# =============================================================================
# Client lifecycle
# =============================================================================

_config: HttpProxyConfig | None = None
_client: httpx.AsyncClient | None = None


def init_client(config: HttpProxyConfig) -> None:
    """Initialise the module-level httpx client. Call once at startup."""
    global _config, _client
    _config = config
    _client = httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.timeout,
        headers=_build_default_headers(config),
    )


def get_config() -> HttpProxyConfig:
    """Return the initialised proxy config. Raises if not initialised."""
    if _config is None:
        raise RuntimeError("http_proxy not initialised. Call init_client() first.")
    return _config


def get_client() -> httpx.AsyncClient:
    """Return the initialised httpx client. Raises if not initialised."""
    if _client is None:
        raise RuntimeError("http_proxy not initialised. Call init_client() first.")
    return _client


async def shutdown_client() -> None:
    """Close the httpx client at shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _build_default_headers(config: HttpProxyConfig) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    return headers


# =============================================================================
# Error normalisation (PROXY-3, PROXY-4, PROXY-5, PROXY-6)
# =============================================================================


def _error_response(error: str, **extra: Any) -> dict[str, Any]:
    """Build a normalised error response dict."""
    result: dict[str, Any] = {"success": False, "error": error}
    result.update(extra)
    return result


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Low-level HTTP request helper with full error normalization.

    Returns either:
    - The parsed JSON response dict on success (2xx)
    - An error dict {"success": false, "error": "..."} on any failure
    """
    client = get_client()
    try:
        response = await client.request(
            method=method,
            url=path,
            json=json_body,
            params=params,
        )
    except httpx.TimeoutException:
        _log.debug("http_proxy timeout: %s %s", method, path)
        return _error_response("timeout", path=path)
    except httpx.ConnectError as exc:
        _log.debug("http_proxy connect error: %s %s: %s", method, path, exc)
        return _error_response("connection_error", detail=str(exc), path=path)
    except httpx.HTTPError as exc:
        _log.debug("http_proxy network error: %s %s: %s", method, path, exc)
        return _error_response("network_error", detail=str(exc), path=path)

    if response.status_code == 401:
        _log.warning(
            "http_proxy auth failed: %s %s — check COORDINATION_API_KEY",
            method,
            path,
        )
        return _error_response(
            "authentication_failed",
            detail="COORDINATION_API_KEY may be missing or invalid",
            status_code=401,
        )

    if response.status_code >= 400:
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            body = {"detail": response.text}
        _log.debug(
            "http_proxy %d: %s %s: %s",
            response.status_code,
            method,
            path,
            body,
        )
        return _error_response(
            f"http_{response.status_code}",
            status_code=response.status_code,
            detail=body,
        )

    try:
        return response.json()  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        _log.debug("http_proxy invalid JSON: %s %s: %s", method, path, exc)
        return _error_response("invalid_json_response", detail=str(exc))


def _agent_identity() -> dict[str, str]:
    """Return agent identity fields to inject into HTTP request bodies."""
    cfg = get_config()
    return {"agent_id": cfg.agent_id, "agent_type": cfg.agent_type}


# =============================================================================
# PROXY FUNCTIONS: File Locks
# =============================================================================


async def proxy_acquire_lock(
    file_path: str,
    reason: str | None = None,
    ttl_minutes: int | None = None,
) -> dict[str, Any]:
    """Proxy acquire_lock to POST /locks/acquire."""
    body = {
        **_agent_identity(),
        "file_path": file_path,
        "reason": reason,
        "ttl_minutes": ttl_minutes or 120,
    }
    return await _request("POST", "/locks/acquire", json_body=body)


async def proxy_release_lock(file_path: str) -> dict[str, Any]:
    """Proxy release_lock to POST /locks/release."""
    body = {
        **_agent_identity(),
        "file_path": file_path,
    }
    return await _request("POST", "/locks/release", json_body=body)


async def proxy_check_locks(
    file_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Proxy check_locks to GET /locks/status/{file_path} (one probe per path).

    Transforms the HTTP per-file response shape into the flat list shape that
    the MCP ``check_locks`` tool returns:

        [{"file_path", "locked_by", "agent_type", "locked_at", "expires_at", "reason"}]

    The HTTP endpoint returns either ``{"locked": False, "file_path": ...}`` or
    ``{"locked": True, "file_path": ..., "lock": {...}}``. Only locked files are
    included in the result, matching MCP behaviour.

    When ``file_paths`` is None, the HTTP API has no "list all locks" endpoint,
    so we return an empty list (graceful degradation — callers should pass
    explicit paths when running in proxy mode).
    """
    from urllib.parse import quote

    if not file_paths:
        return []
    results: list[dict[str, Any]] = []
    for path in file_paths:
        # URL-encode the path but preserve forward slashes (the HTTP route uses
        # ``{file_path:path}`` which captures slashes in the path parameter).
        encoded = quote(path, safe="/")
        response = await _request("GET", f"/locks/status/{encoded}")
        if "error" in response:
            continue
        if not response.get("locked"):
            continue
        lock = response.get("lock") or {}
        results.append(
            {
                "file_path": response.get("file_path", path),
                "locked_by": lock.get("locked_by"),
                "agent_type": lock.get("agent_type"),
                "locked_at": lock.get("locked_at"),
                "expires_at": lock.get("expires_at"),
                "reason": lock.get("reason"),
            }
        )
    return results


# =============================================================================
# PROXY FUNCTIONS: Work Queue
# =============================================================================


async def proxy_get_work(
    task_types: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy get_work to POST /work/claim."""
    body = {
        **_agent_identity(),
        "task_types": task_types,
    }
    return await _request("POST", "/work/claim", json_body=body)


async def proxy_complete_work(
    task_id: str,
    success: bool,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Proxy complete_work to POST /work/complete."""
    body = {
        **_agent_identity(),
        "task_id": task_id,
        "success": success,
        "result": result,
        "error_message": error_message,
    }
    return await _request("POST", "/work/complete", json_body=body)


async def proxy_submit_work(
    task_type: str,
    description: str,
    input_data: dict[str, Any] | None = None,
    priority: int = 5,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy submit_work to POST /work/submit."""
    body = {
        **_agent_identity(),
        "task_type": task_type,
        "task_description": description,
        "input_data": input_data,
        "priority": priority,
        "depends_on": depends_on,
    }
    return await _request("POST", "/work/submit", json_body=body)


async def proxy_get_task(task_id: str) -> dict[str, Any]:
    """Proxy get_task to POST /work/get."""
    body = {
        **_agent_identity(),
        "task_id": task_id,
    }
    return await _request("POST", "/work/get", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Issues
# =============================================================================


async def proxy_issue_create(
    title: str,
    description: str | None = None,
    issue_type: str = "task",
    priority: int = 5,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy issue_create to POST /issues/create."""
    body = {
        **_agent_identity(),
        "title": title,
        "description": description,
        "issue_type": issue_type,
        "priority": priority,
        "labels": labels,
        "parent_id": parent_id,
        "assignee": assignee,
        "depends_on": depends_on,
    }
    return await _request("POST", "/issues/create", json_body=body)


async def proxy_issue_list(
    status: str | None = None,
    issue_type: str | None = None,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Proxy issue_list to POST /issues/list."""
    body = {
        **_agent_identity(),
        "status": status,
        "issue_type": issue_type,
        "labels": labels,
        "parent_id": parent_id,
        "assignee": assignee,
        "limit": limit,
    }
    return await _request("POST", "/issues/list", json_body=body)


async def proxy_issue_show(issue_id: str) -> dict[str, Any]:
    """Proxy issue_show to GET /issues/{issue_id}."""
    return await _request("GET", f"/issues/{issue_id}")


async def proxy_issue_update(
    issue_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """Proxy issue_update to POST /issues/update."""
    body = {
        **_agent_identity(),
        "issue_id": issue_id,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "labels": labels,
        "assignee": assignee,
        "issue_type": issue_type,
    }
    return await _request("POST", "/issues/update", json_body=body)


async def proxy_issue_close(
    issue_id: str | None = None,
    issue_ids: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Proxy issue_close to POST /issues/close."""
    body = {
        **_agent_identity(),
        "issue_id": issue_id,
        "issue_ids": issue_ids,
        "reason": reason,
    }
    return await _request("POST", "/issues/close", json_body=body)


async def proxy_issue_comment(
    issue_id: str,
    body: str,
) -> dict[str, Any]:
    """Proxy issue_comment to POST /issues/comment."""
    json_body = {
        **_agent_identity(),
        "issue_id": issue_id,
        "body": body,
    }
    return await _request("POST", "/issues/comment", json_body=json_body)


async def proxy_issue_search(
    query: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Proxy issue_search to POST /issues/search."""
    body = {
        **_agent_identity(),
        "query": query,
        "limit": limit,
    }
    return await _request("POST", "/issues/search", json_body=body)


async def proxy_issue_ready(
    parent_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Proxy issue_ready to POST /issues/ready."""
    body = {
        **_agent_identity(),
        "parent_id": parent_id,
        "limit": limit,
    }
    return await _request("POST", "/issues/ready", json_body=body)


async def proxy_issue_blocked() -> dict[str, Any]:
    """Proxy issue_blocked to GET /issues/blocked."""
    return await _request("GET", "/issues/blocked")


# =============================================================================
# PROXY FUNCTIONS: Handoffs
# =============================================================================


async def proxy_write_handoff(
    summary: str,
    completed_work: list[str] | None = None,
    in_progress: list[str] | None = None,
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
    relevant_files: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy write_handoff to POST /handoffs/write."""
    body = {
        **_agent_identity(),
        "summary": summary,
        "completed_work": completed_work,
        "in_progress": in_progress,
        "decisions": decisions,
        "next_steps": next_steps,
        "relevant_files": relevant_files,
    }
    return await _request("POST", "/handoffs/write", json_body=body)


async def proxy_read_handoff(
    agent_name: str | None = None,
    limit: int = 1,
) -> dict[str, Any]:
    """Proxy read_handoff to POST /handoffs/read."""
    body = {
        **_agent_identity(),
        "agent_name": agent_name,
        "limit": limit,
    }
    return await _request("POST", "/handoffs/read", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Discovery
# =============================================================================


async def proxy_register_session(
    capabilities: list[str] | None = None,
    current_task: str | None = None,
    delegated_from: str | None = None,
) -> dict[str, Any]:
    """Proxy register_session to POST /discovery/register."""
    body = {
        **_agent_identity(),
        "capabilities": capabilities,
        "current_task": current_task,
        "delegated_from": delegated_from,
    }
    return await _request("POST", "/discovery/register", json_body=body)


async def proxy_discover_agents(
    capability: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Proxy discover_agents to GET /discovery/agents."""
    params: dict[str, Any] = {}
    if capability is not None:
        params["capability"] = capability
    if status is not None:
        params["status"] = status
    return await _request("GET", "/discovery/agents", params=params or None)


async def proxy_heartbeat() -> dict[str, Any]:
    """Proxy heartbeat to POST /discovery/heartbeat."""
    body = {**_agent_identity()}
    return await _request("POST", "/discovery/heartbeat", json_body=body)


async def proxy_cleanup_dead_agents(
    stale_threshold_minutes: int = 15,
) -> dict[str, Any]:
    """Proxy cleanup_dead_agents to POST /discovery/cleanup."""
    body = {
        **_agent_identity(),
        "stale_threshold_minutes": stale_threshold_minutes,
    }
    return await _request("POST", "/discovery/cleanup", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Memory
# =============================================================================


async def proxy_remember(
    event_type: str = "discovery",
    summary: str = "",
    details: dict[str, Any] | None = None,
    outcome: str | None = None,
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy remember to POST /memory/store."""
    body = {
        **_agent_identity(),
        "event_type": event_type,
        "summary": summary,
        "details": details,
        "outcome": outcome,
        "lessons": lessons,
        "tags": tags,
    }
    return await _request("POST", "/memory/store", json_body=body)


async def proxy_recall(
    tags: list[str] | None = None,
    event_type: str | None = None,
    limit: int = 10,
    min_relevance: float = 0.0,
) -> dict[str, Any]:
    """Proxy recall to POST /memory/query."""
    body = {
        **_agent_identity(),
        "tags": tags,
        "event_type": event_type,
        "limit": limit,
        "min_relevance": min_relevance,
    }
    return await _request("POST", "/memory/query", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Guardrails, Profiles, Audit
# =============================================================================


async def proxy_check_guardrails(
    operation_text: str,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Proxy check_guardrails to POST /guardrails/check."""
    body = {
        **_agent_identity(),
        "operation_text": operation_text,
        "file_paths": file_paths,
    }
    return await _request("POST", "/guardrails/check", json_body=body)


async def proxy_get_my_profile() -> dict[str, Any]:
    """Proxy get_my_profile to GET /profiles/me."""
    return await _request("GET", "/profiles/me")


async def proxy_get_agent_dispatch_configs() -> dict[str, Any]:
    """Proxy get_agent_dispatch_configs to GET /agents/dispatch-configs."""
    return await _request("GET", "/agents/dispatch-configs")


async def proxy_query_audit(
    agent_id: str | None = None,
    operation: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Proxy query_audit to GET /audit."""
    params: dict[str, Any] = {"limit": limit}
    if agent_id is not None:
        params["agent_id"] = agent_id
    if operation is not None:
        params["operation"] = operation
    return await _request("GET", "/audit", params=params)


# =============================================================================
# PROXY FUNCTIONS: Policy, Session Grants, Approvals
# =============================================================================


async def proxy_check_policy(
    operation: str,
    resource: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Proxy check_policy to POST /policy/check."""
    body = {
        **_agent_identity(),
        "operation": operation,
        "resource": resource,
        "context": context,
    }
    return await _request("POST", "/policy/check", json_body=body)


async def proxy_validate_cedar_policy(policy_text: str) -> dict[str, Any]:
    """Proxy validate_cedar_policy to POST /policy/validate."""
    body = {
        **_agent_identity(),
        "policy_text": policy_text,
    }
    return await _request("POST", "/policy/validate", json_body=body)


async def proxy_list_policy_versions(
    policy_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Proxy list_policy_versions to GET /policies/{policy_name}/versions."""
    return await _request(
        "GET",
        f"/policies/{policy_name}/versions",
        params={"limit": limit},
    )


async def proxy_request_permission(
    operation: str,
    justification: str | None = None,
) -> dict[str, Any]:
    """Proxy request_permission to POST /permissions/request."""
    body = {
        **_agent_identity(),
        "operation": operation,
        "justification": justification,
    }
    return await _request("POST", "/permissions/request", json_body=body)


async def proxy_request_approval(
    operation: str,
    resource: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Proxy request_approval to POST /approvals/request."""
    body = {
        **_agent_identity(),
        "operation": operation,
        "resource": resource,
        "context": context,
    }
    return await _request("POST", "/approvals/request", json_body=body)


async def proxy_check_approval(request_id: str) -> dict[str, Any]:
    """Proxy check_approval to GET /approvals/{request_id}."""
    return await _request("GET", f"/approvals/{request_id}")


# =============================================================================
# PROXY FUNCTIONS: Ports
# =============================================================================


async def proxy_allocate_ports(session_id: str) -> dict[str, Any]:
    """Proxy allocate_ports to POST /ports/allocate."""
    body = {
        **_agent_identity(),
        "session_id": session_id,
    }
    return await _request("POST", "/ports/allocate", json_body=body)


async def proxy_release_ports(session_id: str) -> dict[str, Any]:
    """Proxy release_ports to POST /ports/release."""
    body = {
        **_agent_identity(),
        "session_id": session_id,
    }
    return await _request("POST", "/ports/release", json_body=body)


async def proxy_ports_status() -> list[dict[str, Any]]:
    """Proxy ports_status to GET /ports/status.

    Returns a list of allocation dicts, or an empty list on error.
    """
    result = await _request("GET", "/ports/status")
    if isinstance(result, list):
        return result
    # Error dict from _request — return empty list to match MCP tool contract
    return []


# =============================================================================
# PROXY FUNCTIONS: Feature Registry
# =============================================================================


async def proxy_register_feature(
    feature_id: str,
    resource_claims: list[str],
    title: str | None = None,
    branch_name: str | None = None,
    merge_priority: int = 5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Proxy register_feature to POST /features/register."""
    body = {
        **_agent_identity(),
        "feature_id": feature_id,
        "resource_claims": resource_claims,
        "title": title,
        "branch_name": branch_name,
        "merge_priority": merge_priority,
        "metadata": metadata,
    }
    return await _request("POST", "/features/register", json_body=body)


async def proxy_deregister_feature(
    feature_id: str,
    status: str = "completed",
) -> dict[str, Any]:
    """Proxy deregister_feature to POST /features/deregister."""
    body = {
        **_agent_identity(),
        "feature_id": feature_id,
        "status": status,
    }
    return await _request("POST", "/features/deregister", json_body=body)


async def proxy_get_feature(feature_id: str) -> dict[str, Any]:
    """Proxy get_feature to GET /features/{feature_id}."""
    return await _request("GET", f"/features/{feature_id}")


async def proxy_list_active_features() -> dict[str, Any]:
    """Proxy list_active_features to GET /features/active."""
    return await _request("GET", "/features/active")


async def proxy_analyze_feature_conflicts(
    candidate_feature_id: str,
    candidate_claims: list[str],
) -> dict[str, Any]:
    """Proxy analyze_feature_conflicts to POST /features/conflicts."""
    body = {
        **_agent_identity(),
        "candidate_feature_id": candidate_feature_id,
        "candidate_claims": candidate_claims,
    }
    return await _request("POST", "/features/conflicts", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Merge Queue
# =============================================================================


async def proxy_enqueue_merge(
    feature_id: str,
    pr_url: str | None = None,
) -> dict[str, Any]:
    """Proxy enqueue_merge to POST /merge-queue/enqueue."""
    body = {
        **_agent_identity(),
        "feature_id": feature_id,
        "pr_url": pr_url,
    }
    return await _request("POST", "/merge-queue/enqueue", json_body=body)


async def proxy_get_merge_queue() -> dict[str, Any]:
    """Proxy get_merge_queue to GET /merge-queue."""
    return await _request("GET", "/merge-queue")


async def proxy_get_next_merge() -> dict[str, Any]:
    """Proxy get_next_merge to GET /merge-queue/next."""
    return await _request("GET", "/merge-queue/next")


async def proxy_run_pre_merge_checks(feature_id: str) -> dict[str, Any]:
    """Proxy run_pre_merge_checks to POST /merge-queue/check/{feature_id}."""
    return await _request(
        "POST",
        f"/merge-queue/check/{feature_id}",
        json_body={**_agent_identity()},
    )


async def proxy_mark_merged(feature_id: str) -> dict[str, Any]:
    """Proxy mark_merged to POST /merge-queue/merged/{feature_id}."""
    return await _request(
        "POST",
        f"/merge-queue/merged/{feature_id}",
        json_body={**_agent_identity()},
    )


async def proxy_remove_from_merge_queue(feature_id: str) -> dict[str, Any]:
    """Proxy remove_from_merge_queue to DELETE /merge-queue/{feature_id}."""
    return await _request("DELETE", f"/merge-queue/{feature_id}")


# =============================================================================
# PROXY FUNCTIONS: Status
# =============================================================================


async def proxy_report_status(
    agent_id: str,
    change_id: str,
    phase: str,
    message: str = "",
    needs_human: bool = False,
    event_type: str = "phase_transition",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Proxy report_status to POST /status/report."""
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "change_id": change_id,
        "phase": phase,
        "message": message,
        "needs_human": needs_human,
        "event_type": event_type,
        "metadata": metadata,
    }
    return await _request("POST", "/status/report", json_body=body)


# =============================================================================
# PROXY FUNCTIONS: Gen-eval
# =============================================================================


async def proxy_list_scenarios(
    category: str | None = None,
    interface: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Proxy list_scenarios to GET /gen-eval/scenarios.

    The HTTP endpoint wraps scenarios in ``{"scenarios": [...]}`` but the MCP
    ``list_scenarios`` tool returns a JSON-encoded raw list. Unwrap the list
    so downstream ``json.dumps`` produces the expected shape. On error, return
    the error dict unchanged.
    """
    params: dict[str, Any] = {}
    if category is not None:
        params["category"] = category
    if interface is not None:
        params["interface"] = interface
    response = await _request("GET", "/gen-eval/scenarios", params=params or None)
    if isinstance(response, dict) and "scenarios" in response and "error" not in response:
        scenarios = response["scenarios"]
        if isinstance(scenarios, list):
            return scenarios
    return response


async def proxy_validate_scenario(yaml_content: str) -> dict[str, Any]:
    """Proxy validate_scenario to POST /gen-eval/validate."""
    body = {
        **_agent_identity(),
        "yaml_content": yaml_content,
    }
    return await _request("POST", "/gen-eval/validate", json_body=body)


async def proxy_create_scenario(
    category: str,
    description: str,
    interfaces: list[str],
    scenario_type: str = "success",
    priority: int = 2,
) -> dict[str, Any]:
    """Proxy create_scenario to POST /gen-eval/create."""
    body = {
        **_agent_identity(),
        "category": category,
        "description": description,
        "interfaces": interfaces,
        "scenario_type": scenario_type,
        "priority": priority,
    }
    return await _request("POST", "/gen-eval/create", json_body=body)


async def proxy_run_gen_eval(
    mode: str = "template-only",
    categories: list[str] | None = None,
    time_budget_minutes: float = 60.0,
) -> dict[str, Any]:
    """Proxy run_gen_eval to POST /gen-eval/run."""
    body = {
        **_agent_identity(),
        "mode": mode,
        "categories": categories,
        "time_budget_minutes": time_budget_minutes,
    }
    return await _request("POST", "/gen-eval/run", json_body=body)
