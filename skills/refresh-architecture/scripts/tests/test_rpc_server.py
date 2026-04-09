"""Tests for the refresh-architecture RPC server (wp-build-graph task 3.8).

Covers the three RPC methods from contracts/internal/refresh-architecture-rpc.yaml:
  - is_graph_stale: freshness probe from file mtime
  - trigger_refresh: spawn async refresh, idempotent when in-flight
  - get_refresh_status: poll status by refresh_id

Uses an injectable subprocess spawner so tests can simulate RUNNING /
COMPLETED / FAILED states without shelling out to refresh_architecture.sh.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rpc_server import (  # noqa: E402
    RefreshServer,
    RefreshStatus,
    main as rpc_main,
)


# ---------------------------------------------------------------------------
# Fake subprocess spawner
# ---------------------------------------------------------------------------


class _FakeProcess:
    """Minimal subprocess.Popen replacement for deterministic tests."""

    def __init__(self, returncode: int | None = None) -> None:
        self._returncode = returncode
        self.pid = 12345

    def poll(self) -> int | None:
        return self._returncode

    def complete(self, rc: int = 0) -> None:
        self._returncode = rc


class _FakeSpawner:
    """Captures calls to spawn and hands out controllable fake processes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.processes: list[_FakeProcess] = []

    def __call__(self, cmd: list[str]) -> _FakeProcess:
        self.calls.append(cmd)
        proc = _FakeProcess(returncode=None)
        self.processes.append(proc)
        return proc


# ---------------------------------------------------------------------------
# is_graph_stale
# ---------------------------------------------------------------------------


class TestIsGraphStale:
    def test_missing_file_is_stale(self, tmp_path: Path) -> None:
        server = RefreshServer(graph_path=tmp_path / "nope.json")
        result = server.is_graph_stale()
        assert result["stale"] is True
        assert result["graph_mtime"] is None
        assert result["node_count"] is None
        assert result["refresh_in_flight"] is False
        assert result["current_refresh_id"] is None

    def test_fresh_graph_reports_stats(self, tmp_path: Path) -> None:
        path = tmp_path / "architecture.graph.json"
        path.write_text(json.dumps({"nodes": [{"id": f"n{i}"} for i in range(50)]}))
        server = RefreshServer(graph_path=path)
        result = server.is_graph_stale()
        assert result["stale"] is False
        assert result["node_count"] == 50
        assert result["graph_mtime"] is not None

    def test_old_graph_stale(self, tmp_path: Path) -> None:
        path = tmp_path / "architecture.graph.json"
        path.write_text("{}")
        import os as _os
        old = time.time() - 10 * 3600  # 10 hours ago, threshold default 6h
        _os.utime(path, (old, old))
        server = RefreshServer(graph_path=path, max_age_hours=6)
        assert server.is_graph_stale()["stale"] is True

    def test_in_flight_flag_reflects_active_refresh(self, tmp_path: Path) -> None:
        path = tmp_path / "architecture.graph.json"
        path.write_text("{}")
        spawner = _FakeSpawner()
        server = RefreshServer(
            graph_path=path,
            spawner=spawner,
            refresh_cmd=["true"],
        )
        server.trigger_refresh(reason="unit-test", caller="test_rpc_server")
        result = server.is_graph_stale()
        assert result["refresh_in_flight"] is True
        assert result["current_refresh_id"] is not None


# ---------------------------------------------------------------------------
# trigger_refresh
# ---------------------------------------------------------------------------


