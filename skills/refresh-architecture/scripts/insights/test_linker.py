#!/usr/bin/env python3
"""Test linker — discover test nodes and link them to source via TEST_COVERS edges.

Walks configured test directories, parses each test file with the ``ast`` module,
emits test nodes (functions and classes) for every definition whose name begins
with ``test_`` / ``Test``, and creates TEST_COVERS edges from each test node to
the imported source modules/functions present in the architecture graph.

This module is the foundation for ``affected_tests(changed_files)`` — given a
set of changed files, we walk the reverse TEST_COVERS edges to find which tests
exercise the changed code.

Phase 1 only performs **direct-import** linking (confidence=high). Transitive
closure and fixture-aware linking are deferred to a later change (see
contracts/internal/test-linker-output.yaml phase_2/phase_3).

Usage:
    python scripts/insights/test_linker.py \\
        --input-dir docs/architecture-analysis \\
        --output docs/architecture-analysis/architecture.graph.json \\
        --repo-root . \\
        --test-dir tests \\
        --test-dir agent-coordinator/tests
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.constants import EdgeType, NodeKind  # noqa: E402
from arch_utils.graph_io import load_graph, save_json  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Stdlib module names that we should NEVER attempt to link as source modules.
#: Uses Python 3.10+ sys.stdlib_module_names where available, with a fallback
#: static set for earlier runtimes.
_STDLIB_NAMES: frozenset[str] = frozenset(
    getattr(
        sys,
        "stdlib_module_names",
        frozenset(
            {
                "abc", "argparse", "ast", "asyncio", "base64", "collections",
                "concurrent", "contextlib", "copy", "csv", "dataclasses",
                "datetime", "decimal", "enum", "functools", "hashlib", "io",
                "inspect", "itertools", "json", "logging", "math", "multiprocessing",
                "os", "pathlib", "pickle", "queue", "random", "re", "shutil",
                "signal", "socket", "sqlite3", "ssl", "string", "subprocess",
                "sys", "tempfile", "textwrap", "threading", "time", "traceback",
                "typing", "unittest", "urllib", "uuid", "warnings", "weakref",
                "xml", "yaml", "zipfile",
            }
        ),
    )
)

#: Common third-party testing / ORM packages we never treat as source.
_THIRD_PARTY_BLOCKLIST: frozenset[str] = frozenset(
    {
        "pytest", "mock", "unittest.mock", "hypothesis", "numpy", "pandas",
        "yaml", "pyyaml", "aiohttp", "httpx", "requests", "sqlalchemy",
        "pydantic", "fastapi", "starlette", "anyio", "trio",
    }
)


# ---------------------------------------------------------------------------
# TestNode dataclass
# ---------------------------------------------------------------------------


@dataclass
class TestNode:
    """In-memory representation of a discovered test function or class."""

    # Tell pytest not to collect this class even though its name starts with
    # "Test" — it's a data carrier, not a test class. (Must be set outside
    # the dataclass field declarations.)
    __test__ = False

    id: str
    kind: str  # "test_function" | "test_class"
    name: str
    file: str
    span_start: int
    span_end: int
    tags: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_graph_node(self) -> dict[str, Any]:
        """Serialize to the shape used in architecture.graph.json."""
        return {
            "id": self.id,
            "kind": self.kind,
            "language": "python",
            "name": self.name,
            "file": self.file,
            "span": {"start": self.span_start, "end": self.span_end},
            "tags": list(self.tags),
            "signatures": {},
        }


# ---------------------------------------------------------------------------
# Stdlib check
# ---------------------------------------------------------------------------


def is_stdlib_module(module_name: str) -> bool:
    """Return True if *module_name* is a stdlib / built-in / known 3rd-party package.

    Checked on the top-level package only (``os.path`` → ``os``).
    """
    if not module_name:
        return False
    top = module_name.split(".")[0]
    return top in _STDLIB_NAMES or top in _THIRD_PARTY_BLOCKLIST


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_test_files(root: Path) -> list[Path]:
    """Walk *root* recursively and return all Python test file paths.

    Naming conventions recognized:
      - ``test_*.py`` (pytest default)
      - ``*_test.py`` (Google/Go-style suffix)

    Excludes ``__pycache__`` and hidden directories.
    """
    if not root.exists():
        return []
    results: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py"):
            results.append(path)
    return results


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------


def _qualified_name(module_stem: str, *parts: str) -> str:
    """Build a dotted test node identifier rooted at the module stem."""
    return ".".join([module_stem, *parts])


def _module_stem(file_path: Path, repo_root: Path) -> str:
    """Convert a test file path to its dotted module stem.

    >>> _module_stem(Path("tests/test_foo.py"), Path("."))
    'tests.test_foo'
    """
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = Path(file_path.name)
    stem = rel.with_suffix("")
    return ".".join(stem.parts)


def _extract_imports(tree: ast.AST) -> list[str]:
    """Return the fully-qualified names referenced by import statements."""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue  # relative imports without module; skip
            base = node.module
            out.append(base)
            for alias in node.names:
                if alias.name != "*":
                    out.append(f"{base}.{alias.name}")
    return out


def _decorator_names(decorators: list[ast.expr]) -> list[str]:
    """Collapse a decorator list into simple dotted names for matching."""
    out: list[str] = []
    for dec in decorators:
        node = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts: list[str] = []
            cur: ast.expr = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            out.append(".".join(reversed(parts)))
    return out


def _compute_tags(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """Derive tags from a test function's AST node."""
    tags: list[str] = ["test"]
    if isinstance(fn, ast.AsyncFunctionDef):
        tags.append("async")
    decos = _decorator_names(fn.decorator_list)
    if any("parametrize" in d for d in decos):
        tags.append("parametrized")
    # Fixture use — any non-self argument is assumed to be a pytest fixture
    # when the function isn't a method (class-level test uses positional self).
    arg_names = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
    if arg_names:
        tags.append("fixture_using")
    return tags


