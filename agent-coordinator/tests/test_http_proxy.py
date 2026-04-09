"""Tests for the HTTP proxy transport module (src/http_proxy.py).

Covers:
- SSRF URL validation (PROXY-7)
- HttpProxyConfig loading from environment
- Startup probes (DB, HTTP API)
- Transport selection (STARTUP-1/2/3/4)
- Client lifecycle (init/get/shutdown)
- Error normalization (PROXY-3/4/5/6)
- Agent identity injection (PROXY-2)
- Representative proxy function behavior (PROXY-1)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from src import http_proxy
from src.http_proxy import (
    HttpProxyConfig,
    _error_response,
    _validate_url,
    probe_database,
    probe_http_api,
    select_transport,
)

# =============================================================================
# SSRF validation (PROXY-7)
# =============================================================================


def test_validate_url_allows_localhost() -> None:
    assert _validate_url("http://localhost:8081") == "http://localhost:8081"
    assert _validate_url("http://127.0.0.1:8081") == "http://127.0.0.1:8081"
    assert _validate_url("http://[::1]:8081") == "http://[::1]:8081"


def test_validate_url_rejects_bad_scheme() -> None:
    assert _validate_url("ftp://localhost") is None
    assert _validate_url("file:///etc/passwd") is None
    assert _validate_url("gopher://localhost") is None


def test_validate_url_rejects_unknown_host_without_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COORDINATION_ALLOWED_HOSTS", raising=False)
    assert _validate_url("https://evil.example.com") is None
    assert _validate_url("https://coord.rotkohl.ai") is None


def test_validate_url_allows_host_in_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "coord.rotkohl.ai")
    assert (
        _validate_url("https://coord.rotkohl.ai") == "https://coord.rotkohl.ai"
    )


def test_validate_url_supports_wildcard_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "*.rotkohl.ai")
    assert _validate_url("https://coord.rotkohl.ai") == "https://coord.rotkohl.ai"
    assert _validate_url("https://api.rotkohl.ai") == "https://api.rotkohl.ai"
    # Bare domain NOT matched by *.rotkohl.ai
    assert _validate_url("https://rotkohl.ai") is None


def test_validate_url_rejects_invalid_url() -> None:
    assert _validate_url("not a url") is None
    assert _validate_url("http://") is None


# =============================================================================
# HttpProxyConfig (D5)
# =============================================================================


def test_config_from_env_returns_none_when_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COORDINATION_API_URL", raising=False)
    assert HttpProxyConfig.from_env() is None


def test_config_from_env_returns_none_for_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COORDINATION_API_URL", "https://evil.example.com")
    monkeypatch.delenv("COORDINATION_ALLOWED_HOSTS", raising=False)
    assert HttpProxyConfig.from_env() is None


def test_config_from_env_loads_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setenv("COORDINATION_API_KEY", "test-key-123")
    monkeypatch.setenv("AGENT_ID", "test-agent")
    monkeypatch.setenv("AGENT_TYPE", "claude_code")
    monkeypatch.setenv("COORDINATION_HTTP_TIMEOUT", "10.0")

    config = HttpProxyConfig.from_env()
    assert config is not None
    assert config.base_url == "http://localhost:8081"
    assert config.api_key == "test-key-123"
    assert config.agent_id == "test-agent"
    assert config.agent_type == "claude_code"
    assert config.timeout == 10.0


def test_config_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081/")
    config = HttpProxyConfig.from_env()
    assert config is not None
    assert config.base_url == "http://localhost:8081"


# =============================================================================
# Startup probes (D1, STARTUP-1/2/3/4)
# =============================================================================


@pytest.mark.asyncio
async def test_probe_database_returns_false_for_empty_dsn() -> None:
    assert await probe_database("") is False


@pytest.mark.asyncio
async def test_probe_database_returns_false_on_connect_failure() -> None:
    # Non-existent port, should fail fast
    assert await probe_database(
        "postgresql://localhost:1/nope",
        timeout_seconds=0.5,
    ) is False


@pytest.mark.asyncio
async def test_probe_http_api_returns_false_for_empty_url() -> None:
    assert await probe_http_api("") is False


@pytest.mark.asyncio
async def test_probe_http_api_returns_true_on_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MockResp:
        status_code = 200

    class _MockClient:
        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, url: str) -> _MockResp:
            return _MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
    assert await probe_http_api("http://localhost:8081") is True


@pytest.mark.asyncio
async def test_probe_http_api_returns_false_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MockResp:
        status_code = 503

    class _MockClient:
        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, url: str) -> _MockResp:
            return _MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
    assert await probe_http_api("http://localhost:8081") is False


@pytest.mark.asyncio
async def test_select_transport_prefers_db_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STARTUP-1: DB available → transport = 'db'."""
    monkeypatch.setattr(http_proxy, "probe_database", AsyncMock(return_value=True))
    monkeypatch.setattr(http_proxy, "probe_http_api", AsyncMock(return_value=True))
    assert await select_transport("postgresql://localhost/db", "http://localhost:8081") == "db"


