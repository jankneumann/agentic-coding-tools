"""Unit tests for gen-eval transport clients with mocked backends."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.gen_eval.clients import (
    CliClient,
    DbClient,
    HttpClient,
    McpClient,
    StepContext,
    StepResult,
    TransportClient,
    TransportClientRegistry,
    WaitClient,
)
from evaluation.gen_eval.descriptor import AuthConfig
from evaluation.gen_eval.models import ActionStep

# ======================================================================
# StepResult / StepContext
# ======================================================================


class TestStepResult:
    def test_defaults(self) -> None:
        r = StepResult()
        assert r.status_code is None
        assert r.body == {}
        assert r.headers == {}
        assert r.exit_code is None
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_populated(self) -> None:
        r = StepResult(status_code=200, body={"ok": True}, duration_ms=12.5)
        assert r.status_code == 200
        assert r.body["ok"] is True


class TestStepContext:
    def test_defaults(self) -> None:
        c = StepContext()
        assert c.variables == {}
        assert c.timeout_seconds == 30.0

    def test_with_variables(self) -> None:
        c = StepContext(variables={"lock_id": "abc"}, timeout_seconds=10.0)
        assert c.variables["lock_id"] == "abc"


# ======================================================================
# TransportClientRegistry
# ======================================================================


class TestTransportClientRegistry:
    @pytest.mark.asyncio
    async def test_register_and_execute(self) -> None:
        registry = TransportClientRegistry()
        mock_client = AsyncMock(spec=TransportClient)
        mock_client.execute.return_value = StepResult(status_code=200)

        registry.register("http", mock_client)
        assert "http" in registry.transports

        step = ActionStep(id="s1", transport="http", method="GET", endpoint="/health")
        ctx = StepContext()
        result = await registry.execute("http", step, ctx)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_transport(self) -> None:
        registry = TransportClientRegistry()
        step = ActionStep(id="s1", transport="http", method="GET", endpoint="/")
        ctx = StepContext()
        result = await registry.execute("http", step, ctx)
        assert result.error is not None
        assert "No client registered" in result.error

    @pytest.mark.asyncio
    async def test_health_check_all(self) -> None:
        registry = TransportClientRegistry()
        healthy = AsyncMock()
        healthy.health_check.return_value = True
        unhealthy = AsyncMock()
        unhealthy.health_check.return_value = False

        registry.register("http", healthy)
        registry.register("mcp", unhealthy)

        results = await registry.health_check_all()
        assert results["http"] is True
        assert results["mcp"] is False

    @pytest.mark.asyncio
    async def test_cleanup_all(self) -> None:
        registry = TransportClientRegistry()
        c1 = AsyncMock()
        c2 = AsyncMock()
        registry.register("http", c1)
        registry.register("cli", c2)
        await registry.cleanup_all()
        c1.cleanup.assert_awaited_once()
        c2.cleanup.assert_awaited_once()

    def test_get(self) -> None:
        registry = TransportClientRegistry()
        assert registry.get("http") is None
        mock = AsyncMock()
        registry.register("http", mock)
        assert registry.get("http") is mock


# ======================================================================
# HttpClient
# ======================================================================


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        client = HttpClient(base_url="http://localhost:8081")
        step = ActionStep(id="s1", transport="http", method="GET", endpoint="/health")
        ctx = StepContext()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"status": "ok"}'

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            # Pre-create the internal client so the mock is used
            import httpx

            client._client = httpx.AsyncClient(base_url="http://localhost:8081")
            with patch.object(client._client, "request", new_callable=AsyncMock) as m:
                m.return_value = mock_response
                result = await client.execute(step, ctx)

        assert result.status_code == 200
        assert result.body["status"] == "ok"
        assert result.error is None
        assert result.duration_ms > 0
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_auth_injection_api_key(self) -> None:
        auth = AuthConfig(type="api_key", header="X-API-Key", value="secret123")
        client = HttpClient(base_url="http://localhost:8081", auth=auth)
        headers = client._resolve_auth_headers()
        assert headers == {"X-API-Key": "secret123"}
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_auth_injection_bearer(self) -> None:
        auth = AuthConfig(type="bearer", header="Authorization", value="tok")
        client = HttpClient(base_url="http://localhost:8081", auth=auth)
        headers = client._resolve_auth_headers()
        assert headers == {"Authorization": "Bearer tok"}

    @pytest.mark.asyncio
    async def test_auth_injection_env_var(self) -> None:
        auth = AuthConfig(type="api_key", header="X-Key", env_var="TEST_KEY_12345")
        client = HttpClient(base_url="http://localhost:8081", auth=auth)
        with patch.dict("os.environ", {"TEST_KEY_12345": "from-env"}):
            headers = client._resolve_auth_headers()
        assert headers == {"X-Key": "from-env"}

    @pytest.mark.asyncio
    async def test_auth_none(self) -> None:
        client = HttpClient(base_url="http://localhost:8081")
        assert client._resolve_auth_headers() == {}

    def test_variable_interpolation(self) -> None:
        result = HttpClient._interpolate("/locks/${lock_id}/release", {"lock_id": "abc"})
        assert result == "/locks/abc/release"

    def test_body_interpolation(self) -> None:
        body = {"lock_id": "${lock_id}", "agent": "test"}
        result = HttpClient._interpolate_body(body, {"lock_id": "xyz"})
        assert result == {"lock_id": "xyz", "agent": "test"}

    def test_body_interpolation_nested_dict(self) -> None:
        body = {"outer": {"inner": "${val}"}, "plain": "ok"}
        result = HttpClient._interpolate_body(body, {"val": "deep"})
        assert result == {"outer": {"inner": "deep"}, "plain": "ok"}

    def test_body_interpolation_nested_list(self) -> None:
        body = {"items": ["${a}", "${b}"], "count": 2}
        result = HttpClient._interpolate_body(body, {"a": "x", "b": "y"})
        assert result == {"items": ["x", "y"], "count": 2}

    def test_body_interpolation_deeply_nested(self) -> None:
        body = {"l1": {"l2": [{"l3": "${v}"}]}}
        result = HttpClient._interpolate_body(body, {"v": "found"})
        assert result == {"l1": {"l2": [{"l3": "found"}]}}

    def test_body_interpolation_none(self) -> None:
        result = HttpClient._interpolate_body(None, {"k": "v"})
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_dict_body_sent_as_json(self) -> None:
        """L4: An intentional empty dict body {} should be sent as JSON, not None."""
        client = HttpClient(base_url="http://localhost:8081")
        step = ActionStep(id="s1", transport="http", method="POST", endpoint="/test", body={})
        ctx = StepContext()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.headers = {"content-type": "application/json"}

        import httpx

        client._client = httpx.AsyncClient(base_url="http://localhost:8081")
        with patch.object(client._client, "request", new_callable=AsyncMock) as m:
            m.return_value = mock_response
            await client.execute(step, ctx)
            # Verify json={} was passed, not json=None
            call_kwargs = m.call_args
            assert call_kwargs.kwargs.get("json") == {} or call_kwargs[1].get("json") == {}
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_execute_error(self) -> None:
        client = HttpClient(base_url="http://localhost:8081")
        step = ActionStep(id="s1", transport="http", method="GET", endpoint="/fail")
        ctx = StepContext()

        import httpx

        client._client = httpx.AsyncClient(base_url="http://localhost:8081")
        with patch.object(
            client._client, "request", new_callable=AsyncMock, side_effect=Exception("conn refused")
        ):
            result = await client.execute(step, ctx)

        assert result.error is not None
        assert "conn refused" in result.error
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        client = HttpClient(base_url="http://localhost:8081")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        import httpx

        client._client = httpx.AsyncClient(base_url="http://localhost:8081")
        with patch.object(client._client, "get", new_callable=AsyncMock) as m:
            m.return_value = mock_resp
            assert await client.health_check() is True
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        client = HttpClient(base_url="http://localhost:8081")
        import httpx

        client._client = httpx.AsyncClient(base_url="http://localhost:8081")
        with patch.object(
            client._client, "get", new_callable=AsyncMock, side_effect=Exception("down")
        ):
            assert await client.health_check() is False
        await client.cleanup()


# ======================================================================
# McpClient
# ======================================================================


class TestMcpClient:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        client = McpClient(mcp_url="http://localhost:8082/sse")

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = {"lock_id": "abc123"}
        client._client = mock_mcp

        step = ActionStep(
            id="s1",
            transport="mcp",
            tool="acquire_lock",
            params={"file_path": "src/main.py"},
        )
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is None
        assert result.body["lock_id"] == "abc123"
        mock_mcp.call_tool.assert_awaited_once_with("acquire_lock", {"file_path": "src/main.py"})

    @pytest.mark.asyncio
    async def test_execute_no_tool(self) -> None:
        client = McpClient(mcp_url="http://localhost:8082/sse")
        client._client = AsyncMock()
        step = ActionStep(id="s1", transport="mcp")
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is not None
        assert "No tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_list_result(self) -> None:
        """fastmcp may return list of content blocks."""
        client = McpClient(mcp_url="http://localhost:8082/sse")
        mock_mcp = AsyncMock()

        # Simulate content block with .text attribute
        block = MagicMock()
        block.text = "lock acquired"
        mock_mcp.call_tool.return_value = [block]
        client._client = mock_mcp

        step = ActionStep(id="s1", transport="mcp", tool="acquire_lock", params={})
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.body == {"result": "lock acquired"}

    @pytest.mark.asyncio
    async def test_execute_variable_substitution(self) -> None:
        client = McpClient(mcp_url="http://localhost:8082/sse")
        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = {"ok": True}
        client._client = mock_mcp

        step = ActionStep(
            id="s1",
            transport="mcp",
            tool="release_lock",
            params={"lock_id": "${lock_id}"},
        )
        ctx = StepContext(variables={"lock_id": "abc123"})
        await client.execute(step, ctx)
        mock_mcp.call_tool.assert_awaited_once_with("release_lock", {"lock_id": "abc123"})

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        client = McpClient(mcp_url="http://localhost:8082/sse")
        mock_mcp = AsyncMock()
        mock_mcp.list_tools.return_value = [{"name": "tool1"}]
        client._client = mock_mcp
        assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        client = McpClient(mcp_url="http://localhost:8082/sse")
        mock_mcp = AsyncMock()
        client._client = mock_mcp
        await client.cleanup()
        assert client._client is None


# ======================================================================
# CliClient
# ======================================================================


class TestCliClient:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        client = CliClient(command="echo", json_flag=None)
        step = ActionStep(
            id="s1",
            transport="cli",
            command=None,
            args=[json.dumps({"result": "ok"})],
        )
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.exit_code == 0
        assert result.body.get("result") == "ok"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_non_json(self) -> None:
        client = CliClient(command="echo", json_flag=None)
        step = ActionStep(id="s1", transport="cli", args=["hello world"])
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.exit_code == 0
        assert "raw" in result.body

    @pytest.mark.asyncio
    async def test_execute_failure_exit_code(self) -> None:
        client = CliClient(command="false")
        step = ActionStep(id="s1", transport="cli")
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_execute_timeout(self) -> None:
        client = CliClient(command="sleep")
        step = ActionStep(id="s1", transport="cli", args=["60"], timeout_seconds=1)
        ctx = StepContext(timeout_seconds=1)
        result = await client.execute(step, ctx)
        assert result.error is not None
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_variable_interpolation(self) -> None:
        client = CliClient(command="echo")
        step = ActionStep(id="s1", transport="cli", args=["${name}"])
        ctx = StepContext(variables={"name": "world"})
        result = await client.execute(step, ctx)
        assert result.exit_code == 0
        assert "world" in result.body.get("raw", "")

    @pytest.mark.asyncio
    async def test_health_check_known_command(self) -> None:
        client = CliClient(command="echo")
        # echo --help should succeed
        healthy = await client.health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_missing_command(self) -> None:
        client = CliClient(command="nonexistent_binary_xyz_12345")
        healthy = await client.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        client = CliClient(command="echo")
        await client.cleanup()  # no-op, should not raise


# ======================================================================
# DbClient
# ======================================================================


class TestDbClient:
    def test_is_select_valid(self) -> None:
        assert DbClient._is_select("SELECT * FROM locks") is True
        assert DbClient._is_select("  select 1  ") is True
        assert DbClient._is_select("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_is_select_rejects_mutations(self) -> None:
        assert DbClient._is_select("INSERT INTO locks VALUES (1)") is False
        assert DbClient._is_select("UPDATE locks SET x=1") is False
        assert DbClient._is_select("DELETE FROM locks") is False
        assert DbClient._is_select("DROP TABLE locks") is False
        assert DbClient._is_select("TRUNCATE locks") is False
        assert DbClient._is_select("ALTER TABLE locks ADD COLUMN x INT") is False

    @pytest.mark.asyncio
    async def test_execute_no_sql(self) -> None:
        client = DbClient()
        step = ActionStep(id="s1", transport="db")
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is not None
        assert "No SQL" in result.error

    @pytest.mark.asyncio
    async def test_execute_rejects_mutation(self) -> None:
        client = DbClient()
        step = ActionStep(id="s1", transport="db", sql="DELETE FROM locks")
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is not None
        assert "SELECT" in result.error

    @staticmethod
    def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
        """Create a mock asyncpg pool whose acquire() is an async ctx manager.

        Also mocks conn.transaction(readonly=True) as an async ctx manager.
        """
        # Mock the transaction context manager
        mock_txn = MagicMock()
        mock_txn.__aenter__ = AsyncMock(return_value=mock_txn)
        mock_txn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_txn)

        mock_pool = MagicMock()
        acm = MagicMock()
        acm.__aenter__ = AsyncMock(return_value=mock_conn)
        acm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = acm
        mock_pool.close = AsyncMock()
        return mock_pool

    @pytest.mark.asyncio
    async def test_execute_select_success(self) -> None:
        client = DbClient(dsn_env="DATABASE_URL")

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"id": 1, "file_path": "src/main.py"},
            {"id": 2, "file_path": "src/lib.py"},
        ]
        client._pool = self._make_mock_pool(mock_conn)

        step = ActionStep(id="s1", transport="db", sql="SELECT * FROM file_locks")
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is None
        assert result.body["count"] == 2
        assert len(result.body["rows"]) == 2

    @pytest.mark.asyncio
    async def test_execute_variable_substitution(self) -> None:
        """Variables are passed as positional params, not interpolated into SQL."""
        client = DbClient()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        client._pool = self._make_mock_pool(mock_conn)

        step = ActionStep(
            id="s1",
            transport="db",
            sql="SELECT * FROM file_locks WHERE file_path = ${path}",
        )
        ctx = StepContext(variables={"path": "src/main.py"})
        await client.execute(step, ctx)
        mock_conn.fetch.assert_awaited_once()
        called_sql = mock_conn.fetch.call_args[0][0]
        # The SQL should contain $1 placeholder, NOT the literal value
        assert "$1" in called_sql
        assert "src/main.py" not in called_sql
        # The value should be passed as a positional parameter
        called_params = mock_conn.fetch.call_args[0][1:]
        assert called_params == ("src/main.py",)

    @pytest.mark.asyncio
    async def test_execute_readonly_transaction(self) -> None:
        """Queries run inside a read-only transaction as defense-in-depth."""
        client = DbClient()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        client._pool = self._make_mock_pool(mock_conn)

        step = ActionStep(id="s1", transport="db", sql="SELECT 1")
        ctx = StepContext()
        await client.execute(step, ctx)
        mock_conn.transaction.assert_called_once_with(readonly=True)

    @pytest.mark.asyncio
    async def test_execute_prevents_sql_injection(self) -> None:
        """A malicious captured variable must be safely parameterized, not interpolated."""
        client = DbClient()

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        client._pool = self._make_mock_pool(mock_conn)

        malicious_value = "'; DROP TABLE users; --"
        step = ActionStep(
            id="s1",
            transport="db",
            sql="SELECT * FROM file_locks WHERE file_path = ${path}",
        )
        ctx = StepContext(variables={"path": malicious_value})
        await client.execute(step, ctx)

        mock_conn.fetch.assert_awaited_once()
        called_sql = mock_conn.fetch.call_args[0][0]
        # The SQL must NOT contain the malicious string
        assert "DROP TABLE" not in called_sql
        assert "$1" in called_sql
        # The malicious value is safely passed as a parameter
        called_params = mock_conn.fetch.call_args[0][1:]
        assert called_params == (malicious_value,)

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        client = DbClient()
        mock_pool = AsyncMock()
        client._pool = mock_pool
        await client.cleanup()
        mock_pool.close.assert_awaited_once()
        assert client._pool is None


# ======================================================================
# WaitClient
# ======================================================================


class TestWaitClient:
    @pytest.mark.asyncio
    async def test_execute(self) -> None:
        client = WaitClient()
        step = ActionStep(id="s1", transport="wait", seconds=0.05)
        ctx = StepContext()
        result = await client.execute(step, ctx)
        assert result.error is None
        assert result.body["waited_seconds"] == 0.05
        assert result.duration_ms >= 40  # at least ~50ms, allow some slack

    @pytest.mark.asyncio
    async def test_execute_default_seconds(self) -> None:
        client = WaitClient()
        step = ActionStep(id="s1", transport="wait")
        ctx = StepContext()
        # Patch asyncio.sleep to return immediately, but wrap in wait_for still
        with patch(
            "evaluation.gen_eval.clients.wait_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await client.execute(step, ctx)
            mock_sleep.assert_awaited_once_with(1.0)
        assert result.body["waited_seconds"] == 1.0

    @pytest.mark.asyncio
    async def test_execute_exceeds_step_timeout(self) -> None:
        """L3: WaitClient should respect step timeout via asyncio.wait_for."""
        client = WaitClient()
        step = ActionStep(id="s1", transport="wait", seconds=10.0)
        ctx = StepContext(timeout_seconds=0.1)
        result = await client.execute(step, ctx)
        assert result.error is not None
        assert "exceeded step timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        client = WaitClient()
        assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        client = WaitClient()
        await client.cleanup()  # no-op


# ======================================================================
# Protocol conformance
# ======================================================================


class TestProtocolConformance:
    """Verify each client is recognized as a TransportClient."""

    def test_http_client(self) -> None:
        assert isinstance(HttpClient(base_url="http://localhost"), TransportClient)

    def test_mcp_client(self) -> None:
        assert isinstance(McpClient(mcp_url="http://localhost/sse"), TransportClient)

    def test_cli_client(self) -> None:
        assert isinstance(CliClient(command="echo"), TransportClient)

    def test_db_client(self) -> None:
        assert isinstance(DbClient(), TransportClient)

    def test_wait_client(self) -> None:
        assert isinstance(WaitClient(), TransportClient)