def extract_test_nodes(file_path: Path, repo_root: Path) -> list[TestNode]:
    """Parse *file_path* and return test nodes contained inside.

    Malformed files (SyntaxError) return an empty list and log a warning —
    a single bad test file should not block the entire pipeline.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        logger.warning("test_linker: failed to parse %s: %s", file_path, exc)
        return []

    imports = _extract_imports(tree)
    module_stem = _module_stem(file_path, repo_root)
    rel_file = str(file_path.resolve().relative_to(repo_root.resolve()))
    nodes: list[TestNode] = []

    def _emit_function(
        fn: ast.FunctionDef | ast.AsyncFunctionDef,
        qname_parts: list[str],
    ) -> None:
        qname = _qualified_name(module_stem, *qname_parts, fn.name)
        nodes.append(
            TestNode(
                id=f"py:test:{qname}",
                kind=NodeKind.TEST_FUNCTION.value,
                name=fn.name,
                file=rel_file,
                span_start=fn.lineno,
                span_end=fn.end_lineno or fn.lineno,
                tags=_compute_tags(fn),
                imports=list(imports),
            )
        )

    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if top.name.startswith("test_"):
                _emit_function(top, [])
        elif isinstance(top, ast.ClassDef):
            if top.name.startswith("Test"):
                qname = _qualified_name(module_stem, top.name)
                nodes.append(
                    TestNode(
                        id=f"py:test:{qname}",
                        kind=NodeKind.TEST_CLASS.value,
                        name=top.name,
                        file=rel_file,
                        span_start=top.lineno,
                        span_end=top.end_lineno or top.lineno,
                        tags=["test"],
                        imports=list(imports),
                    )
                )
                for inner in top.body:
                    if isinstance(
                        inner, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) and inner.name.startswith("test_"):
                        _emit_function(inner, [top.name])

    return nodes


# ---------------------------------------------------------------------------
# TEST_COVERS edge building
# ---------------------------------------------------------------------------


def _strip_src_prefix(name: str) -> str:
    """Normalize module paths by stripping common 'src.' / 'agent-coordinator.src.' prefixes."""
    for prefix in ("agent-coordinator.src.", "src."):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _build_node_id_index(
    nodes: list[dict[str, Any]],
) -> dict[str, str]:
    """Build a lookup from qualified module/function name → graph node id.

    Only python (`py:`) nodes of kind module/function/class are indexed.
    """
    index: dict[str, str] = {}
    for n in nodes:
        if n.get("language") != "python":
            continue
        kind = n.get("kind")
        if kind not in {
            NodeKind.MODULE.value,
            NodeKind.FUNCTION.value,
            NodeKind.CLASS.value,
        }:
            continue
        nid = n["id"]
        if not nid.startswith("py:"):
            continue
        qname = nid[len("py:"):]
        index[qname] = nid
    return index


def build_test_covers_edges(
    test_nodes: list[TestNode],
    source_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create TEST_COVERS edges from test nodes to imported source nodes.

    Direct-import confidence only (phase 1 per contract). Stdlib and unknown
    imports are silently dropped.
    """
    index = _build_node_id_index(source_nodes)
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for test_node in test_nodes:
        for imp in test_node.imports:
            if is_stdlib_module(imp):
                continue
            normalized = _strip_src_prefix(imp)
            # Try exact match first (handles `from feature_flags import resolve_flag`
            # which appears as `feature_flags.resolve_flag`)
            target = index.get(normalized)
            if target is None:
                # Fall back to top-level module name
                target = index.get(normalized.split(".")[0])
            if target is None:
                continue
            key = (test_node.id, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "from": test_node.id,
                    "to": target,
                    "type": EdgeType.TEST_COVERS.value,
                    "confidence": "high",
                    "evidence": "direct_import",
                }
            )

    return edges


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run(
    input_dir: Path,
    output_path: Path,
    repo_root: Path | None = None,
    test_dirs: list[Path] | None = None,
) -> int:
    """Run the test_linker stage over a repo, updating the architecture graph.

    Args:
        input_dir: Directory containing ``architecture.graph.json`` (read).
        output_path: Target path for the updated graph (usually the same file).
        repo_root: Repository root for computing relative paths (default: cwd).
        test_dirs: List of directories to scan (default: repo_root/tests).

    Returns:
        0 on success, 1 on failure.
    """
    repo_root = (repo_root or Path.cwd()).resolve()
    if test_dirs is None:
        test_dirs = [repo_root / "tests"]

    graph = load_graph(input_dir / "architecture.graph.json")
    if not graph:
        logger.error(
            "architecture.graph.json not found or empty. Run graph_builder.py first."
        )
        return 1

    existing_nodes: list[dict[str, Any]] = graph.get("nodes", [])
    existing_edges: list[dict[str, Any]] = graph.get("edges", [])
    existing_node_ids: set[str] = {n["id"] for n in existing_nodes}

    # 1. Discover test files
    all_files: list[Path] = []
    for d in test_dirs:
        discovered = discover_test_files(d)
        all_files.extend(discovered)
    logger.info("test_linker: discovered %d test file(s)", len(all_files))

    # 2. Extract nodes
    all_test_nodes: list[TestNode] = []
    for path in all_files:
        all_test_nodes.extend(extract_test_nodes(path, repo_root=repo_root))
    logger.info("test_linker: extracted %d test node(s)", len(all_test_nodes))

    # 3. Merge new test nodes into graph (skip duplicates by id)
    added_nodes = 0
    for tn in all_test_nodes:
        if tn.id in existing_node_ids:
            continue
        existing_nodes.append(tn.to_graph_node())
        existing_node_ids.add(tn.id)
        added_nodes += 1

    # 4. Build TEST_COVERS edges
    new_edges = build_test_covers_edges(all_test_nodes, existing_nodes)

    # 5. Deduplicate edges by (from, to, type)
    edge_keys: set[tuple[str, str, str]] = {
        (e["from"], e["to"], e["type"]) for e in existing_edges
    }
    added_edges = 0
    for e in new_edges:
        key = (e["from"], e["to"], e["type"])
        if key in edge_keys:
            continue
        existing_edges.append(e)
        edge_keys.add(key)
        added_edges += 1

    graph["nodes"] = existing_nodes
    graph["edges"] = existing_edges
    save_json(output_path, graph)
    logger.info(
        "test_linker: added %d node(s), %d TEST_COVERS edge(s) → %s",
        added_nodes,
        added_edges,
        output_path,
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Walk test directories, extract test nodes, and add TEST_COVERS "
            "edges to the canonical architecture graph."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("docs/architecture-analysis"),
        help="Directory containing architecture.graph.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/architecture.graph.json"),
        help="Output path for the updated graph",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (for relative paths). Defaults to cwd.",
    )
    parser.add_argument(
        "--test-dir",
        action="append",
        default=None,
        type=Path,
        help="Test directory to scan. Repeat for multiple (default: <repo-root>/tests).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    return run(
        input_dir=args.input_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        test_dirs=args.test_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
