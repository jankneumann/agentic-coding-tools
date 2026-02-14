#!/usr/bin/env python3
"""Graph compiler that reads per-language intermediate analysis outputs and produces
the unified canonical architecture graph.

Reads python_analysis.json, ts_analysis.json, and postgres_analysis.json from the
.architecture/ directory and compiles them into:
  - architecture.graph.json  (full canonical graph)
  - architecture.summary.json (adaptive-confidence summary)
  - architecture.sqlite (optional, behind --sqlite flag)

Usage:
    python scripts/compile_architecture_graph.py [--input-dir .architecture] \
        [--output-dir .architecture] [--summary-limit 50] [--sqlite]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arch_utils.constants import DEPENDENCY_EDGE_TYPES, EdgeType  # noqa: E402
from arch_utils.node_id import make_node_id  # noqa: E402
from arch_utils.traversal import build_adjacency, reachable_from  # noqa: E402


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Node = dict[str, Any]
Edge = dict[str, Any]
Entrypoint = dict[str, Any]
Snapshot = dict[str, Any]
Graph = dict[str, Any]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def get_git_sha() -> str:
    """Obtain the current HEAD git SHA, returning 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# File loading helpers
# ---------------------------------------------------------------------------


def load_intermediate(path: Path) -> dict[str, Any] | None:
    """Load a JSON intermediate file, returning None if missing or invalid."""
    if not path.exists():
        print(f"  [skip] {path.name} not found", file=sys.stderr)
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        print(f"  [ok]   {path.name} loaded", file=sys.stderr)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [warn] {path.name}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Python analysis ingestion
# ---------------------------------------------------------------------------


