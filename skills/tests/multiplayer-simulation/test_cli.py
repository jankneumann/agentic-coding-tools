"""CLI tests, running ``bin/mpsim`` by subprocess (P.4, S.4, D.1, D.2, O.2, O.4)."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema
import pytest
import yaml
from openspec_paths import repo_root_from

HARNESS = Path(__file__).resolve().parent
LAUNCHER = HARNESS / "bin" / "mpsim"
REPO = repo_root_from(__file__, 3)
SCHEMA = json.loads(
    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
)
SCENARIOS = [
    "different-requirement-control",
    "independent-principals-control",
    "memory-store-blocked-dependency",
    "same-requirement-collision",
]
HEX40 = re.compile(r"[0-9a-f]{40}")


def mpsim(*args: str, env_extra: dict[str, str] | None = None, unset: tuple[str, ...] = ()):
    env = {k: v for k, v in os.environ.items() if k not in unset}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args], capture_output=True, text=True, env=env,
        cwd=HARNESS,
    )


@pytest.fixture(scope="module")
def baseline() -> dict[str, subprocess.CompletedProcess]:
    """Each scenario once with COORDINATION_API_URL unset, run in parallel."""
    def one(scenario: str):
        return scenario, mpsim("run", "--scenario", scenario, unset=("COORDINATION_API_URL",))

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one, SCENARIOS))


def test_list_prints_the_four_scenario_ids_sorted():
    proc = mpsim("list")
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == SCENARIOS
    assert json.loads(proc.stdout) == sorted(json.loads(proc.stdout))


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["run", "--scenario", "no-such-scenario"], "no-such-scenario"),
        (["run", "--scenario", "same-requirement-collision", "--probe", "does-not-exist"],
         "does-not-exist"),
        (["run", "--scenario", "same-requirement-collision", "--fixture-dir", "/nonexistent/dir"],
         "fixture-dir"),
        (["run", "--scenario", "memory-store-blocked-dependency", "--tick-budget", "0"],
         "tick-budget"),
    ],
)
def test_semantic_usage_errors_exit_64_and_name_the_problem(args, needle):
    proc = mpsim(*args)
    assert proc.returncode == 64, proc.stderr
    assert needle in proc.stderr
    assert proc.stdout == ""


def test_a_one_principal_fixture_exits_64_naming_the_minimum(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
    descriptor = fixture / "scenario.yaml"
    data = yaml.safe_load(descriptor.read_text())
    data["principals"] = data["principals"][:1]
    descriptor.write_text(yaml.safe_dump(data))
    proc = mpsim("run", "--scenario", "same-requirement-collision", "--fixture-dir", str(fixture))
    assert proc.returncode == 64
    assert "at least 2 principals" in proc.stderr


@pytest.mark.parametrize("args", [[], ["run"], ["run", "--tick-budget", "x"]])
def test_argparse_errors_exit_2(args):
    assert mpsim(*args).returncode == 2


def test_repeated_runs_with_different_tmpdirs_are_byte_identical(baseline, tmp_path):
    other_tmp = tmp_path / "other-tmp"
    other_tmp.mkdir()
    again = mpsim("run", "--scenario", "memory-store-blocked-dependency",
                  env_extra={"TMPDIR": str(other_tmp)}, unset=("COORDINATION_API_URL",))
    assert again.returncode == 0
    assert again.stdout == baseline["memory-store-blocked-dependency"].stdout


def test_coordinator_environment_does_not_change_any_scenario(baseline):
    def one(scenario: str):
        return scenario, mpsim("run", "--scenario", scenario,
                               env_extra={"COORDINATION_API_URL": "http://127.0.0.1:9"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        with_env = dict(pool.map(one, SCENARIOS))
    for scenario in SCENARIOS:
        assert with_env[scenario].returncode == 0
        assert with_env[scenario].stdout == baseline[scenario].stdout, scenario


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_scenario_report_validates_and_leaks_nothing(baseline, scenario):
    proc = baseline[scenario]
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    jsonschema.Draft202012Validator(SCHEMA).validate(report)
    assert list(report) == sorted(report)
    assert not HEX40.search(proc.stdout)
    assert "/tmp" not in proc.stdout and "mpsim-" not in proc.stdout
    assert str(HARNESS) not in proc.stdout


def test_the_exit_1_report_validates_and_leaks_nothing(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(HARNESS / "fixtures" / "same-requirement-collision", fixture)
    spec = fixture / "principals/bob/plan/openspec/changes/sim-bob-notes/specs/sim-notes/spec.md"
    spec.write_text(spec.read_text().replace("Note Titles", "Note Bodies"))
    proc = mpsim("run", "--scenario", "same-requirement-collision", "--fixture-dir", str(fixture))
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["error"]
    jsonschema.Draft202012Validator(SCHEMA).validate(report)
    assert str(tmp_path) not in proc.stdout
    assert not HEX40.search(proc.stdout)


FORBIDDEN_TOP = {"src", "agent_coordinator", "coordination_bridge", "httpx", "requests", "mcp",
                 "aiohttp"}
FORBIDDEN_DOTTED = {"urllib.request", "http.client"}


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
            for alias in node.names:
                yield f"{node.module}.{alias.name}"


def test_driver_modules_import_no_coordinator_or_transport():
    offenders = []
    for path in sorted((HARNESS / "mpsim").rglob("*.py")):
        for name in _imports(ast.parse(path.read_text())):
            if name.split(".")[0] in FORBIDDEN_TOP or any(
                name == d or name.startswith(d + ".") for d in FORBIDDEN_DOTTED
            ):
                offenders.append(f"{path.relative_to(HARNESS)}: {name}")
    assert offenders == []
