"""Tests for vendor_probe L0/L1/L2 tiers (tasks 2.1 and 2.3), using fake CLIs."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

import vendor_probe as vp

SENTINEL = "sk-test-SENTINEL-AUTH-42"


def make_cli(
    tmp: Path,
    name: str = "fakecli",
    *,
    version_rc: int = 0,
    version_out: str = "fakecli 1.2.3",
    helps: dict[str, str] | None = None,
    help_rc: int = 0,
    auth_rc: int = 0,
    sleep: float = 0,
) -> Path:
    """Create an executable that logs every argv line to <name>.log."""
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp / f"{name}.log"
    helps = helps or {"--help": "usage: --help"}
    cases = ""
    for key, text in helps.items():
        cases += f'  "{key}") sleep {sleep}; cat <<\'EOT\'\n{text}\nEOT\n    exit {help_rc};;\n'
    script = f"""#!/bin/sh
echo "$*" >> "{log}"
case "$*" in
  "--version") sleep {sleep}; printf '%s\\n' '{version_out}'; exit {version_rc};;
{cases}  *) sleep {sleep}; echo {SENTINEL}; echo {SENTINEL} >&2; exit {auth_rc};;
esac
"""
    path = bindir / name
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def calls(tmp: Path, name: str = "fakecli") -> list[str]:
    log = tmp / f"{name}.log"
    return log.read_text().splitlines() if log.exists() else []


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.delenv("AGENTIC_PROBE_IGNORE_CACHE", raising=False)


def cli(**over):
    block = {
        "command": "fakecli",
        "dispatch_modes": {
            "review": {"args": ["-p", "--output-format=json", "--json-schema", "@review-findings-schema"]},
            "alternative": {"args": ["-p"]},
        },
        "model_flag": "--model",
        "probe": {},
    }
    block.update(over)
    return block


FULL_HELP = "usage: -p --output-format --json-schema --model"


# ------------------------------------------------------------- derivation


def test_required_flags_skip_values_and_placeholders():
    flags = vp.mode_required_flags(cli(), "review")
    assert flags == ["-p", "--output-format", "--json-schema", "--model"]


def test_undeclared_model_flag_defaults_to_dash_m():
    block = cli()
    del block["model_flag"]
    assert "-m" in vp.mode_required_flags(block, "alternative")
    block["model_flag"] = None
    assert "-m" in vp.mode_required_flags(block, "alternative")


def test_ignore_flags_removed():
    block = cli(probe={"ignore_flags": ["--json-schema"]})
    assert "--json-schema" not in vp.mode_required_flags(block, "review")


def test_help_argv_generated_and_partial_override():
    block = cli(
        dispatch_modes={
            "review": {"args": ["exec", "-s", "read-only"]},
            "alternative": {"args": ["-p"]},
        },
        probe={"help_args": {"review": ["exec", "--help"]}},
    )
    assert vp.mode_help_argv(block, "review") == ["exec", "--help"]
    assert vp.mode_help_argv(block, "alternative") == ["--help"]
    del block["probe"]
    assert vp.mode_help_argv(block, "review") == ["exec", "--help"]


# ------------------------------------------------------------------ L0/L1


def test_missing_flag_fails_that_mode_only(tmp_path):
    make_cli(tmp_path, helps={"--help": "usage: -p --output-format --model"})
    entry = vp.probe_lane("a", cli()).entry
    assert entry["l0"] == {"ok": True}
    assert entry["modes"]["review"] == {
        "ok": False,
        "reason": "missing_flags",
        "missing_flags": ["--json-schema"],
    }
    assert entry["modes"]["alternative"] == {"ok": True}
    assert entry["cli_version"] == "fakecli 1.2.3"


def test_whole_token_matching(tmp_path):
    make_cli(tmp_path, helps={"--help": "usage: --output-format-extra -pp --model"})
    entry = vp.probe_lane("a", cli()).entry
    assert entry["modes"]["alternative"]["missing_flags"] == ["-p"]


def test_subcommand_flags_checked_against_subcommand_help(tmp_path):
    make_cli(tmp_path, helps={"exec --help": "usage: -s -m", "--help": "nothing"})
    block = cli(
        dispatch_modes={"review": {"args": ["exec", "-s", "read-only"]}}, model_flag="-m"
    )
    entry = vp.probe_lane("a", block).entry
    assert entry["modes"]["review"] == {"ok": True}
    assert "exec --help" in calls(tmp_path)


def test_ignored_flags_pass(tmp_path):
    make_cli(tmp_path, helps={"--help": "usage: -p --output-format --model"})
    entry = vp.probe_lane("a", cli(probe={"ignore_flags": ["--json-schema"]})).entry
    assert entry["modes"]["review"] == {"ok": True}


def test_no_probe_block_is_version_only(tmp_path):
    make_cli(tmp_path, helps={"--help": "nothing"})
    block = cli()
    del block["probe"]
    result = vp.probe_lane("a", block)
    assert all(t == {"ok": True} for t in result.entry["modes"].values())
    assert result.entry["l2"] == {"status": "auth_unknown", "method": "none"}
    assert calls(tmp_path) == ["--version"]


def test_failing_version_fails_every_mode_without_help(tmp_path):
    make_cli(tmp_path, version_rc=1)
    entry = vp.probe_lane("a", cli()).entry
    assert all(t == {"ok": False, "reason": "probe_failed"} for t in entry["modes"].values())
    assert calls(tmp_path) == ["--version"]


def test_cli_not_found(tmp_path):
    entry = vp.probe_lane("a", cli(command="no-such-cli-xyz")).entry
    assert entry["l0"] == {"ok": False, "reason": "cli_not_found"}
    assert entry["cli_realpath"] is None
    assert entry["modes"]["review"]["reason"] == "cli_not_found"


def test_shared_help_runs_once(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    vp.probe_lane("a", cli())
    assert calls(tmp_path).count("--help") == 1


def test_help_nonzero_is_probe_failed(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP}, help_rc=3)
    entry = vp.probe_lane("a", cli()).entry
    assert entry["modes"]["review"] == {"ok": False, "reason": "probe_failed"}


def test_version_truncated(tmp_path):
    make_cli(tmp_path, version_out="v" * 500, helps={"--help": FULL_HELP})
    entry = vp.probe_lane("a", cli()).entry
    assert entry["cli_version"] == "v" * 200


def test_lane_deadline_bounds_slow_lane(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "SUBPROCESS_TIMEOUT", 0.6)
    make_cli(
        tmp_path,
        sleep=0.5,
        helps={"--help": FULL_HELP, "exec --help": FULL_HELP},
    )
    block = cli(
        dispatch_modes={"review": {"args": ["-p"]}, "alternative": {"args": ["exec", "-p"]}},
        probe={"auth_status_args": ["auth", "status"]},
    )
    start = time.monotonic()
    result = vp.probe_lane("a", block, lane_deadline=1.2)
    assert time.monotonic() - start < 2.5
    reasons = [t.get("reason") for t in result.entry["modes"].values()]
    assert "probe_timeout" in reasons or result.entry["l2"]["status"] == "probe_timeout"


def test_timeout_capped_at_remaining_budget(tmp_path):
    make_cli(tmp_path, sleep=5)
    start = time.monotonic()
    entry = vp.probe_lane("a", cli(), lane_deadline=0.5).entry
    assert time.monotonic() - start < 3
    assert entry["modes"]["review"] == {"ok": False, "reason": "probe_timeout"}


def test_health_probe_never_runs_dispatch_args(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    vp.probe_lane("a", cli(probe={"auth_status_args": ["auth", "status"]}))
    for line in calls(tmp_path):
        assert "--json-schema @review" not in line
        assert line in {"--version", "--help", "auth status"}


# --------------------------------------------------------------------- L2


def test_status_command_exit_codes_and_no_capture(tmp_path, capfd):
    make_cli(tmp_path, helps={"--help": FULL_HELP}, auth_rc=0)
    block = cli(probe={"auth_status_args": ["auth", "status"]})
    result = vp.probe_lane("a", block)
    assert result.entry["l2"] == {"status": "auth_ok", "method": "status_command"}
    out = capfd.readouterr()
    assert SENTINEL not in out.out + out.err
    assert SENTINEL not in repr(result)
    make_cli(tmp_path, helps={"--help": FULL_HELP}, auth_rc=1)
    assert vp.probe_lane("a", block).entry["l2"]["status"] == "auth_failed"


def test_status_command_takes_precedence_over_files(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP}, auth_rc=1)
    existing = tmp_path / "auth.json"
    existing.write_text("x")
    block = cli(probe={"auth_status_args": ["auth", "status"], "credential_files": [str(existing)]})
    assert vp.probe_lane("a", block).entry["l2"] == {
        "status": "auth_failed",
        "method": "status_command",
    }


def test_credential_files_existence_only_on_0000(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    f = tmp_path / "auth.json"
    f.write_text("secret")
    f.chmod(0)
    block = cli(probe={"credential_files": [str(f)]})
    assert vp.probe_lane("a", block).entry["l2"] == {"status": "auth_ok", "method": "credential_files"}
    block = cli(probe={"credential_files": [str(tmp_path / "missing.json")]})
    assert vp.probe_lane("a", block).entry["l2"] == {"status": "auth_failed", "method": "credential_files"}
    f.chmod(0o600)


def test_hanging_auth_is_probe_timeout_and_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "SUBPROCESS_TIMEOUT", 0.5)
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    # hang only on the auth invocation
    path = tmp_path / "bin" / "fakecli"
    path.write_text(path.read_text().replace("*) sleep 0;", "*) sleep 4;"))
    block = cli(probe={"auth_status_args": ["auth", "status"]})
    start = time.monotonic()
    entry = vp.probe_lane("a", block).entry
    assert time.monotonic() - start < 5
    assert entry["l2"] == {"status": "probe_timeout", "method": "status_command"}
    # not an exclusion reason
    assert vp.mode_verdict(entry, None, "review") is None


def test_unlaunchable_auth_command_is_unknown(tmp_path, monkeypatch):
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    real_run = vp._run

    def fake_run(argv, timeout, capture):
        if "auth" in argv:
            return "launch_error", None, ""
        return real_run(argv, timeout, capture)

    monkeypatch.setattr(vp, "_run", fake_run)
    entry = vp.probe_lane("a", cli(probe={"auth_status_args": ["auth", "status"]})).entry
    assert entry["l2"] == {"status": "auth_unknown", "method": "status_command"}


# ------------------------------------------------------------ argv safety


@pytest.mark.parametrize(
    "probe",
    [
        {"auth_status_args": ["logout"]},
        {"version_args": ["auth", "print-api-key"]},
        {"auth_status_args": ["auth", "LOGIN"]},
        {"help_args": {"review": ["--show-token", "--help"]}},
        {"version_args": ["--credentials"]},
    ],
)
def test_unsafe_probe_argv_executes_nothing_and_fails_closed(tmp_path, monkeypatch, probe):
    make_cli(tmp_path, helps={"--help": FULL_HELP})

    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run for an unsafe probe block")

    monkeypatch.setattr(vp, "_run", boom)
    monkeypatch.setattr(vp.subprocess, "run", boom)
    result = vp.probe_lane("a", cli(probe=probe))
    assert calls(tmp_path) == []
    assert result.entry["l0"] == {"ok": True}
    assert all(t == {"ok": False, "reason": "probe_failed"} for t in result.entry["modes"].values())
    assert result.entry["l2"]["status"] == "auth_unknown"
    assert vp.mode_verdict(result.entry, None, "review")[0] in vp.EXCLUDING_REASONS


def test_safe_probe_argv_passes_gate():
    assert vp.probe_argv_unsafe(cli(probe={"auth_status_args": ["login", "status"]})) is None
    assert vp.probe_argv_unsafe(cli(probe={})) is None
    assert vp.probe_argv_unsafe(cli()) is None


def test_stdin_is_devnull(tmp_path):
    make_cli(tmp_path, helps={"--help": FULL_HELP})
    status, rc, _ = vp._run(["sh", "-c", "cat; exit 0"], 5, True)
    assert (status, rc) == ("ok", 0)
