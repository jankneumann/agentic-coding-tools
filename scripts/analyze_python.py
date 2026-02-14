#!/usr/bin/env python3
"""Python AST-based analyzer for extracting call graphs, metadata, and patterns.

Analyzes a Python codebase to extract:
- Function and class metadata (signatures, decorators, docstrings, async markers)
- Call graphs with reverse (called_by) relationships
- Import graphs between modules
- Entry points detected via decorator patterns (FastAPI, Flask, CLI, event handlers)
- Database access patterns (ORM, raw SQL, query builders)
- Summary statistics including dead code candidates and hot functions

Usage:
    python scripts/analyze_python.py <directory> [options]

Examples:
    python scripts/analyze_python.py src/
    python scripts/analyze_python.py . --include "*.py" --exclude "test_*"
    python scripts/analyze_python.py . --output .architecture/python_analysis.json
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ModuleInfo:
    name: str
    file: str
    imports: list[str] = field(default_factory=list)


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    file: str
    line_start: int
    line_end: int
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    db_tables: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    docstring: str | None = None


@dataclass
class ClassInfo:
    name: str
    qualified_name: str
    file: str
    line_start: int
    line_end: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class EntryPoint:
    function: str
    kind: str  # "route" | "cli" | "event_handler"
    method: str | None = None  # "GET", "POST", etc.
    path: str | None = None  # "/api/..."


@dataclass
class DbAccess:
    function: str
    tables: list[str] = field(default_factory=list)
    pattern: str = "orm"  # "orm" | "raw_sql" | "query_builder"


@dataclass
class ImportEdge:
    from_module: str
    to_module: str


# ---------------------------------------------------------------------------
# AST helper utilities
# ---------------------------------------------------------------------------

def decorator_to_string(node: ast.expr) -> str:
    """Convert a decorator AST node to its string representation."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{decorator_to_string(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        func_str = decorator_to_string(node.func)
        args_parts: list[str] = []
        for arg in node.args:
            args_parts.append(_expr_to_string(arg))
        for kw in node.keywords:
            if kw.arg:
                args_parts.append(f"{kw.arg}={_expr_to_string(kw.value)}")
            else:
                args_parts.append(f"**{_expr_to_string(kw.value)}")
        return f"{func_str}({', '.join(args_parts)})"
    if isinstance(node, ast.Subscript):
        return f"{decorator_to_string(node.value)}[{_expr_to_string(node.slice)}]"
    return ast.dump(node)


def _expr_to_string(node: ast.expr) -> str:
    """Best-effort conversion of an AST expression to a readable string."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_expr_to_string(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        func_str = _expr_to_string(node.func)
        args = [_expr_to_string(a) for a in node.args]
        kwargs = []
        for kw in node.keywords:
            if kw.arg:
                kwargs.append(f"{kw.arg}={_expr_to_string(kw.value)}")
            else:
                kwargs.append(f"**{_expr_to_string(kw.value)}")
        all_args = ", ".join(args + kwargs)
        return f"{func_str}({all_args})"
    if isinstance(node, ast.Starred):
        return f"*{_expr_to_string(node.value)}"
    if isinstance(node, ast.JoinedStr):
        return "f'...'"
    if isinstance(node, ast.List):
        elts = ", ".join(_expr_to_string(e) for e in node.elts)
        return f"[{elts}]"
    if isinstance(node, ast.Tuple):
        elts = ", ".join(_expr_to_string(e) for e in node.elts)
        return f"({elts})"
    if isinstance(node, ast.Dict):
        pairs = []
        for k, v in zip(node.keys, node.values):
            if k is not None:
                pairs.append(f"{_expr_to_string(k)}: {_expr_to_string(v)}")
            else:
                pairs.append(f"**{_expr_to_string(v)}")
        return "{" + ", ".join(pairs) + "}"
    if isinstance(node, ast.Subscript):
        return f"{_expr_to_string(node.value)}[{_expr_to_string(node.slice)}]"
    if isinstance(node, ast.BinOp):
        return f"{_expr_to_string(node.left)} {_op_symbol(node.op)} {_expr_to_string(node.right)}"
    if isinstance(node, ast.UnaryOp):
        return f"{_unary_op_symbol(node.op)}{_expr_to_string(node.operand)}"
    return "..."


def _op_symbol(op: ast.operator) -> str:
    symbols = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
        ast.Mod: "%", ast.Pow: "**", ast.BitOr: "|", ast.BitAnd: "&",
        ast.BitXor: "^", ast.FloorDiv: "//", ast.LShift: "<<", ast.RShift: ">>",
        ast.MatMult: "@",
    }
    return symbols.get(type(op), "?")


def _unary_op_symbol(op: ast.unaryop) -> str:
    symbols = {ast.UAdd: "+", ast.USub: "-", ast.Not: "not ", ast.Invert: "~"}
    return symbols.get(type(op), "?")


def _get_call_name(node: ast.Call) -> str | None:
    """Extract the full dotted call name from a Call node."""
    return _resolve_callable(node.func)


def _resolve_callable(node: ast.expr) -> str | None:
    """Resolve a callable expression to a dotted name string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _resolve_callable(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Call):
        # Chained calls like foo()()
        return _resolve_callable(node.func)
    if isinstance(node, ast.Subscript):
        return _resolve_callable(node.value)
    return None


