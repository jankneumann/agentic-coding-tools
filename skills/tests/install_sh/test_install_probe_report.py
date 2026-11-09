"""install.sh --check prints the vendor probe report without changing its exit code."""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
VERSION = (SKILLS_ROOT.parent / "VERSION").read_text().strip()
QUIET = [
    "--deps", "none", "--openspec-assets", "none", "--openspec-cli", "none",
    "--python-tools", "none",
]

AGENTS_YAML = textwrap.dedent(
    """
    agents:
      demo-local:
        type: demo
        cli:
          command: {command}
          dispatch_modes:
            review: {{args: ["-p"]}}
          model_flag: "-m"
    """
)


@pytest.fixture()
def toolkit(tmp_path: Path):
    """A private checkout copy installed into a consumer repo."""
    src = tmp_path / "skills"
    shutil.copytree(
        SKILLS_ROOT, src,
        ignore=shutil.ignore_patterns(".venv", "tests", "__pycache__", "node_modules", ".pytest_cache"),
    )
    (tmp_path / "VERSION").write_text(VERSION + "\n")
    target = tmp_path / "consumer"
    target.mkdir()
    done = subprocess.run(
        ["bash", str(src / "install.sh"), "--target", str(target), "--mode", "copy", *QUIET],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    return src, target, tmp_path


def link_venv(src: Path) -> None:
    (src / ".venv").symlink_to(SKILLS_ROOT / ".venv")


def check(src: Path, target: Path, tmp_path: Path, **env_extra):
    env = {
        k: v for k, v in os.environ.items()
        if k not in {"AGENTS_YAML", "COORDINATION_API_URL", "PYTHONPATH"}
    }
    env["AGENTIC_PROBE_CACHE"] = str(tmp_path / "probe-cache.json")
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(src / "install.sh"), "--target", str(target), "--check"],
        capture_output=True, text=True, env=env, cwd=target,
    )


def write_agents(tmp_path: Path, command: str) -> str:
    path = tmp_path / "agents.yaml"
    path.write_text(AGENTS_YAML.format(command=command))
    return str(path)


def test_no_vendor_cli_installed_reports_and_exits_zero(toolkit):
    src, target, tmp = toolkit
    link_venv(src)
    result = check(src, target, tmp, AGENTS_YAML=write_agents(tmp, "no-such-vendor-cli-xyz"))
    assert result.returncode == 0, result.stderr
    assert "Vendor probe report" in result.stdout
    assert "demo-local" in result.stdout
    assert "cli_not_found" in result.stdout


def test_drift_still_fails_when_every_probe_passes(toolkit):
    src, target, tmp = toolkit
    link_venv(src)
    skill_md = next((target / ".claude" / "skills").glob("*/SKILL.md"))
    skill_md.write_text(skill_md.read_text() + "\nruntime drift\n")
    result = check(src, target, tmp, AGENTS_YAML=write_agents(tmp, "python3"))
    assert result.returncode == 1
    assert "Vendor probe report" in result.stdout
    assert "demo-local" in result.stdout


def test_unresolvable_config_is_reported_not_fatal(toolkit):
    src, target, tmp = toolkit
    link_venv(src)
    result = check(src, target, tmp)
    assert result.returncode == 0, result.stderr
    assert "probe report unavailable: no agents configuration resolved" in result.stdout


def test_bare_interpreter_without_pyyaml_is_reported_not_fatal(toolkit):
    src, target, tmp = toolkit  # no skills/.venv: falls back to python3
    shadow = tmp / "shadow"
    shadow.mkdir()
    (shadow / "yaml.py").write_text("raise ImportError(\"No module named 'yaml'\")\n")
    result = check(src, target, tmp, PYTHONPATH=str(shadow), AGENTS_YAML=write_agents(tmp, "python3"))
    assert result.returncode == 0, result.stderr
    line = next(ln for ln in result.stdout.splitlines() if "probe report unavailable:" in ln)
    assert line.startswith("probe report unavailable:")


def test_crashing_probe_prints_single_unavailable_line(toolkit):
    """A traceback on a non-zero exit is reduced to the one-line contract."""
    src, target, tmp = toolkit
    fake_bin = src / ".venv" / "bin"
    fake_bin.mkdir(parents=True)
    fake_py = fake_bin / "python"
    fake_py.write_text(
        "#!/bin/sh\n"
        "echo 'Traceback (most recent call last):'\n"
        "echo '  File \"vendor_probe.py\", line 1, in <module>'\n"
        "echo 'KeyError: l0' >&2\n"
        "exit 1\n"
    )
    fake_py.chmod(0o755)
    result = check(src, target, tmp, AGENTS_YAML=write_agents(tmp, "python3"))
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout
    assert "KeyError" not in result.stdout
    lines = result.stdout.splitlines()
    idx = lines.index("Vendor probe report:")
    assert lines[idx + 1] == "probe report unavailable: probe error"


def test_formatting_failure_is_single_line_in_python(tmp_path, monkeypatch):
    """cmd_report keeps the single-line contract when format_report raises."""
    import sys

    sys.path.insert(0, str(SKILLS_ROOT / "parallel-infrastructure" / "scripts"))
    import vendor_probe as vp

    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(vp, "_resolve_cli_configs", lambda: {"a": {"command": "python3"}})
    monkeypatch.setattr(vp, "probe_lanes", lambda *a, **k: {"a": vp.LaneProbe("a", {})})
    monkeypatch.setattr(vp, "format_report", lambda _p: (_ for _ in ()).throw(KeyError("l0")))
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = vp.cmd_report([])
    assert rc == 2
    assert buf.getvalue().splitlines() == ["probe report unavailable: 'l0'"]


def test_hung_probe_is_cut_off_at_the_report_timeout(toolkit):
    src, target, tmp = toolkit
    link_venv(src)
    bindir = tmp / "bin"
    bindir.mkdir()
    hang = bindir / "hangcli"
    hang.write_text("#!/bin/sh\nsleep 60\n")
    hang.chmod(0o755)
    start = time.monotonic()
    result = check(
        src, target, tmp,
        AGENTS_YAML=write_agents(tmp, "hangcli"),
        PATH=f"{bindir}:{os.environ['PATH']}",
        AGENTIC_PROBE_REPORT_TIMEOUT="2",
    )
    assert time.monotonic() - start < 40
    assert result.returncode == 0, result.stderr
    assert "probe report unavailable: timeout" in result.stdout
