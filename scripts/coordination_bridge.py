"""Transport-aware HTTP bridge for coordinator capability hooks.

This module keeps Web/Cloud coordination wiring stable for skill scripts.
Helpers return normalized dictionaries and degrade to ``status="skipped"``
when coordinator access is unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

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
)

_CAPABILITY_PROBES: dict[str, list[tuple[str, str, dict[str, Any] | None]]] = {
    # Empty payload intentionally triggers 422 on healthy endpoints and avoids
    # creating side effects during detection.
    "CAN_LOCK": [("POST", "/locks/acquire", {})],
    "CAN_QUEUE_WORK": [("POST", "/work/claim", {})],
    "CAN_HANDOFF": [
        ("POST", "/handoff/write", {}),
        ("POST", "/handoffs/write", {}),
        ("GET", "/handoffs/latest", None),
    ],
    "CAN_MEMORY": [("POST", "/memory/query", {})],
    "CAN_GUARDRAILS": [("POST", "/guardrails/check", {})],
}

_HANDOFF_WRITE_ENDPOINTS: list[tuple[str, str]] = [
    ("POST", "/handoff/write"),
    ("POST", "/handoffs/write"),
    ("POST", "/handoffs"),
]
_HANDOFF_READ_ENDPOINTS: list[tuple[str, str]] = [
    ("POST", "/handoff/read"),
    ("POST", "/handoffs/read"),
    ("GET", "/handoffs/latest"),
]


# SSRF Protection: URL Allowlist
#
# By default, only localhost addresses are allowed for coordinator URLs.
# For cloud deployments (e.g., Railway), add external hostnames via the
# COORDINATION_ALLOWED_HOSTS environment variable.
#
# Format: comma-separated hostnames (no scheme, no port)
# Example: COORDINATION_ALLOWED_HOSTS=your-app.railway.app,your-app-production.up.railway.app
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
    if extra_hosts_raw:
        allowed.update(h.strip().lower() for h in extra_hosts_raw.split(",") if h.strip())

    if hostname not in allowed:
        return None

    return url


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

    response = {
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
    headers = {"Accept": "application/json"}
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
