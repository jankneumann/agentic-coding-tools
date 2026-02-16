#!/usr/bin/env python3
"""Architecture report generator — produce an explanatory architecture.report.md.

Reads Layer 2 JSON artifacts and python_analysis.json to produce a narrative
Markdown report that tells the story of the architecture.  All narrative is
derived algorithmically from the graph data — no LLM calls.

Supports an optional ``architecture.config.yaml`` configuration file that
controls section selection, health diagnostics, project identity overrides,
and best-practices references.  See ``config_schema.py`` for the schema.

Usage:
    python scripts/reports/architecture_report.py \
        --input-dir docs/architecture-analysis \
        --output docs/architecture-analysis/architecture.report.md

    # With explicit config file
    python scripts/reports/architecture_report.py --config architecture.config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
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
from reports.config_schema import (  # noqa: E402
    KNOWN_SECTIONS,
    ReportConfig,
    load_config,
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Graph = dict[str, Any]
PyAnalysis = dict[str, Any]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if missing."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _fmt_count(n: int, singular: str, plural: str | None = None) -> str:
    """Format a count with singular/plural noun."""
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural or singular + ('es' if singular.endswith(('s', 'sh', 'ch', 'x', 'z')) else 's')}"


def _short_id(node_id: str) -> str:
    """Strip the ``py:`` prefix from a node ID for display."""
    return node_id.removeprefix("py:").removeprefix("sql:")


def _module_name(node_id: str) -> str:
    """Extract module name from a qualified node ID like ``py:config.get_config``."""
    bare = _short_id(node_id)
    return bare.split(".")[0]


def _mod_name_from_entry(mod: dict[str, Any]) -> str:
    """Get a module's short name from either ``name`` or ``qualified_name``."""
    if "name" in mod:
        return mod["name"]
    qn = mod.get("qualified_name", "")
    # qualified_name might be e.g. "agent_coordinator.main" — take the last part
    return qn.rsplit(".", 1)[-1] if qn else ""


def _build_function_index(py: PyAnalysis | None) -> dict[str, dict[str, Any]]:
    """Index functions by qualified_name for fast lookup."""
    if not py:
        return {}
    return {f["qualified_name"]: f for f in py.get("functions", [])}


def _first_line(text: str | None) -> str:
    """Return the first non-empty sentence from a docstring."""
    if not text:
        return ""
    line = text.strip().split("\n")[0].strip()
    # Truncate at 80 chars
    if len(line) > 80:
        line = line[:77] + "..."
    return line


# ---------------------------------------------------------------------------
# Section: System Overview
# ---------------------------------------------------------------------------


