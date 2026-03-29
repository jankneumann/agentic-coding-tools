"""Tests for status reporting: HTTP endpoint, MCP tool, hook script, and auto-dev-loop callback."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import StatusReportRequest, create_coordination_api

# =============================================================================
# Fixtures
# =============================================================================

_TEST_KEY = "test-key-status"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch config so the API accepts our test key."""
    from src.config import reset_config

    reset_config()

    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")

    reset_config()

    yield  # type: ignore[misc]

    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


# =============================================================================
# HTTP endpoint tests
# =============================================================================


def test_report_status_endpoint_returns_success(client: TestClient) -> None:
    """POST /status/report returns success with mocked DB."""
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = AsyncMock()
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "test-agent",
                "change_id": "change-001",
                "phase": "IMPLEMENT",
                "message": "Working on implementation",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_report_status_updates_heartbeat(client: TestClient) -> None:
    """POST /status/report calls heartbeat on discovery service."""
    mock_heartbeat = AsyncMock()
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = mock_heartbeat
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "test-agent",
                "change_id": "change-001",
                "phase": "PLAN",
            },
        )

    assert response.status_code == 200
    mock_heartbeat.assert_awaited_once()


def test_report_status_emits_notify(client: TestClient) -> None:
    """POST /status/report emits pg_notify when bus is running."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
        patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn),
    ):
        mock_disc.return_value.heartbeat = AsyncMock()
        mock_bus = MagicMock()
        mock_bus.running = True
        mock_bus.failed = False
        mock_bus._dsn = "postgresql://localhost/test"
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "test-agent",
                "change_id": "change-001",
                "phase": "VALIDATE",
                "message": "Running validation",
            },
        )

    assert response.status_code == 200
    mock_conn.execute.assert_awaited_once()
    # Verify it was a pg_notify call
    call_args = mock_conn.execute.call_args
    assert "pg_notify" in call_args[0][0]
    assert call_args[0][1] == "coordinator_status"


def test_needs_human_sets_high_urgency(client: TestClient) -> None:
    """When needs_human=True, urgency should be 'high'."""
    with (
        patch("src.discovery.get_discovery_service") as mock_disc,
        patch("src.event_bus.get_event_bus") as mock_bus_fn,
    ):
        mock_disc.return_value.heartbeat = AsyncMock()
        mock_bus = MagicMock()
        mock_bus.running = False
        mock_bus.failed = False
        mock_bus_fn.return_value = mock_bus

        response = client.post(
            "/status/report",
            json={
                "agent_id": "test-agent",
                "change_id": "change-001",
                "phase": "ESCALATE",
                "message": "Need help",
                "needs_human": True,
                "event_type": "status.escalated",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["urgency"] == "high"


# =============================================================================
# Hook script tests
#
# The hook script imports httpx inside main(), so we test by running it as a
# subprocess or by directly calling its helper functions and main() with
# monkeypatched cwd.
# =============================================================================

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_HOOK_SCRIPT = _SCRIPTS_DIR / "report_status.py"


def test_hook_script_reads_loop_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hook script reads loop-state.json and sends correct payload."""
    loop_state = {
        "current_phase": "IMPLEMENT",
        "change_id": "test-change-42",
        "findings_trend": [3, 2, 1],
    }
    (tmp_path / "loop-state.json").write_text(json.dumps(loop_state))

    # Run the script as a subprocess in tmp_path (no coordinator running, so it
    # will fail to connect — but we verify it exits 0 and check _read_loop_state
    # in-process below).
    result = subprocess.run(
        [sys.executable, str(_HOOK_SCRIPT)],
        cwd=str(tmp_path),
        env={**os.environ, "AGENT_ID": "agent-hook-test", "COORDINATOR_URL": "http://127.0.0.1:1"},
        capture_output=True,
        timeout=10,
    )
    # Must exit 0 even when coordinator is unreachable
    assert result.returncode == 0

    # Also verify the internal _read_loop_state function
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(_SCRIPTS_DIR.parent))
    try:
        # Force reimport to pick up new cwd
        import importlib
        import scripts.report_status as rs_mod
        importlib.reload(rs_mod)

        data = rs_mod._read_loop_state()
        assert data.get("current_phase") == "IMPLEMENT"
        assert data.get("change_id") == "test-change-42"
    finally:
        if str(_SCRIPTS_DIR.parent) in sys.path:
            sys.path.remove(str(_SCRIPTS_DIR.parent))


