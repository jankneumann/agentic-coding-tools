"""local_remote/prs fixtures, hermetic env, timeout message (tasks 1.2/1.3)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_scenarios import AgentScenario, CLIVendorExecutor, FixtureSpec, materialize_fixture
from agent_scenarios.executor import (
    COORDINATION_URL_SENTINEL,
    HERMETIC_SCRUB,
    FixtureError,
    build_vendor_env,
)
from tests.test_schemas import load_schema

SCEN_GATE = {"verify": [{"id": "g", "check": "file", "path": "README.md"}]}


def _scenario(fixture: dict[str, object], **kw: object) -> AgentScenario:
    return AgentScenario.model_validate(
        {
            "id": "s",
            "name": "s",
            "task_prompt": "/plan-feature do",
            "skill_under_test": "plan-feature",
            "vendors": ["claude"],
            "fixture": fixture,
            "goal_gates": SCEN_GATE,
            **kw,
        }
    )


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


# --- local_remote / prs -------------------------------------------------------------


def test_local_remote_creates_sibling_bare_origin(tmp_path: Path) -> None:
    sc = _scenario({"files": {"README.md": "x"}, "local_remote": True})
    wd = tmp_path / "ws"
    materialize_fixture(sc, wd)
    origin = tmp_path / "ws.origin.git"
    assert origin.is_dir()
    assert _git(wd, "remote", "get-url", "origin") == str(origin)
    assert _git(origin, "rev-parse", "main") == _git(wd, "rev-parse", "main")
    assert not (wd / "ws.origin.git").exists()


def test_prs_push_head_branches(tmp_path: Path) -> None:
    sc = _scenario(
        {
            "files": {"README.md": "x"},
            "local_remote": True,
            "commands": [
                ["git", "checkout", "-q", "-b", "feature/x"],
                ["git", "commit", "-q", "--allow-empty", "-m", "feat: x"],
                ["git", "checkout", "-q", "main"],
            ],
            "prs": [{"number": 7, "head": "feature/x", "title": "X"}],
        }
    )
    wd = tmp_path / "ws"
    materialize_fixture(sc, wd)
    heads = _git(tmp_path / "ws.origin.git", "branch", "--list")
    assert "feature/x" in heads


def test_prs_with_missing_head_branch_is_fixture_error(tmp_path: Path) -> None:
    sc = _scenario(
        {"files": {"README.md": "x"}, "local_remote": True, "prs": [{"number": 1, "head": "nope"}]}
    )
    with pytest.raises(FixtureError):
        materialize_fixture(sc, tmp_path / "ws")


def test_prs_require_local_remote() -> None:
    with pytest.raises(ValueError):
        FixtureSpec.model_validate({"prs": [{"number": 1, "head": "x"}]})


def test_defaults_leave_fixture_unchanged(tmp_path: Path) -> None:
    sc = _scenario({"files": {"README.md": "x"}})
    materialize_fixture(sc, tmp_path / "ws")
    assert not (tmp_path / "ws.origin.git").exists()


# --- hermetic env -----------------------------------------------------------------


def test_empty_scrub_still_applies_builtin_denylist() -> None:
    base = {n: "secret" for n in HERMETIC_SCRUB} | {"ANTHROPIC_API_KEY": "keep", "PATH": "/bin"}
    env = build_vendor_env(base)
    assert not (HERMETIC_SCRUB & env.keys())
    assert env["ANTHROPIC_API_KEY"] == "keep"
    assert env["COORDINATION_API_URL"] == COORDINATION_URL_SENTINEL


def test_env_scrub_extends_and_always_scrub_applies() -> None:
    base = {"EXTRA": "1", "MY_KEY": "k", "MY_URL": "u", "PATH": "/bin"}
    env = build_vendor_env(base, env_scrub=["EXTRA"], always_scrub=["MY_KEY", "MY_URL"])
    assert not ({"EXTRA", "MY_KEY", "MY_URL"} & env.keys())


def test_sentinel_wins_over_env_set_and_runner_value() -> None:
    env = build_vendor_env(
        {"COORDINATION_API_URL": "http://real:3000"},
        env_set={"COORDINATION_API_URL": "http://evil", "FOO": "bar"},
    )
    assert env["COORDINATION_API_URL"] == COORDINATION_URL_SENTINEL
    assert env["FOO"] == "bar"


def test_env_set_cannot_reintroduce_scrubbed_name() -> None:
    env = build_vendor_env({}, env_set={"GH_TOKEN": "t"})
    assert "GH_TOKEN" not in env


def test_executor_subprocess_env_is_hermetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "COORDINATOR_API_KEY", "COORDINATOR_HTTP_URL",
                 "CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "MY_GAP_KEY"):
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("COORDINATION_API_URL", "http://real:3000")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "vendor-cred")
    script = tmp_path / "dump.py"
    script.write_text("import json,os;open('env.json','w').write(json.dumps(dict(os.environ)))")
    ex = CLIVendorExecutor(
        {"claude": f"{sys.executable} {script} {{prompt}}"}, always_scrub=["MY_GAP_KEY"]
    )
    sc = _scenario({"files": {"README.md": "x"}})
    res = ex.run(sc, "claude", tmp_path / "ws")
    assert res.error is None
    env = json.loads((tmp_path / "ws" / "env.json").read_text())
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "COORDINATOR_API_KEY", "COORDINATOR_HTTP_URL",
                 "CF_ACCESS_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET", "MY_GAP_KEY"):
        assert name not in env
    assert env["COORDINATION_API_URL"] == COORDINATION_URL_SENTINEL
    assert env["ANTHROPIC_API_KEY"] == "vendor-cred"
    assert env["PATH"].split(":")[0].endswith("ws.bin")


# --- drift tests -------------------------------------------------------------------


def _bridge_source() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        cand = parent / "skills" / "coordination-bridge" / "scripts" / "coordination_bridge.py"
        if cand.is_file():
            return cand
    return None


def _literal_assign(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


def test_denylist_covers_bridge_variables() -> None:
    src = _bridge_source()
    if src is None:
        pytest.skip("skills tree absent")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    names: set[str] = set()
    names |= set(_literal_assign(tree, "_HTTP_URL_ENV_KEYS"))  # type: ignore[call-overload]
    names |= set(_literal_assign(tree, "_API_KEY_ENV_KEYS"))  # type: ignore[call-overload]
    names.add(str(_literal_assign(tree, "_CF_ACCESS_ID_ENV")))
    names.add(str(_literal_assign(tree, "_CF_ACCESS_SECRET_ENV")))
    # COORDINATION_API_URL is forced to the sentinel rather than scrubbed.
    missing = names - HERMETIC_SCRUB - {"COORDINATION_API_URL"}
    assert not missing, f"bridge variables missing from HERMETIC_SCRUB: {sorted(missing)}"


def test_config_schema_env_set_denylist_matches_executor() -> None:
    schema = load_schema("nightly-config.schema.json")
    listed = set(schema["properties"]["env_set"]["propertyNames"]["not"]["enum"])
    assert listed == set(HERMETIC_SCRUB) | {"COORDINATION_API_URL"}


# --- timeout message ---------------------------------------------------------------


def test_timeout_is_distinct_from_unavailable(tmp_path: Path) -> None:
    sc = _scenario({"files": {"README.md": "x"}})
    slow = CLIVendorExecutor(
        {"claude": f"{sys.executable} -c 'import time; time.sleep(5)'"}, timeout_seconds=1
    )
    res = slow.run(sc, "claude", tmp_path / "a")
    assert res.error is not None and "timed out after 1s" in res.error
    assert "unavailable" not in res.error
    missing = CLIVendorExecutor({"claude": "definitely-not-a-cli-xyz"}, timeout_seconds=5)
    res2 = missing.run(sc, "claude", tmp_path / "b")
    assert res2.error is not None and "unavailable" in res2.error