@pytest.mark.asyncio
async def test_select_transport_falls_back_to_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STARTUP-2: DB unreachable, HTTP reachable → transport = 'http'."""
    monkeypatch.setattr(http_proxy, "probe_database", AsyncMock(return_value=False))
    monkeypatch.setattr(http_proxy, "probe_http_api", AsyncMock(return_value=True))
    assert await select_transport("postgresql://localhost/db", "http://localhost:8081") == "http"


@pytest.mark.asyncio
async def test_select_transport_defaults_db_when_neither_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STARTUP-3: Neither reachable → transport = 'db' (preserve existing failure mode)."""
    monkeypatch.setattr(http_proxy, "probe_database", AsyncMock(return_value=False))
    monkeypatch.setattr(http_proxy, "probe_http_api", AsyncMock(return_value=False))
    assert await select_transport("postgresql://localhost/db", "") == "db"
    assert (
        await select_transport(
            "postgresql://localhost/db", "http://localhost:8081"
        )
        == "db"
    )


# =============================================================================
# Client lifecycle
# =============================================================================


@pytest.fixture()
def _reset_client() -> Any:
    yield
    import asyncio

    if http_proxy._client is not None:
        try:
            asyncio.get_event_loop().run_until_complete(http_proxy.shutdown_client())
        except Exception:
            pass
    http_proxy._config = None
    http_proxy._client = None


def test_get_config_raises_when_not_initialised(_reset_client: None) -> None:
    http_proxy._config = None
    with pytest.raises(RuntimeError, match="not initialised"):
        http_proxy.get_config()


def test_get_client_raises_when_not_initialised(_reset_client: None) -> None:
    http_proxy._client = None
    with pytest.raises(RuntimeError, match="not initialised"):
        http_proxy.get_client()


def test_init_client_sets_module_state(_reset_client: None) -> None:
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key="test-key",
        agent_id="test-agent",
        agent_type="claude_code",
    )
    http_proxy.init_client(config)
    assert http_proxy.get_config() is config
    assert http_proxy.get_client() is not None


# =============================================================================
# Error normalization (PROXY-3/4/5/6)
# =============================================================================


def test_error_response_structure() -> None:
    result = _error_response("timeout", path="/locks/acquire")
    assert result == {"success": False, "error": "timeout", "path": "/locks/acquire"}