# ---------------------------------------------------------------------------
# Entry-point detection
# ---------------------------------------------------------------------------

# Route decorator patterns: (object_attr_method, http_method)
_ROUTE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # FastAPI / APIRouter: router.get("/path"), app.post("/path"), etc.
    (re.compile(r"^(?:\w+)\.(get|post|put|patch|delete|head|options|trace)\("), None),  # type: ignore[arg-type]
    # Flask: @app.route("/path", methods=["GET"])
    (re.compile(r"^(?:\w+)\.route\("), None),  # type: ignore[arg-type]
    # Django/other: @api_view(["GET"])
    (re.compile(r"^api_view\("), None),  # type: ignore[arg-type]
]

_CLI_DECORATOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:\w+)\.command\("),
    re.compile(r"^click\.command"),
    re.compile(r"^(?:\w+)\.group\("),
    re.compile(r"^app\.command\("),
]

_EVENT_HANDLER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:\w+)\.(on_event|on_message|on_startup|on_shutdown|listener|event)\("),
    re.compile(r"^(?:\w+)\.on\("),
    re.compile(r"^receiver\("),
]

# MCP (Model Context Protocol) decorator patterns
_MCP_TOOL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:\w+)\.tool\("),      # @mcp.tool() or @server.tool()
]

_MCP_RESOURCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:\w+)\.resource\("),   # @mcp.resource('uri')
]

_MCP_PROMPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(?:\w+)\.prompt\("),     # @mcp.prompt()
]


def _detect_entry_point(
    qualified_name: str, decorators: list[str],
) -> EntryPoint | None:
    """Detect if a function is an entry point based on its decorators."""
    for dec_str in decorators:
        # Route decorators
        for pattern, _ in _ROUTE_PATTERNS:
            m = pattern.match(dec_str)
            if m:
                http_method = _extract_http_method(dec_str, m)
                path = _extract_route_path(dec_str)
                return EntryPoint(
                    function=qualified_name,
                    kind="route",
                    method=http_method,
                    path=path,
                )

        # CLI decorators
        for pattern in _CLI_DECORATOR_PATTERNS:
            if pattern.match(dec_str):
                return EntryPoint(
                    function=qualified_name,
                    kind="cli",
                )

        # Event handler decorators
        for pattern in _EVENT_HANDLER_PATTERNS:
            if pattern.match(dec_str):
                return EntryPoint(
                    function=qualified_name,
                    kind="event_handler",
                )

        # MCP tool decorators: @mcp.tool(), @server.tool()
        for pattern in _MCP_TOOL_PATTERNS:
            if pattern.match(dec_str):
                return EntryPoint(
                    function=qualified_name,
                    kind="route",
                    method="MCP",
                    path=_extract_mcp_name(dec_str, qualified_name),
                )

        # MCP resource decorators: @mcp.resource('uri')
        for pattern in _MCP_RESOURCE_PATTERNS:
            if pattern.match(dec_str):
                return EntryPoint(
                    function=qualified_name,
                    kind="route",
                    method="MCP",
                    path=_extract_mcp_name(dec_str, qualified_name),
                )

        # MCP prompt decorators: @mcp.prompt()
        for pattern in _MCP_PROMPT_PATTERNS:
            if pattern.match(dec_str):
                return EntryPoint(
                    function=qualified_name,
                    kind="route",
                    method="MCP",
                    path=_extract_mcp_name(dec_str, qualified_name),
                )

    return None


