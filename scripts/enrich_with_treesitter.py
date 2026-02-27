#!/usr/bin/env python3
"""Tree-sitter enrichment pass for architecture analysis.

Runs after existing Layer 1 analyzers to extract comments, patterns, and
security signals that ast/ts-morph cannot provide. Reads source files
and architecture.graph.json, produces treesitter_enrichment.json.

Usage:
    python scripts/enrich_with_treesitter.py \
        --python-src agent-coordinator/src \
        --ts-src web \
        --graph docs/architecture-analysis/architecture.graph.json \
        --queries scripts/treesitter_queries \
        --output docs/architecture-analysis/treesitter_enrichment.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("enrich_with_treesitter")

# ---------------------------------------------------------------------------
# Tree-sitter imports (graceful fallback)
# ---------------------------------------------------------------------------

try:
    from tree_sitter import Language, Node, Parser, Query, QueryCursor

    import tree_sitter_python
    import tree_sitter_typescript

    PY_LANGUAGE = Language(tree_sitter_python.language())
    TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
    TREESITTER_AVAILABLE = True
except ImportError:
    TREESITTER_AVAILABLE = False
    PY_LANGUAGE = None  # type: ignore[assignment]
    TS_LANGUAGE = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Comment classification
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(
    r"\b(TODO|FIXME|HACK|XXX|NOTE|WARN(?:ING)?|BUG|DEPRECATED)\b", re.IGNORECASE
)

_COMMENT_TYPES = {
    "py_line": "inline",      # Python # comments
    "py_docstring": "doc",    # Python """ docstrings
    "ts_line": "inline",      # TypeScript // comments
    "ts_block": "block",      # TypeScript /* */ comments
}


def classify_comment(text: str) -> dict[str, Any]:
    """Classify a comment by type and extract markers."""
    markers = _MARKER_RE.findall(text)
    return {
        "markers": [m.upper() for m in markers],
        "has_markers": bool(markers),
    }


# ---------------------------------------------------------------------------
# Graph node association
# ---------------------------------------------------------------------------


