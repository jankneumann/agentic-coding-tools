"""Tests for the ``vendor_probe.py report`` CLI (task 2.7)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts" / "vendor_probe.py"
REPO_ROOT = Path(__file__).resolve().parents[3]


def run_report(tmp_path, env_extra, cwd=None, python=sys.executable, args=()):
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
        "AGENTIC_PROBE_CACHE": str(tmp_path / "cache.json"),
        "PYTHONPATH": "",
    }
    env.update(env_extra)
    return subprocess.run(
        [python, str(SCRIPT), "report", *args],
        capture_output=True, text=True, env=env, cwd=cwd or tmp_path, timeout=90,
    )


def write_yaml(tmp_path, command="nope-not-installed-xyz"):
    path = tmp_path / "agents.yaml"
    path.write_text(
        textwrap.dedent(
            f"""
            agents:
              demo-local:
                type: demo
                transport: mcp
                cli:
                  command: {command}
                  dispatch_modes:
                    review:
                      args: ["-p"]
                  model_flag: "-m"
            """
        )
    )
    return path


def test_import_does_not_pull_resolver():
    code = (
        "import sys; sys.path.insert(0, %r); import vendor_probe; "
        "assert 'review_dispatcher' not in sys.modules and 'yaml' not in sys.modules"
        % str(SCRIPT.parent)
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_report_table_with_remediation_hint(tmp_path):
    cfg = write_yaml(tmp_path)
    proc = run_report(tmp_path, {"AGENTS_YAML": str(cfg)})
    assert proc.returncode == 0, proc.stderr
    assert "demo-local" in proc.stdout
    assert "cli_not_found" in proc.stdout
    assert "install the CLI" in proc.stdout


def test_zero_dispatchable_vendors_is_a_valid_report(tmp_path):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text("agents:\n  sdk-only:\n    type: x\n    sdk: {package: p, model: m}\n")
    proc = run_report(tmp_path, {"AGENTS_YAML": str(cfg)})
    assert proc.returncode == 0
    assert "no CLI lanes" in proc.stdout


def test_unresolvable_config_message(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = run_report(tmp_path, {}, cwd=empty)
    assert proc.returncode == 2
    assert proc.stdout.strip() == "probe report unavailable: no agents configuration resolved"


def test_hung_probe_is_cut_off(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    hang = bindir / "hangcli"
    hang.write_text("#!/bin/sh\nsleep 60\n")
    hang.chmod(0o755)
    cfg = write_yaml(tmp_path, command="hangcli")
    proc = run_report(tmp_path, {"AGENTS_YAML": str(cfg)}, args=["--timeout", "1"])
    # lane deadline is 25 s so the 1 s report bound wins
    assert proc.returncode == 2
    assert "probe report unavailable: timeout" in proc.stdout