@pytest.mark.asyncio
async def test_request_maps_timeout(_reset_client: None) -> None:
    """PROXY-4: Timeout → error='timeout'."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    async def _raise_timeout(*args: Any, **kw: Any) -> Any:
        raise httpx.TimeoutException("timed out")

    http_proxy.get_client().request = _raise_timeout  # type: ignore[method-assign]
    result = await http_proxy._request("POST", "/locks/acquire", json_body={})
    assert result["success"] is False
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_request_maps_connection_error(_reset_client: None) -> None:
    """PROXY-6: Network error → error='connection_error'."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    async def _raise_connect(*args: Any, **kw: Any) -> Any:
        raise httpx.ConnectError("refused")

    http_proxy.get_client().request = _raise_connect  # type: ignore[method-assign]
    result = await http_proxy._request("POST", "/locks/acquire", json_body={})
    assert result["success"] is False
    assert result["error"] == "connection_error"
    assert "refused" in result["detail"]


@pytest.mark.asyncio
async def test_request_maps_401_to_auth_failure(_reset_client: None) -> None:
    """PROXY-5: 401 → error='authentication_failed'."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    class _MockResponse:
        status_code = 401
        text = '{"detail": "unauthorized"}'

        def json(self) -> dict[str, Any]:
            return {"detail": "unauthorized"}

    async def _return_401(*args: Any, **kw: Any) -> _MockResponse:
        return _MockResponse()

    http_proxy.get_client().request = _return_401  # type: ignore[method-assign]
    result = await http_proxy._request("POST", "/locks/acquire", json_body={})
    assert result["success"] is False
    assert result["error"] == "authentication_failed"
    assert result["status_code"] == 401


@pytest.mark.asyncio
async def test_request_maps_other_http_errors(_reset_client: None) -> None:
    """PROXY-3: 4xx/5xx → error='http_N'."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    class _MockResponse:
        status_code = 500
        text = '{"detail": "server error"}'

        def json(self) -> dict[str, Any]:
            return {"detail": "server error"}

    async def _return_500(*args: Any, **kw: Any) -> _MockResponse:
        return _MockResponse()

    http_proxy.get_client().request = _return_500  # type: ignore[method-assign]
    result = await http_proxy._request("POST", "/locks/acquire", json_body={})
    assert result["success"] is False
    assert result["error"] == "http_500"
    assert result["status_code"] == 500


