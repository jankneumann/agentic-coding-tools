"""Executable contract for skills installed into a clean consumer repository."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SKILLS_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = SKILLS_ROOT / "install.sh"
INSTALL_MANIFEST = SKILLS_ROOT / "install-manifest.json"


def _have_rsync() -> bool:
    return shutil.which("rsync") is not None


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


@pytest.fixture(scope="module")
def installed_target(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Install the exact shipped payload into a repository-shaped empty target."""
    target = tmp_path_factory.mktemp("consumer")
    result = subprocess.run(
        [
            "bash",
            str(INSTALL_SH),
            "--target",
            str(target),
            "--agents",
            "claude,agents",
            "--mode",
            "rsync",
            "--deps",
            "none",
            "--openspec-assets",
            "none",
            "--openspec-cli",
            "none",
            "--python-tools",
            "none",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=_clean_env(),
    )
    assert result.returncode == 0, result.stderr
    assert not (target / "agent-coordinator").exists()
    assert not (target / "skills").exists()
    return target


def _import_file(path: Path) -> subprocess.CompletedProcess[str]:
    code = (
        "import importlib.util, pathlib; "
        f"path = pathlib.Path({str(path)!r}); "
        "spec = importlib.util.spec_from_file_location('consumer_probe', path); "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module)"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(path.parents[4]),
        capture_output=True,
        text=True,
        timeout=30,
        env=_clean_env(),
    )


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
@pytest.mark.parametrize("agent_dir", [".claude", ".agents"])
def test_manifest_entry_points_run_without_source_checkout(
    installed_target: Path, agent_dir: str
) -> None:
    """Every registered baseline probe runs using only the installed closure."""
    installed_skills = installed_target / agent_dir / "skills"
    assert (installed_skills / "install-manifest.json").is_file()
    manifest = json.loads(INSTALL_MANIFEST.read_text())
    failures: list[str] = []

    for entry in manifest["smoke_entrypoints"]:
        path = installed_skills / entry["path"]
        entry_id = entry["path"]
        assert path.is_file(), f"manifest entry is not installed: {entry_id} -> {path}"
        if entry.get("mode") == "import":
            result = _import_file(path)
        else:
            result = subprocess.run(
                [sys.executable, str(path), *entry.get("args", [])],
                cwd=str(installed_skills.parents[1]),
                capture_output=True,
                text=True,
                timeout=30,
                env=_clean_env(),
            )
        if result.returncode != 0:
            failures.append(
                f"{entry_id} (exit {result.returncode})\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

    assert not failures, "\n\n".join(failures)


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
@pytest.mark.parametrize("agent_dir", [".claude", ".agents"])
def test_discover_prs_loads_classifier_from_installed_shared(
    installed_target: Path, agent_dir: str
) -> None:
    installed_skills = installed_target / agent_dir / "skills"
    script = installed_skills / "merge-pull-requests" / "scripts" / "discover_prs.py"
    shared = installed_skills / "shared" / "github_classifier.py"

    assert shared.is_file()
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(installed_skills.parents[1]),
        capture_output=True,
        text=True,
        timeout=30,
        env=_clean_env(),
    )

    assert result.returncode == 0, result.stderr
    assert "Discover and classify" in result.stdout


@pytest.mark.skipif(not _have_rsync(), reason="rsync not available in PATH")
@pytest.mark.parametrize("agent_dir", [".claude", ".agents"])
def test_all_installed_python_compiles(
    installed_target: Path, agent_dir: str
) -> None:
    installed_skills = installed_target / agent_dir / "skills"
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(installed_skills)],
        cwd=installed_target,
        capture_output=True,
        text=True,
        timeout=120,
        env=_clean_env(),
    )
    assert result.returncode == 0, result.stderr


def test_orchestrator_instructions_do_not_import_private_agents_config() -> None:
    skill_names = (
        "plan-feature",
        "implement-feature",
        "iterate-on-plan",
        "iterate-on-implementation",
        "fix-scrub",
    )

    for skill_name in skill_names:
        instructions = (SKILLS_ROOT / skill_name / "SKILL.md").read_text()
        assert "src.agents_config" not in instructions, skill_name
        assert "coordination_bridge.try_resolve_archetype_for_phase" in instructions, (
            skill_name
        )