class TestTriggerRefresh:
    def _server(self, tmp_path: Path) -> tuple[RefreshServer, _FakeSpawner]:
        path = tmp_path / "architecture.graph.json"
        path.write_text("{}")
        spawner = _FakeSpawner()
        server = RefreshServer(
            graph_path=path,
            spawner=spawner,
            refresh_cmd=["/bin/true"],
        )
        return server, spawner

    def test_new_refresh(self, tmp_path: Path) -> None:
        server, spawner = self._server(tmp_path)
        result = server.trigger_refresh(reason="stale", caller="test")
        assert result["is_new"] is True
        assert len(result["refresh_id"]) > 0
        assert result["estimated_duration_s"] > 0
        assert len(spawner.calls) == 1

    def test_idempotent_while_in_flight(self, tmp_path: Path) -> None:
        """Duplicate trigger_refresh while running returns the same id."""
        server, spawner = self._server(tmp_path)
        r1 = server.trigger_refresh(reason="stale", caller="test")
        r2 = server.trigger_refresh(reason="stale", caller="test")
        assert r1["refresh_id"] == r2["refresh_id"]
        assert r1["is_new"] is True
        assert r2["is_new"] is False
        # Only one subprocess spawned
        assert len(spawner.calls) == 1

    def test_new_after_completion(self, tmp_path: Path) -> None:
        server, spawner = self._server(tmp_path)
        r1 = server.trigger_refresh(reason="stale", caller="test")
        # Mark first refresh as complete
        spawner.processes[0].complete(rc=0)
        r2 = server.trigger_refresh(reason="stale-again", caller="test")
        assert r2["is_new"] is True
        assert r1["refresh_id"] != r2["refresh_id"]
        assert len(spawner.calls) == 2

    def test_missing_reason_rejected(self, tmp_path: Path) -> None:
        server, _ = self._server(tmp_path)
        with pytest.raises(ValueError, match="reason"):
            server.trigger_refresh(reason="", caller="test")

    def test_missing_caller_rejected(self, tmp_path: Path) -> None:
        server, _ = self._server(tmp_path)
        with pytest.raises(ValueError, match="caller"):
            server.trigger_refresh(reason="stale", caller="")


# ---------------------------------------------------------------------------
# get_refresh_status
# ---------------------------------------------------------------------------


class TestGetRefreshStatus:
    def _server(self, tmp_path: Path) -> tuple[RefreshServer, _FakeSpawner]:
        path = tmp_path / "architecture.graph.json"
        path.write_text("{}")
        spawner = _FakeSpawner()
        return RefreshServer(
            graph_path=path, spawner=spawner, refresh_cmd=["/bin/true"]
        ), spawner

    def test_running(self, tmp_path: Path) -> None:
        server, _ = self._server(tmp_path)
        triggered = server.trigger_refresh(reason="stale", caller="test")
        status = server.get_refresh_status(triggered["refresh_id"])
        assert status["status"] == RefreshStatus.RUNNING.value
        assert status["started_at"] is not None
        assert status["completed_at"] is None
        assert status["error_message"] is None

    def test_completed(self, tmp_path: Path) -> None:
        server, spawner = self._server(tmp_path)
        triggered = server.trigger_refresh(reason="stale", caller="test")
        spawner.processes[0].complete(rc=0)
        status = server.get_refresh_status(triggered["refresh_id"])
        assert status["status"] == RefreshStatus.COMPLETED.value
        assert status["completed_at"] is not None
        assert status["error_message"] is None

    def test_failed(self, tmp_path: Path) -> None:
        server, spawner = self._server(tmp_path)
        triggered = server.trigger_refresh(reason="stale", caller="test")
        spawner.processes[0].complete(rc=1)
        status = server.get_refresh_status(triggered["refresh_id"])
        assert status["status"] == RefreshStatus.FAILED.value
        assert status["error_message"] is not None

    def test_unknown_id(self, tmp_path: Path) -> None:
        server, _ = self._server(tmp_path)
        status = server.get_refresh_status("no-such-id")
        assert status["status"] == RefreshStatus.UNKNOWN.value


# ---------------------------------------------------------------------------
# CLI entry point (subprocess-style invocation)
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    def test_is_graph_stale_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "architecture.graph.json"
        path.write_text(json.dumps({"nodes": [{"id": "x"}]}))
        monkeypatch.setenv("REFRESH_RPC_GRAPH_PATH", str(path))
        rc = rpc_main(["is_graph_stale", "{}"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert rc == 0
        assert data["stale"] is False
        assert data["node_count"] == 1

    def test_invalid_method(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = rpc_main(["not_a_method", "{}"])
        assert rc != 0
