"""Adaptive archetype delegation remains a safe, default-off wrapper."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from src.agents_config import (
    load_archetypes_config,
    reset_archetypes_config,
    resolve_archetype_for_phase,
)

_ARCHETYPES = Path(__file__).resolve().parents[2] / "archetypes.yaml"


@pytest.fixture(autouse=True)
def _load_real_archetypes() -> None:
    reset_archetypes_config()
    load_archetypes_config(_ARCHETYPES)
    yield
    reset_archetypes_config()


def test_adaptive_flag_off_preserves_exact_static_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROUTING_ADAPTIVE", raising=False)
    baseline = resolve_archetype_for_phase(
        "IMPLEMENT", {"complexity": "high"}, provider="codex"
    )

    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    assert resolve_archetype_for_phase(
        "IMPLEMENT", {"complexity": "high"}, provider="codex"
    ) == baseline


def test_adaptive_flag_forwards_phase_archetype_and_escalation_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _adaptive(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "selected": {
                "vendor": "openrouter",
                "model": "qwen/qwen3-coder",
                "endpoint_kind": "openrouter",
                "score": 0.9,
            }
        }

    monkeypatch.setenv("ROUTING_ADAPTIVE", "true")
    monkeypatch.setattr("src.model_routing.api.resolve_phase_model", _adaptive)

    resolved = resolve_archetype_for_phase(
        "IMPLEMENT",
        {"complexity": "high", "write_allow": ["a/x.py", "b/y.py"]},
        provider="codex",
    )

    assert resolved.model == "qwen/qwen3-coder"
    assert resolved.provider == "openrouter"
    assert captured["task_signals"] == {
        "archetype": resolved.archetype,
        "phase": "IMPLEMENT",
        "task_type": f"{resolved.archetype}/high-complexity",
        "complexity": "high",
        "write_allow": ["a/x.py", "b/y.py"],
        "modality": "programmatic",
    }
    assert any("adaptive routing selected" in reason for reason in resolved.reasons)


def test_adaptive_error_returns_static_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTING_ADAPTIVE", "1")
    monkeypatch.setattr(
        "src.model_routing.api.resolve_phase_model",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("router unavailable")),
    )
    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    expected = resolve_archetype_for_phase("PLAN", {})

    monkeypatch.setenv("ROUTING_ADAPTIVE", "1")
    actual = resolve_archetype_for_phase("PLAN", {})

    assert actual == expected


def test_adaptive_timeout_is_bounded_and_returns_static_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _slow(**_kwargs: Any) -> dict[str, Any]:
        time.sleep(0.2)
        return {"selected": {"vendor": "local", "model": "too-late"}}

    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    expected = resolve_archetype_for_phase("INIT", {})
    monkeypatch.setenv("ROUTING_ADAPTIVE", "true")
    monkeypatch.setenv("ROUTING_ADAPTIVE_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr("src.model_routing.api.resolve_phase_model", _slow)

    started = time.monotonic()
    actual = resolve_archetype_for_phase("INIT", {})

    assert time.monotonic() - started < 0.15
    assert actual == expected
