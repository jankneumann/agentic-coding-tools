"""The real repository's ownership map, registry and CODEOWNERS agree (design D6, D9, D12, D14).

Same pattern as ``agent-coordinator/tests/test_registry_projection.py``: an
error-free, warning-free run over the actual checkout is the invariant.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from openspec_paths import repo_root_from
from owners import load_ownership

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "ownership-runtime" / "scripts"


def _run(script: str, *args: str, root: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args, "--repo-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_owners_is_clean_on_the_real_repository() -> None:
    done = _run("check_owners.py", "--codeowners", "--strict", "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout)
    assert report["findings"] == []
    assert report["mode"] == "solo"


def test_repository_codeowners_reconciles() -> None:
    done = _run("codeowners.py", "reconcile", "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout)
    assert report["disagreements"] == 0
    assert report["stale"] is False


def test_one_principal_repository_with_a_map_stays_solo() -> None:
    assert (REPO_ROOT / "openspec" / "owners.yaml").is_file()
    ctx = load_ownership(REPO_ROOT)
    assert ctx.mode == "solo"
    assert ctx.has_map
    explicit = ctx.resolve_capability("agent-coordinator")
    assert explicit.source == "explicit"
    assert all(p.kind == "human" for p in explicit.owners)


def test_repository_map_exercises_every_resolver_branch() -> None:
    ctx = load_ownership(REPO_ROOT)
    assert ctx.resolve_capability("agent-identity").source == "explicit"
    assert ctx.resolve_roadmap_item("multiplayer-collaboration", "ri-02").source == "explicit"
    assert ctx.resolve_path("openspec/schemas/owners.schema.json").matched_rule is not None
    assert ctx.resolve_path("openspec/specs/agent-coordinator/spec.md").matched_rule == (
        "capability:agent-coordinator"
    )
    assert ctx.resolve_path("README.md").source == "default_owner"


def test_adding_a_capability_directory_causes_no_unowned_churn(tmp_path: Path) -> None:
    """D14: in solo mode a new spec directory must not require editing owners.yaml."""
    copy = tmp_path / "repo"
    for rel in ("openspec/specs", "openspec/roadmaps", "openspec/contracts"):
        shutil.copytree(REPO_ROOT / rel, copy / rel)
    for rel in ("openspec/owners.yaml", "agent-coordinator/agents.yaml", ".github/CODEOWNERS"):
        (copy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, copy / rel)
    (copy / "openspec" / "specs" / "brand-new-capability").mkdir()
    (copy / "openspec" / "specs" / "brand-new-capability" / "spec.md").write_text("# x\n")
    subprocess.run(["git", "init", "-q"], cwd=copy, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=copy, check=True, capture_output=True)

    done = _run("check_owners.py", "--codeowners", "--strict", "--json", root=copy)
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout)
    assert report["findings"] == []
    assert not any(f["code"].startswith("unowned_") for f in report["findings"])
