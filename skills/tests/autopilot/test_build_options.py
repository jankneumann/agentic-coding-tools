"""Tests for the extended _build_options(phase, state_dict).

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/skill-workflow/spec.md
      Requirements:
        - Per-Phase Archetype Resolution in Autopilot
        - Per-Phase Archetype Resolution Override
        - Per-Phase Archetype Resolution Failure Mode
Design decisions: D5, D8, D9, D13.
"""

from __future__ import annotations

from typing import Any

import coordination_bridge
import phase_agent
import pytest

_RESOLVED_ARCHITECT: dict[str, Any] = {
    "model": "opus",
    "system_prompt": "You are a software architect.",
    "archetype": "architect",
    "reasons": ["phase=PLAN maps to archetype=architect"],
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the override env var so tests are deterministic."""
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)


def _stub_bridge(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None) -> None:
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: response,
    )


def test_build_options_sets_isolation_for_implement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    options = phase_agent._build_options("IMPLEMENT", {})
    assert options.get("isolation") == "worktree"


def test_build_options_no_isolation_for_validate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    options = phase_agent._build_options("VALIDATE", {})
    assert "isolation" not in options


def test_build_options_archetype_path_sets_model_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    state_dict: dict[str, Any] = {"capabilities_touched": 3}

    options = phase_agent._build_options("PLAN", state_dict)

    assert options["model"] == "opus"
    assert options["system_prompt"] == "You are a software architect."
    # Resolved archetype recorded for LoopState.phase_archetype propagation.
    assert state_dict["_resolved_archetype"] == "architect"


def test_build_options_passes_filtered_signals_to_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_bridge(phase: str, signals: dict[str, Any] | None = None, **_: Any) -> dict[str, Any] | None:
        captured["phase"] = phase
        captured["signals"] = signals
        return _RESOLVED_ARCHITECT

    monkeypatch.setattr(coordination_bridge, "try_resolve_archetype_for_phase", fake_bridge)

    state_dict = {
        "loc_estimate": 250,
        "write_allow": ["src/api/**"],
        "irrelevant": "dropped",
    }
    phase_agent._build_options("IMPLEMENT", state_dict)

    assert captured["phase"] == "IMPLEMENT"
    # IMPLEMENT signals = [loc_estimate, write_allow, dependencies, complexity]
    assert captured["signals"] == {
        "loc_estimate": 250,
        "write_allow": ["src/api/**"],
    }


def test_build_options_override_path_skips_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator override sets model only; system_prompt stays harness default."""
    monkeypatch.setenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", "PLAN=haiku")
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)  # bridge would return architect

    state_dict: dict[str, Any] = {}
    options = phase_agent._build_options("PLAN", state_dict)

    assert options["model"] == "haiku"  # override wins over architect's opus
    assert "system_prompt" not in options
    # Override path does NOT record _resolved_archetype (no archetype info).
    assert "_resolved_archetype" not in state_dict


def test_build_options_override_does_not_call_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optimization: override path skips the HTTP bridge call entirely."""
    monkeypatch.setenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", "IMPLEMENT=sonnet")

    bridge_called = {"count": 0}

    def fake_bridge(*args: Any, **kwargs: Any) -> None:
        bridge_called["count"] += 1
        return None

    monkeypatch.setattr(coordination_bridge, "try_resolve_archetype_for_phase", fake_bridge)

    phase_agent._build_options("IMPLEMENT", {})

    assert bridge_called["count"] == 0


def test_build_options_bridge_failure_falls_back_to_harness_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D9: bridge None → no model/system_prompt injection, no _resolved_archetype."""
    _stub_bridge(monkeypatch, None)

    state_dict: dict[str, Any] = {}
    options = phase_agent._build_options("PLAN", state_dict)

    # Only isolation may be set (PLAN is not a worktree phase, so even that is absent).
    assert "model" not in options
    assert "system_prompt" not in options
    assert "_resolved_archetype" not in state_dict


def test_build_options_for_state_only_phase_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INIT has empty signals; resolution still attempted; result recorded."""
    runner_resolved: dict[str, Any] = {
        "model": "haiku",
        "system_prompt": "Execute and report.",
        "archetype": "runner",
        "reasons": ["phase=INIT maps to archetype=runner"],
    }
    _stub_bridge(monkeypatch, runner_resolved)

    state_dict: dict[str, Any] = {}
    options = phase_agent._build_options("INIT", state_dict)

    assert options["model"] == "haiku"
    assert state_dict["_resolved_archetype"] == "runner"


def test_build_options_unknown_phase_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown phases get empty signals; bridge will likely return None (404)."""
    _stub_bridge(monkeypatch, None)
    options = phase_agent._build_options("BOGUS_PHASE", {"loc_estimate": 100})
    assert "model" not in options
