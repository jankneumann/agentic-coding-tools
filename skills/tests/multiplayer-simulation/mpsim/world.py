"""The simulated world: a shared bare remote plus N principals (design D6).

The world owns a temporary root holding a ``file://`` bare remote, one clone per
principal and one ``git worktree`` per (principal, change). Principals see each
other's work only through ``git fetch`` from the remote. Every git call runs with
no global config and with author/committer dates derived from the logical tick,
so identical inputs give identical commit ids in any directory.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mpsim.errors import ScenarioError, UsageError

MIN_PRINCIPALS = 2
SEED_IDENTITY = ("sim-seed", "sim-seed@sim.invalid")
SUPERVISOR_IDENTITY = ("sim-supervisor", "sim-supervisor@sim.invalid")
# 2026-01-01T00:00:00Z. A tick is one logical minute.
_EPOCH = 1767225600
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def date_for_tick(tick: int) -> str:
    return f"@{_EPOCH + tick * 60} +0000"


@dataclass(frozen=True)
class Principal:
    name: str
    email: str
    agent_id: str
    clone: Path


@dataclass(frozen=True)
class PrincipalView:
    """Read-only view handed to probes: git state can be read, never mutated."""

    principal: str
    agent_id: str
    change_id: str
    worktree: Path
    remote_url: str

    def read_text(self, relative: str) -> str:
        return (self.worktree / relative).read_text()

    def exists(self, relative: str) -> bool:
        return (self.worktree / relative).exists()

    def list_files(self, relative: str = ".") -> list[str]:
        base = self.worktree / relative
        return sorted(
            str(p.relative_to(self.worktree)) for p in base.rglob("*") if p.is_file()
            and ".git" not in p.relative_to(self.worktree).parts[:1]
        )


class World:
    def __init__(self, root: Path, remote: Path, principals: Mapping[str, Principal]):
        self.root = root
        self._remote = remote
        self._principals = dict(principals)

    # -- construction ------------------------------------------------------

    @classmethod
    def create(
        cls,
        root: Path,
        names: Sequence[str],
        seed_files: Mapping[str, str],
    ) -> World:
        names = list(names)
        if len(names) < MIN_PRINCIPALS:
            raise UsageError(
                f"a world needs at least {MIN_PRINCIPALS} principals, got {len(names)}"
            )
        if len(set(names)) != len(names):
            raise UsageError("principal names must be distinct")
        for name in names:
            if not _NAME_RE.match(name):
                raise UsageError(f"invalid principal name {name!r}")
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        remote = root / "remote.git"
        world = cls(root, remote, {})
        world._run(root, "init", "--bare", "-q", "-b", "main", str(remote))

        seed = root / "seed-work"
        world._run(root, "init", "-q", "-b", "main", str(seed))
        for rel, content in seed_files.items():
            target = seed / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        world._commit(seed, "seed", SEED_IDENTITY, tick=0)
        world._run(seed, "push", "-q", world.remote_url, "main:refs/heads/main")

        for name in names:
            base = root / "principals" / name
            base.mkdir(parents=True)
            clone = base / "clone"
            world._run(root, "clone", "-q", world.remote_url, str(clone))
            email = f"{name}@sim.invalid"
            world._run(clone, "config", "user.name", name)
            world._run(clone, "config", "user.email", email)
            world._principals[name] = Principal(name, email, f"{name}-agent-1", clone)
        return world

    @property
    def remote_url(self) -> str:
        return f"file://{self._remote}"

    @property
    def names(self) -> list[str]:
        return list(self._principals)

    def principal(self, name: str) -> Principal:
        try:
            return self._principals[name]
        except KeyError:
            raise UsageError(f"unknown principal {name!r}") from None

    def worktree_path(self, name: str, change: str) -> Path:
        return self.principal(name).clone.parent / f"wt-{change}"

    def branch(self, name: str, change: str) -> str:
        return f"sim/{name}/{change}"

    def view(self, name: str, change: str) -> PrincipalView:
        p = self.principal(name)
        return PrincipalView(name, p.agent_id, change, self.worktree_path(name, change),
                             self.remote_url)

    # -- git operations ----------------------------------------------------

    def add_worktree(self, name: str, change: str, tick: int) -> Path:
        """Create the principal's worktree and branch from the latest fetched main."""
        clone = self.principal(name).clone
        self.fetch(name)
        path = self.worktree_path(name, change)
        self._run(clone, "worktree", "add", "-q", "-b", self.branch(name, change),
                  str(path), "origin/main")
        return path

    def commit(self, name: str, change: str, message: str, tick: int) -> None:
        p = self.principal(name)
        self._commit(self.worktree_path(name, change), message, (p.name, p.email), tick)

    def push(self, name: str, change: str) -> None:
        branch = self.branch(name, change)
        self._run(self.worktree_path(name, change), "push", "-q", "origin",
                  f"{branch}:refs/heads/{branch}")

    def fetch(self, name: str) -> None:
        self._run(self.principal(name).clone, "fetch", "-q", "--prune", "origin")

    def read_ref(self, name: str, ref: str, path: str) -> str:
        return self._run(self.principal(name).clone, "show", f"{ref}:{path}", strip=False)

    # -- internals ---------------------------------------------------------

    def _env(self, tick: int | None = None, identity: tuple[str, str] | None = None) -> dict:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.root),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
        if identity is not None and tick is not None:
            name, email = identity
            when = date_for_tick(tick)
            env.update(
                GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when,
                GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=when,
            )
        return env

    def _commit(self, cwd: Path, message: str, identity: tuple[str, str], tick: int) -> None:
        self._run(cwd, "add", "-A")
        self._run(
            cwd, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", message,
            env=self._env(tick, identity),
        )

    def _run(self, cwd: Path, *args: str, env: dict | None = None, strip: bool = True) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, env=env or self._env(), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip().replace(str(self.root), "<world>")
            raise ScenarioError(f"git {args[0]} failed: {detail}")
        return proc.stdout.strip() if strip else proc.stdout

    # -- helpers for the status applier (its own clone, not a principal's) --

    def clone_for(self, path: Path, identity: tuple[str, str]) -> Path:
        """Clone the shared remote to ``path`` and set the local committer identity."""
        self._run(self.root, "clone", "-q", self.remote_url, str(path))
        self._run(path, "config", "user.name", identity[0])
        self._run(path, "config", "user.email", identity[1])
        return path

    def commit_as(self, cwd: Path, message: str, identity: tuple[str, str], tick: int) -> None:
        self._commit(cwd, message, identity, tick)

    def run_git(self, cwd: Path, *args: str) -> str:
        return self._run(cwd, *args)
