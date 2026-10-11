"""Skill-under-test materialization (design D5).

Copies the *whole* skills tree of the checkout being evaluated into the workspace's
project-local skill directories, because skills resolve helpers through sibling paths
(``<skill-base-dir>/../worktree/...``). Shared by ``CLIVendorExecutor`` and, opt-in,
``FakeExecutor`` so the acceptance drill can exercise the same code path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

#: Project-local skill locations the vendor CLIs read.
SKILL_TARGET_DIRS = (".claude/skills", ".agents/skills")
#: Names never copied (at any depth).
SKILL_COPY_EXCLUDES = ("tests", ".venv", "__pycache__", "node_modules")


class SkillMaterializationError(RuntimeError):
    """Raised when the skill under test cannot be materialized."""


def skills_sha(skills_root: Path) -> str | None:
    """Git HEAD of the repo containing ``skills_root``; ``+dirty`` when modified.

    Returns None when ``skills_root`` is not inside a git checkout.
    """

    def _git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(skills_root), *args], capture_output=True, text=True, check=False
        )

    head = _git("rev-parse", "HEAD")
    if head.returncode != 0 or not head.stdout.strip():
        return None
    sha = head.stdout.strip()
    status = _git("status", "--porcelain")
    if status.returncode == 0 and status.stdout.strip():
        sha += "+dirty"
    return sha


def _git_exclude(workdir: Path, patterns: list[str]) -> None:
    info = workdir / ".git" / "info"
    if not info.is_dir():
        return
    exclude = info / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [p for p in patterns if p not in existing.splitlines()]
    if missing:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        exclude.write_text(existing + sep + "\n".join(missing) + "\n", encoding="utf-8")


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    """Excluded names plus genuinely dangling symlinks.

    Replaces ``copytree(ignore_dangling_symlinks=True)``, which tests a relative link
    target against the process cwd rather than the link's directory and so drops every
    relative in-tree link (``CLAUDE.md -> AGENTS.md``) as if it were dangling.
    """
    out = {n for n in names if n in SKILL_COPY_EXCLUDES}
    for name in names:
        path = Path(directory) / name
        if path.is_symlink() and not path.exists():
            out.add(name)
    return out


def _reject_escaping_symlinks(skills_root: Path) -> None:
    """Raise when a symlink in the copied tree resolves outside ``skills_root``.

    ``copytree`` follows symlinks, so a link to a host file (credentials under HOME,
    say) would be copied into the agent-readable workspace. In-tree links -- e.g. a
    skill's ``CLAUDE.md -> AGENTS.md`` -- are legitimate and are kept.
    """
    root = skills_root.resolve()
    for entry in sorted(skills_root.iterdir()):
        if entry.name in SKILL_COPY_EXCLUDES or entry.name.startswith("."):
            continue
        candidates = [entry]
        if entry.is_dir() and not entry.is_symlink():
            for dirpath, dirnames, filenames in os.walk(entry):
                dirnames[:] = [d for d in dirnames if d not in SKILL_COPY_EXCLUDES]
                candidates.extend(Path(dirpath) / n for n in (*dirnames, *filenames))
        for path in candidates:
            if path.is_symlink() and not path.resolve().is_relative_to(root):
                raise SkillMaterializationError(
                    f"symlink {path} resolves outside skills_root ({path.resolve()})"
                )


def materialize_skills(skills_root: Path, skill_under_test: str, workdir: Path) -> str | None:
    """Copy the skills tree into ``workdir`` and return the ``skills_sha``.

    Raises :class:`SkillMaterializationError` (before anything is copied) when
    ``skills_root/<skill_under_test>/SKILL.md`` is missing.
    """
    skills_root = Path(skills_root)
    if not (skills_root / skill_under_test / "SKILL.md").is_file():
        raise SkillMaterializationError(
            f"skill under test {skill_under_test!r} not found in skills_root {skills_root}"
        )
    _reject_escaping_symlinks(skills_root)
    ignore = _copy_ignore
    for target_rel in SKILL_TARGET_DIRS:
        target = workdir / target_rel
        target.mkdir(parents=True, exist_ok=True)
        for entry in sorted(skills_root.iterdir()):
            skip = entry.name in SKILL_COPY_EXCLUDES or entry.name.startswith(".")
            if not entry.is_dir() or skip:
                continue
            shutil.copytree(
                entry,
                target / entry.name,
                ignore=ignore,
                dirs_exist_ok=True,
            )
    _git_exclude(workdir, [f"/{t}/" for t in SKILL_TARGET_DIRS])
    return skills_sha(skills_root)
