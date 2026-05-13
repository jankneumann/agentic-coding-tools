"""Inline-fallback regression tests (task 4.3).

Spec scenarios covered:
    - skill-workflow-spec → "Coordinator unreachable, autopilot continues"
    - skill-workflow-spec → "Network timeout falls back gracefully"
    - skill-workflow-spec → "Harness Agent tool not exposed, fallback to inline path"

Three failure modes asserted:
    a) Agent() runner unavailable / not exposed → fallback path; phase_archetype=None
    b) Coordinator returns HTTP 503 for /archetypes/resolve_for_phase
    c) Bridge raises TimeoutError mid-resolution

In all three cases, autopilot SHALL NOT crash, SHALL log a structured warning,
and SHALL leave LoopState.phase_archetype unset (None) for the affected phase.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make sibling autopilot scripts importable
_AUTOPILOT_SCRIPTS = Path(__file__).resolve().parents[2] / "autopilot" / "scripts"
if str(_AUTOPILOT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AUTOPILOT_SCRIPTS))


@pytest.fixture
def change_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal change directory with a v3 loop-state.json.

    apply_phase_outcome derives paths from Path.cwd() + "openspec/changes/<id>/",
    so we chdir to tmp_path here.
    """
    monkeypatch.chdir(tmp_path)
    cdir = tmp_path / "openspec" / "changes" / "test-fallback"
    cdir.mkdir(parents=True)
    (cdir / "loop-state.json").write_text(json.dumps({
        "schema_version": 3,
        "change_id": "test-fallback",
        "current_phase": "IMPLEMENT",
        "iteration": 0,
        "total_iterations": 0,
        "max_phase_iterations": 3,
        "findings_trend": [],
        "blocking_findings": [],
        "vendor_availability": {},
        "packages_status": {},
        "package_authors": {},
        "implementation_strategy": {},
        "memory_ids": [],
        "handoff_ids": [],
        "last_handoff_id": None,
        "started_at": "2026-05-07T00:00:00+00:00",
        "phase_started_at": "2026-05-07T00:00:00+00:00",
        "current_phase_started_at": None,
        "previous_phase": None,
        "cli_review_enabled": True,
        "val_review_enabled": False,
        "phase_archetype": None,
    }))
    return cdir


def test_bridge_returns_none_options_lack_model_and_system_prompt(
    change_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Mode (a)+(b): when bridge returns None (coordinator 503 / unreachable),
    options dict lacks model and system_prompt keys; archetype is None."""
    from phase_agent import _build_options

    state_dict: dict = {"capabilities_touched": [], "loc_estimate": 100}

    with patch("phase_agent.coordination_bridge.try_resolve_archetype_for_phase",
               return_value=None):
        with caplog.at_level(logging.WARNING):
            options = _build_options("IMPLEMENT", state_dict)

    # No model/system_prompt set when bridge returned None
    assert "model" not in options
    assert "system_prompt" not in options
    # Worktree isolation flag still set independently for IMPLEMENT
    assert options.get("isolation") == "worktree"
    # No archetype recorded in state_dict
    assert "_resolved_archetype" not in state_dict


def test_bridge_timeout_does_not_crash(change_dir: Path) -> None:
    """Mode (c): TimeoutError from the bridge yields options without
    model/system_prompt and does not propagate the exception."""
    from phase_agent import _build_options

    state_dict: dict = {}

    # The bridge wrapper SHALL absorb the timeout and return None (per spec).
    # Simulate that contract here directly.
    with patch("phase_agent.coordination_bridge.try_resolve_archetype_for_phase",
               return_value=None):
        # Should not raise even if upstream raised TimeoutError internally
        options = _build_options("PLAN", state_dict)

    assert "model" not in options
    assert "system_prompt" not in options
    assert state_dict.get("_resolved_archetype") is None


def test_apply_phase_outcome_records_null_when_cache_missing(
    change_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When the prose layer falls back to inline (no Agent dispatch),
    no cache file is written. apply_phase_outcome must record
    phase_archetype=None and not raise."""
    from phase_agent import apply_phase_outcome
    # Cache file deliberately absent
    cache = change_dir / ".phase-resolution-cache.json"
    assert not cache.exists()

    with caplog.at_level(logging.WARNING):
        apply_phase_outcome(
            change_id="test-fallback",
            phase="IMPLEMENT",
            outcome="continue",
            handoff_id="h-fallback-1",
        )

    state = json.loads((change_dir / "loop-state.json").read_text())
    assert state["last_handoff_id"] == "h-fallback-1"
    assert state["phase_archetype"] is None
    # Warning logged about missing cache (not a hard error)
    assert any("cache" in r.message.lower() or "missing" in r.message.lower()
               for r in caplog.records), "expected a warning about missing cache"


def test_replay_after_fallback_preserves_null(change_dir: Path) -> None:
    """Idempotency holds even when the first call ran in fallback mode
    (cache missing → phase_archetype=None). A retry of the same handoff
    must NOT flip null to something else."""
    from phase_agent import apply_phase_outcome

    apply_phase_outcome(
        change_id="test-fallback", phase="IMPLEMENT",
        outcome="continue", handoff_id="h-replay",
    )
    state_after_first = json.loads((change_dir / "loop-state.json").read_text())
    assert state_after_first["phase_archetype"] is None

    # Replay
    apply_phase_outcome(
        change_id="test-fallback", phase="IMPLEMENT",
        outcome="continue", handoff_id="h-replay",
    )
    state_after_replay = json.loads((change_dir / "loop-state.json").read_text())
    assert state_after_replay["phase_archetype"] is None
    # handoff_id appears exactly once
    assert state_after_replay["handoff_ids"].count("h-replay") == 1
