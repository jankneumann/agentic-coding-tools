"""Tests for the ``cli.probe`` block in agents.yaml (task 4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from src.agents_config import (
    get_dispatch_configs,
    load_agents_config,
    reset_agents_config,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_agents_config()


def _load(tmp_path: Path, **agents_probe):
    """Write an agents.yaml where each kwarg is agent name -> probe block."""
    agents = {
        name: {
            "type": "codex",
            "profile": f"profile_{name.replace('-', '_')}",
            "trust_level": 3,
            "transport": "mcp",
            "capabilities": ["lock", "queue"],
            "description": "probe test",
            "cli": {
                "command": "codex",
                "dispatch_modes": {"review": {"args": ["exec", "-s", "read-only"]}},
                "model_flag": "-m",
                **({"probe": probe} if probe is not Ellipsis else {}),
            },
        }
        for name, probe in agents_probe.items()
    }
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump({"credential_vendors": [], "agents": agents}))
    secrets = tmp_path / ".secrets.yaml"
    secrets.write_text("{}")
    return load_agents_config(path, secrets_path=secrets)


@pytest.mark.parametrize(
    "probe",
    [
        {"auth_status_args": ["auth", "print-api-key", "--provider", "openai"]},
        {"auth_status_args": ["auth", "Print-API-Key"]},
        {"version_args": ["auth", "print-api-key"]},
        {"help_args": {"review": ["--help", "--show-token"]}},
        {"auth_status_args": ["LOGOUT"]},
        {"auth_status_args": ["--credentials"]},
        {"auth_status_args": ["print-bearer-token"]},
        {"ignore_flags": []},
        {"credential_files": []},
        {"version_args": []},
        {"help_args": {}},
        {"ignore_flags": ["nodash"]},
        {"required_flags": ["--json-schema"]},
    ],
)
def test_schema_rejects(tmp_path, probe):
    with pytest.raises(ValidationError):
        _load(tmp_path, a=probe)


def test_help_override_must_contain_help_token(tmp_path):
    with pytest.raises(ValidationError):
        _load(tmp_path, a={"help_args": {"review": ["exec", "-s", "read-only"]}})
    with pytest.raises(ValidationError):
        _load(tmp_path, a={"help_args": {"review": ["--helpful"]}})
    _load(tmp_path, a={"help_args": {"review": ["exec", "--help"]}})
    _load(tmp_path, a={"help_args": {"review": ["help"]}})


def test_login_status_accepted_bare_login_rejected(tmp_path):
    entries = _load(tmp_path, a={"auth_status_args": ["login", "status"]})
    assert entries[0].cli.probe == {"auth_status_args": ["login", "status"]}
    with pytest.raises(ValidationError, match="login"):
        _load(tmp_path, b={"auth_status_args": ["login"]})


def test_full_probe_block_loads(tmp_path):
    probe = {
        "version_args": ["-V"],
        "help_args": {"review": ["exec", "--help"]},
        "auth_status_args": ["auth", "status"],
        "credential_files": ["~/.x/auth.json"],
        "ignore_flags": ["--foo"],
    }
    assert _load(tmp_path, a=probe)[0].cli.probe == probe


def test_absent_probe_is_none_and_omitted_from_dispatch_configs(tmp_path):
    entries = _load(tmp_path, a=Ellipsis)
    assert entries[0].cli.probe is None
    cli = get_dispatch_configs(entries)["agents"][0]["cli"]
    assert "probe" not in cli


def test_empty_probe_survives_round_trip(tmp_path):
    entries = _load(tmp_path, a={})
    assert entries[0].cli.probe == {}
    cli = get_dispatch_configs(entries)["agents"][0]["cli"]
    assert cli["probe"] == {}
    assert json.loads(json.dumps(cli))["probe"] == {}


def test_probe_round_trips_through_dispatch_configs(tmp_path):
    entries = _load(tmp_path, a={"auth_status_args": ["auth", "status"]})
    cli = get_dispatch_configs(entries)["agents"][0]["cli"]
    assert cli["probe"] == {"auth_status_args": ["auth", "status"]}
