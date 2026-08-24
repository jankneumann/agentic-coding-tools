"""Tests for install.sh OpenSpec asset and CLI handling."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"
REPO_ROOT = SKILLS_ROOT.parent


def _skill_openspec_assets() -> list[tuple[Path, str, str]]:
    """Every skill-owned OpenSpec asset as (path, rel, owning skill).

    install.sh copies ``<skill>/install_assets/openspec/<rel>`` onto
    ``<target>/openspec/<rel>``, so <rel> is the join key between the shipped
    asset and the repository's own copy.
    """
    assets: list[tuple[Path, str, str]] = []
    for assets_dir in sorted(SKILLS_ROOT.glob("*/install_assets/openspec")):
        # <skill>/install_assets/openspec -> parents[1] is <skill>.
        skill_name = assets_dir.parents[1].name
        for asset in sorted(assets_dir.rglob("*")):
            if asset.is_file():
                rel = asset.relative_to(assets_dir).as_posix()
                assets.append((asset, rel, skill_name))
    return assets


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
    shared_dir = scripts_dir / "shared"
    shared_dir.mkdir(exist_ok=True)
    shutil.copy(SKILLS_ROOT / "shared" / "validate_install_manifest.py", shared_dir)
    skill_names = sorted(
        path.parent.name for path in scripts_dir.glob("*/SKILL.md")
    )
    (scripts_dir / "install-manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "shared_libraries": ["shared"],
        "runtime_globs": ["*/SKILL.md"],
        "installed_assets": [],
        "cross_skill_dependencies": {},
        "skills": {
            name: {"distribution": "portable"} for name in skill_names
        },
        "smoke_entrypoints": [],
    }))
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


def test_skill_assets_match_the_repository_openspec_tree() -> None:
    """Shipped assets must equal the repo's own openspec/ copy, byte for byte.

    install.sh copies these assets over ``openspec/``.  When the repository's
    copy has moved ahead -- which is the normal direction of drift, because
    feature work edits ``openspec/`` and forgets the asset -- running the
    installer silently reverts that work.  Three schemas had drifted this way
    before this test existed: roadmap.schema.json lost `superseded`,
    `external_depends_on` and `superseded_by`; consensus-report lost
    `agreed_axis`; the validation-report template lost its architecture gate.

    Nothing at runtime can tell which side is authoritative, so the invariant
    has to be enforced here instead: the two copies are the same file, and a
    change to one is a change to both.
    """
    mismatched: list[str] = []
    missing: list[str] = []

    for asset, rel, skill_name in _skill_openspec_assets():
        repo_copy = REPO_ROOT / "openspec" / rel
        if not repo_copy.is_file():
            missing.append(f"{rel} (shipped by {skill_name})")
        elif repo_copy.read_bytes() != asset.read_bytes():
            mismatched.append(f"{rel} (shipped by {skill_name})")

    assert not missing, (
        "skill assets with no counterpart under openspec/:\n  "
        + "\n  ".join(missing)
    )
    assert not mismatched, (
        "skill-owned assets have drifted from the repository's openspec/ copy. "
        "Running skills/install.sh would overwrite the repo copy with the "
        "stale asset and silently revert whatever changed it.\n  "
        + "\n  ".join(mismatched)
        + "\n\nResolve by copying the current openspec/ file over the asset "
        "(the repo copy is normally the newer one), then re-run this test."
    )


def _run_installer(
    install_copy: Path, target: Path, mode: str = "rsync"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "bash", str(install_copy),
            "--target", str(target),
            "--mode", mode,
            "--deps", "none",
            "--python-tools", "none",
            "--openspec-cli", "none",
            "--force",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _fixture_with_asset(skills_dir: Path, body: str) -> Path:
    """A fixture skill shipping one OpenSpec asset with the given contents."""
    skill_dir = _make_fixture_skill(skills_dir, "schema-owner")
    asset = (
        skill_dir / "install_assets" / "openspec" / "schemas" / "owned.json"
    )
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(body, encoding="utf-8")
    return asset


def test_consumer_install_overwrites_a_differing_openspec_file(
    tmp_path: Path,
) -> None:
    """In a consumer repo the shipped asset stays authoritative.

    openspec/ there is install output, so a skill version bump must still be
    able to update it -- the self-install guard must not block that.
    """
    skills_dir = tmp_path / "fake_skills"
    skills_dir.mkdir()
    _fixture_with_asset(skills_dir, '{"version": "new"}\n')
    install_copy = _copy_installer(skills_dir)

    target = tmp_path / "target"
    installed = target / "openspec" / "schemas" / "owned.json"
    installed.parent.mkdir(parents=True)
    installed.write_text('{"version": "old"}\n', encoding="utf-8")

    result = _run_installer(install_copy, target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert installed.read_text() == '{"version": "new"}\n', (
        "a consumer install must still update its openspec/ copy"
    )


def test_self_install_does_not_overwrite_a_differing_openspec_file(
    tmp_path: Path,
) -> None:
    """The regression: installing into the repo that owns skills/.

    Here openspec/ is hand-maintained source, so a differing file means the
    shipped asset is stale. Overwriting silently reverts whatever edited it.
    """
    # target/skills/ IS the canonical tree -> self-install.
    root = tmp_path / "repo"
    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True)
    _fixture_with_asset(skills_dir, '{"version": "stale-asset"}\n')
    install_copy = _copy_installer(skills_dir)

    live = root / "openspec" / "schemas" / "owned.json"
    live.parent.mkdir(parents=True)
    live.write_text('{"version": "edited-by-feature-work"}\n', encoding="utf-8")

    result = _run_installer(install_copy, root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert live.read_text() == '{"version": "edited-by-feature-work"}\n', (
        "install.sh reverted a hand-edited openspec/ file"
    )
    combined = result.stdout + result.stderr
    assert "differ from this repository's openspec/ copy" in combined, combined
    assert "openspec/schemas/owned.json" in combined, combined


def test_self_install_still_creates_absent_openspec_files(
    tmp_path: Path,
) -> None:
    """The guard only protects existing files; a fresh tree still gets them."""
    root = tmp_path / "repo"
    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True)
    _fixture_with_asset(skills_dir, '{"version": "shipped"}\n')
    install_copy = _copy_installer(skills_dir)

    result = _run_installer(install_copy, root)

    assert result.returncode == 0, result.stdout + result.stderr
    installed = root / "openspec" / "schemas" / "owned.json"
    assert installed.is_file(), "absent asset was not installed"
    assert installed.read_text() == '{"version": "shipped"}\n'


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
