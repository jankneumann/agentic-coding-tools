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


def test_adaptive_flag_preserves_caller_modality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _adaptive(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "selected": {
                "vendor": "local",
                "model": "qwen",
                "endpoint_kind": "local",
                "score": 0.5,
            }
        }

    monkeypatch.setenv("ROUTING_ADAPTIVE", "true")
    monkeypatch.setattr("src.model_routing.api.resolve_phase_model", _adaptive)

    resolve_archetype_for_phase(
        "IMPLEMENT", {"complexity": "low", "modality": "interactive"}
    )

    assert captured["task_signals"]["modality"] == "interactive"


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


# ── incumbent forwarding (retain-static-model-until-routing-evidence) ────────

def _capture(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _adaptive(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return response

    monkeypatch.setenv("ROUTING_ADAPTIVE", "true")
    monkeypatch.setattr("src.model_routing.api.resolve_phase_model", _adaptive)
    return captured


_RETAINED = {
    "selected": None,
    "retention": {"retained": True, "reason": "incumbent-unresolved", "margin": 0.05},
}


@pytest.mark.parametrize(
    ("provider", "catalog_vendor"),
    [("codex", "codex"), ("claude_code", "claude_code"), ("pi", "openrouter")],
)
def test_static_resolution_is_forwarded_as_the_incumbent(
    monkeypatch: pytest.MonkeyPatch, provider: str, catalog_vendor: str
) -> None:
    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    static = resolve_archetype_for_phase("PLAN", {}, provider=provider)
    captured = _capture(monkeypatch, _RETAINED)

    resolve_archetype_for_phase("PLAN", {}, provider=provider)

    assert captured["incumbent"] == {"vendor": catalog_vendor, "model": static.model}


def test_unknown_provider_forwards_a_vendorless_incumbent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTING_ADAPTIVE", "off")
    static = resolve_archetype_for_phase("PLAN", {})
    captured = _capture(monkeypatch, _RETAINED)

    resolve_archetype_for_phase("PLAN", {})

    assert captured["incumbent"] == {"vendor": None, "model": static.model}


@pytest.mark.parametrize(
    "response",
    [
        _RETAINED,
        {
            # A retained incumbent that has a catalog row still returns static.
            "selected": {"vendor": "codex", "model": "catalog-name", "score": 0.1},
            "retention": {"retained": True, "reason": "no-evidence", "margin": 0.05},
        },
    ],
)
def test_retention_returns_the_identical_static_object(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> None:
    import src.agents_config as agents_config

    sentinel = agents_config._resolve_archetype_for_phase_static("PLAN", {}, provider="codex")
    monkeypatch.setattr(
        agents_config, "_resolve_archetype_for_phase_static", lambda *_a, **_k: sentinel
    )
    _capture(monkeypatch, response)

    assert resolve_archetype_for_phase("PLAN", {}, provider="codex") is sentinel


def test_non_retained_selection_still_routes_adaptively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture(
        monkeypatch,
        {
            "selected": {"vendor": "codex", "model": "gpt-5.6-terra", "score": 0.9},
            "retention": {
                "retained": False,
                "reason": "challenger-evidenced-above-margin",
                "margin": 0.05,
            },
        },
    )

    resolved = resolve_archetype_for_phase("PLAN", {}, provider="claude_code")

    assert (resolved.provider, resolved.model) == ("codex", "gpt-5.6-terra")


def test_seam_sends_the_incumbent_and_accepts_a_retained_null_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.model_routing import api

    sent: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return _RETAINED

    def _post(url: str, *, json: dict[str, Any], **_kw: Any) -> _Response:
        sent.update(json)
        return _Response()

    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setattr(api.httpx, "post", _post)

    result = api.resolve_phase_model(
        task_signals={"archetype": "architect"},
        static_model="fable",
        provider="claude_code",
        timeout_seconds=1.0,
        incumbent={"vendor": "claude_code", "model": "fable"},
    )

    assert sent["incumbent"] == {"vendor": "claude_code", "model": "fable"}
    assert result["retention"]["retained"] is True


def test_seam_still_rejects_a_null_selection_without_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.model_routing import api

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"selected": None}

    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setattr(api.httpx, "post", lambda *_a, **_k: _Response())

    with pytest.raises(api.RoutingUnavailableError):
        api.resolve_phase_model(
            task_signals={"archetype": "architect"},
            static_model="fable",
            provider=None,
            timeout_seconds=1.0,
        )
