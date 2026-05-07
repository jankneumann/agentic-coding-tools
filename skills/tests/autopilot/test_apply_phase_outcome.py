"""Tests for `phase_agent.apply_phase_outcome`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Requirement: Sub-Agent Dispatch Protocol Helpers
      Scenarios: "apply_phase_outcome updates loop state and is idempotent under replay",
                 "apply_phase_outcome with mismatched cache writes null archetype"
Design decisions: D4 (cache lifecycle + replay rule), Q1 (idempotency).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import phase_agent
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_state(repo_root: Path, change_id: str, **overrides: Any) -> Path:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 3,
        "change_id": change_id,
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
        "started_at": "2026-05-05T00:00:00+00:00",
        "phase_started_at": "2026-05-05T00:00:00+00:00",
        "previous_phase": None,
        "escalation_reason": None,
        "val_review_enabled": False,
        "cli_review_enabled": True,
        "error": None,
        "phase_archetype": None,
    }
    state.update(overrides)
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return state_path


def _write_cache(
    repo_root: Path,
    change_id: str,
    phase: str,
    archetype: str | None,
    *,
    bad_checksum: bool = False,
    cache_change_id: str | None = None,
    cache_phase: str | None = None,
) -> Path:
    """Write a `.phase-resolution-cache.json` payload (with optional bad checksum)."""
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    arch_bytes = (archetype if archetype is not None else "null").encode("utf-8")
    real_checksum = hashlib.sha256(
        change_id.encode("utf-8")
        + phase.encode("utf-8")
        + arch_bytes
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "change_id": cache_change_id or change_id,
        "phase": cache_phase or phase,
        "archetype": archetype,
        "checksum": "deadbeef" if bad_checksum else real_checksum,
    }
    cache_path = change_dir / ".phase-resolution-cache.json"
    cache_path.write_text(json.dumps(payload, indent=2))
    return cache_path


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Successful apply path
# ---------------------------------------------------------------------------


def test_apply_phase_outcome_updates_handoff_and_archetype(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    _write_cache(chdir_tmp, "demo", "IMPLEMENT", "implementer")

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["last_handoff_id"] == "h-abc"
    assert state["handoff_ids"] == ["h-abc"]
    assert state["phase_archetype"] == "implementer"

    # Cache file deleted on success.
    cache_path = chdir_tmp / "openspec" / "changes" / "demo" / ".phase-resolution-cache.json"
    assert not cache_path.exists()


def test_apply_phase_outcome_archetype_null_when_cache_missing(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    # No cache written.

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["last_handoff_id"] == "h-abc"
    assert state["phase_archetype"] is None


# ---------------------------------------------------------------------------
# Cache validation failures (D4 — never raise; null write + warning)
# ---------------------------------------------------------------------------


def test_apply_phase_outcome_cache_phase_mismatch_writes_null(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    _write_cache(
        chdir_tmp, "demo", "IMPLEMENT", "implementer",
        cache_phase="PLAN",  # mismatch — apply expects IMPLEMENT
    )

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["phase_archetype"] is None


def test_apply_phase_outcome_cache_change_id_mismatch_writes_null(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    _write_cache(
        chdir_tmp, "demo", "IMPLEMENT", "implementer",
        cache_change_id="other-change",
    )

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["phase_archetype"] is None


def test_apply_phase_outcome_cache_checksum_mismatch_writes_null(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    _write_cache(chdir_tmp, "demo", "IMPLEMENT", "implementer", bad_checksum=True)

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["phase_archetype"] is None


def test_apply_phase_outcome_corrupt_cache_writes_null(chdir_tmp: Path) -> None:
    state_path = _seed_state(chdir_tmp, "demo")
    cache_path = chdir_tmp / "openspec" / "changes" / "demo" / ".phase-resolution-cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not valid json")

    phase_agent.apply_phase_outcome(
        change_id="demo",
        phase="IMPLEMENT",
        outcome="continue",
        handoff_id="h-abc",
    )

    state = json.loads(state_path.read_text())
    assert state["phase_archetype"] is None


# ---------------------------------------------------------------------------
# Idempotency / replay rule (Q1, D4)
# ---------------------------------------------------------------------------


def test_apply_phase_outcome_replay_preserves_archetype(chdir_tmp: Path) -> None:
    """Calling twice with same args: archetype preserved, handoff_ids dedup'd."""
    state_path = _seed_state(chdir_tmp, "demo")
    _write_cache(chdir_tmp, "demo", "IMPLEMENT", "implementer")

    phase_agent.apply_phase_outcome(
        change_id="demo", phase="IMPLEMENT", outcome="continue", handoff_id="h-abc",
    )
    state_after_first = json.loads(state_path.read_text())
    # Mark previous_phase to satisfy the replay rule (autopilot writes this on transition).
    state_after_first["previous_phase"] = "IMPLEMENT"
    state_path.write_text(json.dumps(state_after_first, indent=2))

    # Second call — cache is now gone (deleted by first call).
    phase_agent.apply_phase_outcome(
        change_id="demo", phase="IMPLEMENT", outcome="continue", handoff_id="h-abc",
    )

    state_after_second = json.loads(state_path.read_text())
    assert state_after_second["last_handoff_id"] == "h-abc"
    # phase_archetype preserved from the first call.
    assert state_after_second["phase_archetype"] == "implementer"
    # No duplicate append.
    assert state_after_second["handoff_ids"].count("h-abc") == 1


def test_apply_phase_outcome_replay_via_current_phase_match(chdir_tmp: Path) -> None:
    """Replay rule also matches state.current_phase == phase (per spec)."""
    state_path = _seed_state(
        chdir_tmp, "demo",
        current_phase="IMPLEMENT",
        previous_phase=None,
        last_handoff_id="h-xyz",
        handoff_ids=["h-xyz"],
        phase_archetype="implementer",
    )

    # No cache, but replay rule should fire (last_handoff_id matches).
    phase_agent.apply_phase_outcome(
        change_id="demo", phase="IMPLEMENT", outcome="continue", handoff_id="h-xyz",
    )

    state = json.loads(state_path.read_text())
    assert state["phase_archetype"] == "implementer"
    assert state["handoff_ids"].count("h-xyz") == 1


def test_apply_phase_outcome_validates_change_id(chdir_tmp: Path) -> None:
    with pytest.raises(ValueError):
        phase_agent.apply_phase_outcome(
            change_id="../etc/passwd",
            phase="IMPLEMENT",
            outcome="continue",
            handoff_id="h",
        )