@pytest.mark.asyncio
async def test_request_returns_parsed_json_on_success(_reset_client: None) -> None:
    """Success case: 2xx response returns parsed JSON."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    class _MockResponse:
        status_code = 200
        text = '{"success": true, "action": "acquired"}'

        def json(self) -> dict[str, Any]:
            return {"success": True, "action": "acquired"}

    async def _return_200(*args: Any, **kw: Any) -> _MockResponse:
        return _MockResponse()

    http_proxy.get_client().request = _return_200  # type: ignore[method-assign]
    result = await http_proxy._request("POST", "/locks/acquire", json_body={})
    assert result["success"] is True
    assert result["action"] == "acquired"


# =============================================================================
# Agent identity injection (PROXY-2)
# =============================================================================


def test_agent_identity_returns_config_values(_reset_client: None) -> None:
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="my-agent",
        agent_type="claude_code",
    )
    http_proxy.init_client(config)
    identity = http_proxy._agent_identity()
    assert identity == {"agent_id": "my-agent", "agent_type": "claude_code"}


# =============================================================================
# Proxy function integration (PROXY-1)
# =============================================================================


@pytest.mark.asyncio
async def test_proxy_acquire_lock_routes_to_http(_reset_client: None) -> None:
    """PROXY-1: proxy_acquire_lock sends POST /locks/acquire with identity."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key="test-key",
        agent_id="my-agent",
        agent_type="claude_code",
    )
    http_proxy.init_client(config)

    captured: dict[str, Any] = {}

    class _MockResponse:
        status_code = 200
        text = '{"success": true, "action": "acquired", "file_path": "x.py"}'

        def json(self) -> dict[str, Any]:
            return {"success": True, "action": "acquired", "file_path": "x.py"}

    async def _capture(method: str, url: str, **kw: Any) -> _MockResponse:
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResponse()

    http_proxy.get_client().request = _capture  # type: ignore[method-assign]

    result = await http_proxy.proxy_acquire_lock(
        file_path="src/main.py",
        reason="test",
        ttl_minutes=30,
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "/locks/acquire"
    assert captured["json"]["file_path"] == "src/main.py"
    assert captured["json"]["reason"] == "test"
    assert captured["json"]["ttl_minutes"] == 30
    assert captured["json"]["agent_id"] == "my-agent"
    assert captured["json"]["agent_type"] == "claude_code"
    assert result["success"] is True


# =============================================================================
# MCP Resources in Proxy Mode (D6)
# =============================================================================


def test_resource_unavailable_constant_defined_and_used() -> None:
    """D6: MCP resources return a not-available message when transport is http.

    Verifies (a) the constant is defined with the expected message and (b) every
    ``@mcp.resource`` in coordination_mcp.py has the transport check in its body.

    Note: FastMCP wraps ``@mcp.resource`` functions in FunctionResource objects,
    so we cannot invoke them directly from tests. Instead we verify the source
    contains the routing for every resource definition.
    """
    from src import coordination_mcp

    assert hasattr(coordination_mcp, "_RESOURCE_UNAVAILABLE_IN_PROXY_MODE")
    assert "unavailable in HTTP proxy mode" in (
        coordination_mcp._RESOURCE_UNAVAILABLE_IN_PROXY_MODE
    )

    # Source-level check: every @mcp.resource definition should have the guard
    import inspect

    src = inspect.getsource(coordination_mcp)
    resource_count = src.count("@mcp.resource(")
    guard_count = src.count("return _RESOURCE_UNAVAILABLE_IN_PROXY_MODE")
    assert resource_count == guard_count, (
        f"Mismatch: {resource_count} resources but {guard_count} guards"
    )


@pytest.mark.asyncio
async def test_proxy_check_locks_transforms_http_shape(_reset_client: None) -> None:
    """proxy_check_locks transforms HTTP per-file shape to flat MCP list.

    Regression: the HTTP endpoint returns {"locked": bool, "file_path", "lock": {...}}
    but the MCP tool expects a flat list of {file_path, locked_by, agent_type, ...}.
    Also: unlocked files should be filtered out, matching MCP semantics.
    """
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="agent-x",
        agent_type="claude_code",
    )
    http_proxy.init_client(config)

    # Mock three file lookups: one locked, one unlocked, one error
    responses = {
        "src/locked.py": (
            200,
            {
                "locked": True,
                "file_path": "src/locked.py",
                "lock": {
                    "locked_by": "other-agent",
                    "agent_type": "codex",
                    "locked_at": "2026-04-09T10:00:00",
                    "expires_at": "2026-04-09T12:00:00",
                    "reason": "editing",
                },
            },
        ),
        "src/free.py": (200, {"locked": False, "file_path": "src/free.py"}),
        "src/error.py": (500, {"detail": "internal error"}),
    }

    class _MockResponse:
        def __init__(self, status: int, body: dict[str, Any]) -> None:
            self.status_code = status
            self._body = body
            self.text = str(body)

        def json(self) -> dict[str, Any]:
            return self._body

    async def _route(method: str, url: str, **kw: Any) -> _MockResponse:
        # URL is relative to base_url; strip the /locks/status/ prefix
        prefix = "/locks/status/"
        assert url.startswith(prefix), f"unexpected url {url}"
        path = url[len(prefix):]
        # URL-decoded path should match our test keys
        from urllib.parse import unquote
        path = unquote(path)
        status, body = responses[path]
        return _MockResponse(status, body)

    http_proxy.get_client().request = _route  # type: ignore[method-assign]

    result = await http_proxy.proxy_check_locks(
        ["src/locked.py", "src/free.py", "src/error.py"]
    )

    # Only the locked file should be returned
    assert len(result) == 1
    assert result[0]["file_path"] == "src/locked.py"
    assert result[0]["locked_by"] == "other-agent"
    assert result[0]["agent_type"] == "codex"
    assert result[0]["locked_at"] == "2026-04-09T10:00:00"
    assert result[0]["expires_at"] == "2026-04-09T12:00:00"
    assert result[0]["reason"] == "editing"