def _section_system_overview(
    graph: Graph,
    summary: dict[str, Any] | None,
    py: PyAnalysis | None,
    config: ReportConfig | None = None,
) -> str:
    """Narrative overview: what the system is, at a glance."""
    cfg = config or ReportConfig()
    lines: list[str] = ["# Architecture Report", ""]

    # Project identity from config
    if cfg.project.name or cfg.project.description:
        if cfg.project.name and cfg.project.description:
            lines.append(f"**{cfg.project.name}** — {cfg.project.description}")
        elif cfg.project.name:
            lines.append(f"**{cfg.project.name}**")
        else:
            lines.append(cfg.project.description)
        lines.append("")

    # Metadata
    git_sha = "unknown"
    generated_at = datetime.now(timezone.utc).isoformat()
    if summary:
        git_sha = summary.get("git_sha", git_sha)
        generated_at = summary.get("generated_at", generated_at)
    lines.append(f"Generated: {generated_at}  ")
    lines.append(f"Git SHA: `{git_sha}`")
    lines.append("")

    # Derive stats
    stats = summary.get("stats", {}) if summary else {}
    by_kind = stats.get("by_kind", {})
    by_language = stats.get("by_language", {})
    entrypoint_count = stats.get("entrypoint_count", len(graph.get("entrypoints", [])))
    total_modules = by_kind.get("module", 0)
    total_functions = by_kind.get("function", 0)
    total_classes = by_kind.get("class", 0)
    total_tables = by_kind.get("table", 0)

    # Detect protocol — config override or auto-detect from entrypoints
    if cfg.project.protocol and cfg.project.protocol != "auto":
        protocol_map = {
            "mcp": "MCP server",
            "http": "HTTP service",
            "grpc": "gRPC service",
            "cli": "CLI application",
        }
        protocol = protocol_map.get(cfg.project.protocol.lower(), cfg.project.protocol)
    else:
        methods = Counter(
            ep.get("method", "unknown") for ep in graph.get("entrypoints", [])
        )
        protocol = "MCP server" if methods.get("MCP", 0) > 0 else "service"

    # Detect primary language — config override or auto-detect
    if cfg.project.primary_language:
        primary_lang = cfg.project.primary_language
    else:
        code_languages = {k: v for k, v in by_language.items() if k.lower() != "sql"}
        primary_lang = (
            max(code_languages, key=code_languages.get) if code_languages
            else "Python"
        )

    # Count async from python_analysis if available
    py_summary = py.get("summary", {}) if py else {}
    async_count = py_summary.get("async_functions", 0)

    # Classify entrypoints by decorator type
    tools_count = 0
    resources_count = 0
    prompts_count = 0
    if py:
        func_index = _build_function_index(py)
        for ep in py.get("entry_points", []):
            func_name = ep.get("function", "")
            func = func_index.get(func_name, {})
            decorators = " ".join(func.get("decorators", []))
            if "resource" in decorators:
                resources_count += 1
            elif "prompt" in decorators:
                prompts_count += 1
            else:
                tools_count += 1

    lines.append("## System Overview")
    lines.append("")
    lines.append(
        "*Data sources: "
        "[architecture.graph.json](architecture.graph.json), "
        "[architecture.summary.json](architecture.summary.json), "
        "[python_analysis.json](python_analysis.json)*"
    )
    lines.append("")

    # Build narrative paragraph
    parts = []
    parts.append(
        f"This is a **{primary_lang.title()} {protocol}** with "
        f"{total_modules} modules exposing "
        f"**{entrypoint_count} MCP endpoints**"
    )
    endpoint_parts = []
    if tools_count:
        endpoint_parts.append(_fmt_count(tools_count, "tool"))
    if resources_count:
        endpoint_parts.append(_fmt_count(resources_count, "resource"))
    if prompts_count:
        endpoint_parts.append(_fmt_count(prompts_count, "prompt"))
    if endpoint_parts:
        parts[-1] += f" ({', '.join(endpoint_parts)})"

    if total_tables:
        parts[-1] += f", backed by **{_fmt_count(total_tables, 'Postgres table')}**."
    else:
        parts[-1] += "."

    parts.append(
        f"The codebase contains {_fmt_count(total_functions, 'function')} "
        f"({async_count} async) and {_fmt_count(total_classes, 'class')}."
    )
    lines.append(" ".join(parts))
    lines.append("")

    # Quick stats table for precise numbers
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Total nodes | {stats.get('total_nodes', len(graph.get('nodes', [])))} |")
    lines.append(f"| Total edges | {stats.get('total_edges', len(graph.get('edges', [])))} |")
    lines.append(f"| Python modules | {total_modules} |")
    lines.append(f"| Functions | {total_functions} ({async_count} async) |")
    lines.append(f"| Classes | {total_classes} |")
    lines.append(f"| MCP endpoints | {entrypoint_count} |")
    if total_tables:
        lines.append(f"| DB tables | {total_tables} |")
    for lang, count in sorted(by_language.items()):
        lines.append(f"| {lang.title()} nodes | {count} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Module Responsibility Map
# ---------------------------------------------------------------------------


def _section_module_map(
    py: PyAnalysis | None,
    graph: Graph,
) -> str:
    """For each module, show its role, layer classification, and dependency counts."""
    lines: list[str] = ["## Module Responsibility Map", ""]
    lines.append(
        "*Data sources: "
        "[python_analysis.json](python_analysis.json), "
        "[architecture.graph.json](architecture.graph.json)*"
    )
    lines.append("")

    if not py:
        lines.append("No Python analysis data available.")
        lines.append("")
        return "\n".join(lines)

    modules = py.get("modules", [])

    # Compute edge counts per module from the graph
    in_degree: Counter[str] = Counter()
    out_degree: Counter[str] = Counter()
    for edge in graph.get("edges", []):
        from_mod = _module_name(edge.get("from", ""))
        to_mod = _module_name(edge.get("to", ""))
        if from_mod != to_mod:  # only cross-module edges
            out_degree[from_mod] += 1
            in_degree[to_mod] += 1

    # Classify modules into layers
    entry_modules: set[str] = set()
    for ep in py.get("entry_points", []):
        entry_modules.add(ep["function"].split(".")[0])

    # Foundation = imported by 3+ other modules
    importers: dict[str, set[str]] = defaultdict(set)
    module_names = {_mod_name_from_entry(m) for m in modules}
    for mod in modules:
        mod_short = _mod_name_from_entry(mod)
        for imp in mod.get("imports", []):
            if imp in module_names:
                importers[imp].add(mod_short)

    foundation_modules = {mod for mod, imps in importers.items() if len(imps) >= 3}

    def classify(mod_name: str) -> str:
        if mod_name in entry_modules:
            return "Entry"
        if mod_name in foundation_modules:
            return "Foundation"
        if mod_name == "__init__":
            return "Package"
        return "Service"

    # Derive role description from function names / docstrings
    def derive_role(mod_name: str) -> str:
        mod_funcs = [
            f for f in py.get("functions", [])
            if f["qualified_name"].split(".")[0] == mod_name
            and "." not in f["qualified_name"].split(f"{mod_name}.")[1]
            # skip nested class methods for the summary
        ]
        # Try first public function docstring
        for func in mod_funcs:
            doc = func.get("docstring")
            if doc:
                return _first_line(doc)

        # Try class-level: find first class method with docstring
        mod_class_funcs = [
            f for f in py.get("functions", [])
            if f["qualified_name"].startswith(f"{mod_name}.")
            and f.get("docstring")
        ]
        if mod_class_funcs:
            return _first_line(mod_class_funcs[0]["docstring"])

        # Fallback: summarize from function names
        func_names = [f.get("name", f["qualified_name"].rsplit(".", 1)[-1]) for f in mod_funcs[:5]]
        if func_names:
            return f"Provides: {', '.join(func_names)}"
        return "—"

    lines.append("| Module | Layer | Role | In / Out |")
    lines.append("|--------|-------|------|----------|")

    for mod in sorted(modules, key=lambda m: _mod_name_from_entry(m)):
        name = _mod_name_from_entry(mod)
        if name == "__init__":
            continue
        layer = classify(name)
        role = derive_role(name)
        in_c = in_degree.get(name, 0)
        out_c = out_degree.get(name, 0)
        lines.append(f"| `{name}` | {layer} | {role} | {in_c} / {out_c} |")

    lines.append("")
    lines.append(
        "**Layers**: Entry = exposes MCP endpoints; "
        "Service = domain logic; "
        "Foundation = imported by 3+ modules (config, db, audit)."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Dependency Layers
# ---------------------------------------------------------------------------


def _section_dependency_layers(
    py: PyAnalysis | None,
) -> str:
    """Show dependency flow as a layered text diagram."""
    lines: list[str] = ["## Dependency Layers", ""]
    lines.append(
        "*Data source: "
        "[python_analysis.json](python_analysis.json)*"
    )
    lines.append("")

    if not py:
        lines.append("No Python analysis data available.")
        lines.append("")
        return "\n".join(lines)

    modules = py.get("modules", [])
    module_names = {_mod_name_from_entry(m) for m in modules} - {"__init__"}

    # Build import adjacency (only internal modules)
    imports_from: dict[str, set[str]] = defaultdict(set)
    imported_by: dict[str, set[str]] = defaultdict(set)
    for mod in modules:
        name = _mod_name_from_entry(mod)
        for imp in mod.get("imports", []):
            if imp in module_names:
                imports_from[name].add(imp)
                imported_by[imp].add(name)

    # Classify
    entry_modules: set[str] = set()
    for ep in py.get("entry_points", []):
        entry_modules.add(ep["function"].split(".")[0])

    foundation = {m for m in module_names if len(imported_by.get(m, set())) >= 3}
    services = module_names - entry_modules - foundation

    lines.append("```")
    lines.append("┌─────────────────────────────────────────────────┐")
    if entry_modules:
        lines.append(f"│  ENTRY       {', '.join(sorted(entry_modules)):36s}│")
    lines.append("│             ↓ imports ↓                          │")
    if services:
        svc_list = sorted(services)
        # Split into rows of ~4 for readability
        rows = [svc_list[i:i + 4] for i in range(0, len(svc_list), 4)]
        first = True
        for row in rows:
            label = "  SERVICE    " if first else "             "
            lines.append(f"│{label} {', '.join(row):36s}│")
            first = False
    lines.append("│             ↓ imports ↓                          │")
    if foundation:
        lines.append(f"│  FOUNDATION  {', '.join(sorted(foundation)):36s}│")
    lines.append("└─────────────────────────────────────────────────┘")
    lines.append("```")
    lines.append("")

    # Single points of failure callout
    spof = [(m, len(imported_by.get(m, set()))) for m in foundation]
    spof.sort(key=lambda x: -x[1])
    if spof:
        lines.append("**Single points of failure** — changes to these modules ripple widely:")
        lines.append("")
        for mod, count in spof:
            lines.append(f"- `{mod}` — imported by {count} modules")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Entry Points
# ---------------------------------------------------------------------------


def _section_entry_points(
    graph: Graph,
    py: PyAnalysis | None,
) -> str:
    """Group entrypoints by type (tool/resource/prompt) with docstring excerpts."""
    lines: list[str] = ["## Entry Points", ""]
    lines.append(
        "*Data sources: "
        "[architecture.graph.json](architecture.graph.json), "
        "[python_analysis.json](python_analysis.json)*"
    )
    lines.append("")

    entrypoints = graph.get("entrypoints", [])
    if not entrypoints:
        lines.append("No entry points detected.")
        lines.append("")
        return "\n".join(lines)

    func_index = _build_function_index(py) if py else {}

    # Classify by decorator
    tools: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    prompts: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []

    for ep in entrypoints:
        node_id = ep.get("node_id", "")
        func_name = _short_id(node_id)
        func = func_index.get(func_name, {})
        decorators = " ".join(func.get("decorators", []))
        doc = _first_line(func.get("docstring"))
        entry = {"path": ep.get("path", "?"), "doc": doc, "func": func_name}

        if "resource" in decorators:
            resources.append(entry)
        elif "prompt" in decorators:
            prompts.append(entry)
        elif "tool" in decorators:
            tools.append(entry)
        else:
            other.append(entry)

    def _render_group(title: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        lines.append(f"### {title} ({len(items)})")
        lines.append("")
        lines.append("| Endpoint | Description |")
        lines.append("|----------|-------------|")
        for item in sorted(items, key=lambda x: x["path"]):
            lines.append(f"| `{item['path']}` | {item['doc']} |")
        lines.append("")

    _render_group("Tools", tools)
    _render_group("Resources", resources)
    _render_group("Prompts", prompts)
    _render_group("Other", other)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Architecture Health
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"error": 3, "warning": 2, "info": 1}


def _section_health(
    diagnostics: dict[str, Any] | None,
    config: ReportConfig | None = None,
) -> str:
    """Group findings by category with narrative explanations."""
    cfg = config or ReportConfig()
    expected_categories = set(cfg.health.expected_categories)
    category_explanations = cfg.health.category_explanations
    severity_thresholds = cfg.health.severity_thresholds

    lines: list[str] = ["## Architecture Health", ""]
    lines.append(
        "*Data source: "
        "[architecture.diagnostics.json](architecture.diagnostics.json)*"
    )
    lines.append("")

    if not diagnostics:
        lines.append("No diagnostics data available.")
        lines.append("")
        return "\n".join(lines)

    findings = diagnostics.get("findings", [])
    if not findings:
        lines.append("No issues found — architecture looks clean.")
        lines.append("")
        return "\n".join(lines)

    # Apply severity threshold filtering
    if severity_thresholds:
        filtered: list[dict[str, Any]] = []
        for f in findings:
            cat = f.get("category", "unknown")
            sev = f.get("severity", "info")
            threshold = severity_thresholds.get(cat)
            if threshold:
                min_level = _SEVERITY_ORDER.get(threshold, 0)
                if _SEVERITY_ORDER.get(sev, 0) < min_level:
                    continue
            filtered.append(f)
        findings = filtered

    if not findings:
        lines.append("No issues found above configured severity thresholds.")
        lines.append("")
        return "\n".join(lines)

    # Group by category
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_cat[f.get("category", "unknown")].append(f)

    # Summary counts
    lines.append(f"**{len(findings)} findings** across {len(by_cat)} categories:")
    lines.append("")

    # Sort: concerning first, expected last
    def sort_key(cat: str) -> tuple[int, str]:
        return (1 if cat in expected_categories else 0, cat)

    for cat in sorted(by_cat, key=sort_key):
        cat_findings = by_cat[cat]
        count = len(cat_findings)
        explanation = category_explanations.get(cat, "unclassified findings")
        expected = cat in expected_categories
        marker = " (expected)" if expected else ""

        lines.append(f"### {cat.replace('_', ' ').title()}{marker} — {count}")
        lines.append("")
        lines.append(f"{count} {explanation}.")
        lines.append("")

        # Group by severity within category
        by_sev: dict[str, int] = Counter(f.get("severity", "info") for f in cat_findings)
        if len(by_sev) > 1:
            sev_parts = [f"{v} {k}" for k, v in sorted(by_sev.items())]
            lines.append(f"Breakdown: {', '.join(sev_parts)}.")
            lines.append("")

        # Show a few examples
        examples = cat_findings[:5]
        for ex in examples:
            msg = ex.get("message", "")
            # Truncate long messages
            if len(msg) > 120:
                msg = msg[:117] + "..."
            lines.append(f"- {msg}")
        if count > 5:
            lines.append(f"- ... and {count - 5} more")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: High-Impact Nodes
# ---------------------------------------------------------------------------


def _section_impact_analysis(
    impact_data: dict[str, Any] | None,
    zones_data: dict[str, Any] | None,
) -> str:
    """High-impact nodes with risk context from parallel zones dependents."""
    lines: list[str] = ["## High-Impact Nodes", ""]
    lines.append(
        "*Data sources: "
        "[high_impact_nodes.json](high_impact_nodes.json), "
        "[parallel_zones.json](parallel_zones.json)*"
    )
    lines.append("")

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

    lines.append(
        f"{_fmt_count(len(nodes), 'node')} with >= {threshold} transitive dependents. "
        "Changes to these ripple through the codebase — test thoroughly."
    )
    lines.append("")

    # Build dependents lookup from parallel zones for richer context
    hi_modules: dict[str, list[str]] = {}
    if zones_data:
        for m in zones_data.get("high_impact_modules", []):
            hi_modules[m["id"]] = m.get("dependents", [])

    lines.append("| Node | Dependents | Risk |")
    lines.append("|------|------------|------|")
    for node in nodes[:30]:
        nid = node.get("id", "?")
        dep_count = node.get("dependent_count", 0)
        short = _short_id(nid)
        module = _module_name(nid)

        # Build risk note
        dependents = hi_modules.get(nid, [])
        if dep_count >= 20:
            risk = f"Critical — affects {dep_count} downstream functions"
        elif dep_count >= 10:
            risk = f"High — test `{module}` changes thoroughly"
        else:
            risk = "Moderate"

        # If we have the dependents list, mention unique modules affected
        if dependents:
            affected_mods = sorted({_module_name(d) for d in dependents})
            if len(affected_mods) <= 4:
                risk += f" (modules: {', '.join(affected_mods)})"
            else:
                risk += f" ({len(affected_mods)} modules affected)"

        lines.append(f"| `{short}` | {dep_count} | {risk} |")

    if len(nodes) > 30:
        lines.append(f"| ... | | {len(nodes) - 30} more |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Code Health Indicators
# ---------------------------------------------------------------------------


def _section_code_health(py: PyAnalysis | None) -> str:
    """Surface dead code, hot functions, docstring coverage, async ratio."""
    lines: list[str] = ["## Code Health Indicators", ""]
    lines.append(
        "*Data source: "
        "[python_analysis.json](python_analysis.json)*"
    )
    lines.append("")

    if not py:
        lines.append("No Python analysis data available.")
        lines.append("")
        return "\n".join(lines)

    py_summary = py.get("summary", {})
    total_funcs = py_summary.get("total_functions", 0)
    async_funcs = py_summary.get("async_functions", 0)

    # Docstring coverage
    functions = py.get("functions", [])
    with_doc = sum(1 for f in functions if f.get("docstring"))
    doc_pct = round(100 * with_doc / total_funcs) if total_funcs else 0

    lines.append("### Quick Stats")
    lines.append("")
    lines.append("| Indicator | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Async ratio | {async_funcs}/{total_funcs} ({round(100 * async_funcs / total_funcs) if total_funcs else 0}%) |")
    lines.append(f"| Docstring coverage | {with_doc}/{total_funcs} ({doc_pct}%) |")
    lines.append(f"| Dead code candidates | {len(py_summary.get('dead_code_candidates', []))} |")
    lines.append("")

    # Hot functions
    hot = py_summary.get("hot_functions", [])
    if hot:
        lines.append("### Hot Functions")
        lines.append("")
        lines.append("Functions called by the most other functions — changes here have wide blast radius:")
        lines.append("")
        lines.append("| Function | Callers |")
        lines.append("|----------|---------|")
        for hf in hot[:10]:
            lines.append(f"| `{hf['name']}` | {hf['caller_count']} |")
        lines.append("")

    # Dead code candidates
    dead = py_summary.get("dead_code_candidates", [])
    if dead:
        lines.append("### Dead Code Candidates")
        lines.append("")
        lines.append(
            f"{len(dead)} functions are unreachable from entrypoints via static analysis. "
            "Some may be used dynamically (e.g., classmethods, test helpers)."
        )
        lines.append("")

        # Group by module
        by_mod: dict[str, list[str]] = defaultdict(list)
        for name in dead:
            mod = name.split(".")[0]
            by_mod[mod].append(name)

        for mod in sorted(by_mod):
            funcs = by_mod[mod]
            func_list = ", ".join(f"`{f.split('.')[-1]}`" for f in funcs[:6])
            if len(funcs) > 6:
                func_list += f", ... (+{len(funcs) - 6})"
            lines.append(f"- **{mod}** ({len(funcs)}): {func_list}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Parallel Modification Zones
# ---------------------------------------------------------------------------


def _section_parallel_zones(zones_data: dict[str, Any] | None) -> str:
    """Show independent groups for safe parallel modification."""
    lines: list[str] = ["## Parallel Modification Zones", ""]
    lines.append(
        "*Data source: "
        "[parallel_zones.json](parallel_zones.json)*"
    )
    lines.append("")

    if not zones_data:
        lines.append("No parallel zones data available.")
        lines.append("")
        return "\n".join(lines)

    groups = zones_data.get("independent_groups", [])
    zone_summary = zones_data.get("summary", {})

    if not groups:
        lines.append("No independent modification zones detected.")
        lines.append("")
        return "\n".join(lines)

    total_groups = zone_summary.get("total_groups", len(groups))
    largest = zone_summary.get("largest_group_size", 0)
    leaf_count = zone_summary.get("leaf_count", 0)
    hi_count = zone_summary.get("high_impact_count", 0)

    lines.append(
        f"**{total_groups} independent groups** identified. "
        f"The largest interconnected group has {largest} modules; "
        f"{leaf_count} modules are leaf nodes (safe to modify in isolation)."
    )
    lines.append("")

    if hi_count:
        lines.append(
            f"**{hi_count} high-impact modules** act as coupling points — "
            "parallel changes touching these need coordination."
        )
        lines.append("")

    # Show the large groups (size > 1), skip singletons
    large_groups = [g for g in groups if g.get("size", len(g.get("modules", []))) > 1]

    if large_groups:
        lines.append("### Interconnected Groups")
        lines.append("")
        for group in large_groups[:10]:
            gid = group.get("id", "?")
            members = group.get("modules", [])
            size = group.get("size", len(members))
            # Show unique module names (strip py: prefix)
            mod_names = sorted({_module_name(m) for m in members})
            lines.append(f"**Group {gid}** ({size} members spanning {len(mod_names)} modules): {', '.join(f'`{m}`' for m in mod_names[:8])}")
            if len(mod_names) > 8:
                lines.append(f"  ... and {len(mod_names) - 8} more modules")
            lines.append("")

    # Leaf modules
    leaves = zones_data.get("leaf_modules", [])
    if leaves:
        singleton_count = total_groups - len(large_groups)
        lines.append(
            f"### Leaf Modules ({leaf_count})"
        )
        lines.append("")
        lines.append(
            f"{leaf_count} modules have no dependents — changes are fully isolated. "
            f"{singleton_count} of the {total_groups} groups are singletons."
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section: Cross-Layer Flows (kept for completeness)
# ---------------------------------------------------------------------------


def _section_cross_layer_flows(
    summary: dict[str, Any] | None,
    flows_data: dict[str, Any] | None,
) -> str:
    """Build the cross-layer flows section."""
    flows = []
    if flows_data and "flows" in flows_data:
        flows = flows_data["flows"]
    elif summary and "cross_layer_flows" in summary:
        flows = summary["cross_layer_flows"]

    if not flows:
        # Don't emit a section header for empty data
        return ""

    lines: list[str] = ["## Cross-Layer Flows", ""]
    lines.append(
        "*Data sources: "
        "[cross_layer_flows.json](cross_layer_flows.json), "
        "[architecture.summary.json](architecture.summary.json)*"
    )
    lines.append("")
    lines.append(f"{_fmt_count(len(flows), 'flow')} detected spanning frontend → backend → database.")
    lines.append("")

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


# ---------------------------------------------------------------------------
# Section: Mermaid Diagrams
# ---------------------------------------------------------------------------


def _section_mermaid_diagrams(graph: Graph) -> str:
    """Build the Mermaid diagrams section."""
    lines: list[str] = ["## Architecture Diagrams", ""]
    lines.append(
        "*Data source: "
        "[architecture.graph.json](architecture.graph.json)*"
    )
    lines.append("")

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
# Section: Best Practices Context
# ---------------------------------------------------------------------------


def _extract_markdown_sections(text: str, headings: list[str]) -> str:
    """Extract specific markdown sections by heading from *text*.

    Returns the concatenated content of all matching sections.
    """
    if not headings:
        return text

    pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return ""

    heading_set = {h.lower().strip() for h in headings}
    parts: list[str] = []
    for i, m in enumerate(matches):
        heading_text = m.group(2).strip().lower()
        if heading_text in heading_set:
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            parts.append(text[start:end].rstrip())

    return "\n\n".join(parts)


def _section_best_practices(config: ReportConfig | None = None) -> str:
    """Render best-practices references as a collapsible section."""
    cfg = config or ReportConfig()
    if not cfg.best_practices:
        return ""

    parts: list[str] = []
    for ref in cfg.best_practices:
        ref_path = Path(ref.path)
        if not ref_path.exists():
            continue
        try:
            content = ref_path.read_text()
        except OSError:
            continue

        if ref.sections:
            content = _extract_markdown_sections(content, ref.sections)
        if not content.strip():
            continue

        parts.append(f"### {ref_path.name}")
        parts.append("")
        parts.append(content.strip())
        parts.append("")

    if not parts:
        return ""

    lines: list[str] = ["## Best Practices Context", ""]
    lines.append("<details>")
    lines.append("<summary>Referenced project standards and guidelines</summary>")
    lines.append("")
    lines.extend(parts)
    lines.append("</details>")
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
    python_analysis: PyAnalysis | None = None,
    config: ReportConfig | None = None,
) -> str:
    """Assemble the full Markdown report from all analysis outputs."""
    cfg = config or ReportConfig()
    enabled = cfg.report.sections

    # Map section names to builder callables (lazy — only invoked when enabled)
    builders: dict[str, Any] = {
        "system_overview": lambda: _section_system_overview(graph, summary, python_analysis, config=cfg),
        "module_map": lambda: _section_module_map(python_analysis, graph),
        "dependency_layers": lambda: _section_dependency_layers(python_analysis),
        "entry_points": lambda: _section_entry_points(graph, python_analysis),
        "health": lambda: _section_health(diagnostics, config=cfg),
        "impact_analysis": lambda: _section_impact_analysis(impact_data, zones_data),
        "code_health": lambda: _section_code_health(python_analysis),
        "parallel_zones": lambda: _section_parallel_zones(zones_data),
        "cross_layer_flows": lambda: _section_cross_layer_flows(summary, flows_data),
        "diagrams": lambda: _section_mermaid_diagrams(graph),
    }

    # Only invoke builders for enabled sections
    sections: list[str] = []
    for name in enabled:
        if name in KNOWN_SECTIONS and name in builders:
            content = builders[name]()
            if content:
                sections.append(content)

    # Best practices context (not a toggleable section — present if configured)
    bp = _section_best_practices(config=cfg)
    if bp:
        sections.append(bp)

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate analysis outputs into a unified architecture report.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing JSON artifacts (default: docs/architecture-analysis)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the Markdown report (default: docs/architecture-analysis/architecture.report.md)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to architecture.config.yaml (default: auto-detect in current dir)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    # Load config (falls back to defaults if file missing)
    config = load_config(args.config)

    # CLI flags override config paths; config paths override hardcoded defaults
    input_dir: Path = args.input_dir or Path(config.paths.input_dir)
    output_path: Path = args.output or Path(config.paths.output_report)

    # Load the canonical graph (required)
    graph = load_graph(input_dir / "architecture.graph.json")
    if not graph:
        logger.error("architecture.graph.json not found or empty.")
        return 1

    # Load optional analysis outputs
    summary = _load_json(input_dir / "architecture.summary.json")
    diagnostics = _load_json(input_dir / "architecture.diagnostics.json")
    flows_data = _load_json(input_dir / "cross_layer_flows.json")
    impact_data = _load_json(input_dir / "high_impact_nodes.json")
    zones_data = _load_json(input_dir / "parallel_zones.json")
    python_analysis = _load_json(input_dir / "python_analysis.json")

    report = generate_report(
        graph, summary, diagnostics, flows_data, impact_data, zones_data,
        python_analysis=python_analysis,
        config=config,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)
    logger.info(f"Wrote {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
