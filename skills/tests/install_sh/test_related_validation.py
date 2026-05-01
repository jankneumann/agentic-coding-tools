"""Tests for install.sh validation of `related:` frontmatter key.

Verifies that install.sh:
- Accepts skills with valid related: targets (no warning)
- Warns on skills with unknown related: targets (exit 0, message to stderr)
- Emits no warning for skills that omit related: entirely
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"


def _have_rsync() -> bool:
    return shutil.which("rsync") is not None


def _make_fixture_skill(root: Path, name: str, frontmatter_extra: str) -> Path:
    """Create a minimal SKILL.md under <root>/<name>/ with the given extra frontmatter."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: Fixture skill for related: validation tests
category: Testing
tags: [fixture]
triggers:
  - "{name}"
user_invocable: false
{frontmatter_extra}
---

# {name}

Fixture content.
""",
        encoding="utf-8",
    )
    return skill_dir


def _run_install(install_target: Path, scripts_dir: Path) -> subprocess.CompletedProcess:
    """Run install.sh, but pointing it at a custom skills root via copying.

    The install.sh script auto-discovers skills relative to its own directory,
    so we copy install.sh into our scripts_dir alongside the fixture skills.
    """
    install_copy = scripts_dir / "install.sh"
    shutil.copy(INSTALL_SH, install_copy)
    install_copy.chmod(0o755)
    return subprocess.run(
        [
            "bash", str(install_copy),
            "--target", str(install_target),
            "--mode", "rsync",
            "--deps", "none",
            "--python-tools", "none",
        ],
        capture_output=True, text=True, timeout=120,
    )


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
def test_related_with_valid_target_emits_no_warning(tmp_path):
    scripts_dir = tmp_path / "fake_skills"
    scripts_dir.mkdir()
    _make_fixture_skill(scripts_dir, "skill-a", "")
    _make_fixture_skill(scripts_dir, "skill-b", "related:\n  - skill-a")
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = _run_install(install_target, scripts_dir)

    assert result.returncode == 0, f"install.sh failed: {result.stderr}"
    assert "related: warning" not in result.stderr.lower(), \
        f"unexpected warning for valid related: target — stderr was: {result.stderr}"


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
def test_related_with_unknown_target_warns_but_succeeds(tmp_path):
    scripts_dir = tmp_path / "fake_skills"
    scripts_dir.mkdir()
    _make_fixture_skill(scripts_dir, "skill-c", "related:\n  - nonexistent-target")
    # Need at least 2 skills for install.sh to proceed
    _make_fixture_skill(scripts_dir, "skill-d", "")
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = _run_install(install_target, scripts_dir)

    assert result.returncode == 0, f"install.sh should not fail on unknown related: target"
    combined = result.stdout + result.stderr
    assert "nonexistent-target" in combined, \
        f"install.sh should warn on unknown related: target. Output:\n{combined}"
    assert "skill-c" in combined, \
        f"install.sh warning should name the source skill. Output:\n{combined}"


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
def test_related_omitted_emits_no_warning(tmp_path):
    scripts_dir = tmp_path / "fake_skills"
    scripts_dir.mkdir()
    _make_fixture_skill(scripts_dir, "skill-e", "")
    _make_fixture_skill(scripts_dir, "skill-f", "")
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = _run_install(install_target, scripts_dir)

    assert result.returncode == 0
    assert "related" not in result.stderr.lower(), \
        f"unexpected related: warning for skills with no related: key. stderr: {result.stderr}"
