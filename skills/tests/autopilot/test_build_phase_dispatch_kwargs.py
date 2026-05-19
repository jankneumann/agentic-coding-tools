"""Tests for `phase_agent.build_phase_dispatch_kwargs`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Requirement: Sub-Agent Dispatch Protocol Helpers
      Scenario: build_phase_dispatch_kwargs returns dispatch-ready dict
Design decisions: D2 (system_prompt folding inside the helper),
                  D3 (dict return + cache write side-effect),
                  D4 (cache file schema + atomic write).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import coordination_bridge
import phase_agent
import pytest


_RESOLVED_IMPLEMENTER: dict[str, Any] = {
    "model": "sonnet",
    "system_prompt": "You are an implementer. Follow the contract.",
    "archetype": "implementer",
    "reasons": ["phase=IMPLEMENT maps to archetype=implementer"],
}

_RESOLVED_ARCHITECT: dict[str, Any] = {
    "model": "opus",
    "system_prompt": "You are a software architect.",
    "archetype": "architect",
    "reasons": ["phase=PLAN_ITERATE maps to archetype=architect"],
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)


def _stub_bridge(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: response,
    )


def _seed_loop_state(repo_root: Path, change_id: str, **overrides: Any) -> Path:
    """Seed an `openspec/changes/<change_id>/loop-state.json` under *repo_root*."""
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


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into tmp_path so relative `openspec/changes/...` lookups land here."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Happy-path returns
# ---------------------------------------------------------------------------


def test_build_phase_dispatch_kwargs_returns_required_keys(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change", current_phase="IMPLEMENT")

    result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    assert isinstance(result, dict)
    for key in ("prompt", "model", "system_prompt", "isolation", "archetype"):
        assert key in result, f"missing key {key!r} in dispatch dict"


def test_build_phase_dispatch_kwargs_implement_sets_worktree_isolation(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change")

    result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    assert result["isolation"] == "worktree"
    assert result["model"] == "sonnet"
    assert result["archetype"] == "implementer"


def test_build_phase_dispatch_kwargs_plan_iterate_sets_worktree_isolation(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    _seed_loop_state(chdir_tmp, "demo-change", current_phase="PLAN_ITERATE")

    result = phase_agent.build_phase_dispatch_kwargs("PLAN_ITERATE", "demo-change")

    assert result["isolation"] == "worktree"
    assert result["model"] == "opus"
    assert result["archetype"] == "architect"


@pytest.mark.parametrize(
    "phase",
    [
        "PLAN",
        "PLAN_ITERATE",
        "PLAN_REVIEW",
        "PLAN_FIX",
        "IMPLEMENT",
        "IMPL_ITERATE",
        "IMPL_REVIEW",
        "IMPL_FIX",
        "VALIDATE",
        "VAL_REVIEW",
        "VAL_FIX",
    ],
)
def test_build_phase_dispatch_kwargs_write_capable_phases_use_worktree(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    _seed_loop_state(chdir_tmp, "demo-change", current_phase=phase)

    result = phase_agent.build_phase_dispatch_kwargs(phase, "demo-change")

    assert result["isolation"] == "worktree"


# ---------------------------------------------------------------------------
# Folding semantics (D2)
# ---------------------------------------------------------------------------


def test_build_phase_dispatch_kwargs_folds_system_prompt_into_prompt(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`prompt` MUST start with system_prompt + SEPARATOR + phase prompt."""
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change")

    result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    folded: str = result["prompt"]
    assert folded.startswith(_RESOLVED_IMPLEMENTER["system_prompt"])
    assert "\n\n---\n\n" in folded
    # exactly one separator occurrence
    assert folded.count("\n\n---\n\n") == 1
    # system_prompt is echoed back for audit
    assert result["system_prompt"] == _RESOLVED_IMPLEMENTER["system_prompt"]


def test_build_phase_dispatch_kwargs_no_archetype_no_separator(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When bridge returns None, no system_prompt to fold; prompt is the bare phase prompt."""
    _stub_bridge(monkeypatch, None)
    _seed_loop_state(chdir_tmp, "demo-change")

    result = phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    assert result["model"] is None
    assert result["system_prompt"] is None
    assert result["archetype"] is None
    # No separator should be present (bridge returned None → no system_prompt)
    assert "\n\n---\n\n" not in result["prompt"]


# ---------------------------------------------------------------------------
# Cache file write (D4)
# ---------------------------------------------------------------------------


def test_build_phase_dispatch_kwargs_writes_cache_file_with_schema(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change")

    phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    cache_path = chdir_tmp / "openspec" / "changes" / "demo-change" / ".phase-resolution-cache.json"
    assert cache_path.exists()
    cache = json.loads(cache_path.read_text())
    assert cache["schema_version"] == 1
    assert cache["change_id"] == "demo-change"
    assert cache["phase"] == "IMPLEMENT"
    assert cache["archetype"] == "implementer"
    assert "checksum" in cache and isinstance(cache["checksum"], str)


def test_build_phase_dispatch_kwargs_cache_checksum_is_sha256(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change")

    phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    cache_path = chdir_tmp / "openspec" / "changes" / "demo-change" / ".phase-resolution-cache.json"
    cache = json.loads(cache_path.read_text())
    expected = hashlib.sha256(
        b"demo-change" + b"IMPLEMENT" + b"implementer"
    ).hexdigest()
    assert cache["checksum"] == expected


def test_build_phase_dispatch_kwargs_cache_archetype_null_when_bridge_fails(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, None)
    _seed_loop_state(chdir_tmp, "demo-change")

    phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    cache_path = chdir_tmp / "openspec" / "changes" / "demo-change" / ".phase-resolution-cache.json"
    cache = json.loads(cache_path.read_text())
    assert cache["archetype"] is None
    expected = hashlib.sha256(
        b"demo-change" + b"IMPLEMENT" + b"null"
    ).hexdigest()
    assert cache["checksum"] == expected


def test_build_phase_dispatch_kwargs_cache_overwritten_on_second_call(
    chdir_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call for a different phase clobbers the cache file."""
    _stub_bridge(monkeypatch, _RESOLVED_IMPLEMENTER)
    _seed_loop_state(chdir_tmp, "demo-change")

    phase_agent.build_phase_dispatch_kwargs("IMPLEMENT", "demo-change")

    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    phase_agent.build_phase_dispatch_kwargs("PLAN_ITERATE", "demo-change")

    cache_path = chdir_tmp / "openspec" / "changes" / "demo-change" / ".phase-resolution-cache.json"
    cache = json.loads(cache_path.read_text())
    assert cache["phase"] == "PLAN_ITERATE"
    assert cache["archetype"] == "architect"
