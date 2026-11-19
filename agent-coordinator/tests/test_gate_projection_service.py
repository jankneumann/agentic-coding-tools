"""Gate projection: configuration and service behaviour.

The service is exercised against a hand-written fake database and a fake
approval service, so each test states exactly which rows exist and can count
the reads the listing makes.
"""

from __future__ import annotations

import pytest

from src.config import GateProjectionConfig, get_config, reset_config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_config_defaults_to_no_enrolled_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GATE_PROJECTION_PROJECTS", raising=False)
    monkeypatch.delenv("GATE_PROJECTION_STALE_SECONDS", raising=False)

    config = GateProjectionConfig.from_env()

    assert config.projects == frozenset()
    assert config.stale_seconds == 86400


def test_config_reads_a_comma_separated_enrolment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_PROJECTS", " acme/api , acme/web,, ")
    monkeypatch.setenv("GATE_PROJECTION_STALE_SECONDS", "600")

    config = GateProjectionConfig.from_env()

    assert config.projects == frozenset({"acme/api", "acme/web"})
    assert config.stale_seconds == 600


def test_config_stale_window_is_at_least_one_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_STALE_SECONDS", "0")

    assert GateProjectionConfig.from_env().stale_seconds == 1


def test_config_is_attached_to_the_coordinator_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATE_PROJECTION_PROJECTS", "acme/api")
    reset_config()
    try:
        assert get_config().gate_projection.projects == frozenset({"acme/api"})
    finally:
        reset_config()