def _extract_mcp_name(dec_str: str, qualified_name: str) -> str:
    """Extract the MCP tool/resource/prompt name from a decorator string.

    Examples:
        mcp.tool()                   -> function name from qualified_name
        mcp.resource('locks://current') -> 'locks://current'
    """
    # Look for a string argument: mcp.resource('uri') or mcp.tool('name')
    m = re.search(r"""['"](.*?)['"]""", dec_str)
    if m:
        return m.group(1)
    # No explicit name — use the function name
    return qualified_name.rsplit(".", 1)[-1] if "." in qualified_name else qualified_name


def _extract_http_method(dec_str: str, match: re.Match[str]) -> str | None:
    """Extract the HTTP method from a route decorator string."""
    # Direct method decorators: router.get(...), app.post(...)
    parts = dec_str.split("(", 1)[0].rsplit(".", 1)
    if len(parts) == 2:
        method_name = parts[1].upper()
        if method_name in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}:
            return method_name
    # .route() with methods= keyword
    if ".route(" in dec_str:
        methods_match = re.search(r"methods\s*=\s*\[([^\]]*)\]", dec_str)
        if methods_match:
            methods_str = methods_match.group(1)
            methods = re.findall(r"['\"](\w+)['\"]", methods_str)
            if methods:
                return methods[0].upper()
    return None


def _extract_route_path(dec_str: str) -> str | None:
    """Extract the route path from a decorator string."""
    # Look for the first string argument
    path_match = re.search(r"""\(\s*['"]([^'"]+)['"]""", dec_str)
    if path_match:
        return path_match.group(1)
    return None


# ---------------------------------------------------------------------------
# Database access detection
# ---------------------------------------------------------------------------

# ORM patterns (SQLAlchemy, Django ORM, Peewee, etc.)
_ORM_ATTRIBUTE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.query\b"),
    re.compile(r"\bdb\.session\b"),
    re.compile(r"\.objects\b"),          # Django ORM
    re.compile(r"\.filter\b"),
    re.compile(r"\.filter_by\b"),
    re.compile(r"\.select\b"),
    re.compile(r"\.insert\b"),
    re.compile(r"\.update\b"),
    re.compile(r"\.delete\b"),
    re.compile(r"\.join\b"),
    re.compile(r"\.all\b"),
    re.compile(r"\.first\b"),
    re.compile(r"\.get\b"),
    re.compile(r"\.create\b"),
    re.compile(r"\.save\b"),
    re.compile(r"\.add\b"),
    re.compile(r"\.commit\b"),
    re.compile(r"\.execute\b"),
    re.compile(r"\.scalar\b"),
    re.compile(r"\.fetchone\b"),
    re.compile(r"\.fetchall\b"),
    re.compile(r"\.fetchmany\b"),
]

# Raw SQL detection via string content
_RAW_SQL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bSELECT\b.*\bFROM\b", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b.*\bSET\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
]

# Table name extraction from SQL strings
_SQL_TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+[`\"']?(\w+)[`\"']?",
    re.IGNORECASE,
)

# Query builder patterns
_QUERY_BUILDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.table\b"),
    re.compile(r"\.where\b"),
    re.compile(r"\.order_by\b"),
    re.compile(r"\.group_by\b"),
    re.compile(r"\.having\b"),
    re.compile(r"\.limit\b"),
    re.compile(r"\.offset\b"),
]


