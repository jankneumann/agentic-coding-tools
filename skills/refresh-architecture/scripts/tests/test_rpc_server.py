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
    get_server,
    main as rpc_main,
    reset_server,
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


# ---------------------------------------------------------------------------
# Additive provenance projection (ri-04 D6/D7 — scenario architecture-refresh.14)
# ---------------------------------------------------------------------------


def _make_repo_with_provenance(tmp_path: Path) -> Path:
    """Build a git repo with architecture artifacts and matching provenance."""
    import os
    import subprocess

    from arch_utils import provenance as prov

    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('x')\n")
    arch = repo / prov.ARCH_DIR_DEFAULT
    arch.mkdir(parents=True)
    (arch / "architecture.graph.json").write_text('{"nodes": [], "edges": []}\n')
    (arch / "architecture.summary.json").write_text('{"summary": "ok"}\n')
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "init"],
    ):
        subprocess.run(args, cwd=str(repo), check=True, capture_output=True)
    rev = prov.analyzed_revision(repo)
    os.environ["SOURCE_DATE_EPOCH"] = str(prov.deterministic_epoch(repo, rev))
    try:
        doc = prov.build_provenance(repo, mode="full", roots=["src"])
        # Fixture data must satisfy the published schema. Until the producer
        # emits schema 2 with per-artifact tiers, fill those in here; once it
        # does, both statements are no-ops.
        doc["schema_version"] = 2
        for artifact in doc["artifacts"]:
            artifact.setdefault("tier", "committed")
        prov.write_provenance(repo, doc)
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
    return repo


class TestProvenanceProjection:
    def _repo_with_provenance(self, tmp_path: Path) -> Path:
        return _make_repo_with_provenance(tmp_path)

    def test_legacy_fields_remain_and_additive_fields_present(self, tmp_path: Path) -> None:
        # Scenario .14 — legacy fields remain; provenance fields are added.
        from arch_utils import provenance as prov

        repo = self._repo_with_provenance(tmp_path)
        server = RefreshServer(
            graph_path=repo / prov.ARCH_DIR_DEFAULT / "architecture.graph.json",
            repo_root=repo,
        )
        result = server.is_graph_stale(max_age_hours=6)
        # Legacy fields still present.
        for key in ("stale", "graph_mtime", "node_count", "refresh_in_flight"):
            assert key in result
        # Additive provenance fields present and populated.
        assert result["stale"] is False  # content-based freshness
        assert result["source_revision"] == prov.analyzed_revision(repo)
        assert result["producer_version"] == prov.PRODUCER_VERSION
        assert len(result["input_fingerprint"]) == 64
        assert result["provenance_path"].endswith("architecture.provenance.json")
        assert result["reason"] == "fresh"
        assert result["operation_id"] is None  # no operation recorded yet

    def test_mtime_does_not_override_content_freshness(self, tmp_path: Path) -> None:
        # Scenario .3/.4 at the RPC layer: a stale relevant input → stale even if
        # the graph file mtime is recent.
        import os

        from arch_utils import provenance as prov

        repo = self._repo_with_provenance(tmp_path)
        (repo / "src" / "app.py").write_text("print('changed input')\n")
        graph = repo / prov.ARCH_DIR_DEFAULT / "architecture.graph.json"
        os.utime(graph, None)  # bump mtime to "now"
        server = RefreshServer(graph_path=graph, repo_root=repo)
        result = server.is_graph_stale()
        assert result["stale"] is True
        assert result["reason"] == prov.INPUT_FINGERPRINT_MISMATCH

    def test_legacy_mode_keeps_null_provenance_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "architecture.graph.json"
        path.write_text(json.dumps({"nodes": []}))
        server = RefreshServer(graph_path=path)  # no repo_root
        result = server.is_graph_stale()
        assert result["source_revision"] is None
        assert result["operation_id"] is None
        assert result["reason"] == "mtime"


# ---------------------------------------------------------------------------
# Default entry point resolution (scenarios architecture-refresh.20/.21/.22)
# ---------------------------------------------------------------------------


