#!/usr/bin/env python3
"""Analyzer: function size, file size, cyclomatic complexity, nesting depth, and parameter count.

Detects the following code smells from Fowler's *Refactoring* catalog:

- **Long Method** — functions exceeding a line-count threshold
- **Large Class / God File** — modules with too many lines or too many
  top-level definitions
- **Complex Function** — high cyclomatic complexity (McCabe metric)
- **Deep Nesting** — control-flow nesting beyond a readability threshold
- **Long Parameter List** — functions accepting too many parameters

Uses Python's ``ast`` module for accurate, comment-aware analysis.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

from models import AnalyzerResult, TechDebtFinding

ANALYZER = "complexity"

# ── Skip directories ──────────────────────────────────────────────────
SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git", ".tox", "dist", "build",
    ".agents", ".claude", ".codex", ".gemini",  # runtime skill copies
}

# ── Configurable thresholds ───────────────────────────────────────────
# Each tuple: (threshold, severity_at_threshold, severity_well_above)
# "well above" = 2× the threshold.

FUNCTION_LINE_THRESHOLD = 50  # Fowler: "prefer short functions"
FUNCTION_LINE_CRITICAL = 100  # > 100 lines is almost always a smell
FILE_LINE_THRESHOLD = 500
FILE_LINE_CRITICAL = 1000
COMPLEXITY_THRESHOLD = 10  # McCabe standard
COMPLEXITY_CRITICAL = 20
NESTING_THRESHOLD = 4  # levels of indentation nesting
NESTING_CRITICAL = 6
PARAM_THRESHOLD = 5
PARAM_CRITICAL = 8
DEFINITIONS_THRESHOLD = 20  # top-level classes + functions in one file
DEFINITIONS_CRITICAL = 40


def _severity(value: float, threshold: float, critical: float) -> str:
    """Map a metric value to a severity based on threshold bands."""
    if value >= critical:
        return "high"
    if value >= threshold:
        return "medium"
    return "low"


# ── AST visitors ──────────────────────────────────────────────────────


def _count_complexity(node: ast.AST) -> int:
    """Approximate McCabe cyclomatic complexity for a function body.

    Counts decision points: if, for, while, except, with, assert,
    boolean operators (and/or), and ternary (IfExp).
    Each adds 1 to a base complexity of 1.
    """
    complexity = 1  # base path
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, (ast.While,)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # Each `and`/`or` adds one decision point per extra operand
            complexity += len(child.values) - 1
    return complexity


def _max_nesting(node: ast.AST, current: int = 0) -> int:
    """Return the maximum nesting depth of control-flow statements."""
    max_depth = current
    nesting_types = (
        ast.If, ast.For, ast.AsyncFor, ast.While,
        ast.With, ast.AsyncWith, ast.Try, ast.ExceptHandler,
    )
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_types):
            child_depth = _max_nesting(child, current + 1)
            max_depth = max(max_depth, child_depth)
        else:
            child_depth = _max_nesting(child, current)
            max_depth = max(max_depth, child_depth)
    return max_depth


def _function_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Return the number of lines a function spans (inclusive)."""
    return node.end_lineno - node.lineno + 1 if node.end_lineno else 0


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count parameters excluding ``self`` and ``cls``."""
    args = node.args
    all_args = args.posonlyargs + args.args + args.kwonlyargs
    count = len(all_args)
    if args.vararg:
        count += 1
    if args.kwarg:
        count += 1
    # Subtract self/cls
    if all_args and all_args[0].arg in ("self", "cls"):
        count -= 1
    return count


# ── File-level analysis ───────────────────────────────────────────────


def _analyze_file(
    file_path: Path,
    rel_path: str,
    source: str,
) -> list[TechDebtFinding]:
    """Analyze a single Python file and return findings."""
    findings: list[TechDebtFinding] = []
    lines = source.splitlines()
    total_lines = len(lines)

    # Parse AST
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return findings  # skip unparseable files silently

    # ── File-level: large file ────────────────────────────────────
    if total_lines >= FILE_LINE_THRESHOLD:
        sev = _severity(total_lines, FILE_LINE_THRESHOLD, FILE_LINE_CRITICAL)
        findings.append(
            TechDebtFinding(
                id=f"td-large-file-{rel_path}",
                analyzer=ANALYZER,
                severity=sev,  # type: ignore[arg-type]
                category="large-file",  # type: ignore[arg-type]
                title=f"Large file: {total_lines} lines",
                detail=(
                    f"{rel_path} has {total_lines} lines "
                    f"(threshold: {FILE_LINE_THRESHOLD}). "
                    "Consider splitting into focused modules."
                ),
                file_path=rel_path,
                line=1,
                metric_name="file_lines",
                metric_value=total_lines,
                threshold=FILE_LINE_THRESHOLD,
                smell="Large Class / God File",
                recommendation="Extract cohesive groups of functions into separate modules.",
            ),
        )

    # ── File-level: too many definitions ──────────────────────────
    top_level_defs = sum(
        1
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    if top_level_defs >= DEFINITIONS_THRESHOLD:
        sev = _severity(top_level_defs, DEFINITIONS_THRESHOLD, DEFINITIONS_CRITICAL)
        findings.append(
            TechDebtFinding(
                id=f"td-many-defs-{rel_path}",
                analyzer=ANALYZER,
                severity=sev,  # type: ignore[arg-type]
                category="large-file",  # type: ignore[arg-type]
                title=f"Too many top-level definitions: {top_level_defs}",
                detail=(
                    f"{rel_path} has {top_level_defs} top-level classes/functions "
                    f"(threshold: {DEFINITIONS_THRESHOLD}). "
                    "This suggests the module has too many responsibilities."
                ),
                file_path=rel_path,
                line=1,
                metric_name="top_level_definitions",
                metric_value=top_level_defs,
                threshold=DEFINITIONS_THRESHOLD,
                smell="Large Class",
                recommendation=(
                    "Group related definitions and extract them into "
                    "focused modules (Single Responsibility Principle)."
                ),
            ),
        )

    # ── Function-level analysis ───────────────────────────────────
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name
        func_lines = _function_line_count(node)
        complexity = _count_complexity(node)
        nesting = _max_nesting(node)
        params = _param_count(node)

        # Long Method
        if func_lines >= FUNCTION_LINE_THRESHOLD:
            sev = _severity(func_lines, FUNCTION_LINE_THRESHOLD, FUNCTION_LINE_CRITICAL)
            findings.append(
                TechDebtFinding(
                    id=f"td-long-method-{rel_path}:{node.lineno}-{func_name}",
                    analyzer=ANALYZER,
                    severity=sev,  # type: ignore[arg-type]
                    category="long-method",  # type: ignore[arg-type]
                    title=f"Long method: {func_name}() is {func_lines} lines",
                    detail=(
                        f"Function '{func_name}' in {rel_path} spans {func_lines} lines "
                        f"(threshold: {FUNCTION_LINE_THRESHOLD}). "
                        "Long methods are harder to understand, test, and maintain."
                    ),
                    file_path=rel_path,
                    line=node.lineno,
                    end_line=node.end_lineno,
                    metric_name="function_lines",
                    metric_value=func_lines,
                    threshold=FUNCTION_LINE_THRESHOLD,
                    smell="Long Method",
                    recommendation="Extract Method: break into smaller, well-named functions.",
                ),
            )

        # Complex Function
        if complexity >= COMPLEXITY_THRESHOLD:
            sev = _severity(complexity, COMPLEXITY_THRESHOLD, COMPLEXITY_CRITICAL)
            findings.append(
                TechDebtFinding(
                    id=f"td-complex-{rel_path}:{node.lineno}-{func_name}",
                    analyzer=ANALYZER,
                    severity=sev,  # type: ignore[arg-type]
                    category="complex-function",  # type: ignore[arg-type]
                    title=f"Complex function: {func_name}() has complexity {complexity}",
                    detail=(
                        f"Function '{func_name}' in {rel_path} has McCabe complexity "
                        f"{complexity} (threshold: {COMPLEXITY_THRESHOLD}). "
                        "High complexity correlates with bugs and makes testing harder."
                    ),
                    file_path=rel_path,
                    line=node.lineno,
                    end_line=node.end_lineno,
                    metric_name="cyclomatic_complexity",
                    metric_value=complexity,
                    threshold=COMPLEXITY_THRESHOLD,
                    smell="Complex Function",
                    recommendation=(
                        "Replace Conditional with Polymorphism, "
                        "or Extract Method to isolate branches."
                    ),
                ),
            )

        # Deep Nesting
        if nesting >= NESTING_THRESHOLD:
            sev = _severity(nesting, NESTING_THRESHOLD, NESTING_CRITICAL)
            findings.append(
                TechDebtFinding(
                    id=f"td-deep-nesting-{rel_path}:{node.lineno}-{func_name}",
                    analyzer=ANALYZER,
                    severity=sev,  # type: ignore[arg-type]
                    category="deep-nesting",  # type: ignore[arg-type]
                    title=f"Deep nesting: {func_name}() has nesting depth {nesting}",
                    detail=(
                        f"Function '{func_name}' in {rel_path} has control-flow nesting "
                        f"depth {nesting} (threshold: {NESTING_THRESHOLD}). "
                        "Deep nesting hurts readability and increases cognitive load."
                    ),
                    file_path=rel_path,
                    line=node.lineno,
                    end_line=node.end_lineno,
                    metric_name="nesting_depth",
                    metric_value=nesting,
                    threshold=NESTING_THRESHOLD,
                    smell="Deep Nesting",
                    recommendation=(
                        "Use guard clauses (early returns), "
                        "Extract Method, or Decompose Conditional."
                    ),
                ),
            )

        # Long Parameter List
        if params >= PARAM_THRESHOLD:
            sev = _severity(params, PARAM_THRESHOLD, PARAM_CRITICAL)
            findings.append(
                TechDebtFinding(
                    id=f"td-params-{rel_path}:{node.lineno}-{func_name}",
                    analyzer=ANALYZER,
                    severity=sev,  # type: ignore[arg-type]
                    category="parameter-excess",  # type: ignore[arg-type]
                    title=f"Too many parameters: {func_name}() takes {params} params",
                    detail=(
                        f"Function '{func_name}' in {rel_path} accepts {params} parameters "
                        f"(threshold: {PARAM_THRESHOLD}). "
                        "Long parameter lists make calling code harder to read."
                    ),
                    file_path=rel_path,
                    line=node.lineno,
                    metric_name="parameter_count",
                    metric_value=params,
                    threshold=PARAM_THRESHOLD,
                    smell="Long Parameter List",
                    recommendation=(
                        "Introduce Parameter Object or use a dataclass/TypedDict."
                    ),
                ),
            )

    return findings


# ── Public API ────────────────────────────────────────────────────────


def _should_skip(path: Path) -> bool:
    """Return True if any path component is in the skip set."""
    return bool(SKIP_DIRS.intersection(path.parts))


def analyze(project_dir: str) -> AnalyzerResult:
    """Scan all Python files for complexity-related tech debt.

    Parameters
    ----------
    project_dir:
        Absolute or relative path to the project root.

    Returns
    -------
    AnalyzerResult
        ``status`` is ``"ok"`` on success (even if findings exist),
        or ``"error"`` on unexpected failures.
    """
    start = time.monotonic()
    root = Path(project_dir).resolve()
    findings: list[TechDebtFinding] = []

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

            findings.extend(_analyze_file(py_file, str(rel), source))
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return AnalyzerResult(
            analyzer=ANALYZER,
            status="error",
            duration_ms=elapsed,
            messages=[f"Unexpected error: {exc}"],
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return AnalyzerResult(
        analyzer=ANALYZER,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
    )
