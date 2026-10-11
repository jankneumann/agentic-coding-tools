"""Whole-tree skill materialization (tasks 1.4/1.5)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agent_scenarios import AgentScenario, CLIVendorExecutor, FakeExecutor, Outcome
from agent_scenarios.materialize import materialize_skills, skills_sha


def _make_skills(root: Path) -> Path:
    skills = root / "repo" / "skills"
    for name in ("validate-feature", "worktree", "session-log"):
        (skills / name / "scripts").mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        (skills / name / "scripts" / "helper.py").write_text("x = 1\n", encoding="utf-8")
        (skills / name / "__pycache__").mkdir()
        (skills / name / "__pycache__" / "h.pyc").write_text("c", encoding="utf-8")
    (skills / "tests").mkdir()
    (skills / "tests" / "t.py").write_text("t", encoding="utf-8")
    (skills / ".venv").mkdir()
    (skills / "conftest.py").write_text("", encoding="utf-8")
    return skills


def _scenario() -> AgentScenario:
    return AgentScenario.model_validate(
        {
            "id": "s", "name": "s", "task_prompt": "/validate-feature go",
            "skill_under_test": "validate-feature", "vendors": ["claude"],
            "fixture": {"files": {"README.md": "x"}},
            "goal_gates": {"verify": [{"id": "g", "check": "file", "path": "README.md"}]},
        }
    )


def _init_repo(path: Path) -> None:
    for cmd in (["init", "-q", "-b", "main"], ["config", "user.email", "a@b.c"],
                ["config", "user.name", "n"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *cmd], cwd=path, check=True, capture_output=True)


def test_whole_tree_copied_with_excludes(tmp_path: Path) -> None:
    skills = _make_skills(tmp_path)
    wd = tmp_path / "ws"
    wd.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=wd, check=True)
    materialize_skills(skills, "validate-feature", wd)
    for target in (".claude/skills", ".agents/skills"):
        assert (wd / target / "validate-feature" / "SKILL.md").is_file()
        assert (wd / target / "worktree" / "SKILL.md").is_file()
        assert (wd / target / "validate-feature" / "scripts" / "helper.py").is_file()
        assert not (wd / target / "tests").exists()
        assert not (wd / target / ".venv").exists()
        assert not (wd / target / "validate-feature" / "__pycache__").exists()
        assert not (wd / target / "conftest.py").exists()
    exclude = (wd / ".git" / "info" / "exclude").read_text()
    assert ".claude/skills" in exclude and ".agents/skills" in exclude
    status = subprocess.run(["git", "status", "--porcelain"], cwd=wd, capture_output=True,
                            text=True, check=True).stdout
    assert ".claude" not in status and ".agents" not in status


def test_skills_sha_clean_dirty_and_none(tmp_path: Path) -> None:
    skills = _make_skills(tmp_path)
    _init_repo(tmp_path / "repo")
    sha = skills_sha(skills)
    assert sha is not None and "+dirty" not in sha and len(sha) == 40
    (skills / "validate-feature" / "SKILL.md").write_text("changed", encoding="utf-8")
    assert skills_sha(skills) == sha + "+dirty"


def test_missing_skill_is_executor_error_and_no_vendor_run(tmp_path: Path) -> None:
    skills = _make_skills(tmp_path)
    marker = tmp_path / "ran"
    script = tmp_path / "v.py"
    script.write_text(f"open({str(marker)!r}, 'w').write('x')")
    sc = _scenario().model_copy(update={"skill_under_test": "no-such-skill"})
    ex = CLIVendorExecutor({"claude": f"{sys.executable} {script}"}, skills_root=skills)
    res = ex.run(sc, "claude", tmp_path / "ws")
    assert res.error is not None and "no-such-skill" in res.error
    assert not marker.exists()


def test_cli_executor_carries_skills_sha(tmp_path: Path) -> None:
    skills = _make_skills(tmp_path)
    _init_repo(tmp_path / "repo")
    script = tmp_path / "v.py"
    script.write_text("pass")
    ex = CLIVendorExecutor({"claude": f"{sys.executable} {script}"}, skills_root=skills)
    res = ex.run(_scenario(), "claude", tmp_path / "ws")
    assert res.error is None
    assert res.skills_sha is not None and len(res.skills_sha) == 40
    assert (tmp_path / "ws" / ".claude" / "skills" / "worktree" / "SKILL.md").is_file()


def test_fake_executor_opt_in_materialization(tmp_path: Path) -> None:
    skills = _make_skills(tmp_path)
    seen: dict[str, str] = {}

    def play(workdir: Path) -> Outcome:
        seen["skill"] = (workdir / ".claude/skills/validate-feature/SKILL.md").read_text()
        return Outcome()

    ex = FakeExecutor({"s": play}, skills_root=skills)
    res = ex.run(_scenario(), "claude", tmp_path / "ws")
    assert res.error is None
    assert seen["skill"].startswith("# validate-feature")
    missing = FakeExecutor({"s": Outcome()}, skills_root=skills)
    bad = missing.run(_scenario().model_copy(update={"skill_under_test": "zzz"}), "claude",
                      tmp_path / "ws2")
    assert bad.error is not None and "zzz" in bad.error


def test_in_tree_symlink_is_copied_but_an_escaping_one_is_refused(tmp_path: Path) -> None:
    import pytest

    from agent_scenarios.materialize import SkillMaterializationError

    root = _make_skills(tmp_path / "skills")
    skill = next(p for p in root.iterdir() if (p / "SKILL.md").is_file())
    (skill / "CLAUDE.md").symlink_to("SKILL.md")  # in-tree, like CLAUDE.md -> AGENTS.md
    materialize_skills(root, skill.name, tmp_path / "ws1")
    assert (tmp_path / "ws1" / ".claude" / "skills" / skill.name / "CLAUDE.md").is_file()

    secret = tmp_path / "home-credentials"
    secret.write_text("token\n")
    nested = skill / "deep"
    nested.mkdir(exist_ok=True)
    (nested / "creds").symlink_to(secret)
    with pytest.raises(SkillMaterializationError, match="outside skills_root"):
        materialize_skills(root, skill.name, tmp_path / "ws2")
    assert not (tmp_path / "ws2" / ".claude").exists()
