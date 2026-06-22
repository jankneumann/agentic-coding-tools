"""Tests for install.sh OpenSpec asset and CLI handling."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"


def _have_rsync() -> bool:
    return shutil.which("rsync") is not None


def _make_fixture_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {name}
description: Fixture skill for OpenSpec install tests
category: Testing
tags: [fixture]
triggers:
  - "{name}"
user_invocable: false
---

# {name}

Fixture content.
""",
        encoding="utf-8",
    )
    return skill_dir


def _copy_installer(scripts_dir: Path) -> Path:
    install_copy = scripts_dir / "install.sh"
    shutil.copy(INSTALL_SH, install_copy)
    install_copy.chmod(0o755)
    return install_copy


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
def test_skill_openspec_assets_are_synced_to_target(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "fake_skills"
    scripts_dir.mkdir()
    skill_dir = _make_fixture_skill(scripts_dir, "schema-owner")
    schema_path = (
        skill_dir
        / "install_assets"
        / "openspec"
        / "schemas"
        / "schema-owner.schema.json"
    )
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
        encoding="utf-8",
    )
    install_copy = _copy_installer(scripts_dir)
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = subprocess.run(
        [
            "bash",
            str(install_copy),
            "--target",
            str(install_target),
            "--mode",
            "rsync",
            "--deps",
            "none",
            "--python-tools",
            "none",
            "--openspec-cli",
            "none",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    installed_schema = install_target / "openspec" / "schemas" / "schema-owner.schema.json"
    assert installed_schema.exists()
    assert "openspec-assets  schema-owner" in result.stdout


def test_openspec_cli_required_fails_when_binary_is_missing(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "fake_skills"
    scripts_dir.mkdir()
    _make_fixture_skill(scripts_dir, "needs-openspec")
    install_copy = _copy_installer(scripts_dir)
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = subprocess.run(
        [
            "bash",
            str(install_copy),
            "--target",
            str(install_target),
            "--mode",
            "symlink",
            "--deps",
            "none",
            "--python-tools",
            "none",
            "--openspec-assets",
            "none",
            "--openspec-cli",
            "required",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/bin:/usr/bin"},
    )

    assert result.returncode != 0
    assert "OpenSpec CLI missing" in result.stdout
    assert "npm install -g @fission-ai/openspec" in result.stdout


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
def test_canonical_install_syncs_required_openspec_schemas(tmp_path: Path) -> None:
    install_target = tmp_path / "target"
    install_target.mkdir()

    result = subprocess.run(
        [
            "bash",
            str(INSTALL_SH),
            "--target",
            str(install_target),
            "--mode",
            "rsync",
            "--deps",
            "none",
            "--python-tools",
            "none",
            "--openspec-cli",
            "none",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr

    expected = [
        "schemas/review-findings.schema.json",
        "schemas/consensus-report.schema.json",
        "schemas/work-packages.schema.json",
        "schemas/work-queue-result.schema.json",
        "schemas/feature-workflow/schema.yaml",
        "schemas/feature-workflow/templates/proposal.md",
        "schemas/feature-workflow/templates/tasks.md",
        "schemas/roadmap.schema.json",
        "schemas/roadmap/schema.yaml",
        "schemas/roadmap/templates/roadmap.yaml",
        "schemas/checkpoint.schema.json",
        "schemas/learning-log.schema.json",
        "schemas/convergence-state.schema.json",
        "schemas/archetypes.schema.json",
        "schemas/flags.schema.json",
    ]
    for rel_path in expected:
        assert (install_target / "openspec" / rel_path).exists(), rel_path

    assert not (install_target / "openspec" / "changes").exists()
    assert not (install_target / "openspec" / "specs").exists()
