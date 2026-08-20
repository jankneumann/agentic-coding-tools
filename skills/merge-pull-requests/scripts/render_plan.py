#!/usr/bin/env python3
"""Render a merge-plan JSON document as a human-readable projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from merge_plan import validate_plan


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_plan(plan: dict[str, Any]) -> str:
    """Return a pure Markdown projection of a validated plan."""

    validate_plan(plan)
    lines = [
        "# Merge Plan",
        "",
        f"- Schema: `{plan['schema_version']}`",
        f"- Generated: `{plan['generated_at']}`",
        f"- Authoritative storage: `{plan['storage_tier']}`",
        f"- Base branch: `{plan.get('base_branch', 'main')}`",
        "",
        "## Nodes",
        "",
        "| PR | Title | Origin | Outcome | Strategy | Auto | Gates | Revalidate |",
        "|----|-------|--------|---------|----------|------|-------|------------|",
    ]
    for node in plan["nodes"]:
        definition = node["definition"]
        state = node["state"]
        gates = ", ".join(definition["gates"]) or "—"
        lines.append(
            "| "
            f"#{node['pr']} | {_cell(node.get('title', ''))} | {node['origin']} | "
            f"{state['outcome']} | {node['strategy']} | "
            f"{'yes' if node['auto_executable'] else 'no'} | {_cell(gates)} | "
            f"{'yes' if state.get('needs_revalidation', False) else 'no'} |",
        )

    lines.extend(["", "## Dependency Edges", ""])
    edges = [
        f"- #{node['pr']} → #{dependency}"
        for node in plan["nodes"]
        for dependency in node["definition"]["depends_on"]
    ]
    lines.extend(edges or ["- None"])
    lines.append("")
    return "\n".join(lines)


def write_projection(plan: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_plan(plan), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    output = args.output or args.plan.with_suffix(".md")
    write_projection(plan, output)
    print(json.dumps({"projection": str(output), "nodes": len(plan["nodes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
