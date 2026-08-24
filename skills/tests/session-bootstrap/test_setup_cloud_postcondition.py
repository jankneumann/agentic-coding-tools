"""setup-cloud.sh's skill post-condition must accept either harness tree.

`verify_skills_present` exists because every install step in setup-cloud.sh is
`... || log WARNING` followed by exit 0, so a failed install produced a session
that reported successful setup with no skills at all.

The check must not overcorrect, though: `.claude/skills` is Claude Code's tree
and `.agents/skills` is Codex's, and a mirror-layout consumer repo legitimately
ships only the one its harness reads.  Failing a healthy Codex-only checkout
would break the documented Codex setup script.  Only two empty trees mean no
harness can discover anything.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SETUP_CLOUD = (
    Path(__file__).resolve().parents[2]
    / "session-bootstrap/scripts/setup-cloud.sh"
)


def _sourceable_prefix(tmp_path: Path) -> Path:
    """Copy setup-cloud.sh up to its "# Main" block so it can be sourced.

    Sourcing the whole script would run uv sync, npm install and the frontend
    build.  Everything above the invocation block is definitions plus logging,
    which is what these tests need.
    """
    text = SETUP_CLOUD.read_text()
    marker = "# Main\n"
    assert marker in text, "setup-cloud.sh no longer has a '# Main' marker"
    prefix = text[: text.index(marker)]
    path = tmp_path / "setup_cloud_prefix.sh"
    path.write_text(prefix)
    return path


def _make_skill(root: Path, tree: str, name: str) -> None:
    skill_dir = root / tree / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n")


def _verify(project_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    prefix = _sourceable_prefix(tmp_path)
    return subprocess.run(
        ["bash", "-c", f'source "{prefix}"; verify_skills_present'],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(tmp_path),
            "CLAUDE_PROJECT_DIR": str(project_dir),
        },
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_both_trees_populated_passes(project: Path, tmp_path: Path) -> None:
    _make_skill(project, ".claude", "alpha")
    _make_skill(project, ".agents", "alpha")

    result = _verify(project, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_codex_only_tree_passes(project: Path, tmp_path: Path) -> None:
    """The regression: a Codex-only mirror has no .claude/skills at all."""
    _make_skill(project, ".agents", "alpha")

    result = _verify(project, tmp_path)

    assert result.returncode == 0, (
        "a healthy Codex-only checkout must satisfy the post-condition:\n"
        + result.stdout
        + result.stderr
    )
    assert "no skills under .claude/skills" in result.stdout


def test_claude_only_tree_passes(project: Path, tmp_path: Path) -> None:
    _make_skill(project, ".claude", "alpha")

    result = _verify(project, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no skills under .agents/skills" in result.stdout


def test_both_trees_empty_fails(project: Path, tmp_path: Path) -> None:
    """No harness can discover anything -- this is the case worth failing."""
    result = _verify(project, tmp_path)

    assert result.returncode != 0
    assert "ERROR: no skills installed" in result.stdout


def test_directories_without_skill_md_fail(
    project: Path, tmp_path: Path
) -> None:
    """A directory that exists but holds no SKILL.md is not an install.

    This is why the check counts SKILL.md files rather than testing that the
    directory exists: a partial or failed install leaves the tree behind.
    """
    (project / ".claude/skills/half-written").mkdir(parents=True)
    (project / ".agents/skills").mkdir(parents=True)

    result = _verify(project, tmp_path)

    assert result.returncode != 0
    assert "ERROR: no skills installed" in result.stdout