class TestGetServerResolvesRepoRoot:
    """``get_server()`` is the only path production callers use.

    The merge train reaches ``is_graph_stale`` through ``main()`` →
    ``get_server()``, so the freshness verdict every caller actually sees is
    decided here. These tests pin that the default entry point resolves a
    repository and therefore answers from provenance, not from file mtime.
    """

    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REFRESH_RPC_REPO_ROOT", raising=False)
        monkeypatch.delenv("REFRESH_RPC_GRAPH_PATH", raising=False)
        reset_server()
        yield
        reset_server()

    def _graph(self, repo: Path) -> Path:
        from arch_utils import provenance as prov

        return repo / prov.ARCH_DIR_DEFAULT / "architecture.graph.json"

    def test_default_entry_point_is_provenance_backed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Scenario .20 — reached via get_server(), every provenance field is
        # populated and the verdict does not come from mtime.
        repo = _make_repo_with_provenance(tmp_path)
        monkeypatch.setenv("REFRESH_RPC_GRAPH_PATH", str(self._graph(repo)))
        monkeypatch.chdir(tmp_path)

        result = get_server().is_graph_stale()

        assert result["reason"] != "mtime"
        assert result["source_revision"] is not None
        assert result["producer_version"] is not None
        assert result["input_fingerprint"] is not None
        assert result["provenance_path"] is not None
        assert result["stale"] is False

    def test_repo_root_env_override_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D4 step 1 — an explicit operator override short-circuits discovery.
        repo = _make_repo_with_provenance(tmp_path)
        monkeypatch.setenv("REFRESH_RPC_REPO_ROOT", str(repo))
        monkeypatch.chdir(tmp_path)

        server = get_server()

        assert server.repo_root == repo
        assert server.graph_path == self._graph(repo)

    def test_elapsed_time_alone_never_flips_the_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Scenario .21 — inputs unchanged, graph backdated far past the age
        # threshold: still fresh.
        import os as _os

        repo = _make_repo_with_provenance(tmp_path)
        graph = self._graph(repo)
        old = time.time() - 240 * 3600  # 10 days
        _os.utime(graph, (old, old))
        monkeypatch.setenv("REFRESH_RPC_GRAPH_PATH", str(graph))
        monkeypatch.chdir(tmp_path)

        result = get_server().is_graph_stale(max_age_hours=6)

        assert result["stale"] is False
        assert result["reason"] == "fresh"

    def test_verdict_is_independent_of_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Scenario .22 — same repo, two different working directories, one answer.
        repo = _make_repo_with_provenance(tmp_path)
        graph = self._graph(repo)
        monkeypatch.setenv("REFRESH_RPC_GRAPH_PATH", str(graph))

        monkeypatch.chdir(repo)
        from_repo = get_server().is_graph_stale()

        reset_server()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        from_elsewhere = get_server().is_graph_stale()

        assert from_repo == from_elsewhere
        assert from_repo["stale"] is False
        assert from_elsewhere["reason"] != "mtime"

    def test_legacy_mtime_probe_stays_reachable_without_a_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D4 step 3 — a .git-less source export still resolves to legacy mode.
        import subprocess as _subprocess

        graph = tmp_path / "export" / "architecture.graph.json"
        graph.parent.mkdir(parents=True)
        graph.write_text(json.dumps({"nodes": [{"id": "x"}]}))
        monkeypatch.setenv("REFRESH_RPC_GRAPH_PATH", str(graph))
        monkeypatch.chdir(tmp_path)

        probe = _subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(graph.parent),
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            pytest.skip("tmp_path lives inside a git repository")

        server = get_server()
        assert server.repo_root is None
        assert server.is_graph_stale()["reason"] == "mtime"

    def test_reset_server_hands_out_a_new_instance(self) -> None:
        # D5 — the seam tests use instead of poking rpc_server._SERVER.
        first = get_server()
        assert get_server() is first
        reset_server()
        assert get_server() is not first