class _DbPatternDetector:
    """Detects database access patterns within function bodies."""

    def __init__(self) -> None:
        self.tables: list[str] = []
        self.pattern: str | None = None

    def check_call_chain(self, call_name: str) -> None:
        """Check a call/attribute chain for ORM or query builder patterns."""
        for pat in _ORM_ATTRIBUTE_PATTERNS:
            if pat.search(call_name):
                if self.pattern is None:
                    self.pattern = "orm"
                # Try to extract a model/table name from the chain
                # e.g., User.query -> "User", Model.objects -> "Model"
                parts = call_name.split(".")
                if len(parts) >= 2:
                    candidate = parts[0]
                    if candidate[0:1].isupper() and candidate not in ("db",):
                        if candidate not in self.tables:
                            self.tables.append(candidate)
                return

        for pat in _QUERY_BUILDER_PATTERNS:
            if pat.search(call_name):
                if self.pattern is None or self.pattern == "orm":
                    self.pattern = "query_builder"
                # Try to extract table name from .table("name") patterns
                # The call_name chain doesn't include args, but we record it
                return

    def check_string(self, value: str) -> None:
        """Check a string literal for raw SQL patterns."""
        for pat in _RAW_SQL_PATTERNS:
            if pat.search(value):
                self.pattern = "raw_sql"
                # Extract table names from SQL
                for m in _SQL_TABLE_PATTERN.finditer(value):
                    table = m.group(1)
                    # Filter out SQL keywords that might be matched
                    if table.upper() not in {
                        "SELECT", "FROM", "WHERE", "SET", "INTO",
                        "VALUES", "AND", "OR", "NOT", "NULL", "TABLE",
                        "INDEX", "VIEW", "AS", "ON", "IN", "IS",
                    }:
                        if table not in self.tables:
                            self.tables.append(table)
                return

    @property
    def has_db_access(self) -> bool:
        return self.pattern is not None


# ---------------------------------------------------------------------------
# Main AST visitors
# ---------------------------------------------------------------------------

class _CallExtractor(ast.NodeVisitor):
    """Extracts function calls and database patterns from a function body."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.db_detector = _DbPatternDetector()

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _get_call_name(node)
        if call_name:
            if call_name not in self.calls:
                self.calls.append(call_name)
            self.db_detector.check_call_chain(call_name)

            # Extract table names from .table("name") style calls
            if call_name.endswith(".table") and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    table_name = first_arg.value
                    if table_name not in self.db_detector.tables:
                        self.db_detector.tables.append(table_name)

        # Also check string arguments for raw SQL
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                self.db_detector.check_string(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                # f-strings: check the constant parts
                for val in arg.values:
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        self.db_detector.check_string(val.value)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Check top-level string constants (e.g., SQL assigned to variables)."""
        if isinstance(node.value, str) and len(node.value) > 10:
            self.db_detector.check_string(node.value)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute chains that aren't part of calls."""
        chain = _resolve_callable(node)
        if chain:
            self.db_detector.check_call_chain(chain)
        self.generic_visit(node)


