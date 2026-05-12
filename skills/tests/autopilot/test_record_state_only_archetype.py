"""Tests for IMPL_REVIEW finding R-001 (claude) / R-005 (claude).

R-001: SKILL.md INIT/SUBMIT_PR didn't record phase_archetype because the
       state-only resolver was only invoked from `autopilot.run_loop`,
       which the prose path doesn't drive. Fix added a runner subcommand
       `record-state-only-archetype` that SKILL.md shells to. This file
       tests the file-level `phase_agent.record_state_only_archetype`
       helper and the orchestration through `_phase_init`/`_phase_submit_pr`.

R-005: Add tests that go through `_phase_init` / `_phase_submit_pr` rather
       than calling the resolver directly, so regressions to those
       functions (e.g., the resolver call removed) are caught.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import autopilot
import coordination_bridge
import phase_agent
import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)


def _stub_bridge(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: response,
    )


# ---------------------------------------------------------------------------
# record_state_only_archetype helper (file-level — used by runner.py)
# ---------------------------------------------------------------------------


def _seed_state(change_dir: Path, change_id: str) -> Path:
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps({
        "change_id": change_id,
        "current_phase": "INIT",
        "schema_version": 3,
        "handoff_ids": [],
        "last_handoff_id": None,
        "phase_archetype": None,
    }))
    return state_path


def test_record_helper_writes_archetype_for_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    state_path = _seed_state(change_dir, "demo")

    _stub_bridge(monkeypatch, {"archetype": "runner", "model": "haiku", "system_prompt": "..."})

    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")

    persisted = json.loads(state_path.read_text())
    assert persisted["phase_archetype"] == "runner"


def test_record_helper_bridge_none_writes_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Bridge unavailable → phase_archetype persisted as null (D9 fallback)."""
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    state_path = _seed_state(change_dir, "demo")

    _stub_bridge(monkeypatch, None)

    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")

    persisted = json.loads(state_path.read_text())
    assert persisted["phase_archetype"] is None


def test_record_helper_bridge_raises_writes_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Bridge raising any exception → phase_archetype persisted as null."""
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    state_path = _seed_state(change_dir, "demo")

    def _boom(phase: str, signals: Any = None, **_: Any) -> Any:
        raise TimeoutError("bridge unreachable")

    monkeypatch.setattr(coordination_bridge, "try_resolve_archetype_for_phase", _boom)

    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")

    persisted = json.loads(state_path.read_text())
    assert persisted["phase_archetype"] is None


def test_record_helper_missing_state_file_is_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    # Intentionally do NOT seed loop-state.json.

    _stub_bridge(monkeypatch, {"archetype": "runner"})

    # No exception, no state file created.
    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")
    assert not (change_dir / "loop-state.json").exists()


def test_record_helper_rejects_non_state_only_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="phase must be one of"):
        phase_agent.record_state_only_archetype(change_id="demo", phase="IMPLEMENT")


def test_record_helper_writes_archetype_for_submit_pr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    state_path = _seed_state(change_dir, "demo")

    _stub_bridge(monkeypatch, {"archetype": "runner", "model": "haiku", "system_prompt": "..."})

    phase_agent.record_state_only_archetype(change_id="demo", phase="SUBMIT_PR")

    persisted = json.loads(state_path.read_text())
    assert persisted["phase_archetype"] == "runner"


def test_record_helper_idempotent_on_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Re-invoking with the same arguments leaves state in a consistent shape."""
    monkeypatch.chdir(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    state_path = _seed_state(change_dir, "demo")

    _stub_bridge(monkeypatch, {"archetype": "runner"})

    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")
    first = json.loads(state_path.read_text())
    phase_agent.record_state_only_archetype(change_id="demo", phase="INIT")
    second = json.loads(state_path.read_text())

    assert first["phase_archetype"] == "runner"
    assert second["phase_archetype"] == "runner"


# ---------------------------------------------------------------------------
# _phase_init / _phase_submit_pr — exercise the resolver call site (R-005)
# ---------------------------------------------------------------------------


def test_phase_init_invokes_resolver_directly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Direct test of the wire from _phase_init → _resolve_phase_archetype_for_state_only.

    R-005: regressions removing the resolver call from _phase_init
    (e.g., refactor accidentally drops the line) must be caught.
    """
    captured: list[tuple[str, Any]] = []

    real_resolver = autopilot._resolve_phase_archetype_for_state_only

    def spy(state: autopilot.LoopState, phase: str) -> None:
        captured.append((phase, state.change_id))
        real_resolver(state, phase)

    monkeypatch.setattr(autopilot, "_resolve_phase_archetype_for_state_only", spy)
    _stub_bridge(monkeypatch, {"archetype": "runner"})

    change_dir = tmp_path / "change"
    change_dir.mkdir()
    state = autopilot.LoopState(change_id="demo")

    # No assess_complexity_fn → exercise the simplest path through _phase_init.
    autopilot._phase_init(state, change_dir, assess_complexity_fn=None)

    assert captured == [("INIT", "demo")]
    assert state.phase_archetype == "runner"


def test_phase_submit_pr_invokes_resolver_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct test of the wire from _phase_submit_pr → resolver."""
    captured: list[tuple[str, Any]] = []

    real_resolver = autopilot._resolve_phase_archetype_for_state_only

    def spy(state: autopilot.LoopState, phase: str) -> None:
        captured.append((phase, state.change_id))
        real_resolver(state, phase)

    monkeypatch.setattr(autopilot, "_resolve_phase_archetype_for_state_only", spy)
    _stub_bridge(monkeypatch, {"archetype": "runner"})

    state = autopilot.LoopState(change_id="demo")

    def _stub_submit_pr(_state: autopilot.LoopState) -> str:
        return "created"

    autopilot._phase_submit_pr(state, _stub_submit_pr)

    assert captured == [("SUBMIT_PR", "demo")]
    assert state.phase_archetype == "runner"
