"""Vendor CLI subprocesses get an allowlisted environment, not the session's.

A reviewer CLI runs a prompt assembled from repository content, so a prompt
injection in the reviewed diff must not find ``GH_TOKEN`` (push rights) or
``COORDINATION_API_KEY`` (enqueue work) in its environment.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from review_dispatcher import (
    ENV_PASSTHROUGH_VAR,
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
    vendor_subprocess_env,
)

_SCRIPT = Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts" / "review_dispatcher.py"

_SESSION = {
    "PATH": "/usr/bin",
    "HOME": "/home/u",
    "HTTPS_PROXY": "http://proxy:8080",
    "LC_ALL": "C.UTF-8",
    "GH_TOKEN": "ghp_secret",
    "GITHUB_TOKEN": "ghs_secret",
    "COORDINATION_API_KEY": "coord_secret",
    "COORDINATION_API_KEY_IDENTITIES": "{}",
    "BAO_TOKEN": "bao_secret",
    "SSH_AUTH_SOCK": "/tmp/agent.sock",
    "ANTHROPIC_API_KEY": "sk-ant",
    "OPENAI_API_KEY": "sk-openai",
    "XAI_API_KEY": "xai-key",
    "OPENROUTER_API_KEY": "or-key",
    "DATABASE_URL": "postgres://secret",
}


def _cfg(command: str, api_key_env: str = "") -> CliConfig:
    return CliConfig(
        command=command,
        dispatch_modes={"review": ModeConfig(args=["--print"])},
        model_flag="-m",
        api_key_env=api_key_env,
    )


def test_base_names_pass_and_secrets_do_not() -> None:
    env = vendor_subprocess_env(_cfg("claude"), _SESSION)
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/u"
    assert env["HTTPS_PROXY"] == "http://proxy:8080"
    assert env["LC_ALL"] == "C.UTF-8"
    for name in (
        "GH_TOKEN", "GITHUB_TOKEN", "COORDINATION_API_KEY",
        "COORDINATION_API_KEY_IDENTITIES", "BAO_TOKEN", "SSH_AUTH_SOCK", "DATABASE_URL",
    ):
        assert name not in env, name


@pytest.mark.parametrize(
    ("command", "own", "foreign"),
    [
        ("claude", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"),
        ("codex", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        ("grok", "XAI_API_KEY", "OPENROUTER_API_KEY"),
        ("pi", "OPENROUTER_API_KEY", "XAI_API_KEY"),
        ("/usr/local/bin/grok", "XAI_API_KEY", "ANTHROPIC_API_KEY"),
    ],
)
def test_each_vendor_sees_only_its_own_credentials(command: str, own: str, foreign: str) -> None:
    env = vendor_subprocess_env(_cfg(command), _SESSION)
    assert own in env
    assert foreign not in env


def test_api_key_env_is_always_passed() -> None:
    session = {**_SESSION, "CUSTOM_PROVIDER_KEY": "k"}
    env = vendor_subprocess_env(_cfg("unknown-cli", api_key_env="CUSTOM_PROVIDER_KEY"), session)
    assert env["CUSTOM_PROVIDER_KEY"] == "k"
    assert "ANTHROPIC_API_KEY" not in env


def test_passthrough_adds_names_but_never_the_hard_excludes() -> None:
    session = {**_SESSION, "EXTRA_SETTING": "x", ENV_PASSTHROUGH_VAR: "EXTRA_SETTING, GH_TOKEN,BAO_TOKEN"}
    env = vendor_subprocess_env(_cfg("claude"), session)
    assert env["EXTRA_SETTING"] == "x"
    assert "GH_TOKEN" not in env
    assert "BAO_TOKEN" not in env


@patch("review_dispatcher.subprocess.run")
def test_dispatch_passes_scrubbed_env(mock_run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _SESSION.items():
        monkeypatch.setenv(name, value)
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"findings": []}), stderr="",
    )
    adapter = CliVendorAdapter(agent_id="claude-local", vendor="claude", cli_config=_cfg("claude"))
    adapter.dispatch("review", "prompt", cwd=tmp_path)

    env = mock_run.call_args.kwargs["env"]
    assert env["ANTHROPIC_API_KEY"] == "sk-ant"
    assert env["HOME"] == "/home/u"
    assert "GH_TOKEN" not in env
    assert "COORDINATION_API_KEY" not in env


def test_every_adapter_subprocess_call_sets_env() -> None:
    """Async submit and status polling must not fall back to inheriting."""
    tree = ast.parse(_SCRIPT.read_text())
    adapter = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CliVendorAdapter"
    )
    calls = [
        n for n in ast.walk(adapter)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "run"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "subprocess"
    ]
    assert len(calls) >= 3
    missing = [c.lineno for c in calls if not any(k.arg == "env" for k in c.keywords)]
    assert not missing, f"CliVendorAdapter subprocess.run without env= at lines {missing}"
