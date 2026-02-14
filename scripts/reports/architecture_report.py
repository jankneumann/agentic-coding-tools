#!/usr/bin/env python3
"""Architecture report aggregator — produce architecture.report.md from Layer 2 outputs.

Reads all Layer 2 JSON artifacts and optionally embeds Mermaid diagrams from
generate_views.py to produce a unified human-readable Markdown report.

Usage:
    python scripts/reports/architecture_report.py --input-dir .architecture --output .architecture/architecture.report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arch_utils.graph_io import load_graph  # noqa: E402
logger = logging.getLogger(__name__)

from generate_views import (  # noqa: E402
    generate_backend_component_view,
    generate_container_view,
    generate_db_erd,
    generate_frontend_component_view,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Graph = dict[str, Any]


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if missing."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _fmt_count(n: int, singular: str) -> str:
    """Format a count with singular/plural noun."""
    return f"{n} {singular}{'s' if n != 1 else ''}"


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------


def _section_header(graph: Graph, summary: dict[str, Any] | None) -> str:
    """Build the report header with generation metadata and stats."""
    lines: list[str] = ["# Architecture Report", ""]

    git_sha = "unknown"
    generated_at = datetime.now(timezone.utc).isoformat()

    if summary:
        git_sha = summary.get("git_sha", git_sha)
        generated_at = summary.get("generated_at", generated_at)

    lines.append(f"Generated: {generated_at}  ")
    lines.append(f"Git SHA: `{git_sha}`")
    lines.append("")

    stats = summary.get("stats", {}) if summary else {}
    nodes = stats.get("total_nodes", len(graph.get("nodes", [])))
    edges = stats.get("total_edges", len(graph.get("edges", [])))
    entrypoints = stats.get("entrypoint_count", len(graph.get("entrypoints", [])))

    lines.append("## Overview")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Nodes | {nodes} |")
    lines.append(f"| Edges | {edges} |")
    lines.append(f"| Entrypoints | {entrypoints} |")

    by_language = stats.get("by_language", {})
    if by_language:
        for lang, count in sorted(by_language.items()):
            lines.append(f"| {lang.title()} nodes | {count} |")

    lines.append("")
    return "\n".join(lines)


def _section_cross_layer_flows(
    summary: dict[str, Any] | None,
    flows_data: dict[str, Any] | None,
) -> str:
    """Build the cross-layer flows section."""
    lines: list[str] = ["## Cross-Layer Flows", ""]

    flows = []
    if flows_data and "flows" in flows_data:
        flows = flows_data["flows"]
    elif summary and "cross_layer_flows" in summary:
        flows = summary["cross_layer_flows"]

    if not flows:
        lines.append("No cross-layer flows detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"{_fmt_count(len(flows), 'flow')} detected spanning frontend → backend → database.")
    lines.append("")

    # Group by confidence
    by_conf: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}
    for flow in flows:
        conf = flow.get("confidence", "medium")
        by_conf.setdefault(conf, []).append(flow)

    for conf_level in ["high", "medium", "low"]:
        conf_flows = by_conf.get(conf_level, [])
        if not conf_flows:
            continue
        lines.append(f"### {conf_level.title()} Confidence ({len(conf_flows)})")
        lines.append("")
        for flow in conf_flows[:10]:
            frontend = flow.get("frontend_component", "?")
            api_url = flow.get("api_url", "?")
            handler = flow.get("backend_handler", "?")
            tables = flow.get("db_tables", [])
            table_str = ", ".join(f"`{t}`" for t in tables) if tables else "none"
            lines.append(f"- `{frontend}` → `{api_url}` → `{handler}` → {table_str}")
        if len(conf_flows) > 10:
            lines.append(f"- ... and {len(conf_flows) - 10} more")
        lines.append("")

    return "\n".join(lines)


def _section_diagnostics(diagnostics: dict[str, Any] | None) -> str:
    """Build the diagnostics section."""
    lines: list[str] = ["## Diagnostics", ""]

    if not diagnostics:
        lines.append("No diagnostics data available.")
        lines.append("")
        return "\n".join(lines)

    summary = diagnostics.get("summary", {})
    lines.append(f"| Severity | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Errors | {summary.get('errors', 0)} |")
    lines.append(f"| Warnings | {summary.get('warnings', 0)} |")
    lines.append(f"| Info | {summary.get('info', 0)} |")
    lines.append("")

    findings = diagnostics.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warnings = [f for f in findings if f.get("severity") == "warning"]

    if errors:
        lines.append("### Errors")
        lines.append("")
        for finding in errors[:20]:
            lines.append(f"- **{finding.get('check', '?')}**: {finding.get('message', '?')}")
        if len(errors) > 20:
            lines.append(f"- ... and {len(errors) - 20} more")
        lines.append("")

    if warnings:
        lines.append("### Warnings")
        lines.append("")
        for finding in warnings[:20]:
            lines.append(f"- **{finding.get('check', '?')}**: {finding.get('message', '?')}")
        if len(warnings) > 20:
            lines.append(f"- ... and {len(warnings) - 20} more")
        lines.append("")

    return "\n".join(lines)


def _section_impact_analysis(impact_data: dict[str, Any] | None) -> str:
    """Build the impact analysis section."""
    lines: list[str] = ["## High-Impact Nodes", ""]

    if not impact_data:
        lines.append("No impact analysis data available.")
        lines.append("")
        return "\n".join(lines)

    nodes = impact_data.get("high_impact_nodes", [])
    threshold = impact_data.get("threshold", 5)

    if not nodes:
        lines.append(f"No nodes with >= {threshold} transitive dependents.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"{_fmt_count(len(nodes), 'node')} with >= {threshold} transitive dependents:")
    lines.append("")
    lines.append("| Node | Dependents |")
    lines.append("|------|------------|")
    for node in nodes[:30]:
        lines.append(f"| `{node.get('id', '?')}` | {node.get('dependent_count', 0)} |")
    if len(nodes) > 30:
        lines.append(f"| ... | {len(nodes) - 30} more |")
    lines.append("")

    return "\n".join(lines)


def _section_parallel_zones(zones_data: dict[str, Any] | None) -> str:
    """Build the parallel zones section."""
    lines: list[str] = ["## Parallel Modification Zones", ""]

    if not zones_data:
        lines.append("No parallel zones data available.")
        lines.append("")
        return "\n".join(lines)

    zones = zones_data.get("zones", [])
    if not zones:
        lines.append("No independent modification zones detected.")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"{_fmt_count(len(zones), 'independent zone')} for safe parallel modification:")
    lines.append("")

    for i, zone in enumerate(zones[:15], 1):
        members = zone.get("members", zone.get("nodes", []))
        zone_name = zone.get("name", f"Zone {i}")
        lines.append(f"### {zone_name} ({_fmt_count(len(members), 'member')})")
        lines.append("")
        for member in members[:10]:
            if isinstance(member, str):
                lines.append(f"- `{member}`")
            else:
                lines.append(f"- `{member.get('id', '?')}`")
        if len(members) > 10:
            lines.append(f"- ... and {len(members) - 10} more")
        lines.append("")

    if len(zones) > 15:
        lines.append(f"... and {len(zones) - 15} more zones")
        lines.append("")

    return "\n".join(lines)


def _section_disconnected(summary: dict[str, Any] | None) -> str:
    """Build the disconnected endpoints section."""
    lines: list[str] = []

    if not summary:
        return ""

    disconnected_eps = summary.get("disconnected_endpoints", [])
    disconnected_fc = summary.get("disconnected_frontend_calls", [])

    if not disconnected_eps and not disconnected_fc:
        return ""

    lines.append("## Disconnected Endpoints")
    lines.append("")

    if disconnected_eps:
        lines.append(f"### Backend Routes Without Frontend Callers ({len(disconnected_eps)})")
        lines.append("")
        for ep in disconnected_eps[:20]:
            lines.append(f"- `{ep.get('node_id', '?')}` — {ep.get('path', '?')}")
        if len(disconnected_eps) > 20:
            lines.append(f"- ... and {len(disconnected_eps) - 20} more")
        lines.append("")

    if disconnected_fc:
        lines.append(f"### Frontend Calls Without Backend Matches ({len(disconnected_fc)})")
        lines.append("")
        for fc in disconnected_fc[:20]:
            lines.append(f"- `{fc.get('node_id', '?')}` — {fc.get('url', '?')}")
        if len(disconnected_fc) > 20:
            lines.append(f"- ... and {len(disconnected_fc) - 20} more")
        lines.append("")

    return "\n".join(lines)


def _section_mermaid_diagrams(graph: Graph) -> str:
    """Build the Mermaid diagrams section."""
    lines: list[str] = ["## Architecture Diagrams", ""]

    lines.append("### Container View")
    lines.append("")
    lines.append("```mermaid")
    lines.append(generate_container_view(graph).rstrip())
    lines.append("```")
    lines.append("")

    lines.append("### Backend Components")
    lines.append("")
    lines.append("```mermaid")
    lines.append(generate_backend_component_view(graph).rstrip())
    lines.append("```")
    lines.append("")

    lines.append("### Frontend Components")
    lines.append("")
    lines.append("```mermaid")
    lines.append(generate_frontend_component_view(graph).rstrip())
    lines.append("```")
    lines.append("")

    lines.append("### Database ERD")
    lines.append("")
    lines.append("```mermaid")
    lines.append(generate_db_erd(graph).rstrip())
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def generate_report(
    graph: Graph,
    summary: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None,
    flows_data: dict[str, Any] | None,
    impact_data: dict[str, Any] | None,
    zones_data: dict[str, Any] | None,
) -> str:
    """Assemble the full Markdown report from all Layer 2 outputs."""
    sections = [
        _section_header(graph, summary),
        _section_cross_layer_flows(summary, flows_data),
        _section_diagnostics(diagnostics),
        _section_impact_analysis(impact_data),
        _section_parallel_zones(zones_data),
        _section_disconnected(summary),
        _section_mermaid_diagrams(graph),
    ]
    return "\n".join(s for s in sections if s)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate Layer 2 outputs into a unified architecture report.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(".architecture"),
        help="Directory containing Layer 2 JSON artifacts (default: .architecture)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".architecture/architecture.report.md"),
        help="Output path for the Markdown report (default: .architecture/architecture.report.md)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    input_dir: Path = args.input_dir

    # Load the canonical graph (required)
    graph = load_graph(input_dir / "architecture.graph.json")
    if not graph:
        logger.error("architecture.graph.json not found or empty.")
        return 1

    # Load optional Layer 2 outputs
    summary = _load_json(input_dir / "architecture.summary.json")
    diagnostics = _load_json(input_dir / "architecture.diagnostics.json")
    flows_data = _load_json(input_dir / "cross_layer_flows.json")
    impact_data = _load_json(input_dir / "high_impact_nodes.json")
    zones_data = _load_json(input_dir / "parallel_zones.json")

    report = generate_report(graph, summary, diagnostics, flows_data, impact_data, zones_data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(report)
    logger.info(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
