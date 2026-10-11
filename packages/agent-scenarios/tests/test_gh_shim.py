"""The local ``gh`` shim, subprocess-level against a temp local origin (tasks 1.6/1.7)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agent_scenarios import AgentScenario, CLIVendorExecutor, materialize_fixture
from agent_scenarios.gh_shim import install_gh_shim, origin_path_for, unsupported_calls


def _scenario(prs: bool = True) -> AgentScenario:
    fixture: dict[str, object] = {
        "files": {"README.md": "base\n"},
        "local_remote": True,
        "commands": [
            ["git", "checkout", "-q", "-b", "feature/x"],
            ["sh", "-c", "echo feat > feat.txt && git add -A && git commit -q -m 'feat: x'"],
            ["git", "checkout", "-q", "main"],
        ],
    }
    if prs:
        fixture["prs"] = [{"number": 5, "head": "feature/x", "title": "Add X"}]
    return AgentScenario.model_validate(
        {
            "id": "s",
            "name": "s",
            "task_prompt": "/merge-pull-requests go",
            "skill_under_test": "merge-pull-requests",
            "vendors": ["claude"],
            "fixture": fixture,
            "goal_gates": {"verify": [{"id": "g", "check": "file", "path": "README.md"}]},
        }
    )


class Shim:
    def __init__(self, tmp_path: Path) -> None:
        self.wd = tmp_path / "ws"
        sc = _scenario()
        materialize_fixture(sc, self.wd)
        self.origin = origin_path_for(self.wd)
        self.bin = install_gh_shim(sc, self.wd, self.origin)

    def gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        return subprocess.run(["gh", *args], cwd=self.wd, env=env, capture_output=True, text=True)

    def origin_git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "--git-dir", str(self.origin), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()


@pytest.fixture
def shim(tmp_path: Path) -> Shim:
    return Shim(tmp_path)


def test_auth_and_repo_view(shim: Shim) -> None:
    assert shim.gh("auth", "status").returncode == 0
    out = json.loads(shim.gh("repo", "view", "--json", "nameWithOwner,defaultBranchRef").stdout)
    assert out["defaultBranchRef"]["name"] == "main"


def test_pr_list_view_status(shim: Shim) -> None:
    listing = json.loads(shim.gh("pr", "list", "--json", "number,headRefName").stdout)
    assert listing == [{"number": 5, "headRefName": "feature/x"}]
    view = json.loads(shim.gh("pr", "view", "5", "--json", "state,title").stdout)
    assert view == {"state": "OPEN", "title": "Add X"}
    assert shim.gh("pr", "status", "--json", "currentBranch,createdBy").returncode == 0


def test_pr_view_without_pr_for_branch_fails(shim: Shim) -> None:
    assert shim.gh("pr", "view", "--json", "number").returncode != 0
    assert unsupported_calls(shim.bin) == []


def test_pr_create_requires_pushed_head(shim: Shim) -> None:
    bad = shim.gh("pr", "create", "--head", "nope", "--title", "t")
    assert bad.returncode == 1
    ok = shim.gh("pr", "create", "--head", "feature/x", "--base", "main", "--title", "Second")
    assert ok.returncode == 0 and "/pull/6" in ok.stdout


@pytest.mark.parametrize("flag", ["--merge", "--squash", "--rebase"])
def test_pr_merge_modes_land_on_origin(tmp_path: Path, flag: str) -> None:
    s = Shim(tmp_path)
    base_before = s.origin_git("rev-parse", "main")
    res = s.gh("pr", "merge", "5", flag, "--delete-branch")
    assert res.returncode == 0, res.stderr
    assert s.origin_git("show", "main:feat.txt") == "feat"
    assert (
        subprocess.run(
            ["git", "--git-dir", str(s.origin), "merge-base", "--is-ancestor", base_before, "main"]
        ).returncode
        == 0
    )
    assert json.loads(s.gh("pr", "view", "5", "--json", "state").stdout)["state"] == "MERGED"
    assert "feature/x" not in s.origin_git("branch", "--list")


def test_api_permissions_and_protection_404(shim: Shim) -> None:
    repo = json.loads(shim.gh("api", "repos/local/fixture").stdout)
    assert repo["permissions"]["push"] is True
    prot = shim.gh("api", "repos/local/fixture/branches/main/protection")
    assert prot.returncode == 1 and "404" in prot.stderr
    assert unsupported_calls(shim.bin) == []


def test_unsupported_call_is_logged(shim: Shim) -> None:
    res = shim.gh("issue", "list")
    assert res.returncode == 1
    assert unsupported_calls(shim.bin) == ["gh issue list"]


def test_executor_forces_error_on_unsupported_call_and_resolves_post_run_view(
    tmp_path: Path,
) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        "import subprocess\n"
        "subprocess.run(['gh','pr','merge','5','--squash'], check=True)\n"
        "subprocess.run(['gh','release','list'])\n"
    )
    ex = CLIVendorExecutor({"claude": f"{sys.executable} {script}"})
    res = ex.run(_scenario(), "claude", tmp_path / "ws")
    assert res.error is not None and "gh shim: unsupported call" in res.error
    assert "release list" in res.error
    assert res.exit_code != 0


def test_executor_post_run_gh_pr_view_resolves_through_shim(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text("import subprocess\nsubprocess.run(['git','checkout','-q','feature/x'])\n")
    ex = CLIVendorExecutor({"claude": f"{sys.executable} {script}"})
    res = ex.run(_scenario(), "claude", tmp_path / "ws")
    assert res.error is None
    assert res.workspace.created_pr is not None
    assert res.workspace.created_pr.number == 5
    assert res.workspace.created_pr.head == "feature/x"


@pytest.mark.parametrize(
    "args",
    [
        ("pr", "list", "--search", "is:open"),
        ("pr", "merge", "5", "--admin"),
        ("pr", "merge", "5", "--auto", "--squash"),
        ("pr", "create", "--draft", "--head", "feature/x", "--title", "t"),
        ("pr", "view", "5", "--comments"),
        ("pr", "view", "--help"),
        ("api", "-X", "PUT", "repos/local/fixture/branches/main/protection"),
    ],
)
def test_unknown_flag_on_implemented_subcommand_is_unsupported(
    shim: Shim, args: tuple[str, ...]
) -> None:
    """An implemented subcommand with an unimplemented flag is a coverage gap (D5),
    never silently ignored: exit 1, logged, and no state change."""
    res = shim.gh(*args)
    assert res.returncode == 1
    assert unsupported_calls(shim.bin) == ["gh " + " ".join(args)]
    assert json.loads(shim.gh("pr", "view", "5", "--json", "state").stdout)["state"] == "OPEN"


def test_value_flag_argument_starting_with_dash_is_not_a_flag(shim: Shim) -> None:
    res = shim.gh("pr", "create", "--head", "feature/x", "--title", "t", "--body", "- item")
    assert res.returncode == 0, res.stderr
    assert unsupported_calls(shim.bin) == []


def test_pr_list_limit_and_create_body_file(shim: Shim, tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("details\n")
    assert shim.gh("pr", "create", "--head", "feature/x", "--fill", "-F", str(body)).returncode == 0
    listing = json.loads(shim.gh("pr", "list", "--limit", "1", "--json", "number").stdout)
    assert listing == [{"number": 5}]
    created = json.loads(shim.gh("pr", "view", "6", "--json", "title,body").stdout)
    assert created == {"title": "feat: x", "body": "details\n"}


def test_merge_subject_is_used_for_the_merge_commit(shim: Shim) -> None:
    res = shim.gh("pr", "merge", "5", "--squash", "--subject", "custom subject")
    assert res.returncode == 0, res.stderr
    assert shim.origin_git("log", "-1", "--format=%s", "main") == "custom subject"


def test_jq_filter_is_applied_or_reported_unsupported(shim: Shim) -> None:
    res = shim.gh("pr", "view", "5", "--json", "state", "--jq", ".state")
    if shutil.which("jq") is None:
        assert res.returncode == 1 and unsupported_calls(shim.bin)
        return
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "OPEN"
    assert unsupported_calls(shim.bin) == []
