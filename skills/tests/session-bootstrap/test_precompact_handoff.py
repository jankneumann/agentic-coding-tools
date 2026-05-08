"""Tests for skills/session-bootstrap/scripts/hooks/precompact_handoff.py.

We import the module rather than subprocess-invoking it, so we can introspect
the request body that would be sent to /handoffs/write without standing up
an HTTP server. The module's _post() is monkeypatched to capture calls.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HOOK = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap" / "scripts" / "hooks" / "precompact_handoff.py"
)


@pytest.fixture
def hook_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Load precompact_handoff.py as a module each test for clean state."""
    spec = importlib.util.spec_from_file_location("precompact_handoff", _HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["precompact_handoff"] = module
    spec.loader.exec_module(module)
    return module


def _write_handoff(cwd: Path, *, summary: str, next_steps: list[str]) -> Path:
    """Write a local-fallback envelope handoff and return its path."""
    handoff_dir = cwd / "openspec" / "changes" / "test-change" / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    target = handoff_dir / "implementation-1.json"
    target.write_text(json.dumps({
        "schema_version": 1,
        "written_at": "2026-05-08T00:00:00+00:00",
        "coordinator_error": {"error_type": "unreachable", "message": "test"},
        "payload": {
            "agent_name": "claude-opus-4-7",
            "session_id": None,
            "summary": summary,
            "completed_work": ["Did the thing"],
            "in_progress": ["Doing the next thing"],
            "next_steps": next_steps,
            "decisions": [],
            "relevant_files": ["foo.py"],
        },
    }))
    return target


def test_latest_phase_record_returns_payload(
    hook_module: Any, tmp_path: Path,
) -> None:
    _write_handoff(tmp_path, summary="Phase done.", next_steps=["go"])
    record = hook_module._latest_phase_record(cwd=tmp_path)
    assert record is not None
    assert record["summary"] == "Phase done."
    assert record["next_steps"] == ["go"]


def test_latest_phase_record_none_when_missing(
    hook_module: Any, tmp_path: Path,
) -> None:
    record = hook_module._latest_phase_record(cwd=tmp_path)
    assert record is None


def test_build_summary_with_record(hook_module: Any) -> None:
    record = {
        "summary": "Implemented foo.",
        "next_steps": ["Step A", "Step B", "Step C", "Step D"],
    }
    summary = hook_module._build_summary(record)
    assert "Pre-compact snapshot" in summary
    assert "Implemented foo." in summary
    assert "Step A" in summary
    assert "Step B" in summary
    assert "Step C" in summary
    # Fourth step should be elided into the "+N more" tail.
    assert "Step D" not in summary
    assert "+1 more" in summary


def test_build_summary_without_record(hook_module: Any) -> None:
    summary = hook_module._build_summary(None)
    assert "No phase handoffs" in summary


def test_build_summary_caps_length(hook_module: Any) -> None:
    huge = {
        "summary": "x" * 5000,
        "next_steps": ["y" * 5000],
    }
    summary = hook_module._build_summary(huge)
    # Schema caps at 2000; we leave headroom at 1900.
    assert len(summary) <= 1900


def test_write_handoff_forwards_structured_fields(
    hook_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_handoff(
        tmp_path, summary="Phase done.", next_steps=["one", "two"],
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:9999")
    monkeypatch.setenv("AGENT_ID", "test-agent")

    captured: dict[str, Any] = {}

    def fake_post(base_url: str, path: str, payload: dict) -> dict:
        captured["base_url"] = base_url
        captured["path"] = path
        captured["payload"] = payload
        return {"success": True, "handoff_id": "h-123"}

    monkeypatch.setattr(hook_module, "_post", fake_post)

    hook_module._write_handoff({})

    assert captured["path"] == "/handoffs/write"
    body = captured["payload"]
    assert body["agent_id"] == ""
    assert body["agent_type"] == ""
    assert "Phase done." in body["summary"]
    assert body["completed_work"] == ["Did the thing"]
    assert body["in_progress"] == ["Doing the next thing"]
    assert body["next_steps"] == ["one", "two"]
    assert body["relevant_files"] == ["foo.py"]
    # Empty `decisions` list should not be forwarded.
    assert "decisions" not in body


def test_write_handoff_skips_when_no_coordinator(
    hook_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COORDINATION_API_URL", raising=False)

    called = False

    def fake_post(*_args: Any, **_kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(hook_module, "_post", fake_post)
    hook_module._write_handoff({})
    assert not called


def test_clear_flag_is_idempotent(
    hook_module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_ID", "x")
    flag = tmp_path / ".claude" / "compact-pending-x.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    hook_module._clear_flag()
    assert not flag.exists()
    # Running again with no flag is a no-op (no exception).
    hook_module._clear_flag()
