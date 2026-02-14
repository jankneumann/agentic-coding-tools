#!/usr/bin/env python3
"""Flow validator for the canonical architecture graph.

Checks reachability, test coverage alignment, disconnected flows, orphaned code,
and pattern consistency by consuming architecture.graph.json.

Usage:
    python scripts/validate_flows.py
    python scripts/validate_flows.py --graph .architecture/architecture.graph.json
    python scripts/validate_flows.py --files file1.py,file2.py
    python scripts/validate_flows.py --diff "git diff main...HEAD"
    python scripts/validate_flows.py --glob "src/**/*.py"
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arch_utils.constants import SIDE_EFFECT_EDGE_TYPES, EdgeType  # noqa: E402
from arch_utils.traversal import (  # noqa: E402
    build_adjacency,
    reachable_from,
)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _build_adjacency(graph: dict) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Build forward and reverse adjacency lists from edges."""
    edges = graph.get("edges", [])
    forward = build_adjacency(edges)
    reverse = build_adjacency(edges, reverse=True)
    return forward, reverse


def _build_node_index(graph: dict) -> dict[str, dict]:
    """Map node id -> node object."""
    return {n["id"]: n for n in graph.get("nodes", [])}


def _reachable_from(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    """BFS forward reachability from *start*."""
    return reachable_from(start, adjacency)


def _edge_types_for(node_id: str, graph: dict) -> set[str]:
    """Return the set of edge types originating from *node_id*."""
    return {e["type"] for e in graph.get("edges", []) if e["from"] == node_id}


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------

def _resolve_changed_files(
    files_arg: str | None,
    diff_arg: str | None,
    glob_arg: str | None,
) -> list[str] | None:
    """Resolve the set of changed files from CLI arguments.

    Returns None when no scoping was requested (full validation).
    Returns a list of relative file paths otherwise.
    """
    changed: list[str] = []

    if files_arg:
        changed.extend(f.strip() for f in files_arg.split(",") if f.strip())

    if diff_arg:
        # diff_arg is either a literal git command or a diff-spec like "main...HEAD"
        if diff_arg.startswith("git "):
            cmd = diff_arg
        else:
            cmd = f"git diff --name-only {diff_arg}"
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            changed.extend(
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            )
        except subprocess.CalledProcessError as exc:
            print(f"Warning: diff command failed: {exc.stderr.strip()}", file=sys.stderr)

    if glob_arg:
        # Expand the glob against the working tree
        for path in Path(".").rglob("*"):
            rel = str(path)
            if fnmatch.fnmatch(rel, glob_arg):
                changed.append(rel)

    if not files_arg and not diff_arg and not glob_arg:
        return None

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for f in changed:
        normalized = f.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


# ---------------------------------------------------------------------------
# Finding helpers
# ---------------------------------------------------------------------------

Finding = dict[str, Any]


def _finding(
    severity: str,
    category: str,
    message: str,
    *,
    node_id: str | None = None,
    file: str | None = None,
    line: int | None = None,
    suggestion: str | None = None,
) -> Finding:
    f: Finding = {
        "severity": severity,
        "category": category,
        "message": message,
    }
    if node_id is not None:
        f["node_id"] = node_id
    if file is not None:
        f["file"] = file
    if line is not None:
        f["line"] = line
    if suggestion is not None:
        f["suggestion"] = suggestion
    return f


def _in_scope(file_path: str | None, changed_files: list[str] | None) -> bool:
    """Return True if *file_path* is in scope (or scope is not restricted)."""
    if changed_files is None:
        return True
    if file_path is None:
        return False
    normalized = file_path.replace("\\", "/")
    return normalized in changed_files


# ---------------------------------------------------------------------------
# Check: Reachability
# ---------------------------------------------------------------------------

DB_KINDS = {"table", "column", "index", "stored_function", "trigger", "migration"}


def check_reachability(
    graph: dict,
    nodes: dict[str, dict],
    forward: dict[str, list[str]],
    changed_files: list[str] | None,
) -> tuple[list[Finding], int]:
    """For each entrypoint verify downstream service + DB/side-effect exists.

    Returns (findings, entrypoints_checked).
    """
    findings: list[Finding] = []
    checked = 0

    for ep in graph.get("entrypoints", []):
        node_id = ep["node_id"]
        node = nodes.get(node_id)
        if node is None:
            continue

        if not _in_scope(node.get("file"), changed_files):
            continue

        checked += 1
        tags = set(node.get("tags", []))

        # Skip explicitly pure entrypoints
        if "pure" in tags:
            continue

        # Walk the forward graph from this entrypoint
        reachable = _reachable_from(node_id, forward)
        reachable.discard(node_id)  # exclude self

        if not reachable:
            findings.append(_finding(
                "warning",
                "reachability",
                f"Entrypoint '{node.get('name', node_id)}' has no downstream dependencies",
                node_id=node_id,
                file=node.get("file"),
                line=node.get("span", {}).get("start"),
                suggestion="Add downstream calls or tag this entrypoint as 'pure' if it has no side effects",
            ))
            continue

        # Check for at least one DB/side-effect dependency in the reachable set
        has_db_or_side_effect = False
        for rid in reachable:
            rnode = nodes.get(rid)
            if rnode and rnode.get("kind") in DB_KINDS:
                has_db_or_side_effect = True
                break
            # Also check if there are side-effect edges from reachable nodes
            edge_types = _edge_types_for(rid, graph)
            if edge_types & SIDE_EFFECT_EDGE_TYPES:
                has_db_or_side_effect = True
                break

        if not has_db_or_side_effect:
            findings.append(_finding(
                "info",
                "reachability",
                (
                    f"Entrypoint '{node.get('name', node_id)}' has downstream dependencies "
                    f"but none touch a DB or produce side effects"
                ),
                node_id=node_id,
                file=node.get("file"),
                line=node.get("span", {}).get("start"),
                suggestion="Verify this is expected, or tag the entrypoint as 'pure'",
            ))

    return findings, checked


# ---------------------------------------------------------------------------
# Check: Disconnected flows
# ---------------------------------------------------------------------------

def check_disconnected_flows(
    graph: dict,
    nodes: dict[str, dict],
    forward: dict[str, list[str]],
    reverse: dict[str, list[str]],
    changed_files: list[str] | None,
) -> list[Finding]:
    """Detect backend routes with no frontend callers and frontend API calls
    with no backend handlers.
    """
    findings: list[Finding] = []

    # Identify backend route entrypoints
    route_node_ids: set[str] = set()
    for ep in graph.get("entrypoints", []):
        if ep.get("kind") == "route":
            route_node_ids.add(ep["node_id"])

    # Identify api_call edges
    api_call_targets: set[str] = set()
    api_call_sources: dict[str, list[str]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if edge["type"] == EdgeType.API_CALL:
            api_call_targets.add(edge["to"])
            api_call_sources[edge["to"]].append(edge["from"])

    # Backend routes with no frontend callers (no incoming api_call edge)
    for node_id in route_node_ids:
        node = nodes.get(node_id)
        if node is None:
            continue
        if not _in_scope(node.get("file"), changed_files):
            continue

        # Check if any node has an api_call edge pointing to this route node
        has_caller = node_id in api_call_targets
        # Also check if anything in the reverse graph connects via api_call
        if not has_caller:
            for edge in graph.get("edges", []):
                if edge["to"] == node_id and edge["type"] == EdgeType.API_CALL:
                    has_caller = True
                    break

        if not has_caller:
            findings.append(_finding(
                "warning",
                "disconnected_flow",
                f"Backend route '{node.get('name', node_id)}' has no frontend callers",
                node_id=node_id,
                file=node.get("file"),
                line=node.get("span", {}).get("start"),
                suggestion="Add a frontend caller or remove the unused route",
            ))

    # Frontend API calls with no backend handlers
    for edge in graph.get("edges", []):
        if edge["type"] != EdgeType.API_CALL:
            continue
        target_id = edge["to"]
        source_id = edge["from"]
        source_node = nodes.get(source_id)

        if source_node is None:
            continue
        if not _in_scope(source_node.get("file"), changed_files):
            continue

        if target_id not in nodes:
            findings.append(_finding(
                "error",
                "disconnected_flow",
                f"Frontend API call from '{source_node.get('name', source_id)}' targets unknown node '{target_id}'",
                node_id=source_id,
                file=source_node.get("file"),
                line=source_node.get("span", {}).get("start"),
                suggestion="Ensure the backend handler exists and is registered in the graph",
            ))

    return findings


# ---------------------------------------------------------------------------
# Check: Test coverage alignment
# ---------------------------------------------------------------------------

# Common test file patterns
_TEST_FILE_PATTERNS = [
    re.compile(r"tests?/.*test_.*\.py$"),
    re.compile(r"tests?/.*_test\.py$"),
    re.compile(r".*\.test\.[tj]sx?$"),
    re.compile(r".*\.spec\.[tj]sx?$"),
    re.compile(r"__tests__/.*\.[tj]sx?$"),
    re.compile(r"tests?/.*\.py$"),
]


def _is_test_file(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    return any(p.search(normalized) for p in _TEST_FILE_PATTERNS)


def _corresponding_test_names(name: str) -> list[str]:
    """Generate plausible test function/file name fragments for *name*.

    Only returns patterns that are specific enough to avoid false positives.
    Short names (<=3 chars) are prefixed to avoid matching common words.
    """
    if not name:
        return []
    results = [
        f"test_{name}",
        f"Test{name[0].upper()}{name[1:]}",
    ]
    # Only include the bare name if it's long enough to be specific
    if len(name) > 6:
        results.append(name)
    return results


def check_test_coverage(
    graph: dict,
    nodes: dict[str, dict],
    forward: dict[str, list[str]],
    reverse: dict[str, list[str]],
    changed_files: list[str] | None,
) -> tuple[list[Finding], int, int]:
    """Verify modified/new functions have corresponding test references.

    Returns (findings, flows_with_coverage, flows_without_coverage).
    """
    findings: list[Finding] = []

    # Build set of test node ids and the names they reference
    test_node_ids: set[str] = set()
    test_referenced_names: set[str] = set()
    test_referenced_node_ids: set[str] = set()

    for ep in graph.get("entrypoints", []):
        if ep.get("kind") == "test":
            test_node_ids.add(ep["node_id"])

    for nid, node in nodes.items():
        if _is_test_file(node.get("file", "")):
            test_node_ids.add(nid)

    # Collect what test nodes call (forward edges from tests)
    for tid in test_node_ids:
        for target in forward.get(tid, []):
            test_referenced_node_ids.add(target)
            target_node = nodes.get(target)
            if target_node:
                test_referenced_names.add(target_node["name"])

    # Check non-test nodes in scope
    with_coverage = 0
    without_coverage = 0

    for nid, node in nodes.items():
        if nid in test_node_ids:
            continue
        if node.get("kind") not in ("function", "class", "component", "hook"):
            continue
        if not _in_scope(node.get("file"), changed_files):
            continue

        # A node has coverage if it is directly referenced by a test or
        # its name appears in any test_referenced_names
        has_coverage = (
            nid in test_referenced_node_ids
            or node["name"] in test_referenced_names
        )

        if has_coverage:
            with_coverage += 1
        else:
            without_coverage += 1
            findings.append(_finding(
                "warning",
                "test_coverage",
                f"Function '{node['name']}' has no corresponding test references",
                node_id=nid,
                file=node.get("file"),
                line=node.get("span", {}).get("start"),
                suggestion=(
                    f"Add tests that reference '{node['name']}' "
                    f"(e.g., test_{node['name']} or import it in a test file)"
                ),
            ))

    return findings, with_coverage, without_coverage


# ---------------------------------------------------------------------------
# Check: Orphaned code
# ---------------------------------------------------------------------------

def check_orphaned_code(
    graph: dict,
    nodes: dict[str, dict],
    forward: dict[str, list[str]],
    reverse: dict[str, list[str]],
    changed_files: list[str] | None,
) -> list[Finding]:
    """Detect functions/components unreachable from any entrypoint or test."""
    findings: list[Finding] = []

    # Collect all entrypoint and test node ids as roots
    roots: set[str] = set()
    for ep in graph.get("entrypoints", []):
        roots.add(ep["node_id"])
    for nid, node in nodes.items():
        if _is_test_file(node.get("file", "")):
            roots.add(nid)

    # Compute reachability from all roots
    reachable_from_roots: set[str] = set()
    for root in roots:
        reachable_from_roots |= _reachable_from(root, forward)

    # Also consider nodes reachable via reverse edges from entrypoints
    # (e.g., a utility imported by many modules -- it is reachable if
    # any importer is reachable)
    all_reachable: set[str] = set(reachable_from_roots)
    for root in roots:
        all_reachable |= _reachable_from(root, forward)

    for nid, node in nodes.items():
        if node.get("kind") not in ("function", "class", "component", "hook", "module"):
            continue
        if not _in_scope(node.get("file"), changed_files):
            continue
        # Skip test files themselves
        if _is_test_file(node.get("file", "")):
            continue
        # Skip entrypoints
        if nid in roots:
            continue

        tags = set(node.get("tags", []))
        if "dead_code" in tags:
            # Already tagged; just confirm
            continue

        if nid not in all_reachable:
            findings.append(_finding(
                "warning",
                "orphan",
                f"'{node['name']}' is unreachable from any entrypoint or test",
                node_id=nid,
                file=node.get("file"),
                line=node.get("span", {}).get("start"),
                suggestion="Remove the dead code or add an entrypoint/test that exercises it",
            ))

    return findings


# ---------------------------------------------------------------------------
# Check: Pattern consistency
# ---------------------------------------------------------------------------

def check_pattern_consistency(
    graph: dict,
    nodes: dict[str, dict],
    changed_files: list[str] | None,
) -> list[Finding]:
    """Compare decorator usage and naming conventions against codebase norms."""
    findings: list[Finding] = []

    # Gather decorator usage frequencies per node kind
    kind_decorators: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    kind_naming: dict[str, list[str]] = defaultdict(list)

    for node in nodes.values():
        kind = node.get("kind", "")
        name = node.get("name", "")
        sigs = node.get("signatures", {})
        decorators = sigs.get("decorators", [])

        if isinstance(decorators, list):
            for dec in decorators:
                kind_decorators[kind][dec] += 1

        kind_naming[kind].append(name)

    # Determine dominant patterns per kind
    # A decorator is "dominant" if used by >= 60% of nodes of that kind
    dominant_decorators: dict[str, set[str]] = {}
    for kind, dec_counts in kind_decorators.items():
        total = sum(dec_counts.values())
        if total < 2:
            continue
        # Count how many distinct nodes of this kind exist
        kind_node_count = sum(1 for n in nodes.values() if n.get("kind") == kind)
        dominant = set()
        for dec, count in dec_counts.items():
            if kind_node_count > 0 and count / kind_node_count >= 0.6:
                dominant.add(dec)
        if dominant:
            dominant_decorators[kind] = dominant

    # Determine naming convention per kind (snake_case vs camelCase vs PascalCase)
    _SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
    _CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*$")
    _PASCAL = re.compile(r"^[A-Z][a-zA-Z0-9]*$")

    def _classify_name(name: str) -> str | None:
        if _SNAKE.match(name):
            return "snake_case"
        if _PASCAL.match(name):
            return "PascalCase"
        if _CAMEL.match(name):
            return "camelCase"
        return None

    dominant_naming: dict[str, str] = {}
    for kind, names in kind_naming.items():
        if len(names) < 3:
            continue
        convention_counts: dict[str, int] = defaultdict(int)
        for name in names:
            conv = _classify_name(name)
            if conv:
                convention_counts[conv] += 1
        if convention_counts:
            dominant_conv = max(convention_counts, key=lambda c: convention_counts[c])
            total_classified = sum(convention_counts.values())
            if convention_counts[dominant_conv] / total_classified >= 0.7:
                dominant_naming[kind] = dominant_conv

    # Now flag deviations in scoped files
    for nid, node in nodes.items():
        if not _in_scope(node.get("file"), changed_files):
            continue

        kind = node.get("kind", "")
        name = node.get("name", "")
        sigs = node.get("signatures", {})
        decorators = set(sigs.get("decorators", [])) if isinstance(sigs.get("decorators"), list) else set()

        # Check decorator consistency
        if kind in dominant_decorators:
            missing = dominant_decorators[kind] - decorators
            for dec in missing:
                findings.append(_finding(
                    "info",
                    "pattern_consistency",
                    (
                        f"'{name}' ({kind}) is missing decorator '@{dec}' "
                        f"which is used by most {kind}s in the codebase"
                    ),
                    node_id=nid,
                    file=node.get("file"),
                    line=node.get("span", {}).get("start"),
                    suggestion=f"Consider adding '@{dec}' for consistency",
                ))

        # Check naming convention
        if kind in dominant_naming:
            expected_conv = dominant_naming[kind]
            actual_conv = _classify_name(name)
            if actual_conv and actual_conv != expected_conv:
                findings.append(_finding(
                    "info",
                    "pattern_consistency",
                    (
                        f"'{name}' uses {actual_conv} but most {kind}s "
                        f"use {expected_conv}"
                    ),
                    node_id=nid,
                    file=node.get("file"),
                    line=node.get("span", {}).get("start"),
                    suggestion=f"Rename to follow {expected_conv} convention",
                ))

    return findings


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def validate_flows(
    graph_path: Path,
    output_path: Path,
    changed_files: list[str] | None,
) -> dict:
    """Run all flow validation checks and produce the diagnostics report."""
    with open(graph_path) as f:
        graph = json.load(f)

    nodes = _build_node_index(graph)
    forward, reverse = _build_adjacency(graph)

    all_findings: list[Finding] = []

    # 1. Reachability
    reachability_findings, entrypoints_checked = check_reachability(
        graph, nodes, forward, changed_files,
    )
    all_findings.extend(reachability_findings)

    # 2. Disconnected flows
    disconnected_findings = check_disconnected_flows(
        graph, nodes, forward, reverse, changed_files,
    )
    all_findings.extend(disconnected_findings)

    # 3. Test coverage alignment
    coverage_findings, flows_with, flows_without = check_test_coverage(
        graph, nodes, forward, reverse, changed_files,
    )
    all_findings.extend(coverage_findings)

    # 4. Orphaned code
    orphan_findings = check_orphaned_code(
        graph, nodes, forward, reverse, changed_files,
    )
    all_findings.extend(orphan_findings)

    # 5. Pattern consistency
    pattern_findings = check_pattern_consistency(graph, nodes, changed_files)
    all_findings.extend(pattern_findings)

    # Build summary
    errors = sum(1 for f in all_findings if f["severity"] == "error")
    warnings = sum(1 for f in all_findings if f["severity"] == "warning")
    info = sum(1 for f in all_findings if f["severity"] == "info")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "changed" if changed_files is not None else "full",
        "changed_files": changed_files or [],
        "findings": all_findings,
        "summary": {
            "total_findings": len(all_findings),
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "entrypoints_checked": entrypoints_checked,
            "flows_with_coverage": flows_with,
            "flows_without_coverage": flows_without,
        },
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate architecture flows: reachability, test coverage, orphans, and pattern consistency.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path(".architecture/architecture.graph.json"),
        help="Path to architecture.graph.json (default: .architecture/architecture.graph.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/architecture.diagnostics.json"),
        help="Path to write the diagnostics JSON (default: .architecture/architecture.diagnostics.json)",
    )
    parser.add_argument(
        "--files",
        type=str,
        default=None,
        help="Comma-separated list of files to scope validation to",
    )
    parser.add_argument(
        "--diff",
        type=str,
        default=None,
        help='Git diff spec to resolve changed files (e.g., "main...HEAD" or "git diff --name-only main...HEAD")',
    )
    parser.add_argument(
        "--glob",
        type=str,
        default=None,
        help='Glob pattern to match changed files (e.g., "src/**/*.py")',
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.graph.exists():
        print(f"Error: graph file not found: {args.graph}", file=sys.stderr)
        print(
            "Generate the architecture graph first, then run this validator.",
            file=sys.stderr,
        )
        return 1

    changed_files = _resolve_changed_files(args.files, args.diff, args.glob)

    report = validate_flows(args.graph, args.output, changed_files)

    summary = report["summary"]
    scope_label = f" (scope: {len(report['changed_files'])} files)" if report["scope"] == "changed" else ""
    print(f"Flow validation complete{scope_label}.")
    print(f"  Entrypoints checked: {summary['entrypoints_checked']}")
    print(f"  Flows with test coverage: {summary['flows_with_coverage']}")
    print(f"  Flows without test coverage: {summary['flows_without_coverage']}")
    print(f"  Findings: {summary['total_findings']} total "
          f"({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info)")
    print(f"  Output: {args.output}")

    if summary["errors"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
