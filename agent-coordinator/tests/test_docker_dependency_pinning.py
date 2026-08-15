"""The deployed image's dependency set must come from the lockfile.

Every input to `uv sync` in the builder stage is pinned, so rebuilding one commit
installs one dependency set. These are cheap text assertions rather than a
container build: the build itself is covered by the `docker-smoke-import` CI job,
and what is worth guarding here is that nobody quietly relaxes a flag.

Each check corresponds to a way the image previously took its dependencies from
somewhere other than uv.lock.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "agent-coordinator" / "Dockerfile"
LOCKFILE = ROOT / "agent-coordinator" / "uv.lock"


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_lockfile_is_committed() -> None:
    """The pins the image installs have to exist in the repository."""
    assert LOCKFILE.is_file(), f"{LOCKFILE} is missing; `uv sync --locked` cannot work"


def test_uv_sync_refuses_a_stale_lockfile() -> None:
    """`--locked` turns lock/pyproject drift into a red build.

    Without it, `uv sync` silently re-resolves, so a dependency added to
    pyproject.toml but never locked is installed into the deployed image anyway.
    """
    sync = [line for line in _dockerfile().splitlines() if "uv sync" in line]
    assert len(sync) == 1, f"expected exactly one `uv sync` line, found {len(sync)}"
    assert "--locked" in sync[0], (
        "uv sync must run with --locked so a stale lockfile fails the build "
        f"instead of re-resolving: {sync[0]}"
    )


def test_lockfile_copy_is_not_optional() -> None:
    """A globbed `uv.lock*` makes the lockfile optional.

    Docker only errors when *no* source matches, and `pyproject.toml` always
    does — so a missing lock left the COPY satisfied and the build fell through
    to resolving from scratch.
    """
    copies = [
        line
        for line in _dockerfile().splitlines()
        if line.startswith("COPY") and "uv.lock" in line
    ]
    assert copies, "the Dockerfile never copies uv.lock"
    for line in copies:
        assert "uv.lock*" not in line, (
            f"uv.lock must not be globbed — that makes it optional: {line}"
        )


def test_uv_itself_is_pinned() -> None:
    """An unpinned resolver is an unpinned build input.

    `pip install uv` takes whatever is newest at build time, so the same commit
    can resolve differently later through no change of ours.
    """
    installs = [
        line
        for line in _dockerfile().splitlines()
        if re.search(r"pip install .*\buv\b", line)
    ]
    assert installs, "the Dockerfile never installs uv"
    for line in installs:
        assert re.search(r"\buv==\d+\.\d+", line), (
            f"uv must be installed at a pinned version: {line}"
        )
