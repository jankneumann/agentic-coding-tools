"""Tests for refresh_rpc_client (wp-integration task 5.8a).

Contract: contracts/internal/refresh-architecture-rpc.yaml

The client wraps the three RPC methods of the refresh-architecture service:
  - is_graph_stale(max_age_hours=6)
  - trigger_refresh(reason, caller)
  - get_refresh_status(refresh_id)

**Failure-mode contract**: if the RPC subsystem is unreachable (subprocess
missing, timeout, malformed response), the client MUST return a sentinel
``RefreshClientUnavailable`` instance rather than raising. Callers
(compose_train) must treat this as a signal to fall back to the "full test
suite" path. This invariant is load-bearing — merge train progress must
NEVER be blocked on refresh-architecture availability.

Transport is subprocess-style: the client shells out to ``python -m rpc_server
<method> <json_args>`` and parses stdout JSON. Tests inject a fake runner so
no real subprocess is spawned.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from src.refresh_rpc_client import (
    DEFAULT_METHOD_TIMEOUTS,
    RefreshClientUnavailable,
    RefreshRpcClient,
)

# ---------------------------------------------------------------------------
# Fake subprocess runner
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeRunner:
    """Captures runner invocations. Tests queue responses and assert on calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: list[Any] = []

    def queue(self, response: Any) -> None:
        """Queue a response (CompletedProcess, exception, or lambda)."""
        self._responses.append(response)

    def __call__(
        self,
        cmd: list[str],
        *,
        timeout: float,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        self.calls.append({"cmd": list(cmd), "timeout": timeout})
        if not self._responses:
            raise AssertionError(
                f"FakeRunner had no queued response for call {len(self.calls)}: {cmd}"
            )
        resp = self._responses.pop(0)
        if isinstance(resp, BaseException):
            raise resp
        if callable(resp):
            return resp(cmd, timeout)  # type: ignore[no-any-return]
        return resp  # type: ignore[no-any-return]


@pytest.fixture
def runner() -> _FakeRunner:
    return _FakeRunner()


@pytest.fixture
def client(runner: _FakeRunner) -> RefreshRpcClient:
    return RefreshRpcClient(runner=runner, rpc_module="rpc_server")


# ---------------------------------------------------------------------------
# is_graph_stale
# ---------------------------------------------------------------------------


class TestIsGraphStale:
    def test_happy_path(self, client: RefreshRpcClient, runner: _FakeRunner) -> None:
        """Happy path: subprocess returns valid JSON, client returns parsed dict."""
        payload = {
            "stale": False,
            "graph_mtime": "2026-04-09T10:00:00+00:00",
            "node_count": 1234,
            "refresh_in_flight": False,
            "current_refresh_id": None,
        }
        runner.queue(_FakeCompletedProcess(0, json.dumps(payload)))

        result = client.is_graph_stale(max_age_hours=6)

        assert result == payload
        # Verify the command line was correct
        call = runner.calls[0]
        assert call["cmd"][0:3] == ["python3", "-m", "rpc_server"]
        assert call["cmd"][3] == "is_graph_stale"
        assert json.loads(call["cmd"][4]) == {"max_age_hours": 6}
        assert call["timeout"] == DEFAULT_METHOD_TIMEOUTS["is_graph_stale"]

    def test_default_max_age_hours_omitted(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        """Calling with default sends an empty kwargs dict (server uses its default)."""
        runner.queue(
            _FakeCompletedProcess(
                0, json.dumps({"stale": True, "graph_mtime": None, "node_count": None,
                               "refresh_in_flight": False, "current_refresh_id": None})
            )
        )
        client.is_graph_stale()
        call = runner.calls[0]
        # When no max_age_hours is passed, we send {}
        assert json.loads(call["cmd"][4]) == {}

    def test_subprocess_timeout_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        """Timeout → RefreshClientUnavailable, never raises."""
        runner.queue(subprocess.TimeoutExpired(cmd="rpc_server", timeout=30))
        result = client.is_graph_stale()
        assert isinstance(result, RefreshClientUnavailable)
        assert "timeout" in result.reason.lower()

    def test_subprocess_nonzero_exit_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        """Non-zero exit → sentinel."""
        runner.queue(_FakeCompletedProcess(2, "", "argparse error"))
        result = client.is_graph_stale()
        assert isinstance(result, RefreshClientUnavailable)
        assert "exit" in result.reason.lower() or "nonzero" in result.reason.lower()

    def test_malformed_json_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        """Bad JSON in stdout → sentinel (don't raise)."""
        runner.queue(_FakeCompletedProcess(0, "not json at all"))
        result = client.is_graph_stale()
        assert isinstance(result, RefreshClientUnavailable)
        assert "json" in result.reason.lower() or "parse" in result.reason.lower()

    def test_file_not_found_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        """Missing python binary / module → sentinel."""
        runner.queue(FileNotFoundError("python3 not found"))
        result = client.is_graph_stale()
        assert isinstance(result, RefreshClientUnavailable)


# ---------------------------------------------------------------------------
# trigger_refresh
# ---------------------------------------------------------------------------


class TestTriggerRefresh:
    def test_happy_path(self, client: RefreshRpcClient, runner: _FakeRunner) -> None:
        payload = {
            "refresh_id": "abc123def456",
            "is_new": True,
            "estimated_duration_s": 60,
        }
        runner.queue(_FakeCompletedProcess(0, json.dumps(payload)))

        result = client.trigger_refresh(
            reason="compose_train:stale>6h", caller="merge_queue"
        )

        assert result == payload
        call = runner.calls[0]
        assert call["cmd"][3] == "trigger_refresh"
        assert json.loads(call["cmd"][4]) == {
            "reason": "compose_train:stale>6h",
            "caller": "merge_queue",
        }
        assert call["timeout"] == DEFAULT_METHOD_TIMEOUTS["trigger_refresh"]

    def test_unavailable_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        runner.queue(_FakeCompletedProcess(1, "", "boom"))
        result = client.trigger_refresh(reason="test", caller="test")
        assert isinstance(result, RefreshClientUnavailable)


# ---------------------------------------------------------------------------
# get_refresh_status
# ---------------------------------------------------------------------------


class TestGetRefreshStatus:
    def test_happy_path(self, client: RefreshRpcClient, runner: _FakeRunner) -> None:
        payload = {
            "status": "RUNNING",
            "started_at": "2026-04-09T10:00:00+00:00",
            "completed_at": None,
            "error_message": None,
        }
        runner.queue(_FakeCompletedProcess(0, json.dumps(payload)))
        result = client.get_refresh_status(refresh_id="abc123")
        assert result == payload
        call = runner.calls[0]
        assert call["cmd"][3] == "get_refresh_status"
        assert json.loads(call["cmd"][4]) == {"refresh_id": "abc123"}
        assert call["timeout"] == DEFAULT_METHOD_TIMEOUTS["get_refresh_status"]

    def test_unavailable_returns_sentinel(
        self, client: RefreshRpcClient, runner: _FakeRunner
    ) -> None:
        runner.queue(subprocess.TimeoutExpired(cmd="rpc_server", timeout=5))
        result = client.get_refresh_status(refresh_id="x")
        assert isinstance(result, RefreshClientUnavailable)


# ---------------------------------------------------------------------------
# RefreshClientUnavailable sentinel
# ---------------------------------------------------------------------------


class TestRefreshClientUnavailable:
    def test_has_reason(self) -> None:
        sentinel = RefreshClientUnavailable(reason="timeout after 30s")
        assert sentinel.reason == "timeout after 30s"

    def test_is_not_dict_instance(self) -> None:
        """Callers can distinguish sentinel from a real response dict."""
        sentinel = RefreshClientUnavailable(reason="x")
        assert not isinstance(sentinel, dict)

    def test_repr_includes_reason(self) -> None:
        assert "timeout" in repr(RefreshClientUnavailable(reason="timeout"))


# ---------------------------------------------------------------------------
# Default runner binding (smoke check: we don't invoke subprocess.run in tests)
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_default_timeouts_match_contract(self) -> None:
        """Contract requires 30s for is_graph_stale, 10s for trigger, 5s for status."""
        assert DEFAULT_METHOD_TIMEOUTS["is_graph_stale"] == 30
        assert DEFAULT_METHOD_TIMEOUTS["trigger_refresh"] == 10
        assert DEFAULT_METHOD_TIMEOUTS["get_refresh_status"] == 5

    def test_client_can_be_constructed_without_injected_runner(self) -> None:
        """Default construction uses subprocess.run — we don't call it in this test."""
        c = RefreshRpcClient()
        assert c is not None


# ---------------------------------------------------------------------------
# compute_affected_tests (task 5.4)
# ---------------------------------------------------------------------------


class TestComputeAffectedTests:
    """Shells out to affected_tests.py and parses the newline-separated output.

    The script prints one test path per line, or the single line "ALL" when
    the graph is missing/stale/traversal-exceeded. ALL → None sentinel to
    signal "full suite needed".
    """

    def test_parses_path_list(self) -> None:
        from src.refresh_rpc_client import compute_affected_tests

        runner = _FakeRunner()
        runner.queue(
            _FakeCompletedProcess(
                0, stdout="tests/test_a.py\ntests/test_b.py\n"
            )
        )
        result = compute_affected_tests(
            ["src/foo.py", "src/bar.py"], runner=runner
        )
        assert result == ["tests/test_a.py", "tests/test_b.py"]
        call = runner.calls[0]
        assert "src/foo.py" in call["cmd"]
        assert "src/bar.py" in call["cmd"]

    def test_all_sentinel_returns_none(self) -> None:
        from src.refresh_rpc_client import compute_affected_tests

        runner = _FakeRunner()
        runner.queue(_FakeCompletedProcess(0, stdout="ALL\n"))
        result = compute_affected_tests(["src/x.py"], runner=runner)
        assert result is None

    def test_empty_output_returns_empty_list(self) -> None:
        """Empty stdout → no affected tests (safe for empty changed_files)."""
        from src.refresh_rpc_client import compute_affected_tests

        runner = _FakeRunner()
        runner.queue(_FakeCompletedProcess(0, stdout=""))
        result = compute_affected_tests([], runner=runner)
        assert result == []

    def test_subprocess_failure_returns_none(self) -> None:
        """Any transport error → None (full suite fallback)."""
        from src.refresh_rpc_client import compute_affected_tests

        runner = _FakeRunner()
        runner.queue(subprocess.TimeoutExpired(cmd="x", timeout=30))
        result = compute_affected_tests(["src/x.py"], runner=runner)
        assert result is None

    def test_nonzero_exit_returns_none(self) -> None:
        from src.refresh_rpc_client import compute_affected_tests

        runner = _FakeRunner()
        runner.queue(_FakeCompletedProcess(1, stdout="", stderr="boom"))
        result = compute_affected_tests(["src/x.py"], runner=runner)
        assert result is None