@pytest.mark.asyncio
async def test_proxy_check_locks_url_encodes_paths(_reset_client: None) -> None:
    """proxy_check_locks URL-encodes file paths while preserving forward slashes."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    captured: dict[str, str] = {}

    class _MockResponse:
        status_code = 200
        text = '{"locked": false}'

        def json(self) -> dict[str, Any]:
            return {"locked": False, "file_path": "x"}

    async def _capture(method: str, url: str, **kw: Any) -> _MockResponse:
        captured["url"] = url
        return _MockResponse()

    http_proxy.get_client().request = _capture  # type: ignore[method-assign]
    await http_proxy.proxy_check_locks(["src/has space.py"])
    # %20 is the URL encoding for a space; forward slashes preserved
    assert captured["url"] == "/locks/status/src/has%20space.py"


@pytest.mark.asyncio
async def test_proxy_list_scenarios_unwraps_scenarios_key(
    _reset_client: None,
) -> None:
    """proxy_list_scenarios unwraps the HTTP {scenarios: [...]} envelope.

    Regression: MCP list_scenarios returns json.dumps of a raw list, but the
    HTTP endpoint wraps scenarios in {"scenarios": [...]}. The proxy must
    unwrap so downstream json.dumps produces the expected shape.
    """
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    class _MockResponse:
        status_code = 200
        text = '{"scenarios": []}'

        def json(self) -> dict[str, Any]:
            return {
                "scenarios": [
                    {"id": "s1", "name": "lock-ack", "category": "lock-lifecycle"},
                    {"id": "s2", "name": "auth-deny", "category": "auth"},
                ]
            }

    async def _return(*args: Any, **kw: Any) -> _MockResponse:
        return _MockResponse()

    http_proxy.get_client().request = _return  # type: ignore[method-assign]

    result = await http_proxy.proxy_list_scenarios()
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "s1"
    assert result[1]["id"] == "s2"


@pytest.mark.asyncio
async def test_proxy_list_scenarios_preserves_error_dict(
    _reset_client: None,
) -> None:
    """On error, proxy_list_scenarios returns the error dict unchanged."""
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    async def _fail(*args: Any, **kw: Any) -> None:
        raise httpx.ConnectError("refused")

    http_proxy.get_client().request = _fail  # type: ignore[method-assign]

    result = await http_proxy.proxy_list_scenarios()
    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "connection_error"


@pytest.mark.asyncio
async def test_proxy_check_locks_returns_empty_list_for_none(
    _reset_client: None,
) -> None:
    """proxy_check_locks returns empty list when file_paths is None.

    The HTTP API has no 'list all locks' endpoint, so we gracefully degrade.
    """
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="x",
        agent_type="y",
    )
    http_proxy.init_client(config)

    result = await http_proxy.proxy_check_locks(None)
    assert result == []


@pytest.mark.asyncio
async def test_proxy_release_lock_sends_identity(_reset_client: None) -> None:
    config = HttpProxyConfig(
        base_url="http://localhost:8081",
        api_key=None,
        agent_id="agent-x",
        agent_type="claude_code",
    )
    http_proxy.init_client(config)

    captured: dict[str, Any] = {}

    class _MockResponse:
        status_code = 200
        text = '{"success": true}'

        def json(self) -> dict[str, Any]:
            return {"success": True}

    async def _capture(method: str, url: str, **kw: Any) -> _MockResponse:
        captured["json"] = kw.get("json")
        return _MockResponse()

    http_proxy.get_client().request = _capture  # type: ignore[method-assign]
    await http_proxy.proxy_release_lock("x.py")
    assert captured["json"]["agent_id"] == "agent-x"
    assert captured["json"]["file_path"] == "x.py"
