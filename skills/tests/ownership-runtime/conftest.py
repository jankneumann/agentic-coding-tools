"""Shared fixtures for the ownership-runtime suite.

Every module in this package builds its fixture repository with ``make_repo``;
none of them touch the real checkout except ``test_repository_invariant.py``.
Git identity is isolated from the host so that the "no git identity" paths are
deterministic on a developer machine that has a global ``user.email``.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "ownership-runtime" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

#: Environment that makes ``git`` ignore the host's global and system configuration.
ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


@pytest.fixture(autouse=True)
def _isolated_git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the host git identity and any operator registry override."""
    for key, value in ISOLATED_GIT_ENV.items():
        monkeypatch.setenv(key, value)
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL", "OWNERSHIP_REGISTRY_PATH", "EMAIL"):
        monkeypatch.delenv(key, raising=False)


def run_git(repo: Path, *args: str) -> str:
    """Run ``git`` in ``repo`` and return stdout (raises on failure)."""
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def git_add_all(repo: Path) -> None:
    """Stage everything so ``git ls-files`` sees files written after ``make_repo``."""
    run_git(repo, "add", "-A")


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


MakeRepo = Callable[..., Path]


@pytest.fixture
def make_repo(tmp_path: Path) -> MakeRepo:
    """Build a fixture repository under ``tmp_path / "repo"`` and return its root.

    ``humans``      mapping id -> entry for the registry ``humans:`` block (``None`` omits it)
    ``agents``      iterable of agent names, or mapping name -> entry, for ``agents:``
    ``owners``      mapping written as ``openspec/owners.yaml`` (``None`` writes no map);
                    a ``str`` is written verbatim so tests can plant invalid YAML
    ``registry``    repo-relative registry location (default ``agent-coordinator/agents.yaml``)
    ``git``         initialise a git checkout and stage every written file
    ``git_email`` / ``git_name``  repo-local git identity (none by default)
    ``specs``       capability directory names to create under ``openspec/specs/``
    ``roadmaps``    mapping roadmap id -> item ids, written as active ``roadmap.yaml`` files
    ``archived_roadmaps``  same, written under ``openspec/roadmaps/archive/``
    """

    def _make(
        *,
        humans: Mapping[str, Mapping[str, Any]] | None = None,
        owners: Mapping[str, Any] | str | None = None,
        agents: Iterable[str] | Mapping[str, Any] | None = None,
        git: bool = True,
        registry: str = "agent-coordinator/agents.yaml",
        git_email: str | None = None,
        git_name: str | None = None,
        specs: Iterable[str] = (),
        roadmaps: Mapping[str, Iterable[str]] | None = None,
        archived_roadmaps: Mapping[str, Iterable[str]] | None = None,
    ) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir(exist_ok=True)

        if humans is not None or agents is not None:
            registry_doc: dict[str, Any] = {}
            if agents is not None:
                registry_doc["agents"] = (
                    dict(agents) if isinstance(agents, Mapping) else {name: {} for name in agents}
                )
            if humans is not None:
                registry_doc["humans"] = {k: dict(v) for k, v in humans.items()}
            write_yaml(repo / registry, registry_doc)

        if isinstance(owners, str):
            write_text(repo / "openspec" / "owners.yaml", owners)
        elif owners is not None:
            write_yaml(repo / "openspec" / "owners.yaml", dict(owners))

        for name in specs:
            write_text(repo / "openspec" / "specs" / name / "spec.md", f"# {name}\n")

        for base, table in (("", roadmaps), ("archive/", archived_roadmaps)):
            for roadmap_id, item_ids in (table or {}).items():
                write_yaml(
                    repo / "openspec" / "roadmaps" / f"{base}{roadmap_id}" / "roadmap.yaml",
                    {
                        "schema_version": 1,
                        "roadmap_id": roadmap_id,
                        "items": [{"item_id": item} for item in item_ids],
                    },
                )

        if git:
            run_git(repo, "init", "-q")
            if git_email is not None:
                run_git(repo, "config", "user.email", git_email)
            if git_name is not None:
                run_git(repo, "config", "user.name", git_name)
            git_add_all(repo)
        return repo

    return _make
