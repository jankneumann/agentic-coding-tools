"""The systemd user template unit and its example env file (D5, D6, D7)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DANGEROUS_FLAGS = ("--privileged",)


def parse_unit(text: str) -> dict[str, list[tuple[str, str]]]:
    """INI parser that keeps repeated keys, as systemd does."""
    sections: dict[str, list[tuple[str, str]]] = {}
    cur: list[tuple[str, str]] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = sections.setdefault(line[1:-1], [])
            continue
        assert cur is not None, f"key outside a section: {raw!r}"
        key, _, value = line.partition("=")
        cur.append((key.strip(), value.strip()))
    return sections


def parse_env(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("\"'")
    return env


def values(unit, section: str, key: str) -> list[str]:
    return [v for k, v in unit.get(section, []) if k == key]


def expand_exec(line: str, env: dict[str, str], instance: str = "1") -> list[str]:
    """Expand an Exec line with systemd word-splitting semantics.

    ``${VAR}`` is substituted into a single argument; a standalone ``$VAR`` word is
    split on whitespace (so an empty value yields zero arguments). Specifiers ``%i`` and
    ``%t``/``%h`` are replaced with stand-ins.
    """
    line = line.lstrip("-@+!:")
    line = line.replace("%i", instance).replace("%t", "/run/user/1000").replace("%h", "/home/x")
    out: list[str] = []
    for word in line.split():
        m = re.fullmatch(r"\$([A-Za-z_]\w*)", word)
        if m:
            out.extend(env.get(m.group(1), "").split())
            continue
        out.append(re.sub(r"\$\{(\w+)\}", lambda mm: env.get(mm.group(1), ""), word))
    return out


@pytest.fixture(scope="module")
def unit(kit_dir):
    return parse_unit((kit_dir / "systemd" / "gx10-runner@.service").read_text())


@pytest.fixture(scope="module")
def env(kit_dir):
    return parse_env((kit_dir / "gx10-runner.env.example").read_text())


@pytest.fixture(scope="module")
def exec_start(unit):
    (line,) = values(unit, "Service", "ExecStart")
    return line


def test_restart_and_install_properties(unit):
    assert values(unit, "Service", "Restart") == ["always"]
    assert int(values(unit, "Service", "TimeoutStartSec")[0]) > 90
    assert values(unit, "Unit", "StartLimitIntervalSec") == ["0"]
    assert "StartLimitIntervalSec" not in dict(unit["Service"])
    assert values(unit, "Install", "WantedBy") == ["default.target"]


def test_start_timeout_exceeds_mint_budget(unit, env):
    assert int(values(unit, "Service", "TimeoutStartSec")[0]) > int(env["GX10_MINT_MAX_ELAPSED"])


def test_pre_and_post_hooks(unit):
    (pre,) = values(unit, "Service", "ExecStartPre")
    (post,) = values(unit, "Service", "ExecStopPost")
    assert "mint-jitconfig.sh" in pre
    assert "cleanup-runner.sh" in post


def test_configuration_and_credential_wiring(unit, env, exec_start):
    assert values(unit, "Service", "EnvironmentFile") == ["%h/.config/gx10-runner/env"]
    assert values(unit, "Service", "LoadCredential") == [
        "github-token:%h/.config/gx10-runner/token"
    ]
    assert "GX10_RUNNER_TOKEN_FILE" not in env
    (pre,) = values(unit, "Service", "ExecStartPre")
    referenced = set(re.findall(r"\$\{?([A-Za-z_]\w*)\}?", pre + " " + exec_start))
    assert referenced, "expected the unit to reference env variables"
    assert referenced <= set(env), f"undefined in example env: {referenced - set(env)}"


@pytest.mark.parametrize(
    "needle",
    [
        "podman run",
        "--rm",
        "--replace",
        "--pull=never",
        "--env-file",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--network slirp4netns:allow_host_loopback=false",
        "--pids-limit",
        "--cpus",
        "--memory",
        "--tmpfs /tmp",
    ],
)
def test_exec_start_has_hardening(exec_start, needle):
    assert needle in exec_start


def test_exec_start_has_no_dangerous_options(exec_start):
    for flag in DANGEROUS_FLAGS:
        assert flag not in exec_start
    assert "--network host" not in exec_start and "--network=host" not in exec_start
    networks = re.findall(r"--network[= ](\S+)", exec_start)
    assert networks == ["slirp4netns:allow_host_loopback=false"]
    assert not re.search(r"\S*\.sock\b", exec_start)
    assert "%h" not in exec_start and "$HOME" not in exec_start
    for src in re.findall(r"(?:--volume|-v)[= ](\S+)", exec_start):
        assert not src.startswith(("/", "%", "$", "~")), src


def test_cache_switch_is_a_bare_word_and_off_by_default(exec_start, env):
    assert re.search(r"(?:^|\s)\$GX10_RUNNER_CACHE_ARGS(?:\s|$)", exec_start)
    assert "--volume" not in exec_start and " -v " not in exec_start
    assert env["GX10_RUNNER_CACHE_ARGS"] == ""
    assert "--volume" not in expand_exec(exec_start, env)


def test_cache_opt_in_adds_only_the_named_volume(exec_start, env):
    base = expand_exec(exec_start, env)
    opted = expand_exec(
        exec_start,
        {**env, "GX10_RUNNER_CACHE_ARGS": "--volume gx10-runner-uv-cache:/home/runner/.cache/uv"},
    )
    added = [a for a in opted if a not in base]
    assert added == ["--volume", "gx10-runner-uv-cache:/home/runner/.cache/uv"]
    assert len(opted) == len(base) + 2


def test_env_example_contents(env):
    for key in (
        "GX10_RUNNER_REPO",
        "GX10_RUNNER_IMAGE",
        "GX10_RUNNER_CPUS",
        "GX10_RUNNER_MEMORY",
        "GX10_RUNNER_LABELS",
        "GX10_MINT_MAX_ELAPSED",
        "GX10_RUNNER_CACHE_ARGS",
    ):
        assert key in env, key
    assert env["GX10_MINT_MAX_ELAPSED"] == "600"


def test_env_labels_mirror_manifest(env, manifest):
    got = {x.strip().lower() for x in env["GX10_RUNNER_LABELS"].split(",")}
    assert got == {x.lower() for x in manifest["routing"]["self_hosted_labels"]}


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze missing")
def test_systemd_analyze_verify(kit_dir, tmp_path: Path):
    text = (kit_dir / "systemd" / "gx10-runner@.service").read_text()
    stub = tmp_path / "stub.sh"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    out = []
    for line in text.splitlines():
        m = re.match(r"^(ExecStartPre|ExecStart|ExecStopPost)=", line)
        out.append(f"{m.group(1)}={stub}" if m else line)
    unit_path = tmp_path / "gx10-runner@1.service"
    unit_path.write_text("\n".join(out) + "\n")
    res = subprocess.run(
        ["systemd-analyze", "verify", "--user", str(unit_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    problems = [
        ln for ln in (res.stdout + res.stderr).splitlines() if "gx10-runner" in ln and ln.strip()
    ]
    assert not problems, problems
