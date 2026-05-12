"""Transport-aware HTTP bridge for coordinator capability hooks.

This module keeps Web/Cloud coordination wiring stable for skill scripts.
Helpers return normalized dictionaries and degrade to ``status="skipped"``
when coordinator access is unavailable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("COORDINATION_HTTP_TIMEOUT", "1.5"))

_HTTP_URL_ENV_KEYS = (
    "COORDINATION_API_URL",
    "COORDINATOR_HTTP_URL",
    "AGENT_COORDINATOR_API_URL",
    "AGENT_COORDINATOR_HTTP_URL",
)
_API_KEY_ENV_KEYS = (
    "COORDINATION_API_KEY",
    "COORDINATOR_API_KEY",
)

_CAPABILITY_FLAGS = (
    "CAN_LOCK",
    "CAN_QUEUE_WORK",
    "CAN_HANDOFF",
    "CAN_MEMORY",
    "CAN_GUARDRAILS",
    "CAN_FEATURE_REGISTRY",
    "CAN_MERGE_QUEUE",
    "CAN_ISSUES",
)

_CAPABILITY_PROBES: dict[str, list[tuple[str, str, dict[str, Any] | None]]] = {
    # Empty payload intentionally triggers 422 on healthy endpoints and avoids
    # creating side effects during detection.
    "CAN_LOCK": [("POST", "/locks/acquire", {})],
    "CAN_QUEUE_WORK": [("POST", "/work/claim", {})],
    "CAN_HANDOFF": [("POST", "/handoffs/write", {})],
    "CAN_MEMORY": [("POST", "/memory/query", {})],
    "CAN_GUARDRAILS": [("POST", "/guardrails/check", {})],
    "CAN_FEATURE_REGISTRY": [("GET", "/features/active", None)],
    "CAN_MERGE_QUEUE": [("GET", "/merge-queue", None)],
    # Read-only list with empty filter — returns 200 on healthy deployments,
    # 404 when the issues feature isn't deployed.
    "CAN_ISSUES": [("POST", "/issues/list", {})],
}

_HANDOFF_WRITE_ENDPOINTS: list[tuple[str, str]] = [
    ("POST", "/handoffs/write"),
]
_HANDOFF_READ_ENDPOINTS: list[tuple[str, str]] = [
    ("POST", "/handoffs/read"),
]


# SSRF Protection: URL Allowlist
#
# By default, only localhost addresses are allowed for coordinator URLs.
# For cloud deployments (e.g., Railway, Cloudflare custom domains), add
# external hostnames via the COORDINATION_ALLOWED_HOSTS environment variable.
#
# Format: comma-separated hostnames (no scheme, no port)
# Exact:    COORDINATION_ALLOWED_HOSTS=your-app.railway.app
# Wildcard: COORDINATION_ALLOWED_HOSTS=*.yourdomain.com
# Mixed:    COORDINATION_ALLOWED_HOSTS=*.yourdomain.com,specific.railway.app
#
# Wildcard entries (*.domain.com) match any subdomain (coord.domain.com,
# mcp.domain.com) but NOT the bare domain itself (domain.com).
#
# The _validate_url() function merges COORDINATION_ALLOWED_HOSTS with the
# built-in localhost allowlist. Requests to unlisted hosts are blocked.
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _validate_url(url: str) -> str | None:
    """Validate that a URL targets an allowed scheme and host.

    Returns the validated URL or ``None`` if the URL is not allowed.
    Only ``http``/``https`` schemes targeting localhost (or an explicitly
    configured ``COORDINATION_ALLOWED_HOSTS`` list) are permitted, which
    prevents SSRF when the URL originates from environment variables.
    """
    try:
        parsed = url_parse.urlparse(url)
    except ValueError:
        return None

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    extra_hosts_raw = os.environ.get("COORDINATION_ALLOWED_HOSTS", "").strip()
    allowed = set(_ALLOWED_HOSTS)
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

    # Check wildcard patterns: *.domain.com matches sub.domain.com
    for suffix in wildcards:
        if hostname.endswith(suffix) and hostname != suffix.lstrip("."):
            return url

    return None


def _coordinator_state(
    *,
    available: bool,
    transport: str,
    http_url: str | None,
    reason: str | None = None,
    flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    capability_flags = {name: False for name in _CAPABILITY_FLAGS}
    if flags:
        capability_flags.update(flags)

    response: dict[str, Any] = {
        "status": "ok" if available else "skipped",
        "COORDINATOR_AVAILABLE": available,
        "COORDINATION_TRANSPORT": transport,
        "http_url": http_url,
        "reason": reason,
    }
    response.update(capability_flags)
    response["capabilities"] = {
        "lock": response["CAN_LOCK"],
        "queue_work": response["CAN_QUEUE_WORK"],
        "handoff": response["CAN_HANDOFF"],
        "memory": response["CAN_MEMORY"],
        "guardrails": response["CAN_GUARDRAILS"],
        "feature_registry": response["CAN_FEATURE_REGISTRY"],
        "merge_queue": response["CAN_MERGE_QUEUE"],
    }
    return response


def _resolve_http_url(http_url: str | None = None) -> str | None:
    if http_url:
        candidate = http_url.rstrip("/")
        return _validate_url(candidate)

    for key in _HTTP_URL_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            candidate = value.rstrip("/")
            validated = _validate_url(candidate)
            if validated:
                return validated

    rest_port = os.environ.get("AGENT_COORDINATOR_REST_PORT", "3000").strip()
    if not rest_port:
        return None
    if not rest_port.isdigit() or not (1 <= int(rest_port) <= 65535):
        return None
    return f"http://localhost:{rest_port}"


def _resolve_api_key(api_key: str | None = None) -> str | None:
    if api_key:
        return api_key
    for key in _API_KEY_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def _decode_payload(raw_body: bytes) -> Any:
    if not raw_body:
        return {}
    text = raw_body.decode("utf-8", errors="replace")
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _http_request(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not http_url:
        return {"status_code": None, "data": None, "error": "missing_http_url"}

    normalized_path = path if path.startswith("/") else f"/{path}"
    target_url = f"{http_url}{normalized_path}"

    if _validate_url(target_url) is None:
        return {"status_code": None, "data": None, "error": "url_not_allowed"}
    headers = {"Accept": "application/json", "User-Agent": "agentic-coding-tools/0.1"}
    body: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if api_key:
        headers["X-API-Key"] = api_key

    request_obj = url_request.Request(
        target_url,
        data=body,
        headers=headers,
        method=method.upper(),
    )

    try:
        with url_request.urlopen(request_obj, timeout=timeout) as response:
            response_body = response.read()
            return {
                "status_code": response.getcode(),
                "data": _decode_payload(response_body),
                "error": None,
            }
    except url_error.HTTPError as exc:
        response_body = exc.read() if hasattr(exc, "read") else b""
        return {
            "status_code": exc.code,
            "data": _decode_payload(response_body),
            "error": str(exc),
        }
    except (url_error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"status_code": None, "data": None, "error": str(exc)}


def _probe_capability(
    *,
    probes: list[tuple[str, str, dict[str, Any] | None]],
    http_url: str,
    api_key: str | None,
) -> bool:
    for method, path, payload in probes:
        response = _http_request(
            method=method,
            path=path,
            payload=payload,
            http_url=http_url,
            api_key=api_key,
        )
        status_code = response["status_code"]
        if status_code is None:
            continue
        if status_code in (401, 403, 404):
            continue
        if status_code >= 500:
            continue
        # 2xx, 4xx validation, and 405 all indicate route availability.
        return True
    return False


def detect_coordination(
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Detect coordinator HTTP reachability and capability flags."""
    resolved_url = _resolve_http_url(http_url)
    if not resolved_url:
        return _coordinator_state(
            available=False,
            transport="none",
            http_url=None,
            reason="missing_http_url",
        )

    health_response = _http_request(
        method="GET",
        path="/health",
        http_url=resolved_url,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    health_status = health_response["status_code"]
    if health_status is None:
        return _coordinator_state(
            available=False,
            transport="none",
            http_url=resolved_url,
            reason="health_unreachable",
        )
    if health_status == 404 or health_status >= 500:
        return _coordinator_state(
            available=False,
            transport="none",
            http_url=resolved_url,
            reason=f"health_status_{health_status}",
        )

    resolved_api_key = _resolve_api_key(api_key)
    flags = {
        name: _probe_capability(
            probes=probes,
            http_url=resolved_url,
            api_key=resolved_api_key,
        )
        for name, probes in _CAPABILITY_PROBES.items()
    }

    return _coordinator_state(
        available=True,
        transport="http",
        http_url=resolved_url,
        reason="http_reachable",
        flags=flags,
    )


def _skipped_operation(
    *,
    operation: str,
    reason: str,
    state: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": "skipped",
        "operation": operation,
        "reason": reason,
        "COORDINATOR_AVAILABLE": bool(
            state and state.get("COORDINATOR_AVAILABLE", False)
        ),
        "COORDINATION_TRANSPORT": (
            state.get("COORDINATION_TRANSPORT", "none") if state else "none"
        ),
    }
    if extra:
        result.update(extra)
    return result


def _normalize_operation_response(
    *,
    operation: str,
    response: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    status_code = response["status_code"]
    if status_code is None or status_code >= 500:
        return _skipped_operation(
            operation=operation,
            reason="coordinator_unreachable",
            state=state,
            extra={"error": response.get("error")},
        )
    if status_code == 404:
        return _skipped_operation(
            operation=operation,
            reason="capability_unavailable",
            state=state,
        )
    if status_code in (401, 403):
        return _skipped_operation(
            operation=operation,
            reason="unauthorized",
            state=state,
        )
    if 200 <= status_code < 300:
        return {
            "status": "ok",
            "operation": operation,
            "COORDINATOR_AVAILABLE": True,
            "COORDINATION_TRANSPORT": state.get("COORDINATION_TRANSPORT", "http"),
            "status_code": status_code,
            "response": response.get("data"),
        }
    return {
        "status": "error",
        "operation": operation,
        "COORDINATOR_AVAILABLE": True,
        "COORDINATION_TRANSPORT": state.get("COORDINATION_TRANSPORT", "http"),
        "status_code": status_code,
        "response": response.get("data"),
        "error": response.get("error"),
    }


def _execute_single_endpoint_operation(
    *,
    operation: str,
    capability_flag: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    http_url: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    state = detect_coordination(http_url=http_url, api_key=api_key)
    if not state["COORDINATOR_AVAILABLE"]:
        return _skipped_operation(
            operation=operation,
            reason="coordinator_unavailable",
            state=state,
        )
    if not state.get(capability_flag, False):
        return _skipped_operation(
            operation=operation,
            reason="capability_unavailable",
            state=state,
        )

    response = _http_request(
        method=method,
        path=path,
        payload=payload,
        http_url=state.get("http_url"),
        api_key=_resolve_api_key(api_key),
    )
    return _normalize_operation_response(
        operation=operation,
        response=response,
        state=state,
    )


def _execute_multi_endpoint_operation(
    *,
    operation: str,
    capability_flag: str,
    endpoints: list[tuple[str, str]],
    payload: dict[str, Any] | None,
    http_url: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    state = detect_coordination(http_url=http_url, api_key=api_key)
    if not state["COORDINATOR_AVAILABLE"]:
        return _skipped_operation(
            operation=operation,
            reason="coordinator_unavailable",
            state=state,
        )
    if not state.get(capability_flag, False):
        return _skipped_operation(
            operation=operation,
            reason="capability_unavailable",
            state=state,
        )

    resolved_api_key = _resolve_api_key(api_key)
    saw_not_found = False
    for method, path in endpoints:
        response = _http_request(
            method=method,
            path=path,
            payload=payload if method.upper() != "GET" else None,
            http_url=state.get("http_url"),
            api_key=resolved_api_key,
        )
        status_code = response["status_code"]
        if status_code == 404:
            saw_not_found = True
            continue
        return _normalize_operation_response(
            operation=operation,
            response=response,
            state=state,
        )

    if saw_not_found:
        return _skipped_operation(
            operation=operation,
            reason="capability_unavailable",
            state=state,
        )
    return _skipped_operation(
        operation=operation,
        reason="coordinator_unreachable",
        state=state,
    )


def try_lock(
    *,
    file_path: str,
    agent_id: str,
    agent_type: str,
    session_id: str | None = None,
    reason: str | None = None,
    ttl_minutes: int = 30,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Acquire a coordinator lock when lock capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_lock",
        capability_flag="CAN_LOCK",
        method="POST",
        path="/locks/acquire",
        payload={
            "file_path": file_path,
            "agent_id": agent_id,
            "agent_type": agent_type,
            "session_id": session_id,
            "reason": reason,
            "ttl_minutes": ttl_minutes,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_unlock(
    *,
    file_path: str,
    agent_id: str,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Release a coordinator lock when lock capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_unlock",
        capability_flag="CAN_LOCK",
        method="POST",
        path="/locks/release",
        payload={
            "file_path": file_path,
            "agent_id": agent_id,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_submit_work(
    *,
    task_type: str,
    task_description: str,
    input_data: dict[str, Any] | None = None,
    priority: int = 5,
    depends_on: list[str] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Submit queue work when queue capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_submit_work",
        capability_flag="CAN_QUEUE_WORK",
        method="POST",
        path="/work/submit",
        payload={
            "task_type": task_type,
            "task_description": task_description,
            "input_data": input_data,
            "priority": priority,
            "depends_on": depends_on,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_get_work(
    *,
    agent_id: str,
    agent_type: str,
    task_types: list[str] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Claim queue work when queue capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_get_work",
        capability_flag="CAN_QUEUE_WORK",
        method="POST",
        path="/work/claim",
        payload={
            "agent_id": agent_id,
            "agent_type": agent_type,
            "task_types": task_types,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_complete_work(
    *,
    task_id: str,
    agent_id: str,
    success: bool,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Complete queue work when queue capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_complete_work",
        capability_flag="CAN_QUEUE_WORK",
        method="POST",
        path="/work/complete",
        payload={
            "task_id": task_id,
            "agent_id": agent_id,
            "success": success,
            "result": result,
            "error_message": error_message,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_handoff_write(
    *,
    agent_id: str,
    summary: str,
    session_id: str | None = None,
    content: dict[str, Any] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Write handoff context when handoff capability is available."""
    return _execute_multi_endpoint_operation(
        operation="try_handoff_write",
        capability_flag="CAN_HANDOFF",
        endpoints=_HANDOFF_WRITE_ENDPOINTS,
        payload={
            "agent_id": agent_id,
            "session_id": session_id,
            "summary": summary,
            "content": content or {},
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_handoff_read(
    *,
    agent_id: str | None = None,
    session_id: str | None = None,
    limit: int = 1,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Read handoff context when handoff capability is available."""
    return _execute_multi_endpoint_operation(
        operation="try_handoff_read",
        capability_flag="CAN_HANDOFF",
        endpoints=_HANDOFF_READ_ENDPOINTS,
        payload={
            "agent_id": agent_id,
            "session_id": session_id,
            "limit": limit,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_remember(
    *,
    agent_id: str,
    event_type: str,
    summary: str,
    session_id: str | None = None,
    details: dict[str, Any] | None = None,
    outcome: str | None = None,
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Store coordinator memory when memory capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_remember",
        capability_flag="CAN_MEMORY",
        method="POST",
        path="/memory/store",
        payload={
            "agent_id": agent_id,
            "session_id": session_id,
            "event_type": event_type,
            "summary": summary,
            "details": details,
            "outcome": outcome,
            "lessons": lessons,
            "tags": tags,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_recall(
    *,
    agent_id: str,
    tags: list[str] | None = None,
    event_type: str | None = None,
    limit: int = 10,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Query coordinator memory when memory capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_recall",
        capability_flag="CAN_MEMORY",
        method="POST",
        path="/memory/query",
        payload={
            "agent_id": agent_id,
            "tags": tags,
            "event_type": event_type,
            "limit": limit,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_check_guardrails(
    *,
    operation_text: str,
    file_paths: list[str] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run a guardrail pre-check when guardrail capability is available."""
    return _execute_single_endpoint_operation(
        operation="try_check_guardrails",
        capability_flag="CAN_GUARDRAILS",
        method="POST",
        path="/guardrails/check",
        payload={
            "operation_text": operation_text,
            "file_paths": file_paths,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_register_feature(
    *,
    feature_id: str,
    resource_claims: list[str],
    title: str | None = None,
    agent_id: str | None = None,
    branch_name: str | None = None,
    merge_priority: int = 5,
    metadata: dict[str, Any] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Register a feature with resource claims via HTTP."""
    return _execute_single_endpoint_operation(
        operation="try_register_feature",
        capability_flag="CAN_FEATURE_REGISTRY",
        method="POST",
        path="/features/register",
        payload={
            "feature_id": feature_id,
            "resource_claims": resource_claims,
            "title": title,
            "agent_id": agent_id,
            "branch_name": branch_name,
            "merge_priority": merge_priority,
            "metadata": metadata,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_deregister_feature(
    *,
    feature_id: str,
    status: str = "completed",
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Deregister a feature (mark completed/cancelled) via HTTP."""
    return _execute_single_endpoint_operation(
        operation="try_deregister_feature",
        capability_flag="CAN_FEATURE_REGISTRY",
        method="POST",
        path="/features/deregister",
        payload={
            "feature_id": feature_id,
            "status": status,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_enqueue_merge(
    *,
    feature_id: str,
    pr_url: str | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Enqueue a feature for merge ordering via HTTP."""
    return _execute_single_endpoint_operation(
        operation="try_enqueue_merge",
        capability_flag="CAN_MERGE_QUEUE",
        method="POST",
        path="/merge-queue/enqueue",
        payload={
            "feature_id": feature_id,
            "pr_url": pr_url,
        },
        http_url=http_url,
        api_key=api_key,
    )


def try_pre_merge_checks(
    *,
    feature_id: str,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run pre-merge validation checks via HTTP."""
    return _execute_single_endpoint_operation(
        operation="try_pre_merge_checks",
        capability_flag="CAN_MERGE_QUEUE",
        method="POST",
        path=f"/merge-queue/check/{feature_id}",
        payload=None,
        http_url=http_url,
        api_key=api_key,
    )


def try_mark_merged(
    *,
    feature_id: str,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Mark a feature as merged and deregister via HTTP."""
    return _execute_single_endpoint_operation(
        operation="try_mark_merged",
        capability_flag="CAN_MERGE_QUEUE",
        method="POST",
        path=f"/merge-queue/merged/{feature_id}",
        payload=None,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_create(
    *,
    title: str,
    description: str | None = None,
    issue_type: str = "task",
    priority: int = 5,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    depends_on: list[str] | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create a new issue via the coordinator HTTP API."""
    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "issue_type": issue_type,
        "priority": priority,
    }
    if labels is not None:
        payload["labels"] = labels
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if assignee is not None:
        payload["assignee"] = assignee
    if depends_on is not None:
        payload["depends_on"] = depends_on
    return _execute_single_endpoint_operation(
        operation="try_issue_create",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/create",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_list(
    *,
    status: str | None = None,
    issue_type: str | None = None,
    labels: list[str] | None = None,
    parent_id: str | None = None,
    assignee: str | None = None,
    limit: int | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """List issues with optional filters via the coordinator HTTP API."""
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status
    if issue_type is not None:
        payload["issue_type"] = issue_type
    if labels is not None:
        payload["labels"] = labels
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if assignee is not None:
        payload["assignee"] = assignee
    if limit is not None:
        payload["limit"] = limit
    return _execute_single_endpoint_operation(
        operation="try_issue_list",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/list",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_show(
    *,
    issue_id: str,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Fetch a single issue's full details via the coordinator HTTP API."""
    return _execute_single_endpoint_operation(
        operation="try_issue_show",
        capability_flag="CAN_ISSUES",
        method="GET",
        path=f"/issues/{issue_id}",
        payload=None,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_update(
    *,
    issue_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: int | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    issue_type: str | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Update an issue via the coordinator HTTP API."""
    payload: dict[str, Any] = {"issue_id": issue_id}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if status is not None:
        payload["status"] = status
    if priority is not None:
        payload["priority"] = priority
    if labels is not None:
        payload["labels"] = labels
    if assignee is not None:
        payload["assignee"] = assignee
    if issue_type is not None:
        payload["issue_type"] = issue_type
    return _execute_single_endpoint_operation(
        operation="try_issue_update",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/update",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_close(
    *,
    issue_id: str | None = None,
    issue_ids: list[str] | None = None,
    reason: str | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Close one or more issues via the coordinator HTTP API.

    Exactly one of ``issue_id`` (single) or ``issue_ids`` (batch) must be set.
    """
    payload: dict[str, Any] = {}
    if issue_id is not None:
        payload["issue_id"] = issue_id
    if issue_ids is not None:
        payload["issue_ids"] = issue_ids
    if reason is not None:
        payload["reason"] = reason
    return _execute_single_endpoint_operation(
        operation="try_issue_close",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/close",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_comment(
    *,
    issue_id: str,
    body: str,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Append a comment to an issue via the coordinator HTTP API."""
    return _execute_single_endpoint_operation(
        operation="try_issue_comment",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/comment",
        payload={"issue_id": issue_id, "body": body},
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_ready(
    *,
    parent_id: str | None = None,
    limit: int | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """List issues with no unresolved dependencies via the coordinator HTTP API."""
    payload: dict[str, Any] = {}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    if limit is not None:
        payload["limit"] = limit
    return _execute_single_endpoint_operation(
        operation="try_issue_ready",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/ready",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_blocked(
    *,
    limit: int | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """List issues blocked by unresolved dependencies via the coordinator HTTP API.

    This endpoint is a GET that accepts ``limit`` as a query parameter.
    """
    path = "/issues/blocked"
    if limit is not None:
        path = f"{path}?limit={int(limit)}"
    return _execute_single_endpoint_operation(
        operation="try_issue_blocked",
        capability_flag="CAN_ISSUES",
        method="GET",
        path=path,
        payload=None,
        http_url=http_url,
        api_key=api_key,
    )


def try_issue_search(
    *,
    query: str,
    limit: int | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Search issues by text matching via the coordinator HTTP API."""
    payload: dict[str, Any] = {"query": query}
    if limit is not None:
        payload["limit"] = limit
    return _execute_single_endpoint_operation(
        operation="try_issue_search",
        capability_flag="CAN_ISSUES",
        method="POST",
        path="/issues/search",
        payload=payload,
        http_url=http_url,
        api_key=api_key,
    )


_ARCHETYPE_RESOLVE_REQUIRED_FIELDS = ("model", "system_prompt", "archetype", "reasons")


def try_resolve_archetype_for_phase(
    phase: str,
    signals: dict[str, Any] | None = None,
    *,
    http_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """Resolve archetype, model, and system_prompt for an autopilot phase.

    Returns the response body dict ``{model, system_prompt, archetype, reasons}``
    on HTTP 200, or ``None`` on any failure (missing URL, network error,
    timeout, non-200 status, malformed response). Failures emit a structured
    WARNING via the module logger and never raise.

    Spec: openspec/changes/add-per-phase-archetype-resolution/specs/
          agent-coordinator/spec.md -- Phase Archetype Resolution Bridge Helper.
    Design decisions: D4 (bridge helper), D9 (failure mode).
    """
    resolved_url = _resolve_http_url(http_url)
    if not resolved_url:
        logger.warning(
            "try_resolve_archetype_for_phase failed for phase=%s: missing_http_url; "
            "set COORDINATION_API_URL or AUTOPILOT_PHASE_MODEL_OVERRIDE to mitigate",
            phase,
        )
        return None

    resolved_key = _resolve_api_key(api_key)
    payload: dict[str, Any] = {"phase": phase, "signals": signals or {}}
    response = _http_request(
        method="POST",
        path="/archetypes/resolve_for_phase",
        payload=payload,
        http_url=resolved_url,
        api_key=resolved_key,
        timeout=timeout,
    )
    status = response.get("status_code")
    if status != 200:
        logger.warning(
            "try_resolve_archetype_for_phase failed for phase=%s: HTTP status=%s error=%s; "
            "phase will dispatch with harness defaults; set AUTOPILOT_PHASE_MODEL_OVERRIDE "
            "to force a specific model",
            phase,
            status,
            response.get("error"),
        )
        return None

    data = response.get("data")
    if not isinstance(data, dict):
        logger.warning(
            "try_resolve_archetype_for_phase failed for phase=%s: malformed_response "
            "(expected dict, got %s)",
            phase,
            type(data).__name__,
        )
        return None

    if not all(k in data for k in _ARCHETYPE_RESOLVE_REQUIRED_FIELDS):
        logger.warning(
            "try_resolve_archetype_for_phase failed for phase=%s: malformed_response "
            "(missing required fields; got keys=%s)",
            phase,
            sorted(data.keys()),
        )
        return None

    return data


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coordinator HTTP bridge helper")
    parser.add_argument(
        "command",
        choices=["detect"],
        help="Bridge helper command",
    )
    parser.add_argument("--http-url", help="Coordinator HTTP base URL")
    parser.add_argument("--api-key", help="Coordinator API key")
    args = parser.parse_args(argv)

    if args.command == "detect":
        print(
            json.dumps(
                detect_coordination(http_url=args.http_url, api_key=args.api_key),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
