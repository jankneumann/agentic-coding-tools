#!/usr/bin/env python3
"""Analyzer: import graph complexity and circular dependencies.

Builds a module-level import graph from Python ``import`` / ``from ... import``
statements and detects:

- **Circular Imports** — cycles in the import graph (fragile initialization order)
- **Import Fan-out** — modules importing from too many others (lack of focus)
- **Star Imports** — ``from X import *`` (namespace pollution, readability)

Uses Python's ``ast`` module for reliable import extraction.
"""

from __future__ import annotations

import ast
import time
from collections import deque
from pathlib import Path

from models import AnalyzerResult, TechDebtFinding

ANALYZER = "imports"

SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git", ".tox", "dist", "build",
    ".agents", ".claude", ".codex", ".gemini",  # runtime skill copies
}

# ── Thresholds ────────────────────────────────────────────────────────
IMPORT_FAN_OUT_THRESHOLD = 15  # unique modules imported
IMPORT_FAN_OUT_CRITICAL = 25
MAX_CYCLES_REPORTED = 10


def _should_skip(path: Path) -> bool:
    return bool(SKIP_DIRS.intersection(path.parts))


def _module_name_from_path(rel_path: Path) -> str:
    """Convert a relative file path to a dotted module name."""
    parts = list(rel_path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _extract_imports(source: str, module_name: str) -> tuple[list[str], list[str]]:
    """Extract imported module names and star imports from source.

    Returns
    -------
    (imports, star_imports)
        imports: list of dotted module names imported
        star_imports: list of modules with ``from X import *``
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []

    imports: list[str] = []
    star_imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module
                # Handle relative imports
                if node.level and node.level > 0:
                    parts = module_name.split(".")
                    if len(parts) >= node.level:
                        prefix = ".".join(parts[: -node.level])
                        base = f"{prefix}.{node.module}" if prefix else node.module
                    else:
                        base = node.module

                imports.append(base)

                # Detect star imports
                for alias in node.names:
                    if alias.name == "*":
                        star_imports.append(base)

    return imports, star_imports


def _find_cycles(graph: dict[str, set[str]], max_cycles: int = MAX_CYCLES_REPORTED) -> list[list[str]]:
    """Find cycles in the import graph using iterative DFS.

    Returns up to max_cycles unique cycles (by frozenset of nodes).
    """
    cycles: list[list[str]] = []
    seen_cycle_sets: set[frozenset[str]] = set()

    for start_node in graph:
        # DFS with path tracking
        stack: list[tuple[str, list[str], set[str]]] = [(start_node, [start_node], {start_node})]

        while stack and len(cycles) < max_cycles:
            node, path, visited = stack.pop()

            for neighbor in graph.get(node, set()):
                if neighbor == start_node and len(path) > 1:
                    cycle = path + [start_node]
                    cycle_set = frozenset(path)
                    if cycle_set not in seen_cycle_sets:
                        seen_cycle_sets.add(cycle_set)
                        cycles.append(cycle)
                        if len(cycles) >= max_cycles:
                            break
                elif neighbor not in visited and neighbor in graph:
                    # Limit depth to avoid combinatorial explosion
                    if len(path) < 6:
                        stack.append((neighbor, path + [neighbor], visited | {neighbor}))

    return cycles


def _severity(value: float, threshold: float, critical: float) -> str:
    if value >= critical:
        return "high"
    if value >= threshold:
        return "medium"
    return "low"


def analyze(project_dir: str) -> AnalyzerResult:
    """Scan Python files for import complexity issues.

    Parameters
    ----------
    project_dir:
        Path to the project root.

    Returns
    -------
    AnalyzerResult
    """
    start = time.monotonic()
    root = Path(project_dir).resolve()

    # module_name -> set of imported module names
    import_graph: dict[str, set[str]] = {}
    # module_name -> (rel_path, line_count)
    module_meta: dict[str, tuple[str, int]] = {}
    # Collect star imports: module_name -> list of star-imported modules
    star_import_map: dict[str, list[str]] = {}

    try:
        py_files = sorted(root.glob("**/*.py"))
        for py_file in py_files:
            rel = py_file.relative_to(root)
            if _should_skip(rel):
                continue

            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            mod_name = _module_name_from_path(rel)
            imports, stars = _extract_imports(source, mod_name)

            # Only track internal imports (those that resolve to project modules)
            import_graph[mod_name] = set(imports)
            module_meta[mod_name] = (str(rel), len(source.splitlines()))
            if stars:
                star_import_map[mod_name] = stars

    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return AnalyzerResult(
            analyzer=ANALYZER,
            status="error",
            duration_ms=elapsed,
            messages=[f"Unexpected error: {exc}"],
        )

    # Filter import_graph to only include edges where target is a known module
    known_modules = set(import_graph.keys())
    internal_graph: dict[str, set[str]] = {}
    for mod, deps in import_graph.items():
        internal_deps = set()
        for dep in deps:
            if dep in known_modules:
                internal_deps.add(dep)
            else:
                # Check if it's a parent package of a known module
                for known in known_modules:
                    if known.startswith(dep + "."):
                        internal_deps.add(dep)
                        break
        if internal_deps:
            internal_graph[mod] = internal_deps

    findings: list[TechDebtFinding] = []

    # ── Circular imports ──────────────────────────────────────────
    cycles = _find_cycles(internal_graph)
    for idx, cycle in enumerate(cycles):
        cycle_str = " -> ".join(cycle)
        cycle_len = len(cycle) - 1  # edges, not nodes

        severity = "high" if cycle_len >= 3 else "medium"
        # Use the first module's file as the primary location
        first_mod = cycle[0]
        file_path = module_meta.get(first_mod, ("", 0))[0]

        findings.append(
            TechDebtFinding(
                id=f"td-circular-import-{idx}",
                analyzer=ANALYZER,
                severity=severity,  # type: ignore[arg-type]
                category="import-complexity",  # type: ignore[arg-type]
                title=f"Circular import: {cycle_str}",
                detail=(
                    f"Circular dependency detected ({cycle_len} modules): {cycle_str}. "
                    "Circular imports make initialization order fragile and "
                    "can cause ImportError at runtime."
                ),
                file_path=file_path,
                metric_name="cycle_length",
                metric_value=cycle_len,
                threshold=1,
                smell="Circular Dependency",
                recommendation=(
                    "Break the cycle by extracting shared types into a "
                    "separate module, or use lazy imports (import inside function)."
                ),
            ),
        )

    # ── Import fan-out ────────────────────────────────────────────
    for mod_name, deps in sorted(
        import_graph.items(), key=lambda x: -len(x[1])
    ):
        count = len(deps)
        if count < IMPORT_FAN_OUT_THRESHOLD:
            continue

        sev = _severity(count, IMPORT_FAN_OUT_THRESHOLD, IMPORT_FAN_OUT_CRITICAL)
        file_path = module_meta.get(mod_name, ("", 0))[0]

        findings.append(
            TechDebtFinding(
                id=f"td-import-fanout-{mod_name}",
                analyzer=ANALYZER,
                severity=sev,  # type: ignore[arg-type]
                category="import-complexity",  # type: ignore[arg-type]
                title=f"High import fan-out: {mod_name} imports {count} modules",
                detail=(
                    f"Module '{mod_name}' imports {count} unique modules "
                    f"(threshold: {IMPORT_FAN_OUT_THRESHOLD}). "
                    "This suggests the module has too many responsibilities."
                ),
                file_path=file_path,
                line=1,
                metric_name="import_fan_out",
                metric_value=count,
                threshold=IMPORT_FAN_OUT_THRESHOLD,
                smell="Divergent Change",
                recommendation=(
                    "Split the module along responsibility boundaries. "
                    "Each module should import from a focused set of dependencies."
                ),
            ),
        )

    # ── Star imports ──────────────────────────────────────────────
    for mod_name, stars in star_import_map.items():
        file_path = module_meta.get(mod_name, ("", 0))[0]
        for star_mod in stars:
            findings.append(
                TechDebtFinding(
                    id=f"td-star-import-{mod_name}-{star_mod}",
                    analyzer=ANALYZER,
                    severity="medium",  # type: ignore[arg-type]
                    category="import-complexity",  # type: ignore[arg-type]
                    title=f"Star import: from {star_mod} import *",
                    detail=(
                        f"Module '{mod_name}' uses ``from {star_mod} import *``. "
                        "Star imports pollute the namespace and make it impossible "
                        "to determine where a name comes from."
                    ),
                    file_path=file_path,
                    line=1,
                    metric_name="star_imports",
                    metric_value=1,
                    threshold=0,
                    smell="Namespace Pollution",
                    recommendation="Replace with explicit named imports.",
                ),
            )

    elapsed = int((time.monotonic() - start) * 1000)
    return AnalyzerResult(
        analyzer=ANALYZER,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
    )
