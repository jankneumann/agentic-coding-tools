"""Resolve the interpreter that runs the optional tree-sitter stages (issue #378).

This module is the single source of truth for "is tree-sitter available, and
which Python has it". Before it existed there were two answers:

* ``refresh_architecture.sh`` probed ``${SCRIPTS_DIR}/.venv/bin/python`` — a
  per-skill venv that does not exist in this repository and that nothing
  creates — and required both ``tree_sitter`` and ``tree_sitter_sql``; while
* :func:`provenance.detect_optional_tools` imported ``tree_sitter`` in whatever
  process happened to be running provenance, and never checked
  ``tree_sitter_sql``.

The generated artifacts follow the first answer and the recorded provenance
follows the second, so a refresh could skip the enrichment, comment-linker and
pattern-reporter stages while stamping ``tree-sitter available: true``. Both
callers now ask this module, so they cannot disagree.

Resolution deliberately ends at a *project root* venv. Per repository
convention a virtualenv belongs to a project (``skills/``, the repo root), never
nested inside an individual skill directory.

Run as a script, it prints the resolved interpreter and exits 0, or exits 1 when
tree-sitter is unavailable — which is how the shell pipeline consumes it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Both are required. The SQL analyzer needs ``tree_sitter_sql``; an interpreter
#: carrying only ``tree_sitter`` cannot run every stage that claims the tool, and
#: reporting it as available is what let provenance overstate what ran.
REQUIRED_MODULES: tuple[str, ...] = ("tree_sitter", "tree_sitter_sql")

#: Explicit override, checked first, for callers that must pin the interpreter.
OVERRIDE_ENV = "ARCH_TREESITTER_PYTHON"

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def candidate_pythons(scripts_dir: Path | None = None) -> list[Path]:
    """Return interpreters to try, most specific first.

    The current interpreter comes early because the Makefile already resolves
    ``PYTHON`` to ``skills/.venv`` when it exists; honoring it keeps `make` and
    the shell pipeline on one interpreter instead of two.
    """
    scripts = Path(scripts_dir) if scripts_dir is not None else _SCRIPTS_DIR
    candidates: list[Path] = []

    override = os.environ.get(OVERRIDE_ENV)
    if override:
        candidates.append(Path(override))

    candidates.append(Path(sys.executable))

    # scripts/ -> <skill>/ -> skills/ -> <repo root>. Project-root venvs only.
    for ancestor in (scripts.parents[1], scripts.parents[2]):
        candidates.append(ancestor / ".venv" / "bin" / "python")

    which = shutil.which("python3")
    if which:
        candidates.append(Path(which))

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _can_import(python: Path, modules: tuple[str, ...]) -> bool:
    """Return whether *python* can import every module in *modules*."""
    if not (python.is_file() or shutil.which(str(python))):
        return False
    code = "".join(f"import {name}\n" for name in modules)
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_treesitter_python(scripts_dir: Path | None = None) -> Path | None:
    """Return the first interpreter that can import every required module.

    ``None`` means the tree-sitter stages cannot run, and every caller must then
    agree that the tool is unavailable.
    """
    if os.environ.get("TREESITTER_ENABLED", "true") != "true":
        return None
    for candidate in candidate_pythons(scripts_dir):
        if _can_import(candidate, REQUIRED_MODULES):
            return candidate
    return None


def treesitter_version(python: Path) -> str | None:
    """Return the ``tree-sitter`` version *python* reports, or ``None``."""
    code = (
        "from importlib.metadata import PackageNotFoundError, version\n"
        "try:\n"
        "    print(version('tree-sitter'))\n"
        "except PackageNotFoundError:\n"
        "    pass\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    """Print the resolved interpreter; exit 1 when tree-sitter is unavailable."""
    resolved = resolve_treesitter_python()
    if resolved is None:
        return 1
    print(str(resolved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
