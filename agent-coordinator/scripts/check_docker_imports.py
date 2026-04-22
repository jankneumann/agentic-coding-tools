#!/usr/bin/env python3
"""Verify that every local package imported from src/ is COPY'd in the Dockerfile.

This catches a common class of deployment bug where code references a local
package (e.g., ``from evaluation.gen_eval.mcp_service import ...``) but the
Dockerfile only copies ``src/``, causing a runtime ImportError in production
while unit tests (which see the full source tree) pass green.

How it works:

1. Parse every .py file in ``src/`` via ``ast`` and collect every top-level
   package name that appears in ``import`` / ``from ... import`` statements.
2. Scan ``src/`` for ``Path(__file__).parent... / "dirname"`` patterns to detect
   directories loaded at runtime (e.g., database migrations, config files).
3. Query the installed virtual environment via ``importlib.metadata`` for
   every distribution's ``top_level.txt`` (reliably handles cases where the
   package name and the importable module name diverge — e.g.,
   ``pyyaml`` → ``yaml``, ``google-api-python-client`` → ``googleapiclient``).
4. Parse the Dockerfile and collect every ``COPY <local>/ /app/<local>/``
   statement in the runtime stage.
5. Compute the set difference for both imports and data directory references:

       imports - stdlib - installed - copied - {"src"}
       data_dir_refs - copied

   If either result is non-empty, those are local packages or data directories
   referenced by ``src/`` but will not exist in the runtime image → hard failure.

The check also warns (non-fatal) when a ``COPY`` exists for a directory that
isn't referenced by any import or runtime path in ``src/``.

Usage:
    check_docker_imports.py [--root PATH] [--dockerfile PATH] [--src PATH]
                             [--venv PATH] [--json]

Exit codes:
    0 — all imports covered
    1 — at least one import is missing a COPY statement (hard failure)
    2 — script error (bad arguments, missing files, etc.)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import TypedDict


class CheckResult(TypedDict):
    """Structured result of a Dockerfile import coverage check."""

    status: str  # "ok" | "missing_copies"
    missing: list[str]
    missing_refs: dict[str, list[str]]
    missing_data_dirs: list[str]
    missing_data_refs: dict[str, list[str]]
    unused_copies: list[str]
    imports: list[str]
    copies: list[str]
    installed_count: int

# ---------------------------------------------------------------------------
# Collecting imports from src/
# ---------------------------------------------------------------------------


def collect_imports(src_dir: Path) -> dict[str, list[str]]:
    """Return a mapping of top-level package name → list of files that import it.

    Only considers absolute (level 0) imports. Relative imports are intra-package
    and don't need a separate COPY.
    """
    imports: dict[str, list[str]] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        rel_path = str(py_file.relative_to(src_dir.parent))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top:
                        imports.setdefault(top, []).append(rel_path)
            elif isinstance(node, ast.ImportFrom):
                # level > 0 means relative import (from .foo import bar) — skip
                if node.level == 0 and node.module:
                    top = node.module.split(".")[0]
                    if top:
                        imports.setdefault(top, []).append(rel_path)

    return imports


# ---------------------------------------------------------------------------
# Detecting runtime data directory references
# ---------------------------------------------------------------------------

# Matches: Path(__file__).resolve().parent.parent / "dirname"
# Captures the first string literal after a Path(__file__)-based navigation.
_DATA_DIR_RE = re.compile(
    r"""Path\(__file__\)         # Path(__file__)
        (?:\.\w+(?:\(\))?)*     # .resolve().parent.parent etc.
        \s*/\s*                 # the / operator
        ["']([^"']+)["']        # "dirname" — captured
    """,
    re.VERBOSE,
)


def collect_runtime_data_refs(
    src_dir: Path,
    project_root: Path,
) -> dict[str, list[str]]:
    """Detect directories referenced at runtime via ``Path(__file__)`` expressions.

    Scans all ``.py`` files in *src_dir* for patterns like::

        Path(__file__).resolve().parent.parent / "database" / "migrations"

    Extracts the first path component (``"database"``), checks if it is an
    actual directory under *project_root*, and returns a mapping of
    ``dirname → list of files that reference it``.

    Individual files (e.g., ``agents.yaml``) are ignored — only directories
    are relevant because they need a ``COPY dir/ /app/dir/`` in the Dockerfile.
    """
    refs: dict[str, list[str]] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(py_file.relative_to(src_dir.parent))

        for match in _DATA_DIR_RE.finditer(text):
            raw = match.group(1)
            # Extract just the top-level directory component
            top_dir = raw.split("/")[0]
            # Skip dotfiles, skip src (already handled)
            if top_dir.startswith(".") or top_dir == "src":
                continue
            # Only flag if it's an actual directory on disk
            if (project_root / top_dir).is_dir():
                refs.setdefault(top_dir, []).append(rel_path)

    return refs


# ---------------------------------------------------------------------------
# Collecting installed package top-level modules
# ---------------------------------------------------------------------------


def collect_installed_modules(venv_python: Path | None = None) -> set[str]:
    """Return the set of top-level module names provided by installed distributions.

    Uses ``importlib.metadata.packages_distributions()`` (Python 3.10+), which
    reliably maps every importable top-level module name to its providing
    distribution. This handles cases where the distribution name and module
    name differ (e.g., ``pyyaml`` → ``yaml``, ``google-api-python-client`` →
    ``googleapiclient``) without relying on the legacy ``top_level.txt`` file
    (which isn't always present in modern wheels).

    If ``venv_python`` is provided, delegates to that interpreter so we can
    inspect a different venv. Otherwise inspects the current process's venv.
    """
    script = (
        "import importlib.metadata, json\n"
        "pkgs = importlib.metadata.packages_distributions()\n"
        "print(json.dumps(sorted(pkgs.keys())))\n"
    )

    if venv_python and venv_python.exists():
        import subprocess

        try:
            result = subprocess.run(
                [str(venv_python), "-c", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return set(json.loads(result.stdout))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return set()

    # Inspect current interpreter
    try:
        import importlib.metadata

        packages_map = importlib.metadata.packages_distributions()
        return set(packages_map.keys())
    except Exception:  # noqa: BLE001
        return set()


# ---------------------------------------------------------------------------
# Parsing the Dockerfile
# ---------------------------------------------------------------------------


def collect_dockerfile_copies(dockerfile: Path) -> set[str]:
    """Collect top-level directory names that are COPY'd into /app/ in the Dockerfile.

    Only matches the runtime stage (we're interested in what ships, not what's
    used during build). Multi-stage Dockerfiles typically use a ``FROM ... AS
    runtime`` directive for the final stage — we collect COPY statements from
    the last stage.
    """
    content = dockerfile.read_text(encoding="utf-8")

    # Split into stages; each stage starts with a FROM directive
    stages = re.split(r"(?m)^FROM\s+", content)
    # Reattach FROM prefix to each stage (except the first which is pre-FROM content)
    runtime_stage = "FROM " + stages[-1] if len(stages) > 1 else content

    copies: set[str] = set()
    # Match: COPY <src>/ /app/... or COPY <src>/ /<abs>/
    # Also match: COPY <src> /app/...  (without trailing slash)
    pattern = re.compile(r"^\s*COPY\s+(?:--from=\S+\s+)?(\S+?)/?\s+(?:/app/|/)", re.MULTILINE)
    for match in pattern.finditer(runtime_stage):
        src = match.group(1)
        # Skip COPY --from (cross-stage copies, not local directories)
        if src.startswith("/") or src.startswith("--"):
            continue
        # Only track directory-like copies (no file extensions like .toml, .yaml)
        if "." not in Path(src).name or src.endswith(("/", "/*")):
            copies.add(src.rstrip("/").split("/")[0])

    return copies


# ---------------------------------------------------------------------------
# Stdlib detection
# ---------------------------------------------------------------------------


def stdlib_modules() -> set[str]:
    """Return the set of stdlib top-level module names for the current interpreter.

    Python 3.10+ provides ``sys.stdlib_module_names``. Falls back to a small
    curated set on earlier versions.
    """
    if hasattr(sys, "stdlib_module_names"):
        return set(sys.stdlib_module_names)
    # Fallback for Python < 3.10 (should not apply to this project)
    return {
        "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
        "copy", "csv", "dataclasses", "datetime", "enum", "errno", "functools",
        "hashlib", "hmac", "http", "importlib", "inspect", "io", "ipaddress",
        "itertools", "json", "logging", "math", "os", "pathlib", "re", "secrets",
        "shutil", "signal", "socket", "sqlite3", "ssl", "string", "subprocess",
        "sys", "tempfile", "threading", "time", "traceback", "typing", "unittest",
        "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
    }


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------


IGNORED_PSEUDO_MODULES: frozenset[str] = frozenset(
    {
        "__future__",  # Python pseudo-module
        "src",          # Always COPY'd by definition (the check is about src/)
    }
)


def check_dockerfile_imports(
    src_dir: Path,
    dockerfile: Path,
    venv_python: Path | None = None,
    data_dirs: set[str] | None = None,
    project_root: Path | None = None,
) -> CheckResult:
    """Run the full check and return a structured result.

    Args:
        src_dir: Directory to scan for Python imports
        dockerfile: Dockerfile to parse for COPY statements
        venv_python: Optional venv interpreter to inspect for installed modules
        data_dirs: Directory names that are COPY'd as runtime data (read from
            disk, not imported as Python packages). These are excluded from
            the "unused copies" warning. Example: ``{"cedar", "profiles"}``
            for directories containing YAML/JSON config files loaded at runtime.
        project_root: Project root for resolving runtime data directory
            references. Defaults to ``src_dir.parent``.

    The returned dict contains:

        status: "ok" | "missing_copies" | "error"
        missing: list[str]  — local packages imported but not COPY'd
        missing_refs: dict[str, list[str]]  — missing pkg → files that import it
        missing_data_dirs: list[str]  — data dirs referenced at runtime but not COPY'd
        missing_data_refs: dict[str, list[str]]  — data dir → files that reference it
        unused_copies: list[str]  — dirs COPY'd but not imported (warnings)
        imports: list[str]  — all top-level package names found in src/
        copies: list[str]  — all directories COPY'd in the runtime stage
        installed_count: int — number of modules provided by the venv
    """
    data_dirs = data_dirs or set()
    root = project_root or src_dir.parent
    imports = collect_imports(src_dir)
    copies = collect_dockerfile_copies(dockerfile)
    installed = collect_installed_modules(venv_python)
    stdlib = stdlib_modules()

    # Local packages = imports that aren't stdlib, aren't installed, and aren't ignored
    local_imports = {
        pkg
        for pkg in imports
        if pkg not in stdlib
        and pkg not in installed
        and pkg not in IGNORED_PSEUDO_MODULES
    }

    missing = sorted(local_imports - copies)

    # Runtime data directory detection: scan src/ for Path(__file__)-based
    # references to sibling directories that need to be COPY'd.
    runtime_refs = collect_runtime_data_refs(src_dir, root)
    missing_data = sorted(set(runtime_refs) - copies)
    missing_data_refs = {d: sorted(set(runtime_refs[d]))[:5] for d in missing_data}

    # Exclude data dirs AND auto-detected runtime refs from "unused" warnings
    all_data = data_dirs | set(runtime_refs)
    unused = sorted(copies - local_imports - {"src"} - all_data)

    missing_refs = {pkg: sorted(set(imports[pkg]))[:5] for pkg in missing}

    has_failures = bool(missing or missing_data)
    return CheckResult(
        status="ok" if not has_failures else "missing_copies",
        missing=missing,
        missing_refs=missing_refs,
        missing_data_dirs=missing_data,
        missing_data_refs=missing_data_refs,
        unused_copies=unused,
        imports=sorted(imports.keys()),
        copies=sorted(copies),
        installed_count=len(installed),
    )


def format_report(result: CheckResult, verbose: bool = False) -> str:
    """Format the check result as a human-readable report."""
    lines: list[str] = []

    missing = result["missing"]
    missing_data = result["missing_data_dirs"]
    unused = result["unused_copies"]
    missing_refs = result["missing_refs"]
    missing_data_refs = result["missing_data_refs"]

    if missing:
        lines.append("ERROR: Dockerfile is missing COPY for local packages imported by src/:")
        lines.append("")
        for pkg in missing:
            refs = missing_refs.get(pkg, [])
            ref_str = ", ".join(refs[:3]) if refs else "(unknown)"
            suffix = "" if len(refs) <= 3 else f" (+{len(refs) - 3} more)"
            lines.append(f"  {pkg}  — imported by {ref_str}{suffix}")
        lines.append("")
        lines.append("Fix: add a matching COPY statement to the Dockerfile runtime stage, e.g.:")
        for pkg in missing:
            lines.append(f"  COPY {pkg}/ /app/{pkg}/")
        lines.append("")

    if missing_data:
        lines.append(
            "ERROR: Dockerfile is missing COPY for data directories loaded at runtime by src/:"
        )
        lines.append("")
        for d in missing_data:
            refs = missing_data_refs.get(d, [])
            ref_str = ", ".join(refs[:3]) if refs else "(unknown)"
            suffix = "" if len(refs) <= 3 else f" (+{len(refs) - 3} more)"
            lines.append(f"  {d}/  — referenced by {ref_str}{suffix}")
        lines.append("")
        lines.append("Fix: add a matching COPY statement to the Dockerfile runtime stage, e.g.:")
        for d in missing_data:
            lines.append(f"  COPY {d}/ /app/{d}/")
        lines.append("")

    if unused:
        lines.append(f"WARNING: {len(unused)} directory COPY(s) are not imported by src/:")
        for d in unused:
            lines.append(f"  {d}  — consider removing from the Dockerfile")
        lines.append("")

    if verbose:
        lines.append("Summary:")
        lines.append(f"  Imports from src/:         {len(result['imports'])}")
        lines.append(f"  Installed venv modules:    {result['installed_count']}")
        lines.append(f"  Directories copied:        {len(result['copies'])}")
        lines.append(f"  Missing copies:            {len(missing)}")
        lines.append(f"  Missing data dirs:         {len(missing_data)}")
        lines.append(f"  Unused copies (warnings):  {len(unused)}")

    if not missing and not missing_data and not unused:
        lines.append(
            "OK: every local package imported by src/ has a matching COPY in the Dockerfile"
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Dockerfile COPY coverage for src/ imports",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=None,
        help="Source directory to scan (default: <root>/src)",
    )
    parser.add_argument(
        "--dockerfile",
        type=Path,
        default=None,
        help="Path to Dockerfile (default: <root>/Dockerfile)",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        default=None,
        help="Path to venv Python interpreter (default: current interpreter)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include summary counts in the report",
    )
    parser.add_argument(
        "--strict-unused",
        action="store_true",
        help="Treat unused COPYs as errors (default: warnings only)",
    )
    parser.add_argument(
        "--data-dir",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Mark a COPY'd directory as a runtime data directory "
            "(loaded from disk, not imported as a Python package). "
            "Excluded from the 'unused copies' warning. Repeatable."
        ),
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    src_dir = (args.src or root / "src").resolve()
    dockerfile = (args.dockerfile or root / "Dockerfile").resolve()

    if not src_dir.exists():
        print(f"ERROR: src directory not found: {src_dir}", file=sys.stderr)
        return 2
    if not dockerfile.exists():
        print(f"ERROR: Dockerfile not found: {dockerfile}", file=sys.stderr)
        return 2

    result = check_dockerfile_imports(
        src_dir=src_dir,
        dockerfile=dockerfile,
        venv_python=args.venv,
        data_dirs=set(args.data_dir),
        project_root=root,
    )

    if args.json_output:
        print(json.dumps(result, indent=2, default=list))
    else:
        print(format_report(result, verbose=args.verbose))

    if result["missing"] or result["missing_data_dirs"]:
        return 1
    if args.strict_unused and result["unused_copies"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