def ingest_python(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert python_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- modules ---
    for mod in data.get("modules", []):
        nid = make_node_id("py", mod.get("qualified_name", mod.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "module",
            "language": "python",
            "name": mod.get("name", ""),
            "file": mod.get("file", ""),
            "span": mod.get("span", {"start": 1, "end": 1}),
            "tags": mod.get("tags", []),
            "signatures": mod.get("signatures", {}),
        })

    # --- classes ---
    for cls in data.get("classes", []):
        nid = make_node_id("py", cls.get("qualified_name", cls.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "class",
            "language": "python",
            "name": cls.get("name", ""),
            "file": cls.get("file", ""),
            "span": cls.get("span", {"start": 1, "end": 1}),
            "tags": cls.get("tags", []),
            "signatures": cls.get("signatures", {}),
        })

    # --- functions ---
    for func in data.get("functions", []):
        nid = make_node_id("py", func.get("qualified_name", func.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        tags = list(func.get("tags", []))
        node = {
            "id": nid,
            "kind": "function",
            "language": "python",
            "name": func.get("name", ""),
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": tags,
            "signatures": func.get("signatures", {}),
        }
        nodes.append(node)

        # Detect entrypoints from decorators/tags
        for ep in func.get("entrypoints", []):
            ep_entry: Entrypoint = {"node_id": nid, "kind": ep.get("kind", "route")}
            if ep.get("method"):
                ep_entry["method"] = ep["method"]
            if ep.get("path"):
                ep_entry["path"] = ep["path"]
            entrypoints.append(ep_entry)
            if "entrypoint" not in tags:
                tags.append("entrypoint")

    # --- intra-language edges: calls ---
    # The Python analyzer stores calls as a list of names on each function.
    # Build a lookup from short/qualified names to node IDs so we can resolve them.
    name_to_nid: dict[str, str] = {}
    for func in data.get("functions", []):
        qn = func.get("qualified_name", func.get("name", ""))
        nid = make_node_id("py", qn)
        name_to_nid[qn] = nid
        # Also register by short name for unqualified calls
        short = func.get("name", "")
        if short and short not in name_to_nid:
            name_to_nid[short] = nid

    for func in data.get("functions", []):
        from_qn = func.get("qualified_name", func.get("name", ""))
        from_id = make_node_id("py", from_qn)
        for call_name in func.get("calls", []):
            to_id = name_to_nid.get(call_name)
            if to_id and to_id != from_id:
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "type": "call",
                    "confidence": "high",
                    "evidence": f"ast:call:{call_name}",
                })

    # --- intra-language edges: imports ---
    # The Python analyzer stores these in "import_graph" (not "import_edges").
    for edge in data.get("import_graph", data.get("import_edges", [])):
        from_id = make_node_id("py", edge.get("from", ""))
        to_id = make_node_id("py", edge.get("to", ""))
        if from_id != to_id:
            edges.append({
                "from": from_id,
                "to": to_id,
                "type": "import",
                "confidence": "high",
                "evidence": "ast:import",
            })

    # --- intra-language edges: db_access ---
    # The Python analyzer stores these in "db_access" (not "db_access_edges").
    for da in data.get("db_access", data.get("db_access_edges", [])):
        func_qn = da.get("function", da.get("from", ""))
        from_id = make_node_id("py", func_qn)
        for table_name in da.get("tables", []):
            if not table_name:
                continue
            to_id = make_node_id(
                "pg", f"public.{table_name}" if "." not in table_name else table_name
            )
            edges.append({
                "from": from_id,
                "to": to_id,
                "type": "db_access",
                "confidence": da.get("confidence", "medium"),
                "evidence": f"orm:{da.get('pattern', 'model_usage')}",
            })

    # --- entrypoints from entry_points array ---
    for ep in data.get("entry_points", []):
        func_qn = ep.get("function", "")
        func_nid = make_node_id("py", func_qn)
        if func_nid in node_ids:
            ep_entry: Entrypoint = {"node_id": func_nid, "kind": ep.get("kind", "route")}
            if ep.get("method"):
                ep_entry["method"] = ep["method"]
            if ep.get("path"):
                ep_entry["path"] = ep["path"]
            entrypoints.append(ep_entry)

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# TypeScript analysis ingestion
# ---------------------------------------------------------------------------


def ingest_typescript(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert ts_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- modules ---
    for mod in data.get("modules", []):
        nid = make_node_id("ts", mod.get("qualified_name", mod.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "module",
            "language": "typescript",
            "name": mod.get("name", ""),
            "file": mod.get("file", ""),
            "span": mod.get("span", {"start": 1, "end": 1}),
            "tags": mod.get("tags", []),
            "signatures": mod.get("signatures", {}),
        })

    # --- components ---
    for comp in data.get("components", []):
        nid = make_node_id("ts", comp.get("qualified_name", comp.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "component",
            "language": "typescript",
            "name": comp.get("name", ""),
            "file": comp.get("file", ""),
            "span": comp.get("span", {"start": 1, "end": 1}),
            "tags": comp.get("tags", []),
            "signatures": comp.get("signatures", {}),
        })

    # --- hooks ---
    for hook in data.get("hooks", []):
        nid = make_node_id("ts", hook.get("qualified_name", hook.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "hook",
            "language": "typescript",
            "name": hook.get("name", ""),
            "file": hook.get("file", ""),
            "span": hook.get("span", {"start": 1, "end": 1}),
            "tags": hook.get("tags", []),
            "signatures": hook.get("signatures", {}),
        })

    # --- functions ---
    for func in data.get("functions", []):
        nid = make_node_id("ts", func.get("qualified_name", func.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "function",
            "language": "typescript",
            "name": func.get("name", ""),
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": func.get("tags", []),
            "signatures": func.get("signatures", {}),
        })

    # --- intra-language edges: imports ---
    for edge in data.get("import_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": "import",
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:import"),
        })

    # --- intra-language edges: component_child ---
    for edge in data.get("component_child_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": "component_child",
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "jsx:child_component"),
        })

    # --- intra-language edges: hook_usage ---
    for edge in data.get("hook_usage_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": "hook_usage",
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:hook_call"),
        })

    # --- intra-language edges: calls ---
    for edge in data.get("call_edges", []):
        from_id = make_node_id("ts", edge.get("from", ""))
        to_id = make_node_id("ts", edge.get("to", ""))
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": "call",
            "confidence": edge.get("confidence", "high"),
            "evidence": edge.get("evidence", "ast:call"),
        })

    # --- entrypoints ---
    for ep in data.get("entrypoints", []):
        nid = make_node_id("ts", ep.get("qualified_name", ep.get("node_id", "")))
        ep_entry: Entrypoint = {"node_id": nid, "kind": ep.get("kind", "event_handler")}
        if ep.get("method"):
            ep_entry["method"] = ep["method"]
        if ep.get("path"):
            ep_entry["path"] = ep["path"]
        entrypoints.append(ep_entry)

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# Postgres analysis ingestion
# ---------------------------------------------------------------------------


