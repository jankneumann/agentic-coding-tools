"""Tests for AUTOPILOT_PHASE_MODEL_OVERRIDE parsing and application.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/skill-workflow/spec.md
      Requirement: Per-Phase Archetype Resolution Override.
Design decision: D8 (env var format).
"""

from __future__ import annotations

import logging

import phase_agent
import pytest


def test_parse_empty_override_returns_empty_dict() -> None:
    assert phase_agent._parse_phase_model_override(None) == {}
    assert phase_agent._parse_phase_model_override("") == {}
    assert phase_agent._parse_phase_model_override("   ") == {}


def test_parse_single_override() -> None:
    assert phase_agent._parse_phase_model_override("PLAN=opus") == {"PLAN": "opus"}


def test_parse_multiple_overrides() -> None:
    raw = "PLAN=opus,IMPL_REVIEW=sonnet,VALIDATE=haiku"
    assert phase_agent._parse_phase_model_override(raw) == {
        "PLAN": "opus",
        "IMPL_REVIEW": "sonnet",
        "VALIDATE": "haiku",
    }


def test_parse_handles_whitespace() -> None:
    raw = "  PLAN = opus , IMPL_REVIEW=sonnet  "
    out = phase_agent._parse_phase_model_override(raw)
    assert out == {"PLAN": "opus", "IMPL_REVIEW": "sonnet"}


def test_parse_unknown_phase_warns_and_skips(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="phase_agent"):
        out = phase_agent._parse_phase_model_override("BOGUS=opus,PLAN=sonnet")
    assert out == {"PLAN": "sonnet"}
    assert any("BOGUS" in r.message for r in caplog.records), (
        f"expected WARNING about BOGUS phase, got: {[r.message for r in caplog.records]}"
    )


def test_parse_malformed_entry_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="phase_agent"):
        out = phase_agent._parse_phase_model_override("PLAN=opus,no-equals,IMPLEMENT=sonnet")
    assert out == {"PLAN": "opus", "IMPLEMENT": "sonnet"}
    assert any("no-equals" in r.message or "missing '='" in r.message for r in caplog.records)


def test_parse_unknown_model_passes_through() -> None:
    """Unknown model names pass through (validated downstream)."""
    out = phase_agent._parse_phase_model_override("PLAN=experimental-v9")
    assert out == {"PLAN": "experimental-v9"}


def test_parse_empty_model_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="phase_agent"):
        out = phase_agent._parse_phase_model_override("PLAN=,IMPLEMENT=sonnet")
    assert out == {"IMPLEMENT": "sonnet"}


def test_check_phase_model_override_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", "PLAN=opus,IMPLEMENT=haiku")
    assert phase_agent._check_phase_model_override("PLAN") == "opus"
    assert phase_agent._check_phase_model_override("IMPLEMENT") == "haiku"
    assert phase_agent._check_phase_model_override("VALIDATE") is None


def test_check_phase_model_override_no_env_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)
    assert phase_agent._check_phase_model_override("PLAN") is None
