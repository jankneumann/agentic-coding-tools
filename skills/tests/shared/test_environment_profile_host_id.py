"""environment_profile.host_id() (dispatch-contract D7)."""
from __future__ import annotations

import re
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import environment_profile as ep  # noqa: E402

_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ep._HOST_ID_VARS:
        monkeypatch.delenv(name, raising=False)


def test_cloud_environment_id_is_used_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_ENVIRONMENT_ID", "env_01ABCdef")
    assert ep.host_id() == "env_01ABCdef"


def test_explicit_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_ENVIRONMENT_ID", "env_01ABCdef")
    monkeypatch.setenv("AGENT_HOST_ID", "host-a")
    assert ep.host_id() == "host-a"


def test_unportable_environment_id_is_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_HOST_ID", "/not a portable id/")
    value = ep.host_id()
    assert value.startswith("env-") and _PATTERN.fullmatch(value)


def test_machine_id_is_hashed_never_raw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    machine = tmp_path / "machine-id"
    machine.write_text("0123456789abcdef0123456789abcdef\n")
    monkeypatch.setattr(ep, "_MACHINE_ID_PATHS", (str(machine),))
    value = ep.host_id()
    assert value.startswith("machine-")
    assert "0123456789abcdef0123456789abcdef" not in value
    assert value == ep.host_id(), "stable across calls"


def test_fallback_never_uses_hostname_or_username(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ep, "_MACHINE_ID_PATHS", (str(tmp_path / "absent"),))
    value = ep.host_id()
    assert _PATTERN.fullmatch(value)
    assert socket.gethostname() not in value
    assert value.startswith("node-")
