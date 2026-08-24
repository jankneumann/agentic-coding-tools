"""install.sh must still install skills when rsync is absent.

Minimal container images frequently ship without rsync.  install.sh used to
abort with "rsync mode requested but rsync was not found in PATH", and
setup-cloud.sh invokes it as `... || log WARNING` and then exits 0 -- so a
cloud session reported a successful setup while `.claude/skills/` stayed
empty and the harness found no skills at all.

These tests run install.sh against a PATH that genuinely has no rsync on it
(shadowing the binary is not enough: `command -v` finds any executable file),
and assert the cp fallback produces the same tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"


def _rsync_free_path(tmp_path: Path) -> str:
    """Build a PATH exposing the usual tools but no rsync.

    rsync commonly lives in /usr/bin next to coreutils, so the directory
    cannot simply be dropped from PATH; symlink everything except rsync into
    a scratch bin instead.
    """
    fake_bin = tmp_path / "rsync_free_bin"
    fake_bin.mkdir(exist_ok=True)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        src_dir = Path(entry)
        if not src_dir.is_dir():
            continue
        try:
            children = list(src_dir.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name == "rsync":
                continue
            link = fake_bin / child.name
            if not link.exists():
                try:
                    link.symlink_to(child)
                except OSError:
                    pass
    return str(fake_bin)


def _install(target: Path, path_env: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=path_env)
    return subprocess.run(
        [
            "bash", str(INSTALL_SH),
            "--target", str(target),
            "--mode", "rsync",
            "--force",
            "--deps", "none",
            "--python-tools", "none",
            "--openspec-cli", "none",
        ],
        capture_output=True, text=True, timeout=300, env=env,
    )


def _skill_count(root: Path) -> int:
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return 0
    return len(list(skills_dir.glob("*/SKILL.md")))


def test_installs_skills_without_rsync(tmp_path):
    """With no rsync on PATH, install.sh still populates .claude/skills/."""
    path_env = _rsync_free_path(tmp_path)
    assert shutil.which("rsync", path=path_env) is None, (
        "test scaffolding failed: rsync is still reachable"
    )

    target = tmp_path / "target"
    target.mkdir()
    result = _install(target, path_env)

    assert result.returncode == 0, (
        f"install.sh failed without rsync.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert _skill_count(target) > 0, (
        "no skills installed under .claude/skills/ -- the harness would find "
        f"nothing.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_excludes_still_honored_without_rsync(tmp_path):
    """The cp fallback must honor the tests/ and __pycache__/ excludes."""
    path_env = _rsync_free_path(tmp_path)
    target = tmp_path / "target"
    target.mkdir()

    assert _install(target, path_env).returncode == 0

    skills_dir = target / ".claude" / "skills"
    assert not list(skills_dir.glob("*/tests")), "tests/ leaked into the mirror"
    assert not list(skills_dir.rglob("__pycache__")), (
        "__pycache__/ leaked into the mirror"
    )


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
def test_cp_fallback_matches_rsync_output(tmp_path):
    """cp and rsync must produce the same tree, so the fallback is not a
    second, subtly different install path."""
    with_rsync = tmp_path / "with_rsync"
    without_rsync = tmp_path / "without_rsync"
    with_rsync.mkdir()
    without_rsync.mkdir()

    assert _install(with_rsync, os.environ["PATH"]).returncode == 0
    assert _install(without_rsync, _rsync_free_path(tmp_path)).returncode == 0

    def tree(root: Path) -> set[str]:
        base = root / ".claude" / "skills"
        return {
            str(p.relative_to(base))
            for p in base.rglob("*")
            if p.is_file()
        }

    rsync_tree, cp_tree = tree(with_rsync), tree(without_rsync)
    assert rsync_tree == cp_tree, (
        "cp fallback diverged from rsync.\n"
        f"only in rsync: {sorted(rsync_tree - cp_tree)[:10]}\n"
        f"only in cp:    {sorted(cp_tree - rsync_tree)[:10]}"
    )