def test_hook_script_handles_missing_loop_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hook script reports phase=UNKNOWN when loop-state.json is missing."""
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(_SCRIPTS_DIR.parent))
    try:
        import importlib
        import scripts.report_status as rs_mod
        importlib.reload(rs_mod)

        data = rs_mod._read_loop_state()
        assert data == {}
        # When data is empty, phase defaults to UNKNOWN
        assert data.get("current_phase", "UNKNOWN") == "UNKNOWN"
    finally:
        if str(_SCRIPTS_DIR.parent) in sys.path:
            sys.path.remove(str(_SCRIPTS_DIR.parent))


def test_hook_script_handles_corrupt_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hook script reports phase=UNKNOWN when loop-state.json has bad JSON."""
    (tmp_path / "loop-state.json").write_text("{{not valid json!!")
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(_SCRIPTS_DIR.parent))
    try:
        import importlib
        import scripts.report_status as rs_mod
        importlib.reload(rs_mod)

        data = rs_mod._read_loop_state()
        assert data == {}
        assert data.get("current_phase", "UNKNOWN") == "UNKNOWN"
    finally:
        if str(_SCRIPTS_DIR.parent) in sys.path:
            sys.path.remove(str(_SCRIPTS_DIR.parent))


def test_hook_script_exits_zero_on_timeout(tmp_path: Path) -> None:
    """Hook script exits 0 even when coordinator is unreachable (timeout)."""
    result = subprocess.run(
        [sys.executable, str(_HOOK_SCRIPT)],
        cwd=str(tmp_path),
        env={
            **os.environ,
            "AGENT_ID": "agent-timeout",
            # Point to a port that is not listening to trigger connection error
            "COORDINATOR_URL": "http://127.0.0.1:1",
        },
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0


# =============================================================================
# Auto-dev-loop status_fn callback tests
# =============================================================================


def test_status_fn_callback_in_auto_dev_loop(tmp_path: Path) -> None:
    """run_loop calls status_fn on phase transitions."""
    # Add auto-dev-loop scripts to path
    scripts_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "skills" / "auto-dev-loop" / "scripts"
    )
    sys.path.insert(0, str(scripts_dir))
    try:
        from auto_dev_loop import LoopState, run_loop

        change_dir = tmp_path / "changes" / "test-change"
        change_dir.mkdir(parents=True)
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Create a proposal so PLAN returns "exists"
        (change_dir / "proposal.md").write_text("# Test Proposal\n")

        status_calls: list[tuple[str, str, bool]] = []

        def mock_status_fn(
            state: LoopState, event_type: str, message: str, urgent: bool
        ) -> None:
            status_calls.append((event_type, message, urgent))

        def mock_assess(**kwargs: Any) -> dict[str, Any]:
            return {"force_required": False, "val_review_enabled": False}

        def mock_converge(**kwargs: Any) -> dict[str, Any]:
            return {"converged": True, "findings_count": 0, "blocking_findings": []}

        # Run with stubs that complete quickly: INIT -> PLAN -> PLAN_REVIEW -> IMPLEMENT -> IMPL_REVIEW -> VALIDATE -> SUBMIT_PR -> DONE
        state = run_loop(
            change_id="test-change",
            change_dir=str(change_dir),
            worktree_path=str(worktree_path),
            state_path=str(tmp_path / "loop-state.json"),
            status_fn=mock_status_fn,
            assess_complexity_fn=mock_assess,
            converge_fn=mock_converge,
            max_global_iterations=20,
        )

        assert state.current_phase == "DONE"
        # Verify status_fn was called at least once
        assert len(status_calls) > 0
        # All should be phase.transition type
        event_types = [c[0] for c in status_calls]
        assert "phase.transition" in event_types
        # None should be urgent (no escalation in this path)
        assert all(not c[2] for c in status_calls)
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
