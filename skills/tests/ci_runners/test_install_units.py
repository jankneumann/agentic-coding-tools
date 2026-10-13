"""install-units.sh copies beneath --prefix and only prints host commands (D7)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

FORBIDDEN = ("systemctl", "loginctl", "podman")


@pytest.fixture()
def guarded_path(tmp_path: Path) -> tuple[Path, Path]:
    """PATH prefix whose systemctl/loginctl/podman stubs record any invocation."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "INVOKED"
    for name in FORBIDDEN:
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{marker}"\nexit 99\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return bin_dir, marker


def _run(kit_dir, tmp_path, guarded_path, *extra):
    bin_dir, _ = guarded_path
    prefix = tmp_path / "home"
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "realhome")}
    return prefix, subprocess.run(
        ["bash", str(kit_dir / "install-units.sh"), "--prefix", str(prefix), *extra],
        env=env,
        capture_output=True,
        text=True,
    )


def test_files_land_only_under_prefix(kit_dir, tmp_path, guarded_path):
    prefix, res = _run(kit_dir, tmp_path, guarded_path)
    assert res.returncode == 0, res.stderr
    assert (prefix / ".config/systemd/user/gx10-runner@.service").is_file()
    for script in ("mint-jitconfig.sh", "cleanup-runner.sh"):
        installed = prefix / ".local/lib/gx10-runner" / script
        assert installed.is_file() and os.access(installed, os.X_OK)
    env_file = prefix / ".config/gx10-runner/env"
    assert env_file.is_file() and oct(env_file.stat().st_mode & 0o777) == "0o600"
    # nothing was written outside the prefix (the fake real HOME was never created)
    assert not (tmp_path / "realhome").exists()
    written = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert all(prefix in p.parents or p.parent.name in {"bin"} for p in written)


def test_host_commands_are_printed_not_executed(kit_dir, tmp_path, guarded_path):
    _, marker = guarded_path
    _, res = _run(kit_dir, tmp_path, guarded_path)
    assert not marker.exists(), marker.read_text() if marker.exists() else ""
    assert "loginctl enable-linger ghrunner" in res.stdout
    assert "systemctl --user enable --now gx10-runner@{1..8}" in res.stdout
    # Unit commands must target ghrunner's user manager, never the invoking operator's, and
    # the `$(id -u ghrunner)` is printed for the operator's shell, not expanded by the script.
    runas = "sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/$(id -u ghrunner) systemctl --user"
    unit_lines = [ln.strip() for ln in res.stdout.splitlines() if "systemctl --user" in ln]
    assert unit_lines and all(ln.startswith(runas) for ln in unit_lines), unit_lines


def test_instance_count_is_printed(kit_dir, tmp_path, guarded_path):
    _, res = _run(kit_dir, tmp_path, guarded_path, "--instances", "3")
    assert "gx10-runner@{1..3}" in res.stdout


def test_existing_operator_env_is_not_overwritten(kit_dir, tmp_path, guarded_path):
    prefix, _ = _run(kit_dir, tmp_path, guarded_path)
    env_file = prefix / ".config/gx10-runner/env"
    env_file.write_text("GX10_RUNNER_REPO=me/mine\n")
    _run(kit_dir, tmp_path, guarded_path)
    assert env_file.read_text() == "GX10_RUNNER_REPO=me/mine\n"


def test_script_never_invokes_host_commands(kit_dir):
    in_heredoc = False
    for line in (kit_dir / "install-units.sh").read_text().splitlines():
        if in_heredoc:  # text printed for the operator, not executed
            in_heredoc = line.strip() != "MSG"
            continue
        in_heredoc = "<<MSG" in line
        code = line.split("#", 1)[0].strip()
        if code.startswith(("sudo ", "systemctl ", "loginctl ", "podman ")):
            raise AssertionError(f"install-units.sh executes: {line}")


def test_unknown_argument_is_rejected(kit_dir, tmp_path, guarded_path):
    _, res = _run(kit_dir, tmp_path, guarded_path, "--bogus")
    assert res.returncode == 2
