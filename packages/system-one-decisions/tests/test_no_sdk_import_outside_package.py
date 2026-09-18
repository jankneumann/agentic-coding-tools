"""Guard test: typesafe_sdk is imported nowhere but this package.

Spec: specs/system-one-decisions/spec.md
  "decide() declares a live extra and imports the vendor SDK nowhere else"
  Scenario: "No other package or skill imports the vendor SDK"

Scoped to git-tracked files only (``git ls-files``), so vendored/build
directories (``.venv``, ``node_modules``, ``.git-worktrees``) are excluded
without a hand-maintained allowlist that would silently rot as new such
directories appear.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

_PACKAGE_DIR_NAME = "system-one-decisions"


def _repo_root() -> Path:
    """Walk up from this file looking for the repo root marker, rather than
    a fixed `parents[N]` index -- the same "walk named parents" principle
    `packages/context-eval`'s loader documents, so this test survives a
    future path-depth change instead of silently pointing at the wrong tree.
    """
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / ".git").exists() and (candidate / "openspec").is_dir():
            return candidate
    raise RuntimeError(f"could not locate repo root by walking up from {current}")


def _imports_typesafe_sdk(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "typesafe_sdk" for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "typesafe_sdk"
        ):
            return True
    return False


def test_typesafe_sdk_is_imported_only_inside_this_package() -> None:
    repo_root = _repo_root()
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    offenders = [
        rel_path
        for rel_path in tracked
        if f"packages/{_PACKAGE_DIR_NAME}/" not in rel_path
        and _imports_typesafe_sdk(repo_root / rel_path)
    ]

    assert not offenders, (
        "typesafe_sdk imported outside packages/system-one-decisions: "
        f"{offenders}"
    )
