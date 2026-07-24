"""Contract parity tests for HTTP, direct MCP, and proxy code search."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from src import coordination_mcp, http_proxy
from src.code_search import (
    CodeSearchForbiddenError,
    CodeSearchResponse,
    CodeSearchState,
    Fallback,
    RequestedIdentity,
    ScopeDisposition,
)
from src.code_search_runtime import (
    CodeSearchOverloadedError,
    CodeSearchStatus,
    set_code_search_runtime,
)
from src.coordination_api import create_coordination_api

API_KEY = "secret"
REQUEST = {
    "query": "find readiness",
    "repo_slug": "agentic_coding_tools",
    "source_revision": "a" * 40,
    "namespace": {"kind": "main", "key": "main"},
    "scope": {"kind": "explicit", "read_allow": ["agent-coordinator/**"]},
    "limit": 10,
    "offset": 0,
}
FORBIDDEN_PROBLEM = {
    "type": "urn:coordinator:code-search:forbidden",
    "title": "Code-search scope is not authorized",
    "status": 403,
    "detail": "The principal has no code-search grant for this repository.",
}
OVERLOADED_PROBLEM = {
    "type": "urn:coordinator:code-search:overloaded",
    "title": "Code search is busy",
    "status": 429,
    "detail": "Retry semantic search after the indicated delay.",
}


class _Runtime:
    def __init__(self, response: CodeSearchResponse | None = None) -> None:
        self.response = response or _unavailable()
        self.principals: list[str] = []

    async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
        assert request.repo_slug == "agentic_coding_tools"
        self.principals.append(principal_id)
        return self.response

    async def status(self) -> CodeSearchStatus:
        return CodeSearchStatus(
            available=False,
            state="unavailable",
            reason="no_usable_index",
            usable_index_count=0,
        )


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERGE_TRAIN_SWEEP_DISABLED", "1")
    monkeypatch.setenv("MERGE_WATCHER_DISABLED", "1")
    monkeypatch.setenv("CODE_SEARCH_ENABLED", "1")
    monkeypatch.setenv("COORDINATION_API_KEYS", API_KEY)
    monkeypatch.setenv(
        "COORDINATION_API_KEY_IDENTITIES",
        '{"secret":{"agent_id":"bound-agent","agent_type":"codex"}}',
    )
    set_code_search_runtime(None)
    yield
    set_code_search_runtime(None)


def test_http_requires_auth_binds_principal_and_returns_typed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    set_code_search_runtime(runtime)
    monkeypatch.setattr(
        "src.coordination_api.start_code_search_runtime",
        _keep_runtime,
        raising=False,
    )
    monkeypatch.setattr(
        "src.coordination_api.stop_code_search_runtime",
        _no_op,
        raising=False,
    )
    app = create_coordination_api()

    with TestClient(app) as client:
        assert client.post("/search/code", json=REQUEST).status_code == 401
        response = client.post(
            "/search/code",
            json=REQUEST,
            headers={"X-Coordinator-API-Key": API_KEY},
        )
        assert response.status_code == 200
        assert response.json() == _unavailable().to_dict()
        assert client.get("/search/code/status").json() == {
            "available": False,
            "state": "unavailable",
            "reason": "no_usable_index",
            "usable_index_count": 0,
        }
    assert runtime.principals == ["bound-agent"]
    assert API_KEY not in runtime.principals


def test_disabled_http_search_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODE_SEARCH_ENABLED")
    app = create_coordination_api()
    with TestClient(app) as client:
        response = client.post(
            "/search/code",
            json=REQUEST,
        )
    assert response.status_code == 404


def test_disabled_mcp_does_not_register_search_tool() -> None:
    environment = dict(os.environ)
    environment.pop("CODE_SEARCH_ENABLED", None)
    coordinator = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import asyncio, sys\n"
                "from src.coordination_mcp import mcp\n"
                "async def main():\n"
                " tools = await mcp.list_tools()\n"
                " print(any(tool.name == 'search_code' for tool in tools))\n"
                " print('src.code_search' in sys.modules)\n"
                " print(any(name == 'code_search_pkg' or name.startswith('code_search_pkg.') "
                "for name in sys.modules))\n"
                "asyncio.run(main())\n"
            ),
        ],
        cwd=coordinator,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == ["False", "False", "False"]


def test_http_rejects_malformed_cross_grant_and_overload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRuntime(_Runtime):
        failure: Exception

        async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
            raise self.failure

    runtime = FailingRuntime()
    set_code_search_runtime(runtime)
    monkeypatch.setattr(
        "src.coordination_api.start_code_search_runtime",
        _keep_runtime,
        raising=False,
    )
    monkeypatch.setattr(
        "src.coordination_api.stop_code_search_runtime",
        _no_op,
        raising=False,
    )
    app = create_coordination_api()
    headers = {"X-Coordinator-API-Key": API_KEY}
    with TestClient(app) as client:
        malformed = {**REQUEST, "scope": {"kind": "explicit", "read_allow": ["./bad"]}}
        assert client.post("/search/code", json=malformed, headers=headers).status_code == 422

        runtime.failure = CodeSearchForbiddenError(
            "The principal has no code-search grant for this repository."
        )
        assert client.post("/search/code", json=REQUEST, headers=headers).status_code == 403

        runtime.failure = CodeSearchOverloadedError()
        response = client.post("/search/code", json=REQUEST, headers=headers)
        assert response.status_code == 429
        assert response.headers["retry-after"] == "2"


def test_http_errors_use_frozen_problem_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRuntime(_Runtime):
        failure: Exception

        async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
            raise self.failure

    runtime = FailingRuntime()
    set_code_search_runtime(runtime)
    monkeypatch.setattr(
        "src.coordination_api.start_code_search_runtime",
        _keep_runtime,
        raising=False,
    )
    monkeypatch.setattr(
        "src.coordination_api.stop_code_search_runtime",
        _no_op,
        raising=False,
    )
    app = create_coordination_api()
    headers = {"X-Coordinator-API-Key": API_KEY}

    with TestClient(app) as client:
        unauthorized = client.post("/search/code", json=REQUEST)
        malformed = {**REQUEST, "scope": {"kind": "explicit", "read_allow": ["./bad"]}}
        invalid = client.post("/search/code", json=malformed, headers=headers)

        runtime.failure = CodeSearchForbiddenError(FORBIDDEN_PROBLEM["detail"])
        forbidden = client.post("/search/code", json=REQUEST, headers=headers)

        runtime.failure = CodeSearchOverloadedError()
        overloaded = client.post("/search/code", json=REQUEST, headers=headers)

    monkeypatch.delenv("CODE_SEARCH_ENABLED")
    disabled_app = create_coordination_api()
    with TestClient(disabled_app) as client:
        disabled = client.post("/search/code", json=REQUEST)

    expected = [
        (
            unauthorized,
            {
                "type": "urn:coordinator:authentication:required",
                "title": "Authentication required",
                "status": 401,
                "detail": "A valid coordinator credential is required.",
            },
        ),
        (
            disabled,
            {
                "type": "urn:coordinator:code-search:disabled",
                "title": "Code search disabled",
                "status": 404,
                "detail": "Semantic code search is disabled.",
            },
        ),
        (forbidden, FORBIDDEN_PROBLEM),
        (
            invalid,
            {
                "type": "urn:coordinator:code-search:invalid-request",
                "title": "Invalid code-search request",
                "status": 422,
                "detail": "A full source revision and authoritative scope are required.",
            },
        ),
        (overloaded, OVERLOADED_PROBLEM),
    ]
    for response, problem in expected:
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json() == problem
    assert overloaded.headers["retry-after"] == "2"


@pytest.mark.asyncio
async def test_direct_mcp_and_proxy_forward_identical_v2_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _Runtime()
    set_code_search_runtime(runtime)
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_agent_id", lambda: "local-agent")

    direct = await coordination_mcp.search_code(**REQUEST)
    captured: dict[str, Any] = {}

    async def request(_method: str, _path: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        captured.update(json_body)
        return direct

    monkeypatch.setattr(http_proxy, "_request", request)
    proxied = await http_proxy.proxy_search_code(**REQUEST)

    assert proxied == direct == _unavailable().to_dict()
    assert captured == REQUEST
    assert runtime.principals == ["local-agent"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "proxy_error", "problem"),
    [
        (
            CodeSearchForbiddenError(FORBIDDEN_PROBLEM["detail"]),
            {
                "success": False,
                "error": "http_403",
                "status_code": 403,
                "detail": FORBIDDEN_PROBLEM,
            },
            FORBIDDEN_PROBLEM,
        ),
        (
            CodeSearchOverloadedError(),
            {
                "success": False,
                "error": "http_429",
                "status_code": 429,
                "detail": OVERLOADED_PROBLEM,
                "retry_after": 2,
            },
            {**OVERLOADED_PROBLEM, "retry_after": 2},
        ),
    ],
)
async def test_direct_and_proxy_mcp_preserve_expected_error_semantics(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    proxy_error: dict[str, Any],
    problem: dict[str, Any],
) -> None:
    class FailingRuntime(_Runtime):
        async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
            raise failure

    set_code_search_runtime(FailingRuntime())
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_agent_id", lambda: "local-agent")
    direct = await coordination_mcp.search_code(**REQUEST)

    async def request(_method: str, _path: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        return proxy_error

    monkeypatch.setattr(http_proxy, "_request", request)
    proxied = await http_proxy.proxy_search_code(**REQUEST)

    assert direct == proxied == problem


@pytest.mark.asyncio
async def test_proxy_transport_carries_http_retry_signal_to_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        async def request(self, **_kwargs: Any) -> httpx.Response:
            return httpx.Response(
                status_code=429,
                json=OVERLOADED_PROBLEM,
                headers={"Retry-After": "2"},
                request=httpx.Request("POST", "http://coordinator/search/code"),
            )

    monkeypatch.setattr(http_proxy, "get_client", Client)
    normalized = await http_proxy._request("POST", "/search/code", json_body=REQUEST)

    async def request(_method: str, _path: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        return normalized

    monkeypatch.setattr(http_proxy, "_request", request)
    response = await http_proxy.proxy_search_code(**REQUEST)

    assert response == {**OVERLOADED_PROBLEM, "retry_after": 2}


@pytest.mark.asyncio
async def test_unexpected_direct_mcp_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRuntime(_Runtime):
        async def search(self, request: Any, *, principal_id: str) -> CodeSearchResponse:
            raise RuntimeError("postgresql://user:secret@host/database")

    set_code_search_runtime(BrokenRuntime())
    monkeypatch.setattr(coordination_mcp, "_transport", "db")
    monkeypatch.setattr(coordination_mcp, "get_agent_id", lambda: "local-agent")

    response = await coordination_mcp.search_code(**REQUEST)
    rendered = str(response)
    assert response["state"] == CodeSearchState.UNAVAILABLE
    assert "secret" not in rendered
    assert "postgresql" not in rendered


@pytest.mark.asyncio
async def test_proxy_transport_failure_uses_same_sanitized_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def request(_method: str, _path: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "error": "network_error",
            "detail": "postgresql://user:secret@host/database",
        }

    monkeypatch.setattr(http_proxy, "_request", request)
    response = await http_proxy.proxy_search_code(**REQUEST)

    assert response == _unavailable().to_dict()
    assert "secret" not in str(response)


async def _keep_runtime() -> _Runtime:
    from src.code_search_runtime import get_code_search_runtime

    return get_code_search_runtime()  # type: ignore[return-value]


async def _no_op() -> None:
    return None


def _unavailable() -> CodeSearchResponse:
    return CodeSearchResponse(
        state=CodeSearchState.UNAVAILABLE,
        current=False,
        request=RequestedIdentity(
            repo_slug="agentic_coding_tools",
            source_revision="a" * 40,
            namespace={"kind": "main", "key": "main"},
            index_id=None,
        ),
        index=None,
        scope=ScopeDisposition(
            decision="allowed",
            source="explicit",
            authority="principal_grant",
        ),
        results=[],
        fallback=Fallback(required=True, reason=CodeSearchState.UNAVAILABLE),
    )
