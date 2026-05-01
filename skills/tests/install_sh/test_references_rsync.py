"""Tests for install.sh handling of skills/references/ library.

Verifies:
- references/ files are rsynced to .claude/skills/references/ and .agents/skills/references/
- references/ is NOT enumerated as a skill (no fake "references" entry under .claude/skills/)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"
REFERENCES_DIR = SKILLS_ROOT / "references"


def _have_rsync() -> bool:
    return shutil.which("rsync") is not None


@pytest.fixture
def install_target(tmp_path):
    """A throwaway target dir under tmp_path."""
    target = tmp_path / "install_target"
    target.mkdir()
    return target


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
@pytest.mark.skipif(not REFERENCES_DIR.exists(), reason="skills/references/ not yet created")
def test_references_files_rsynced_to_target(install_target):
    """install.sh in rsync mode must place references/ files at the destination."""
    result = subprocess.run(
        [
            "bash", str(INSTALL_SH),
            "--target", str(install_target),
            "--mode", "rsync",
            "--deps", "none",
            "--python-tools", "none",
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"install.sh failed: {result.stderr}"

    for agent_dir in ("claude", "agents"):
        ref_dir = install_target / f".{agent_dir}/skills/references"
        assert ref_dir.is_dir(), f"references/ not synced to .{agent_dir}/skills/"
        assert (ref_dir / "skill-tail-template.md").exists(), \
            f"skill-tail-template.md missing at {ref_dir}"


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
@pytest.mark.skipif(not REFERENCES_DIR.exists(), reason="skills/references/ not yet created")
def test_references_not_treated_as_skill(install_target):
    """references/ has no SKILL.md and must not be enumerated as a skill."""
    result = subprocess.run(
        [
            "bash", str(INSTALL_SH),
            "--target", str(install_target),
            "--mode", "rsync",
            "--deps", "none",
            "--python-tools", "none",
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"install.sh failed: {result.stderr}"

    # references/ should appear under .claude/skills/ as the references library,
    # but it must not be listed in install.sh's skill-installed log lines
    # (which read like "  sync  <skill-name> -> ...").
    for line in result.stdout.splitlines():
        # The skill-install log lines have format "  sync  <name> -> <path>".
        # Acceptable references log line is something like "  refs  references -> ..." or similar.
        if " sync  references " in line or line.strip().startswith("link  references"):
            pytest.fail(
                f"install.sh treated references/ as a skill: {line!r}. "
                "It must be rsynced as a sibling library, not enumerated as a skill."
            )

    # And references/ must not have a SKILL.md ever appear at the destination
    # (we don't ship one in the source either).
    skill_md = install_target / ".claude/skills/references/SKILL.md"
    assert not skill_md.exists(), \
        f"references/ should not contain SKILL.md, found {skill_md}"
