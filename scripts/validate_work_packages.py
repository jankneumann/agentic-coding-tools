#!/usr/bin/env python3
"""Validate work-packages.yaml against work-packages.schema.json.

Performs:
1. YAML-to-JSON parsing
2. JSON Schema validation against work-packages.schema.json
3. DAG cycle detection (topological sort)
4. Lock key canonicalization checks
5. Scope non-overlap validation for parallel packages (optional, via --check-overlap)

Run via agent-coordinator venv:
  agent-coordinator/.venv/bin/python scripts/validate_work_packages.py <path-to-work-packages.yaml>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

try:
    import jsonschema
except ImportError:
    sys.exit("jsonschema is required: pip install jsonschema")


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "openspec" / "schemas" / "work-packages.schema.json"

# Lock key canonicalization patterns
LOCK_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "api": re.compile(r"^api:[A-Z]+ /.+$"),
    "db:migration-slot": re.compile(r"^db:migration-slot$"),
    "db:schema": re.compile(r"^db:schema:[a-z][a-z0-9_]*$"),
    "event": re.compile(r"^event:[a-z][a-z0-9.]*$"),
    "flag": re.compile(r"^flag:[a-z][a-z0-9/.*]*$"),
    "env": re.compile(r"^env:[a-z][a-z0-9_-]*$"),
    "contract": re.compile(r"^contract:.+$"),
    "feature": re.compile(r"^feature:[A-Za-z0-9._:-]+:[a-z]+$"),
}


def load_schema() -> dict[str, Any]:
    """Load the work-packages JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_work_packages(path: Path) -> dict[str, Any]:
    """Load and parse work-packages.yaml."""
    with open(path) as f:
        return yaml.safe_load(f)


def validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate data against JSON schema, return list of errors."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"  {path}: {error.message}" if path else f"  {error.message}")
    return errors


def detect_cycles(packages: list[dict[str, Any]]) -> list[list[str]]:
    """Detect cycles in the package dependency DAG.

    Returns list of cycles (each cycle is a list of package_ids).
    """
    id_set = {p["package_id"] for p in packages}
    adj: dict[str, list[str]] = defaultdict(list)
    for p in packages:
        for dep in p.get("depends_on", []):
            if dep in id_set:
                adj[dep].append(p["package_id"])

    # Kahn's algorithm for topological sort
    in_degree: dict[str, int] = {p["package_id"]: 0 for p in packages}
    for p in packages:
        for dep in p.get("depends_on", []):
            if dep in id_set:
                in_degree[p["package_id"]] = in_degree.get(p["package_id"], 0) + 1

    queue: deque[str] = deque(pid for pid, deg in in_degree.items() if deg == 0)
    sorted_nodes: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_nodes.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_nodes) == len(packages):
        return []

    # There are cycles — find them via DFS
    remaining = id_set - set(sorted_nodes)
    cycles: list[list[str]] = []
    visited: set[str] = set()

    for start in remaining:
        if start in visited:
            continue
        path: list[str] = []
        path_set: set[str] = set()
        stack: list[tuple[str, bool]] = [(start, False)]

        while stack:
            node, processed = stack.pop()
            if processed:
                path.pop()
                path_set.discard(node)
                continue

            if node in path_set:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                continue

            visited.add(node)
            path.append(node)
            path_set.add(node)
            stack.append((node, True))

            for dep in adj.get(node, []):
                if dep in remaining:
                    stack.append((dep, False))

    return cycles


def validate_lock_keys(packages: list[dict[str, Any]]) -> list[str]:
    """Validate lock key canonicalization for all packages."""
    # Sort prefixes longest-first so "db:schema" matches before "db:migration-slot"
    sorted_prefixes = sorted(LOCK_KEY_PATTERNS.keys(), key=len, reverse=True)
    errors = []
    for pkg in packages:
        pid = pkg["package_id"]
        for key in pkg.get("locks", {}).get("keys", []):
            matched = False
            for pat_prefix in sorted_prefixes:
                if key == pat_prefix or key.startswith(pat_prefix + ":") or key.startswith(pat_prefix + " "):
                    pattern = LOCK_KEY_PATTERNS[pat_prefix]
                    if pattern.match(key):
                        matched = True
                    else:
                        errors.append(
                            f"  {pid}: key '{key}' matches prefix '{pat_prefix}' "
                            f"but fails canonicalization (expected pattern: {pattern.pattern})"
                        )
                        matched = True  # Don't double-report
                    break

            if not matched:
                errors.append(f"  {pid}: key '{key}' has unrecognized namespace prefix")

    return errors


def validate_depends_on_refs(packages: list[dict[str, Any]]) -> list[str]:
    """Validate that all depends_on references point to existing package_ids."""
    id_set = {p["package_id"] for p in packages}
    errors = []
    for pkg in packages:
        for dep in pkg.get("depends_on", []):
            if dep not in id_set:
                errors.append(f"  {pkg['package_id']}: depends_on '{dep}' not found in packages")
    return errors


