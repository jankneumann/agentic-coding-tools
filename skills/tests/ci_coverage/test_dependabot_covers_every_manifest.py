"""Every dependency manifest in the repo must have a Dependabot entry.

`.github/dependabot.yml` covered pip, github-actions and docker. It did not
cover npm, so `apps/kanban-viz/` — the repo's only JavaScript surface — had no
automated advisory coverage at all. That gap surfaced on 2026-09-10, when the
first real OWASP dependency-check scan found GHSA-82fw-gwwq-j7x9
(vitest/@vitest/mocker 3.2.7, moderate, CVSS 5.9) sitting in
`apps/kanban-viz/package-lock.json`.

Nothing had been watching. Not because a scanner failed, but because no manifest
scanner was ever pointed at that directory — and an ecosystem nobody configured
looks exactly like an ecosystem with no vulnerabilities.

Adding one npm entry fixes today. This asserts the general property, because the
next surface added in a new language would land in the same silence: a manifest
this repo tracks must be claimed by some `updates:` entry.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"

#: Directories that are not this repository's source: vendored trees, build
#: caches, installed runtimes, and the transient branch checkouts under
#: `.git-worktrees/` (which hold *copies* of manifests already covered at their
#: real path — the same duplication that made the dependency-check scan attribute
#: a finding to a worktree instead of to `apps/kanban-viz/`).
SKIP_PARTS = frozenset({
    ".git", ".git-worktrees", ".claude", ".agents", "node_modules",
    ".venv", ".uv-cache", "__pycache__", "site-packages", "archive",
})

#: manifest filename -> the Dependabot ecosystem that claims it.
ECOSYSTEM_FOR = {
    "package.json": "npm",
    "pyproject.toml": "pip",
    "requirements.txt": "pip",
    "go.mod": "gomod",
    "Cargo.toml": "cargo",
    "Gemfile": "bundler",
}


def _config() -> dict:
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))


def _covered() -> set[tuple[str, str]]:
    """`(ecosystem, directory)` pairs the config declares, directories normalized."""
    out = set()
    for entry in _config().get("updates", []) or []:
        directory = str(entry.get("directory", "/")).rstrip("/") or "/"
        out.add((entry["package-ecosystem"], directory))
    return out


def _manifests() -> list[tuple[str, str, Path]]:
    """`(ecosystem, directory, path)` for every first-party manifest."""
    found = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.name not in ECOSYSTEM_FOR:
            continue
        rel = path.relative_to(REPO_ROOT)
        if SKIP_PARTS & set(rel.parts):
            continue
        directory = "/" + str(rel.parent) if str(rel.parent) != "." else "/"
        found.append((ECOSYSTEM_FOR[path.name], directory.rstrip("/") or "/", rel))
    return sorted(set(found))


@pytest.mark.parametrize(
    "ecosystem,directory,rel",
    _manifests(),
    ids=lambda v: str(v) if not isinstance(v, Path) else str(v),
)
def test_every_manifest_has_a_dependabot_entry(
    ecosystem: str, directory: str, rel: Path
) -> None:
    covered = _covered()
    assert (ecosystem, directory) in covered, (
        f"{rel} is a {ecosystem} manifest at {directory}, and no "
        f".github/dependabot.yml entry claims it. An ecosystem nobody configured "
        f"looks exactly like an ecosystem with no vulnerabilities — that is how "
        f"GHSA-82fw-gwwq-j7x9 sat in apps/kanban-viz for months. Declared "
        f"entries: {sorted(covered)}"
    )


def test_the_manifest_scan_finds_something() -> None:
    """A zero-length parametrization would pass vacuously.

    Names the ecosystems present when this was written; a new one is expected to
    appear and is deliberately not asserted against.
    """
    found = _manifests()
    assert len(found) >= 3, f"only {len(found)} manifests found; SKIP_PARTS is too broad"
    ecosystems = {e for e, _, _ in found}
    assert {"npm", "pip"} <= ecosystems, f"expected npm and pip, got {ecosystems}"


def test_worktree_copies_are_not_counted() -> None:
    """`.git-worktrees/` holds duplicate manifests at paths Dependabot cannot use.

    Counting them would demand entries for `/.git-worktrees/<branch>/apps/...`,
    which exist only while that branch is checked out.
    """
    assert not any(".git-worktrees" in str(rel) for _, _, rel in _manifests())