def ingest_postgres(data: dict[str, Any]) -> tuple[list[Node], list[Edge], list[Entrypoint]]:
    """Convert postgres_analysis.json into canonical nodes, edges, and entrypoints."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    entrypoints: list[Entrypoint] = []
    node_ids: set[str] = set()

    # --- tables ---
    for table in data.get("tables", []):
        schema = table.get("schema", "public")
        table_name = table.get("name", "")
        qualified = f"{schema}.{table_name}"
        nid = make_node_id("pg", qualified)
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "table",
            "language": "sql",
            "name": table_name,
            "file": table.get("file", table.get("migration_file", "")),
            "span": table.get("span", {"start": 1, "end": 1}),
            "tags": table.get("tags", []),
            "signatures": table.get("signatures", {}),
        })

        # --- columns as nodes (optional, if present) ---
        for col in table.get("columns", []):
            col_qualified = f"{qualified}.{col.get('name', '')}"
            col_nid = make_node_id("pg", col_qualified)
            if col_nid in node_ids:
                continue
            node_ids.add(col_nid)
            nodes.append({
                "id": col_nid,
                "kind": "column",
                "language": "sql",
                "name": col.get("name", ""),
                "file": table.get("file", table.get("migration_file", "")),
                "span": col.get("span", {"start": 1, "end": 1}),
                "tags": col.get("tags", []),
                "signatures": col.get("signatures", {"type": col.get("type", "")}),
            })

    # --- indexes ---
    for idx in data.get("indexes", []):
        nid = make_node_id("pg", idx.get("qualified_name", idx.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "index",
            "language": "sql",
            "name": idx.get("name", ""),
            "file": idx.get("file", ""),
            "span": idx.get("span", {"start": 1, "end": 1}),
            "tags": idx.get("tags", []),
            "signatures": idx.get("signatures", {}),
        })

    # --- stored functions ---
    for func in data.get("functions", []):
        schema = func.get("schema", "public")
        func_name = func.get("name", "")
        qualified = f"{schema}.{func_name}"
        nid = make_node_id("pg", qualified)
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "stored_function",
            "language": "sql",
            "name": func_name,
            "file": func.get("file", ""),
            "span": func.get("span", {"start": 1, "end": 1}),
            "tags": func.get("tags", []),
            "signatures": func.get("signatures", {}),
        })

    # --- triggers ---
    for trigger in data.get("triggers", []):
        nid = make_node_id("pg", trigger.get("qualified_name", trigger.get("name", "")))
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "kind": "trigger",
            "language": "sql",
            "name": trigger.get("name", ""),
            "file": trigger.get("file", ""),
            "span": trigger.get("span", {"start": 1, "end": 1}),
            "tags": trigger.get("tags", []),
            "signatures": trigger.get("signatures", {}),
        })

    # --- migrations as entrypoints ---
    for migration in data.get("migrations", []):
        nid = make_node_id("pg", migration.get("qualified_name", migration.get("name", "")))
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append({
                "id": nid,
                "kind": "migration",
                "language": "sql",
                "name": migration.get("name", ""),
                "file": migration.get("file", ""),
                "span": migration.get("span", {"start": 1, "end": 1}),
                "tags": migration.get("tags", []),
                "signatures": migration.get("signatures", {}),
            })
        entrypoints.append({
            "node_id": nid,
            "kind": "migration",
        })

    # --- foreign key edges ---
    for fk in data.get("foreign_keys", []):
        from_table = fk.get("from_table", "")
        to_table = fk.get("to_table", "")
        from_schema = fk.get("from_schema", "public")
        to_schema = fk.get("to_schema", "public")
        from_id = make_node_id("pg", f"{from_schema}.{from_table}")
        to_id = make_node_id("pg", f"{to_schema}.{to_table}")
        edges.append({
            "from": from_id,
            "to": to_id,
            "type": "fk_reference",
            "confidence": "high",
            "evidence": fk.get("evidence", f"fk:{fk.get('constraint_name', 'unnamed')}"),
        })

    return nodes, edges, entrypoints


# ---------------------------------------------------------------------------
# Cross-language linking: Frontend -> Backend
# ---------------------------------------------------------------------------


def _normalize_path_for_matching(path: str) -> str:
    """Normalize a URL path by stripping trailing slashes and lowering."""
    path = path.strip().rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return path.lower()


def _to_regex_pattern(route_path: str) -> str:
    """Convert a route path with parameter placeholders to a regex.

    Handles both Python-style ``{param}`` and TS-style ``:param`` placeholders.
    """
    # Normalize to a common form first: replace :param with {param}
    normalized = re.sub(r":(\w+)", r"{\1}", route_path)
    # Escape everything except the placeholders
    parts = re.split(r"(\{[^}]+\})", normalized)
    regex_parts: list[str] = []
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            regex_parts.append(r"[^/]+")
        else:
            regex_parts.append(re.escape(part))
    return "^" + "".join(regex_parts) + "$"


def _is_parameterized(path: str) -> bool:
    """Check if a path contains parameter placeholders ({param} or :param)."""
    return bool(re.search(r"\{[^}]+\}|:\w+", path))


def link_frontend_to_backend(
    ts_data: dict[str, Any] | None,
    py_entrypoints: list[Entrypoint],
    all_nodes: list[Node],
) -> tuple[list[Edge], list[dict[str, str]], list[dict[str, str]]]:
    """Match TS API call URLs to Python route decorator paths.

    Returns:
        - list of cross-language api_call edges
        - list of disconnected backend endpoints (no frontend caller)
        - list of disconnected frontend calls (no backend match)
    """
    cross_edges: list[Edge] = []
    disconnected_endpoints: list[dict[str, str]] = []
    disconnected_frontend_calls: list[dict[str, str]] = []

    if ts_data is None:
        # No TS analysis: all backend routes are disconnected from frontend
        for ep in py_entrypoints:
            if ep["kind"] == "route":
                disconnected_endpoints.append({
                    "node_id": ep["node_id"],
                    "path": ep.get("path", ""),
                })
        return cross_edges, disconnected_endpoints, disconnected_frontend_calls

    # Build a lookup of backend routes: path -> list of entrypoint info
    route_lookup: dict[str, list[Entrypoint]] = defaultdict(list)
    for ep in py_entrypoints:
        if ep["kind"] == "route" and ep.get("path"):
            normalized = _normalize_path_for_matching(ep["path"])
            route_lookup[normalized].append(ep)

    # Collect all API call sites from TS analysis
    api_calls: list[dict[str, Any]] = ts_data.get("api_calls", [])

    # Track which routes and frontend calls have been matched
    matched_routes: set[str] = set()
    matched_frontend_calls: set[int] = set()

    # Pass 1: Exact URL matches (high confidence)
    for idx, call in enumerate(api_calls):
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)
        if normalized_url in route_lookup:
            for ep in route_lookup[normalized_url]:
                caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                cross_edges.append({
                    "from": caller_id,
                    "to": ep["node_id"],
                    "type": "api_call",
                    "confidence": "high",
                    "evidence": f"string_match:{url}",
                })
                matched_routes.add(ep["node_id"])
                matched_frontend_calls.add(idx)

    # Pass 2: Parameterized path matches (medium confidence)
    for idx, call in enumerate(api_calls):
        if idx in matched_frontend_calls:
            continue
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)

        for route_path, eps in route_lookup.items():
            if not _is_parameterized(route_path) and not _is_parameterized(normalized_url):
                continue  # Already handled by exact match or no params to match
            pattern = _to_regex_pattern(route_path)
            if re.match(pattern, normalized_url):
                for ep in eps:
                    caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                    cross_edges.append({
                        "from": caller_id,
                        "to": ep["node_id"],
                        "type": "api_call",
                        "confidence": "medium",
                        "evidence": f"param_match:{url}~{ep.get('path', '')}",
                    })
                    matched_routes.add(ep["node_id"])
                    matched_frontend_calls.add(idx)
            else:
                # Also try matching the other way: frontend URL might have :param style
                url_pattern = _to_regex_pattern(normalized_url)
                if re.match(url_pattern, route_path):
                    for ep in eps:
                        caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
                        cross_edges.append({
                            "from": caller_id,
                            "to": ep["node_id"],
                            "type": "api_call",
                            "confidence": "medium",
                            "evidence": f"param_match:{url}~{ep.get('path', '')}",
                        })
                        matched_routes.add(ep["node_id"])
                        matched_frontend_calls.add(idx)

    # Pass 3: Heuristic partial matches (low confidence)
    # Match if the URL path shares a significant common prefix with a route
    for idx, call in enumerate(api_calls):
        if idx in matched_frontend_calls:
            continue
        url = call.get("url", "")
        if not url:
            continue
        normalized_url = _normalize_path_for_matching(url)
        url_segments = [s for s in normalized_url.split("/") if s]

        if len(url_segments) < 2:
            continue

        best_match_ep: Entrypoint | None = None
        best_match_score = 0
        best_route_path = ""

        for route_path, eps in route_lookup.items():
            route_segments = [s for s in route_path.split("/") if s]
            # Count matching leading segments (ignoring parameter segments)
            match_count = 0
            for us, rs in zip(url_segments, route_segments):
                rs_is_param = rs.startswith("{") or rs.startswith(":")
                us_is_param = us.startswith("{") or us.startswith(":")
                if rs_is_param or us_is_param or us == rs:
                    match_count += 1
                else:
                    break

            # Require at least 2 matching segments for a heuristic match
            if match_count >= 2 and match_count > best_match_score:
                best_match_score = match_count
                best_match_ep = eps[0] if eps else None
                best_route_path = route_path

        if best_match_ep is not None:
            caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
            cross_edges.append({
                "from": caller_id,
                "to": best_match_ep["node_id"],
                "type": "api_call",
                "confidence": "low",
                "evidence": f"heuristic_match:{url}~{best_route_path}",
            })
            matched_routes.add(best_match_ep["node_id"])
            matched_frontend_calls.add(idx)

    # Disconnected backend endpoints (routes not called by any frontend)
    for ep in py_entrypoints:
        if ep["kind"] == "route" and ep["node_id"] not in matched_routes:
            disconnected_endpoints.append({
                "node_id": ep["node_id"],
                "path": ep.get("path", ""),
            })

    # Disconnected frontend calls (no matching backend route)
    for idx, call in enumerate(api_calls):
        if idx not in matched_frontend_calls:
            caller_id = make_node_id("ts", call.get("qualified_name", call.get("from", "")))
            disconnected_frontend_calls.append({
                "node_id": caller_id,
                "url": call.get("url", ""),
            })

    return cross_edges, disconnected_endpoints, disconnected_frontend_calls


# ---------------------------------------------------------------------------
# Cross-language linking: Backend -> Database
# ---------------------------------------------------------------------------


def link_backend_to_database(
    py_data: dict[str, Any] | None,
    pg_data: dict[str, Any] | None,
) -> list[Edge]:
    """Match Python ORM model usage and SQL patterns to DB table names.

    This complements the db_access_edges already ingested from python_analysis.json
    by adding edges for functions that reference table names via other patterns
    (e.g., raw SQL strings, model class names that map to tables).
    """
    if py_data is None or pg_data is None:
        return []

    edges: list[Edge] = []

    # Build a set of known table names (schema.table and just table)
    table_names: set[str] = set()
    table_qualified: dict[str, str] = {}  # lowercase table name -> qualified pg ID
    for table in pg_data.get("tables", []):
        schema = table.get("schema", "public")
        name = table.get("name", "")
        qualified = f"{schema}.{name}"
        table_names.add(name.lower())
        table_qualified[name.lower()] = qualified

    # Check Python functions for db_tables metadata not already captured in db_access
    existing_db_edges: set[tuple[str, str]] = set()
    for da in py_data.get("db_access", py_data.get("db_access_edges", [])):
        from_qn = da.get("function", da.get("from", ""))
        for table in da.get("tables", []):
            existing_db_edges.add((from_qn, table.lower()))

    for func in py_data.get("functions", []):
        func_qn = func.get("qualified_name", func.get("name", ""))
        func_nid = make_node_id("py", func_qn)

        # Check db_tables metadata on the function (model class references, raw SQL)
        for table_ref in func.get("db_tables", []):
            table_lower = table_ref.lower()
            if (func_qn, table_lower) in existing_db_edges:
                continue  # Already captured
            if table_lower in table_qualified:
                table_nid = make_node_id("pg", table_qualified[table_lower])
                edges.append({
                    "from": func_nid,
                    "to": table_nid,
                    "type": "db_access",
                    "confidence": "medium",
                    "evidence": f"table_ref:{table_ref}",
                })

        # Check sql_patterns metadata for raw SQL containing table names
        for sql_pattern in func.get("sql_patterns", []):
            sql_lower = sql_pattern.lower()
            for table_name, qualified in table_qualified.items():
                if table_name in sql_lower and (func_qn, table_name) not in existing_db_edges:
                    table_nid = make_node_id("pg", qualified)
                    edges.append({
                        "from": func_nid,
                        "to": table_nid,
                        "type": "db_access",
                        "confidence": "low",
                        "evidence": f"sql_pattern:{sql_pattern[:80]}",
                    })
                    existing_db_edges.add((func_qn, table_name))

    return edges


# ---------------------------------------------------------------------------
# Cross-layer flow inference
# ---------------------------------------------------------------------------


def infer_cross_layer_flows(
    all_nodes: list[Node],
    all_edges: list[Edge],
    entrypoints: list[Entrypoint],
    cross_api_edges: list[Edge],
) -> list[dict[str, Any]]:
    """Infer Frontend->Database indirect flows by chaining endpoint->service->query->table paths.

    Returns a list of cross-layer flow dicts suitable for the summary.
    """
    flows: list[dict[str, Any]] = []
    node_map: dict[str, Node] = {n["id"]: n for n in all_nodes}
    adj = build_adjacency(all_edges)

    # For each cross-language API call edge (frontend -> backend), trace
    # the backend call chain to find database tables
    for api_edge in cross_api_edges:
        frontend_id = api_edge["from"]
        backend_handler_id = api_edge["to"]

        frontend_node = node_map.get(frontend_id)
        backend_node = node_map.get(backend_handler_id)
        if frontend_node is None or backend_node is None:
            continue

        # BFS from backend handler to find all reachable db tables
        visited: set[str] = set()
        queue: list[str] = [backend_handler_id]
        service_functions: list[str] = []
        db_tables: list[str] = []

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            current_node = node_map.get(current)
            if current_node is None:
                continue

            # If it's a table node, record it
            if current_node.get("kind") == "table":
                db_tables.append(current)
                continue

            # If it's a python function/class and not the handler itself, it's a service function
            if (
                current != backend_handler_id
                and current_node.get("language") == "python"
                and current_node.get("kind") in ("function", "class")
            ):
                service_functions.append(current)

            # Follow edges
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        # Determine the API URL from the api_edge evidence
        api_url = ""
        evidence = api_edge.get("evidence", "")
        match = re.search(r"(?:string_match|param_match|heuristic_match):([^~]+)", evidence)
        if match:
            api_url = match.group(1)

        # Build the flow entry
        flow: dict[str, Any] = {
            "frontend_component": frontend_id,
            "api_url": api_url,
            "backend_handler": backend_handler_id,
            "service_functions": service_functions,
            "db_tables": db_tables,
            "confidence": api_edge.get("confidence", "medium"),
        }
        flows.append(flow)

    return flows


# ---------------------------------------------------------------------------
# High-impact node detection
# ---------------------------------------------------------------------------


def compute_high_impact_nodes(
    all_nodes: list[Node],
    all_edges: list[Edge],
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Find nodes with the most dependents (reverse transitive closure)."""
    # Build reverse adjacency (who depends on this node?)
    reverse_adj: dict[str, set[str]] = defaultdict(set)
    for edge in all_edges:
        if edge["type"] in DEPENDENCY_EDGE_TYPES:
            reverse_adj[edge["to"]].add(edge["from"])

    # Compute transitive dependents for each node
    high_impact: list[dict[str, Any]] = []

    for node in all_nodes:
        nid = node["id"]
        if nid not in reverse_adj:
            continue

        # BFS to count transitive dependents
        visited: set[str] = set()
        queue = list(reverse_adj[nid])
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for dep in reverse_adj.get(current, set()):
                if dep not in visited:
                    queue.append(dep)

        if len(visited) >= threshold:
            high_impact.append({
                "id": nid,
                "dependent_count": len(visited),
            })

    # Sort by dependent count descending
    high_impact.sort(key=lambda x: x["dependent_count"], reverse=True)
    return high_impact