def get_parallel_pairs(packages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Find all pairs of packages that can run in parallel.

    Two packages can run in parallel if neither depends (transitively) on the other.
    """
    id_set = {p["package_id"] for p in packages}
    # Build transitive dependency sets
    deps: dict[str, set[str]] = {p["package_id"]: set() for p in packages}
    adj: dict[str, set[str]] = defaultdict(set)
    for p in packages:
        for d in p.get("depends_on", []):
            if d in id_set:
                adj[d].add(p["package_id"])
                deps[p["package_id"]].add(d)

    # Compute transitive closure
    trans: dict[str, set[str]] = {}
    for pid in id_set:
        visited: set[str] = set()
        queue: deque[str] = deque(deps[pid])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(deps.get(node, set()) - visited)
        trans[pid] = visited

    pairs = []
    pkg_ids = sorted(id_set)
    for i, a in enumerate(pkg_ids):
        for b in pkg_ids[i + 1 :]:
            if b not in trans[a] and a not in trans[b]:
                pairs.append((a, b))
    return pairs


def validate_scope_overlap(packages: list[dict[str, Any]]) -> list[str]:
    """Check that parallel packages have non-overlapping write_allow scopes."""
    from fnmatch import fnmatch

    pkg_map = {p["package_id"]: p for p in packages}
    pairs = get_parallel_pairs(packages)
    errors = []

    for a_id, b_id in pairs:
        # Skip wp-integration (it's allowed to overlap with everything)
        if a_id == "wp-integration" or b_id == "wp-integration":
            continue

        a_writes = pkg_map[a_id].get("scope", {}).get("write_allow", [])
        b_writes = pkg_map[b_id].get("scope", {}).get("write_allow", [])

        # Check if any glob from A matches any glob from B (approximate)
        for a_glob in a_writes:
            for b_glob in b_writes:
                if fnmatch(a_glob, b_glob) or fnmatch(b_glob, a_glob) or a_glob == b_glob:
                    errors.append(
                        f"  parallel pair ({a_id}, {b_id}): "
                        f"write_allow overlap: '{a_glob}' vs '{b_glob}'"
                    )

    return errors


def validate_lock_overlap(packages: list[dict[str, Any]]) -> list[str]:
    """Check that parallel packages have non-overlapping lock keys."""
    pkg_map = {p["package_id"]: p for p in packages}
    pairs = get_parallel_pairs(packages)
    errors = []

    for a_id, b_id in pairs:
        if a_id == "wp-integration" or b_id == "wp-integration":
            continue

        a_keys = set(pkg_map[a_id].get("locks", {}).get("keys", []))
        b_keys = set(pkg_map[b_id].get("locks", {}).get("keys", []))
        overlap = a_keys & b_keys
        if overlap:
            errors.append(
                f"  parallel pair ({a_id}, {b_id}): "
                f"lock key overlap: {sorted(overlap)}"
            )

        a_files = set(pkg_map[a_id].get("locks", {}).get("files", []))
        b_files = set(pkg_map[b_id].get("locks", {}).get("files", []))
        file_overlap = a_files & b_files
        if file_overlap:
            errors.append(
                f"  parallel pair ({a_id}, {b_id}): "
                f"file lock overlap: {sorted(file_overlap)}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate work-packages.yaml against schema and constraints"
    )
    parser.add_argument("path", type=Path, help="Path to work-packages.yaml")
    parser.add_argument(
        "--check-overlap",
        action="store_true",
        help="Also check scope and lock overlap for parallel packages",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="Path to work-packages.schema.json (default: auto-detected)",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: {args.path} not found", file=sys.stderr)
        return 1

    if not args.schema.exists():
        print(f"Error: schema not found at {args.schema}", file=sys.stderr)
        return 1

    # Load
    schema = load_schema() if args.schema == SCHEMA_PATH else json.loads(args.schema.read_text())
    data = load_work_packages(args.path)

    results: dict[str, Any] = {
        "file": str(args.path),
        "valid": True,
        "checks": {},
    }

    # 1. JSON Schema validation
    schema_errors = validate_schema(data, schema)
    results["checks"]["schema"] = {"passed": not schema_errors, "errors": schema_errors}
    if schema_errors:
        results["valid"] = False

    packages = data.get("packages", [])

    # 2. depends_on reference validation
    ref_errors = validate_depends_on_refs(packages)
    results["checks"]["depends_on_refs"] = {"passed": not ref_errors, "errors": ref_errors}
    if ref_errors:
        results["valid"] = False

    # 3. DAG cycle detection
    cycles = detect_cycles(packages)
    results["checks"]["dag_cycles"] = {
        "passed": not cycles,
        "cycles": [c for c in cycles],
    }
    if cycles:
        results["valid"] = False

    # 4. Lock key canonicalization
    key_errors = validate_lock_keys(packages)
    results["checks"]["lock_keys"] = {"passed": not key_errors, "errors": key_errors}
    if key_errors:
        results["valid"] = False

    # 5. Optional: scope and lock overlap
    if args.check_overlap:
        scope_errors = validate_scope_overlap(packages)
        results["checks"]["scope_overlap"] = {"passed": not scope_errors, "errors": scope_errors}
        if scope_errors:
            results["valid"] = False

        lock_errors = validate_lock_overlap(packages)
        results["checks"]["lock_overlap"] = {"passed": not lock_errors, "errors": lock_errors}
        if lock_errors:
            results["valid"] = False

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        status = "VALID" if results["valid"] else "INVALID"
        print(f"work-packages validation: {status}")
        for check_name, check_result in results["checks"].items():
            symbol = "pass" if check_result["passed"] else "FAIL"
            print(f"  [{symbol}] {check_name}")
            for err in check_result.get("errors", []):
                print(f"    {err}")
            for cycle in check_result.get("cycles", []):
                print(f"    cycle: {' -> '.join(cycle)}")

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
