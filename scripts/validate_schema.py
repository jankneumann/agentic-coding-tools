#!/usr/bin/env python3
"""Validate an architecture.graph.json file against the canonical schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema


SCHEMA_PATH = Path(__file__).parent / "architecture_schema.json"


def load_schema() -> dict:
    """Load the canonical architecture graph JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_graph(graph_path: str | Path) -> list[str]:
    """Validate an architecture graph JSON file.

    Returns a list of error messages. Empty list means valid.
    """
    schema = load_schema()
    with open(graph_path) as f:
        graph = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(graph), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)

    # Additional semantic checks beyond JSON Schema
    node_ids = {n["id"] for n in graph.get("nodes", [])}

    for i, edge in enumerate(graph.get("edges", [])):
        if edge["from"] not in node_ids:
            errors.append(f"edges[{i}].from: node '{edge['from']}' not found in nodes")
        if edge["to"] not in node_ids:
            errors.append(f"edges[{i}].to: node '{edge['to']}' not found in nodes")

    for i, ep in enumerate(graph.get("entrypoints", [])):
        if ep["node_id"] not in node_ids:
            errors.append(
                f"entrypoints[{i}].node_id: node '{ep['node_id']}' not found in nodes"
            )

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <architecture.graph.json>", file=sys.stderr)
        return 1

    graph_path = Path(sys.argv[1])
    if not graph_path.exists():
        print(f"File not found: {graph_path}", file=sys.stderr)
        return 1

    errors = validate_graph(graph_path)
    if errors:
        print(f"Validation failed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