def _build_file_node_map(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build a mapping from file path to graph nodes in that file."""
    file_map: dict[str, list[dict[str, Any]]] = {}
    for node in graph.get("nodes", []):
        file_path = node.get("file", "")
        if file_path:
            file_map.setdefault(file_path, []).append(node)
    return file_map


def find_enclosing_node(
    line: int,
    file_nodes: list[dict[str, Any]],
) -> str | None:
    """Find the graph node that encloses a given line number."""
    best_node_id = None
    best_span_size = float("inf")

    for node in file_nodes:
        span = node.get("span", {})
        start = span.get("start", 0)
        end = span.get("end", 0)
        if start <= line <= end:
            span_size = end - start
            if span_size < best_span_size:
                best_span_size = span_size
                best_node_id = node["id"]

    return best_node_id


# ---------------------------------------------------------------------------
# Query loading
# ---------------------------------------------------------------------------


def load_query(language: Any, query_path: Path) -> Any | None:
    """Load a tree-sitter query from a .scm file. Returns None on failure."""
    if not query_path.exists():
        logger.debug("Query file not found: %s", query_path)
        return None
    try:
        query_text = query_path.read_text()
        return Query(language, query_text)
    except Exception as e:
        logger.warning("Failed to load query %s: %s", query_path, e)
        return None


# ---------------------------------------------------------------------------
# Enrichment engine
# ---------------------------------------------------------------------------


class TreeSitterEnricher:
    """Runs tree-sitter enrichment over Python and TypeScript source files."""

    def __init__(
        self,
        queries_dir: Path,
        graph: dict[str, Any] | None = None,
    ) -> None:
        if not TREESITTER_AVAILABLE:
            raise RuntimeError("tree-sitter is not installed")

        self.py_parser = Parser(PY_LANGUAGE)
        self.ts_parser = Parser(TS_LANGUAGE)
        self.queries_dir = queries_dir
        self.graph = graph or {}
        self.file_node_map = _build_file_node_map(self.graph) if graph else {}

        # Load queries
        self.py_query = load_query(PY_LANGUAGE, queries_dir / "python.scm")
        self.ts_query = load_query(TS_LANGUAGE, queries_dir / "typescript.scm")
        self.security_py_query = load_query(PY_LANGUAGE, queries_dir / "security.scm")

        # Results
        self.comments: list[dict[str, Any]] = []
        self.python_patterns: dict[str, list[dict[str, Any]]] = {
            "bare_except": [],
            "broad_except": [],
            "context_managers": [],
            "type_hints": [],
            "assertions": [],
        }
        self.typescript_patterns: dict[str, list[dict[str, Any]]] = {
            "empty_catch": [],
            "catch_clauses": [],
            "dynamic_imports": [],
        }
        self.security_patterns: list[dict[str, Any]] = []

    def enrich_python(self, src_dir: Path) -> None:
        """Run enrichment over all Python files in src_dir."""
        if not src_dir.is_dir():
            logger.warning("Python source dir not found: %s", src_dir)
            return

        for py_file in sorted(src_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            self._process_python_file(py_file, src_dir)

    def enrich_typescript(self, src_dir: Path) -> None:
        """Run enrichment over all TypeScript files in src_dir."""
        if not src_dir.is_dir():
            logger.warning("TypeScript source dir not found: %s", src_dir)
            return

        for ts_file in sorted(src_dir.rglob("*.ts")):
            if "node_modules" in str(ts_file):
                continue
            self._process_typescript_file(ts_file, src_dir)

        for tsx_file in sorted(src_dir.rglob("*.tsx")):
            if "node_modules" in str(tsx_file):
                continue
            self._process_typescript_file(tsx_file, src_dir)

    def _process_python_file(self, path: Path, src_root: Path) -> None:
        """Process a single Python file."""
        try:
            source = path.read_bytes()
        except OSError:
            return

        tree = self.py_parser.parse(source)
        rel_path = str(path.relative_to(src_root))
        file_nodes = self.file_node_map.get(rel_path, [])

        # Extract comments
        self._extract_comments(tree.root_node, rel_path, file_nodes, "python")

        # Run pattern queries
        if self.py_query:
            self._run_python_patterns(tree, rel_path, file_nodes, source)

        # Run security queries
        if self.security_py_query:
            self._run_security_patterns(tree, rel_path, file_nodes, source)

    def _process_typescript_file(self, path: Path, src_root: Path) -> None:
        """Process a single TypeScript file."""
        try:
            source = path.read_bytes()
        except OSError:
            return

        tree = self.ts_parser.parse(source)
        rel_path = str(path.relative_to(src_root))
        file_nodes = self.file_node_map.get(rel_path, [])

        # Extract comments
        self._extract_comments(tree.root_node, rel_path, file_nodes, "typescript")

        # Run pattern queries
        if self.ts_query:
            self._run_typescript_patterns(tree, rel_path, file_nodes, source)

    def _extract_comments(
        self,
        root: Node,
        rel_path: str,
        file_nodes: list[dict[str, Any]],
        language: str,
    ) -> None:
        """Extract and classify all comments from a syntax tree."""
        for node in self._walk_tree(root):
            if node.type == "comment":
                text = node.text.decode("utf8") if node.text else ""
                line = node.start_point[0] + 1
                classification = classify_comment(text)
                enclosing = find_enclosing_node(line, file_nodes)

                # Determine comment type
                if language == "python":
                    comment_type = "inline"
                elif text.startswith("//"):
                    comment_type = "inline"
                elif text.startswith("/*"):
                    comment_type = "block"
                else:
                    comment_type = "inline"

                self.comments.append({
                    "file": rel_path,
                    "line": line,
                    "text": text.strip(),
                    "language": language,
                    "type": comment_type,
                    "markers": classification["markers"],
                    "enclosing_node": enclosing,
                })

    def _run_python_patterns(
        self,
        tree: Any,
        rel_path: str,
        file_nodes: list[dict[str, Any]],
        source: bytes,
    ) -> None:
        """Run Python pattern queries and collect results."""
        cursor = QueryCursor(self.py_query)
        captures = cursor.captures(tree.root_node)

        # Process all except clauses
        _EXCEPT_TYPE_NODES = {"identifier", "attribute", "tuple", "as_pattern"}
        for node in captures.get("except.any", []):
            line = node.start_point[0] + 1
            # Check if it has any exception type child
            has_type = any(c.type in _EXCEPT_TYPE_NODES for c in node.children)
            if not has_type:
                # Bare except (no exception type)
                self.python_patterns["bare_except"].append({
                    "file": rel_path,
                    "line": line,
                    "enclosing_node": find_enclosing_node(line, file_nodes),
                })

        # Broad except (catches Exception) — manually filter
        for node in captures.get("except.broad_type", []):
            text = node.text.decode("utf8") if node.text else ""
            if text == "Exception":
                line = node.start_point[0] + 1
                self.python_patterns["broad_except"].append({
                    "file": rel_path,
                    "line": line,
                    "enclosing_node": find_enclosing_node(line, file_nodes),
                })

        # Context managers
        for node in captures.get("context_manager.usage", []):
            line = node.start_point[0] + 1
            self.python_patterns["context_managers"].append({
                "file": rel_path,
                "line": line,
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

        # Type hints
        for node in captures.get("type_hint.function_name", []):
            line = node.start_point[0] + 1
            func_name = node.text.decode("utf8") if node.text else ""
            self.python_patterns["type_hints"].append({
                "file": rel_path,
                "line": line,
                "function": func_name,
                "kind": "return_type",
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

        for node in captures.get("type_hint.param_name", []):
            line = node.start_point[0] + 1
            param_name = node.text.decode("utf8") if node.text else ""
            self.python_patterns["type_hints"].append({
                "file": rel_path,
                "line": line,
                "parameter": param_name,
                "kind": "param_type",
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

        # Assertions
        for node in captures.get("assertion.usage", []):
            line = node.start_point[0] + 1
            self.python_patterns["assertions"].append({
                "file": rel_path,
                "line": line,
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

    def _run_typescript_patterns(
        self,
        tree: Any,
        rel_path: str,
        file_nodes: list[dict[str, Any]],
        source: bytes,
    ) -> None:
        """Run TypeScript pattern queries and collect results."""
        cursor = QueryCursor(self.ts_query)
        captures = cursor.captures(tree.root_node)

        # All catch clauses
        for node in captures.get("catch.any", []):
            line = node.start_point[0] + 1
            # Check if catch body is empty (only whitespace/comments)
            body = node.child_by_field_name("body")
            is_empty = True
            if body:
                for child in body.children:
                    if child.type not in ("{", "}", "comment"):
                        is_empty = False
                        break

            entry = {
                "file": rel_path,
                "line": line,
                "is_empty": is_empty,
                "enclosing_node": find_enclosing_node(line, file_nodes),
            }
            self.typescript_patterns["catch_clauses"].append(entry)
            if is_empty:
                self.typescript_patterns["empty_catch"].append(entry)

        # Dynamic imports
        for node in captures.get("import.dynamic", []):
            line = node.start_point[0] + 1
            self.typescript_patterns["dynamic_imports"].append({
                "file": rel_path,
                "line": line,
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

    _EVAL_EXEC_NAMES = {"eval", "exec"}
    _SECRET_VAR_RE = re.compile(
        r"(?i)(secret|password|token|api_key|apikey|private_key)"
    )

    def _run_security_patterns(
        self,
        tree: Any,
        rel_path: str,
        file_nodes: list[dict[str, Any]],
        source: bytes,
    ) -> None:
        """Run security pattern queries and collect findings.

        Note: tree-sitter Python bindings do NOT automatically apply
        predicate filters (#match?, #eq?) in captures(), so we filter manually.
        """
        cursor = QueryCursor(self.security_py_query)
        captures = cursor.captures(tree.root_node)

        # eval/exec usage — filter manually since #match? not applied
        for node in captures.get("security.eval_exec", []):
            text = node.text.decode("utf8") if node.text else ""
            if text not in self._EVAL_EXEC_NAMES:
                continue
            line = node.start_point[0] + 1
            self.security_patterns.append({
                "file": rel_path,
                "line": line,
                "category": "eval_exec",
                "severity": "high",
                "detail": f"{text}() usage detected",
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

        # Hardcoded secrets — filter manually since #match? not applied
        for node in captures.get("security.secret_var_name", []):
            var_name = node.text.decode("utf8") if node.text else ""
            if not self._SECRET_VAR_RE.search(var_name):
                continue
            line = node.start_point[0] + 1
            self.security_patterns.append({
                "file": rel_path,
                "line": line,
                "category": "hardcoded_secret",
                "severity": "medium",
                "detail": f"Potential hardcoded secret in '{var_name}'",
                "enclosing_node": find_enclosing_node(line, file_nodes),
            })

        # Also check for SQL string concatenation using manual tree walking
        self._check_sql_string_patterns(tree.root_node, rel_path, file_nodes, source)

    def _check_sql_string_patterns(
        self,
        root: Node,
        rel_path: str,
        file_nodes: list[dict[str, Any]],
        source: bytes,
    ) -> None:
        """Check for SQL injection patterns via string operations."""
        sql_keywords = {b"SELECT", b"INSERT", b"UPDATE", b"DELETE", b"DROP", b"ALTER"}

        for node in self._walk_tree(root):
            if node.type == "binary_operator":
                # Check for string concatenation with SQL keywords
                text = node.text if node.text else b""
                if node.children and any(c.type == "+" for c in node.children):
                    for kw in sql_keywords:
                        if kw in text.upper():
                            line = node.start_point[0] + 1
                            self.security_patterns.append({
                                "file": rel_path,
                                "line": line,
                                "category": "sql_concatenation",
                                "severity": "high",
                                "detail": "SQL built via string concatenation",
                                "enclosing_node": find_enclosing_node(
                                    line, file_nodes
                                ),
                            })
                            break

    @staticmethod
    def _walk_tree(node: Node) -> list[Node]:
        """Depth-first walk of all nodes in the tree."""
        nodes = []
        cursor = node.walk()
        visited = False
        while True:
            if not visited:
                nodes.append(cursor.node)
                if not cursor.goto_first_child():
                    visited = True
            elif cursor.goto_next_sibling():
                visited = False
            elif not cursor.goto_parent():
                break
        return nodes

    def build_output(self) -> dict[str, Any]:
        """Build the final enrichment JSON."""
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "treesitter_version": _get_treesitter_version(),
            "comments": {
                "total": len(self.comments),
                "with_markers": sum(1 for c in self.comments if c["markers"]),
                "items": self.comments,
            },
            "python_patterns": {
                category: {
                    "count": len(items),
                    "items": items,
                }
                for category, items in self.python_patterns.items()
            },
            "typescript_patterns": {
                category: {
                    "count": len(items),
                    "items": items,
                }
                for category, items in self.typescript_patterns.items()
            },
            "security_patterns": {
                "total": len(self.security_patterns),
                "by_severity": _group_by_severity(self.security_patterns),
                "items": self.security_patterns,
            },
        }


def _get_treesitter_version() -> str:
    """Get tree-sitter version string."""
    try:
        import tree_sitter
        return getattr(tree_sitter, "__version__", "unknown")
    except ImportError:
        return "unavailable"


def _group_by_severity(patterns: list[dict[str, Any]]) -> dict[str, int]:
    """Group security patterns by severity."""
    counts: dict[str, int] = {}
    for p in patterns:
        sev = p.get("severity", "unknown")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tree-sitter enrichment pass for architecture analysis.",
    )
    parser.add_argument(
        "--python-src",
        type=Path,
        default=None,
        help="Python source directory to enrich",
    )
    parser.add_argument(
        "--ts-src",
        type=Path,
        default=None,
        help="TypeScript source directory to enrich",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Path to architecture.graph.json for node association",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("scripts/treesitter_queries"),
        help="Directory containing .scm query files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/treesitter_enrichment.json"),
        help="Output path for enrichment JSON",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    if not TREESITTER_AVAILABLE:
        logger.error(
            "tree-sitter is not installed. "
            "Run 'cd scripts && uv sync' to install dependencies."
        )
        return 1

    # Load graph if available
    graph = None
    if args.graph and args.graph.exists():
        with open(args.graph) as f:
            graph = json.load(f)

    enricher = TreeSitterEnricher(queries_dir=args.queries, graph=graph)

    if args.python_src:
        enricher.enrich_python(args.python_src)
    if args.ts_src:
        enricher.enrich_typescript(args.ts_src)

    output = enricher.build_output()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    # Summary
    logger.info(
        "Enrichment complete: %d comments (%d with markers), "
        "%d Python patterns, %d TypeScript patterns, %d security findings",
        output["comments"]["total"],
        output["comments"]["with_markers"],
        sum(v["count"] for v in output["python_patterns"].values()),
        sum(v["count"] for v in output["typescript_patterns"].values()),
        output["security_patterns"]["total"],
    )
    logger.info("Wrote %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