class ModuleAnalyzer(ast.NodeVisitor):
    """Analyzes a single Python module's AST."""

    def __init__(self, file_path: str, module_name: str, source: str) -> None:
        self.file_path = file_path
        self.module_name = module_name
        self.source = source
        self.functions: list[FunctionInfo] = []
        self.classes: list[ClassInfo] = []
        self.imports: list[str] = []
        self.import_edges: list[ImportEdge] = []
        self.entry_points: list[EntryPoint] = []
        self.db_accesses: list[DbAccess] = []
        self._scope_stack: list[str] = []

    def _qualified_name(self, name: str) -> str:
        """Build a qualified name from the current scope stack."""
        parts = [self.module_name] + self._scope_stack + [name]
        return ".".join(parts)

    def _get_end_lineno(self, node: ast.AST) -> int:
        """Get end line number, falling back to start if unavailable."""
        return getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module_name = alias.name
            self.imports.append(module_name)
            self.import_edges.append(
                ImportEdge(from_module=self.module_name, to_module=module_name)
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.append(node.module)
            self.import_edges.append(
                ImportEdge(from_module=self.module_name, to_module=node.module)
            )
        self.generic_visit(node)

    def _analyze_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> FunctionInfo:
        """Analyze a function or async function definition."""
        name = node.name
        qualified = self._qualified_name(name)
        is_async = isinstance(node, ast.AsyncFunctionDef)

        decorators = [decorator_to_string(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node)

        # Extract calls and DB patterns from the function body
        extractor = _CallExtractor()
        for child in node.body:
            extractor.visit(child)

        tags: list[str] = []
        if is_async:
            tags.append("async")
        if any("staticmethod" in d for d in decorators):
            tags.append("staticmethod")
        if any("classmethod" in d for d in decorators):
            tags.append("classmethod")
        if any("property" in d for d in decorators):
            tags.append("property")
        if name.startswith("_") and not name.startswith("__"):
            tags.append("private")
        if name.startswith("__") and name.endswith("__"):
            tags.append("dunder")

        func_info = FunctionInfo(
            name=name,
            qualified_name=qualified,
            file=self.file_path,
            line_start=node.lineno,
            line_end=self._get_end_lineno(node),
            is_async=is_async,
            decorators=decorators,
            calls=extractor.calls,
            called_by=[],  # populated in post-processing
            db_tables=extractor.db_detector.tables,
            tags=tags,
            docstring=docstring,
        )

        # Detect entry points
        ep = _detect_entry_point(qualified, decorators)
        if ep:
            self.entry_points.append(ep)
            if "entry_point" not in tags:
                func_info.tags.append("entry_point")

        # Record DB access
        if extractor.db_detector.has_db_access:
            self.db_accesses.append(DbAccess(
                function=qualified,
                tables=extractor.db_detector.tables,
                pattern=extractor.db_detector.pattern or "orm",
            ))
            if "db_access" not in tags:
                func_info.tags.append("db_access")

        return func_info

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        func_info = self._analyze_function(node)
        self.functions.append(func_info)

        # Visit nested definitions
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        func_info = self._analyze_function(node)
        self.functions.append(func_info)

        # Visit nested definitions
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        name = node.name
        qualified = self._qualified_name(name)
        bases = [_expr_to_string(b) for b in node.bases]
        decorators = [decorator_to_string(d) for d in node.decorator_list]

        class_info = ClassInfo(
            name=name,
            qualified_name=qualified,
            file=self.file_path,
            line_start=node.lineno,
            line_end=self._get_end_lineno(node),
            bases=bases,
            methods=[],
            decorators=decorators,
        )

        # Visit class body to collect methods
        self._scope_stack.append(name)
        prev_func_count = len(self.functions)
        self.generic_visit(node)
        self._scope_stack.pop()

        # Record methods that were added during class body traversal
        for func_info in self.functions[prev_func_count:]:
            class_info.methods.append(func_info.name)

        self.classes.append(class_info)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_python_files(
    root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Discover Python files under root, respecting include/exclude globs."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip __pycache__ directories
        dirnames[:] = [
            d for d in dirnames
            if d != "__pycache__" and not d.startswith(".")
        ]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            # Check include patterns (if any specified)
            if include_patterns:
                if not any(fnmatch.fnmatch(filename, pat) for pat in include_patterns):
                    continue

            # Check exclude patterns
            if exclude_patterns:
                if any(fnmatch.fnmatch(filename, pat) for pat in exclude_patterns):
                    continue

            filepath = Path(dirpath) / filename
            files.append(filepath)

    return sorted(files)


def file_to_module_name(filepath: Path, root: Path) -> str:
    """Convert a file path to a Python module name relative to root."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        rel = filepath

    parts = list(rel.parts)
    # Remove .py extension from last part
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # Handle __init__.py -> package name
    if parts and parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts) if parts else filepath.stem


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _populate_called_by(functions: list[FunctionInfo]) -> None:
    """Populate called_by reverse relationships across all functions."""
    # Build a lookup from function names (various forms) to qualified names
    name_to_qualified: dict[str, list[str]] = defaultdict(list)
    for func in functions:
        name_to_qualified[func.name].append(func.qualified_name)
        name_to_qualified[func.qualified_name].append(func.qualified_name)
        # Also register the short qualified forms (class.method, module.func)
        parts = func.qualified_name.split(".")
        for i in range(1, len(parts)):
            partial = ".".join(parts[i:])
            name_to_qualified[partial].append(func.qualified_name)

    qualified_to_func: dict[str, FunctionInfo] = {
        f.qualified_name: f for f in functions
    }

    for func in functions:
        for call_name in func.calls:
            # Resolve call_name to possible qualified names
            targets = name_to_qualified.get(call_name, [])
            for target_qname in targets:
                target_func = qualified_to_func.get(target_qname)
                if target_func and func.qualified_name not in target_func.called_by:
                    target_func.called_by.append(func.qualified_name)


def _compute_summary(
    modules: list[ModuleInfo],
    functions: list[FunctionInfo],
    classes: list[ClassInfo],
    entry_points: list[EntryPoint],
) -> dict[str, Any]:
    """Compute summary statistics."""
    async_count = sum(1 for f in functions if f.is_async)

    # Entry point qualified names for dead code exclusion
    entry_point_names = {ep.function for ep in entry_points}

    # Dead code candidates: functions with no callers and not entry points,
    # and not dunder methods, and not private overrides
    dead_code: list[str] = []
    for func in functions:
        if func.called_by:
            continue
        if func.qualified_name in entry_point_names:
            continue
        if "entry_point" in func.tags:
            continue
        # Exclude dunder methods (they're called implicitly)
        if func.name.startswith("__") and func.name.endswith("__"):
            continue
        dead_code.append(func.qualified_name)

    # Hot functions: sorted by number of callers (descending), top 10
    hot = sorted(functions, key=lambda f: len(f.called_by), reverse=True)
    hot_functions = [
        {"name": f.qualified_name, "caller_count": len(f.called_by)}
        for f in hot[:10]
        if f.called_by  # only include functions that are actually called
    ]

    return {
        "total_functions": len(functions),
        "total_classes": len(classes),
        "total_modules": len(modules),
        "async_functions": async_count,
        "entry_points": len(entry_points),
        "dead_code_candidates": dead_code,
        "hot_functions": hot_functions,
    }


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize_output(
    modules: list[ModuleInfo],
    functions: list[FunctionInfo],
    classes: list[ClassInfo],
    import_edges: list[ImportEdge],
    entry_points: list[EntryPoint],
    db_accesses: list[DbAccess],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Serialize analysis results to the output JSON format."""
    return {
        "modules": [
            {"name": m.name, "file": m.file, "imports": m.imports}
            for m in modules
        ],
        "functions": [
            {
                "name": f.name,
                "qualified_name": f.qualified_name,
                "file": f.file,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "is_async": f.is_async,
                "decorators": f.decorators,
                "calls": f.calls,
                "called_by": f.called_by,
                "db_tables": f.db_tables,
                "tags": f.tags,
                "docstring": f.docstring,
            }
            for f in functions
        ],
        "classes": [
            {
                "name": c.name,
                "qualified_name": c.qualified_name,
                "file": c.file,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "bases": c.bases,
                "methods": c.methods,
                "decorators": c.decorators,
            }
            for c in classes
        ],
        "import_graph": [
            {"from": e.from_module, "to": e.to_module}
            for e in import_edges
        ],
        "entry_points": [
            {
                k: v
                for k, v in {
                    "function": ep.function,
                    "kind": ep.kind,
                    "method": ep.method,
                    "path": ep.path,
                }.items()
                if v is not None
            }
            for ep in entry_points
        ],
        "db_access": [
            {
                "function": da.function,
                "tables": da.tables,
                "pattern": da.pattern,
            }
            for da in db_accesses
        ],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def analyze_directory(
    root: Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Run the full analysis pipeline on a directory.

    Args:
        root: Root directory to analyze.
        include_patterns: Glob patterns for files to include (default: all .py).
        exclude_patterns: Glob patterns for files to exclude.

    Returns:
        Analysis results as a dictionary matching the output JSON schema.
    """
    root = root.resolve()
    include = include_patterns or []
    exclude = exclude_patterns or []

    files = discover_python_files(root, include, exclude)

    all_modules: list[ModuleInfo] = []
    all_functions: list[FunctionInfo] = []
    all_classes: list[ClassInfo] = []
    all_import_edges: list[ImportEdge] = []
    all_entry_points: list[EntryPoint] = []
    all_db_accesses: list[DbAccess] = []

    for filepath in files:
        module_name = file_to_module_name(filepath, root)
        rel_path = str(filepath.relative_to(root))

        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            warnings.warn(f"Could not read {filepath}: {exc}", stacklevel=2)
            continue

        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError as exc:
            warnings.warn(
                f"SyntaxError in {filepath} (line {exc.lineno}): {exc.msg}",
                stacklevel=2,
            )
            continue

        analyzer = ModuleAnalyzer(rel_path, module_name, source)
        analyzer.visit(tree)

        module_info = ModuleInfo(
            name=module_name,
            file=rel_path,
            imports=analyzer.imports,
        )
        all_modules.append(module_info)
        all_functions.extend(analyzer.functions)
        all_classes.extend(analyzer.classes)
        all_import_edges.extend(analyzer.import_edges)
        all_entry_points.extend(analyzer.entry_points)
        all_db_accesses.extend(analyzer.db_accesses)

    # Post-processing: populate called_by reverse relationships
    _populate_called_by(all_functions)

    # Deduplicate import edges
    seen_edges: set[tuple[str, str]] = set()
    unique_edges: list[ImportEdge] = []
    for edge in all_import_edges:
        key = (edge.from_module, edge.to_module)
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(edge)

    # Compute summary
    summary = _compute_summary(
        all_modules, all_functions, all_classes, all_entry_points,
    )

    return _serialize_output(
        all_modules, all_functions, all_classes,
        unique_edges, all_entry_points, all_db_accesses,
        summary,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze Python codebase using AST to extract call graphs, "
        "metadata, entry points, import graphs, and database access patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/analyze_python.py src/\n"
            "  python scripts/analyze_python.py . --include '*.py' --exclude 'test_*'\n"
            "  python scripts/analyze_python.py . --output .architecture/python_analysis.json\n"
        ),
    )
    parser.add_argument(
        "directory",
        type=str,
        help="Root directory of the Python codebase to analyze.",
    )
    parser.add_argument(
        "--include",
        type=str,
        action="append",
        default=None,
        help="Glob pattern(s) for files to include (e.g. '*.py'). "
        "Can be specified multiple times.",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        default=None,
        help="Glob pattern(s) for files to exclude (e.g. 'test_*'). "
        "Can be specified multiple times.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=".architecture/python_analysis.json",
        help="Output file path (default: .architecture/python_analysis.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.directory)
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        return 1

    include = args.include or []
    exclude = args.exclude or []

    print(f"Analyzing Python files in: {root.resolve()}")
    if include:
        print(f"  Include patterns: {include}")
    if exclude:
        print(f"  Exclude patterns: {exclude}")

    result = analyze_directory(root, include, exclude)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    summary = result["summary"]
    print(f"\nAnalysis complete. Results written to: {output_path}")
    print(f"  Modules:    {summary['total_modules']}")
    print(f"  Functions:  {summary['total_functions']}")
    print(f"  Classes:    {summary['total_classes']}")
    print(f"  Async:      {summary['async_functions']}")
    print(f"  Entry pts:  {summary['entry_points']}")
    print(f"  Dead code:  {len(summary['dead_code_candidates'])} candidates")
    print(f"  Hot funcs:  {len(summary['hot_functions'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