# ---------------------------------------------------------------------------
# Summary generation with adaptive confidence threshold
# ---------------------------------------------------------------------------


def generate_summary(
    graph: Graph,
    flows: list[dict[str, Any]],
    disconnected_endpoints: list[dict[str, str]],
    disconnected_frontend_calls: list[dict[str, str]],
    high_impact_nodes: list[dict[str, Any]],
    summary_limit: int,
    git_sha: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build architecture.summary.json with adaptive confidence threshold."""
    nodes = graph["nodes"]
    edges = graph["edges"]

    # Stats
    by_language: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    for node in nodes:
        by_language[node.get("language", "unknown")] += 1
        by_kind[node.get("kind", "unknown")] += 1

    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "by_language": dict(by_language),
        "by_kind": dict(by_kind),
        "entrypoint_count": len(graph["entrypoints"]),
    }

    # Adaptive confidence threshold for flows
    high_flows = [f for f in flows if f.get("confidence") == "high"]
    medium_flows = [f for f in flows if f.get("confidence") == "medium"]
    low_flows = [f for f in flows if f.get("confidence") == "low"]

    selected_flows: list[dict[str, Any]] = list(high_flows)
    remaining = summary_limit - len(selected_flows)

    if remaining > 0:
        selected_flows.extend(medium_flows[:remaining])
        remaining = summary_limit - len(selected_flows)

    if remaining > 0:
        selected_flows.extend(low_flows[:remaining])

    return {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "stats": stats,
        "cross_layer_flows": selected_flows,
        "disconnected_endpoints": disconnected_endpoints,
        "disconnected_frontend_calls": disconnected_frontend_calls,
        "high_impact_nodes": high_impact_nodes,
    }


# ---------------------------------------------------------------------------
# SQLite output
# ---------------------------------------------------------------------------


def emit_sqlite(graph: Graph, output_path: Path) -> None:
    """Write the canonical graph to a SQLite database for queryable storage."""
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(str(output_path))
    cursor = conn.cursor()

    # Create tables
    cursor.executescript("""
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            git_sha TEXT NOT NULL,
            tool_versions TEXT NOT NULL,
            notes TEXT
        );

        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            language TEXT NOT NULL,
            name TEXT NOT NULL,
            file TEXT NOT NULL,
            span_start INTEGER,
            span_end INTEGER,
            tags TEXT,
            signatures TEXT
        );

        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            type TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence TEXT NOT NULL,
            FOREIGN KEY (from_node) REFERENCES nodes(id),
            FOREIGN KEY (to_node) REFERENCES nodes(id)
        );

        CREATE TABLE entrypoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            method TEXT,
            path TEXT,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE INDEX idx_nodes_language ON nodes(language);
        CREATE INDEX idx_nodes_kind ON nodes(kind);
        CREATE INDEX idx_edges_from ON edges(from_node);
        CREATE INDEX idx_edges_to ON edges(to_node);
        CREATE INDEX idx_edges_type ON edges(type);
        CREATE INDEX idx_edges_confidence ON edges(confidence);
        CREATE INDEX idx_entrypoints_kind ON entrypoints(kind);
    """)

    # Insert snapshots
    for snap in graph.get("snapshots", []):
        cursor.execute(
            "INSERT INTO snapshots (generated_at, git_sha, tool_versions, notes) VALUES (?, ?, ?, ?)",
            (
                snap["generated_at"],
                snap["git_sha"],
                json.dumps(snap.get("tool_versions", {})),
                json.dumps(snap.get("notes", [])),
            ),
        )

    # Insert nodes
    for node in graph.get("nodes", []):
        span = node.get("span", {})
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, kind, language, name, file, span_start, span_end, tags, signatures) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node["id"],
                node["kind"],
                node["language"],
                node["name"],
                node["file"],
                span.get("start"),
                span.get("end"),
                json.dumps(node.get("tags", [])),
                json.dumps(node.get("signatures", {})),
            ),
        )

    # Insert edges
    for edge in graph.get("edges", []):
        cursor.execute(
            "INSERT INTO edges (from_node, to_node, type, confidence, evidence) VALUES (?, ?, ?, ?, ?)",
            (edge["from"], edge["to"], edge["type"], edge["confidence"], edge["evidence"]),
        )

    # Insert entrypoints
    for ep in graph.get("entrypoints", []):
        cursor.execute(
            "INSERT INTO entrypoints (node_id, kind, method, path) VALUES (?, ?, ?, ?)",
            (ep["node_id"], ep["kind"], ep.get("method"), ep.get("path")),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------


def deduplicate_nodes(nodes: list[Node]) -> list[Node]:
    """Remove duplicate nodes, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[Node] = []
    for node in nodes:
        if node["id"] not in seen:
            seen.add(node["id"])
            unique.append(node)
    return unique


