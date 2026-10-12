"""Tests for the extended _build_options(phase, state_dict).

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/skill-workflow/spec.md
      Requirements:
        - Per-Phase Archetype Resolution in Autopilot
        - Per-Phase Archetype Resolution Override
        - Per-Phase Archetype Resolution Failure Mode
Design decisions: D5, D8, D9, D13.

Also covers `_selected_provider` and `build_phase_dispatch_payload`'s default
-provider behavior: openspec/changes/add-infeasible-incumbent-fallback
design D1/D2 (task 1.1). D2's default-provider precondition is applied
client-side here (provider threaded into the stubbed bridge call); the
server-side tier -> concrete-alias mapping (`resolve_provider_model_spec` in
`agent-coordinator/src/agents_config.py`) is out of this package's scope and
is exercised by its own suite, not re-tested through a mock here.
"""

from __future__ import annotations

from pathlib import Path
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


def test_build_options_sets_isolation_for_validate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bridge(monkeypatch, _RESOLVED_ARCHITECT)
    options = phase_agent._build_options("VALIDATE", {})
    assert options.get("isolation") == "worktree"


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


# ---------------------------------------------------------------------------
# _selected_provider (D2) — default provider applied before resolution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop provider-selection env vars so these tests are deterministic."""
    monkeypatch.delenv("AUTOPILOT_PROVIDER", raising=False)
    monkeypatch.delenv("AGENT_TYPE", raising=False)


def test_selected_provider_defaults_to_claude_code_with_no_signal() -> None:
    """No explicit arg, no env var -> the concrete default, not None (D2)."""
    assert phase_agent._selected_provider() == "claude_code"


@pytest.mark.parametrize("raw", ["   ", "\t", "\n "])
def test_selected_provider_defaults_to_claude_code_for_whitespace_env(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A whitespace-only env value is treated as unset, not as a literal provider."""
    monkeypatch.setenv("AUTOPILOT_PROVIDER", raw)
    assert phase_agent._selected_provider() == "claude_code"


def test_selected_provider_whitespace_explicit_arg_defaults() -> None:
    """A whitespace-only explicit arg also falls through to the default."""
    assert phase_agent._selected_provider("   ") == "claude_code"


def test_selected_provider_agent_type_still_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AGENT_TYPE is consulted when no explicit arg and no AUTOPILOT_PROVIDER."""
    monkeypatch.setenv("AGENT_TYPE", "codex")
    assert phase_agent._selected_provider() == "codex"


def test_selected_provider_autopilot_provider_wins_over_agent_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TYPE", "codex")
    monkeypatch.setenv("AUTOPILOT_PROVIDER", "grok")
    assert phase_agent._selected_provider() == "grok"


def test_selected_provider_explicit_arg_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit arg has the highest precedence, over both env vars."""
    monkeypatch.setenv("AUTOPILOT_PROVIDER", "codex")
    monkeypatch.setenv("AGENT_TYPE", "grok")
    assert phase_agent._selected_provider("pi") == "pi"


def test_selected_provider_return_type_is_always_str(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D2 narrows the return type from `str | None` to `str` — never None."""
    for raw in (None, "", "   "):
        assert isinstance(phase_agent._selected_provider(raw), str)


def test_build_options_default_provider_yields_concrete_model_not_tier_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no explicit/env provider, the bridge now sees `provider="claude_code"`
    (not None), so a fixture standing in for the server's tier mapping returns a
    concrete model (`sonnet`) rather than a bare tier alias (`standard`)."""
    captured: dict[str, Any] = {}

    def fake_bridge(
        phase: str, signals: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        captured["provider"] = kwargs.get("provider")
        # Stand-in for resolve_provider_model_spec: a concrete provider gets a
        # concrete alias; a falsy one (pre-D2 behavior) would pass the bare tier
        # name through unchanged.
        model = "sonnet" if kwargs.get("provider") else "standard"
        return {
            "model": model,
            "system_prompt": "You are an implementer.",
            "archetype": "implementer",
            "reasons": ["phase=IMPLEMENT maps to archetype=implementer"],
        }

    monkeypatch.setattr(coordination_bridge, "try_resolve_archetype_for_phase", fake_bridge)

    options = phase_agent._build_options("IMPLEMENT", {})

    assert captured["provider"] == "claude_code"
    assert options["model"] == "sonnet"


# ---------------------------------------------------------------------------
# build_phase_dispatch_payload (D2) — default provider survives end to end
# ---------------------------------------------------------------------------


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into tmp_path so relative `openspec/changes/...` lookups land here."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_payload_pre_change_provider_preserved_when_resolver_unavailable(
    monkeypatch: pytest.MonkeyPatch, chdir_tmp: Path
) -> None:
    """Resolver unavailable (bridge returns None): provider still defaults to
    the pre-change `claude_code`, and no model is fabricated."""
    _stub_bridge(monkeypatch, None)

    payload = phase_agent.build_phase_dispatch_payload("IMPLEMENT", "demo-change")

    assert payload["provider"] == "claude_code"
    assert payload["model"] is None


def test_payload_pre_change_provider_preserved_with_explicit_provider(
    monkeypatch: pytest.MonkeyPatch, chdir_tmp: Path
) -> None:
    """An explicit/env-selected provider is unaffected by the new default (the
    'pre-change provider' for a caller that already set one)."""
    monkeypatch.setenv("AGENT_TYPE", "codex")
    _stub_bridge(monkeypatch, None)

    payload = phase_agent.build_phase_dispatch_payload("IMPLEMENT", "demo-change")

    assert payload["provider"] == "codex"


def test_payload_default_provider_with_retained_incumbent_gets_concrete_alias(
    monkeypatch: pytest.MonkeyPatch, chdir_tmp: Path
) -> None:
    """Flag off / a retained incumbent: the bridge still resolves (no cross
    -vendor fallback fired), and with the default provider now concrete the
    payload carries the tier's concrete model alias, not a bare tier name."""
    _stub_bridge(
        monkeypatch,
        {
            "model": "sonnet",
            "system_prompt": "You are an implementer.",
            "archetype": "implementer",
            "reasons": ["phase=IMPLEMENT maps to archetype=implementer"],
        },
    )

    payload = phase_agent.build_phase_dispatch_payload("IMPLEMENT", "demo-change")

    assert payload["provider"] == "claude_code"
    assert payload["model"] == "sonnet"