def deduplicate_edges(edges: list[Edge]) -> list[Edge]:
    """Remove duplicate edges (same from, to, type)."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[Edge] = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["type"])
        if key not in seen:
            seen.add(key)
            unique.append(edge)
    return unique


# ---------------------------------------------------------------------------
# Edge validation
# ---------------------------------------------------------------------------


def validate_edges(edges: list[Edge], node_ids: set[str]) -> list[Edge]:
    """Remove edges that reference nodes not in the graph."""
    valid: list[Edge] = []
    for edge in edges:
        if edge["from"] in node_ids and edge["to"] in node_ids:
            valid.append(edge)
        else:
            missing = []
            if edge["from"] not in node_ids:
                missing.append(f"from={edge['from']}")
            if edge["to"] not in node_ids:
                missing.append(f"to={edge['to']}")
            print(
                f"  [warn] dropping edge {edge['from']} -> {edge['to']}: "
                f"missing node(s): {', '.join(missing)}",
                file=sys.stderr,
            )
    return valid


# ---------------------------------------------------------------------------
# Main compilation pipeline
# ---------------------------------------------------------------------------


def compile_graph(
    input_dir: Path,
    output_dir: Path,
    summary_limit: int,
    emit_sqlite_flag: bool,
) -> int:
    """Run the full compilation pipeline. Returns 0 on success, 1 on failure."""
    print("Loading intermediate analysis files...", file=sys.stderr)

    py_data = load_intermediate(input_dir / "python_analysis.json")
    ts_data = load_intermediate(input_dir / "ts_analysis.json")
    pg_data = load_intermediate(input_dir / "postgres_analysis.json")

    if py_data is None and ts_data is None and pg_data is None:
        print(
            "Error: No intermediate analysis files found. "
            "Run the per-language analyzers first.",
            file=sys.stderr,
        )
        return 1

    notes: list[str] = []
    if py_data is None:
        notes.append("Python analysis not available")
    if ts_data is None:
        notes.append("TypeScript analysis not available")
    if pg_data is None:
        notes.append("Postgres analysis not available")

    # --- Ingest per-language data ---
    print("Ingesting per-language data...", file=sys.stderr)

    all_nodes: list[Node] = []
    all_edges: list[Edge] = []
    all_entrypoints: list[Entrypoint] = []
    py_entrypoints: list[Entrypoint] = []

    if py_data is not None:
        nodes, edges, entrypoints = ingest_python(py_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)
        py_entrypoints = entrypoints

    if ts_data is not None:
        nodes, edges, entrypoints = ingest_typescript(ts_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)

    if pg_data is not None:
        nodes, edges, entrypoints = ingest_postgres(pg_data)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        all_entrypoints.extend(entrypoints)

    # --- Deduplicate ---
    all_nodes = deduplicate_nodes(all_nodes)
    all_edges = deduplicate_edges(all_edges)

    # --- Cross-language linking ---
    print("Performing cross-language linking...", file=sys.stderr)

    # Frontend -> Backend
    cross_api_edges, disconnected_endpoints, disconnected_frontend_calls = link_frontend_to_backend(
        ts_data, py_entrypoints, all_nodes,
    )
    all_edges.extend(cross_api_edges)

    # Backend -> Database
    backend_db_edges = link_backend_to_database(py_data, pg_data)
    all_edges.extend(backend_db_edges)

    # Deduplicate again after cross-language edges
    all_edges = deduplicate_edges(all_edges)

    # Validate edges: drop any that reference missing nodes
    node_id_set = {n["id"] for n in all_nodes}
    all_edges = validate_edges(all_edges, node_id_set)

    # --- Infer cross-layer flows ---
    print("Inferring cross-layer flows...", file=sys.stderr)
    flows = infer_cross_layer_flows(all_nodes, all_edges, all_entrypoints, cross_api_edges)

    # --- High-impact nodes ---
    high_impact = compute_high_impact_nodes(all_nodes, all_edges)

    # --- Build snapshot ---
    git_sha = get_git_sha()
    generated_at = datetime.now(timezone.utc).isoformat()

    tool_versions: dict[str, str] = {"compile_architecture_graph": "1.0.0"}
    # Collect tool versions from intermediate files
    for label, data in [("python_analyzer", py_data), ("ts_analyzer", ts_data), ("postgres_analyzer", pg_data)]:
        if data is not None and "tool_version" in data:
            tool_versions[label] = data["tool_version"]

    snapshot: Snapshot = {
        "generated_at": generated_at,
        "git_sha": git_sha,
        "tool_versions": tool_versions,
        "notes": notes,
    }

    # --- Assemble the canonical graph ---
    graph: Graph = {
        "snapshots": [snapshot],
        "nodes": all_nodes,
        "edges": all_edges,
        "entrypoints": all_entrypoints,
    }

    # --- Generate summary ---
    print("Generating summary...", file=sys.stderr)
    summary = generate_summary(
        graph,
        flows,
        disconnected_endpoints,
        disconnected_frontend_calls,
        high_impact,
        summary_limit,
        git_sha,
        generated_at,
    )

    # --- Write outputs ---
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_path = output_dir / "architecture.graph.json"
    with open(graph_path, "w") as f:
        json.dump(graph, f, indent=2)
    print(f"Wrote {graph_path}", file=sys.stderr)

    summary_path = output_dir / "architecture.summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {summary_path}", file=sys.stderr)

    if emit_sqlite_flag:
        sqlite_path = output_dir / "architecture.sqlite"
        emit_sqlite(graph, sqlite_path)
        print(f"Wrote {sqlite_path}", file=sys.stderr)

    # --- Report ---
    print(
        f"\nCompilation complete: "
        f"{len(all_nodes)} nodes, {len(all_edges)} edges, "
        f"{len(all_entrypoints)} entrypoints, {len(flows)} cross-layer flows",
        file=sys.stderr,
    )
    if disconnected_endpoints:
        print(f"  {len(disconnected_endpoints)} disconnected backend endpoint(s)", file=sys.stderr)
    if disconnected_frontend_calls:
        print(f"  {len(disconnected_frontend_calls)} disconnected frontend call(s)", file=sys.stderr)
    if notes:
        print(f"  Notes: {'; '.join(notes)}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Compile per-language analysis outputs into a unified architecture graph.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing intermediate analysis JSON files (default: .architecture)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory for output files (default: .architecture)",
    )
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=50,
        help="Maximum number of flow entries in the summary (default: 50)",
    )
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Also emit architecture.sqlite for queryable storage",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    return compile_graph(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        summary_limit=args.summary_limit,
        emit_sqlite_flag=args.sqlite,
    )


if __name__ == "__main__":
    sys.exit(main())
