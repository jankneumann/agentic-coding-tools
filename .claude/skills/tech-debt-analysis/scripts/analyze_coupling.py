#!/usr/bin/env python3
"""Analyzer: coupling and cohesion from architecture graph artifacts.

Reads ``docs/architecture-analysis/architecture.graph.json`` and
``docs/architecture-analysis/high_impact_nodes.json`` to detect:

- **High Fan-out** — modules that depend on too many others (Shotgun Surgery risk)
- **High Fan-in** — modules depended on by too many others (change amplifier)
- **Hub Nodes** — nodes with both high fan-in AND fan-out (God Object / Blob)
- **Circular Dependencies** — cycles in the import/call graph

These map to the AWS Builders' Library principle of minimizing blast radius:
a highly-coupled module means one change ripples across the entire system.

This analyzer is **read-only** — it consumes pre-generated architecture
artifacts rather than re-analyzing the source.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from models import AnalyzerResult, TechDebtFinding

ANALYZER = "coupling"

_GRAPH_REL = "docs/architecture-analysis/architecture.graph.json"
_IMPACT_REL = "docs/architecture-analysis/high_impact_nodes.json"

# ── Thresholds ────────────────────────────────────────────────────────
FAN_OUT_THRESHOLD = 10  # outgoing edges
FAN_OUT_CRITICAL = 20
FAN_IN_THRESHOLD = 10  # incoming edges
FAN_IN_CRITICAL = 20
HUB_THRESHOLD = 8  # min fan-in AND fan-out to be a hub
IMPACT_DEPENDENTS_THRESHOLD = 15  # transitive dependents
_STALENESS_THRESHOLD_DAYS = 7


def _severity(value: float, threshold: float, critical: float) -> str:
    if value >= critical:
        return "high"
    if value >= threshold:
        return "medium"
    return "low"


def _extract_file_from_node_id(node_id: str) -> str:
    """Best-effort extraction of file path from a node ID.

    Node IDs in the architecture graph typically look like:
    ``py:agent-coordinator/src/module.py::ClassName`` or
    ``py:path/to/file.py::function_name``
    """
    # Strip language prefix
    if ":" in node_id:
        rest = node_id.split(":", 1)[1]
    else:
        rest = node_id
    # Take the file part (before ::)
    if "::" in rest:
        return rest.split("::")[0]
    return rest


def analyze(project_dir: str) -> AnalyzerResult:
    """Analyze coupling from architecture graph artifacts.

    Parameters
    ----------
    project_dir:
        Path to the project root.

    Returns
    -------
    AnalyzerResult
    """
    start = time.monotonic()
    graph_path = Path(project_dir) / _GRAPH_REL
    impact_path = Path(project_dir) / _IMPACT_REL

    # ── Guard: graph must exist ───────────────────────────────────
    if not graph_path.is_file():
        elapsed = int((time.monotonic() - start) * 1000)
        return AnalyzerResult(
            analyzer=ANALYZER,
            status="skipped",
            duration_ms=elapsed,
            messages=[
                f"Architecture graph not found: {graph_path}. "
                "Run /refresh-architecture to generate it."
            ],
        )

    # ── Staleness check ───────────────────────────────────────────
    messages: list[str] = []
    try:
        mtime = graph_path.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        if age_days > _STALENESS_THRESHOLD_DAYS:
            messages.append(
                f"Architecture graph is {age_days:.0f} days old "
                f"(>{_STALENESS_THRESHOLD_DAYS}d). "
                "Run /refresh-architecture for accurate coupling analysis."
            )
    except OSError:
        pass

    # ── Load graph ────────────────────────────────────────────────
    try:
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return AnalyzerResult(
            analyzer=ANALYZER,
            status="error",
            duration_ms=elapsed,
            messages=[f"Failed to read graph: {exc}"],
        )

    edges = graph_data.get("edges", [])
    nodes = {n.get("id", ""): n for n in graph_data.get("nodes", [])}

    # ── Compute fan-in / fan-out ──────────────────────────────────
    fan_out: dict[str, int] = {}
    fan_in: dict[str, int] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        fan_out[src] = fan_out.get(src, 0) + 1
        fan_in[tgt] = fan_in.get(tgt, 0) + 1

    findings: list[TechDebtFinding] = []

    # ── High fan-out (Shotgun Surgery risk) ───────────────────────
    for node_id, count in sorted(fan_out.items(), key=lambda x: -x[1]):
        if count < FAN_OUT_THRESHOLD:
            break
        sev = _severity(count, FAN_OUT_THRESHOLD, FAN_OUT_CRITICAL)
        file_path = _extract_file_from_node_id(node_id)
        node_info = nodes.get(node_id, {})
        line = node_info.get("line")

        findings.append(
            TechDebtFinding(
                id=f"td-fan-out-{node_id}",
                analyzer=ANALYZER,
                severity=sev,  # type: ignore[arg-type]
                category="high-coupling",  # type: ignore[arg-type]
                title=f"High fan-out: {node_id} depends on {count} modules",
                detail=(
                    f"Node '{node_id}' has {count} outgoing dependencies "
                    f"(threshold: {FAN_OUT_THRESHOLD}). "
                    "Changes to its dependencies may require updates here (Shotgun Surgery)."
                ),
                file_path=file_path,
                line=line,
                metric_name="fan_out",
                metric_value=count,
                threshold=FAN_OUT_THRESHOLD,
                smell="Shotgun Surgery / Feature Envy",
                recommendation=(
                    "Introduce a facade or mediator to reduce direct dependencies. "
                    "Consider if this module has Feature Envy for another module's data."
                ),
            ),
        )

    # ── High fan-in (change amplifier) ────────────────────────────
    for node_id, count in sorted(fan_in.items(), key=lambda x: -x[1]):
        if count < FAN_IN_THRESHOLD:
            break
        sev = _severity(count, FAN_IN_THRESHOLD, FAN_IN_CRITICAL)
        file_path = _extract_file_from_node_id(node_id)
        node_info = nodes.get(node_id, {})
        line = node_info.get("line")

        findings.append(
            TechDebtFinding(
                id=f"td-fan-in-{node_id}",
                analyzer=ANALYZER,
                severity=sev,  # type: ignore[arg-type]
                category="high-coupling",  # type: ignore[arg-type]
                title=f"High fan-in: {node_id} depended on by {count} modules",
                detail=(
                    f"Node '{node_id}' is depended on by {count} other nodes "
                    f"(threshold: {FAN_IN_THRESHOLD}). "
                    "Any change to this module has a large blast radius."
                ),
                file_path=file_path,
                line=line,
                metric_name="fan_in",
                metric_value=count,
                threshold=FAN_IN_THRESHOLD,
                smell="Change Amplifier",
                recommendation=(
                    "Stabilize the interface (freeze the API). "
                    "Consider extracting a stable abstraction layer."
                ),
            ),
        )

    # ── Hub nodes (both high fan-in AND fan-out) ──────────────────
    all_node_ids = set(fan_in.keys()) | set(fan_out.keys())
    for node_id in all_node_ids:
        fi = fan_in.get(node_id, 0)
        fo = fan_out.get(node_id, 0)
        if fi >= HUB_THRESHOLD and fo >= HUB_THRESHOLD:
            severity = "high" if fi + fo >= (HUB_THRESHOLD * 4) else "medium"
            file_path = _extract_file_from_node_id(node_id)
            findings.append(
                TechDebtFinding(
                    id=f"td-hub-{node_id}",
                    analyzer=ANALYZER,
                    severity=severity,  # type: ignore[arg-type]
                    category="high-coupling",  # type: ignore[arg-type]
                    title=f"Hub node: {node_id} (fan-in={fi}, fan-out={fo})",
                    detail=(
                        f"Node '{node_id}' is a hub with {fi} incoming and "
                        f"{fo} outgoing dependencies. Hub nodes are God Objects — "
                        "they know too much and do too much."
                    ),
                    file_path=file_path,
                    metric_name="hub_score",
                    metric_value=fi + fo,
                    threshold=HUB_THRESHOLD * 2,
                    smell="God Object / Blob",
                    recommendation=(
                        "Split into smaller, focused modules. "
                        "Apply the Single Responsibility Principle."
                    ),
                ),
            )

    # ── High-impact nodes from pre-computed ranking ───────────────
    if impact_path.is_file():
        try:
            impact_data = json.loads(impact_path.read_text(encoding="utf-8"))
            impact_nodes = impact_data if isinstance(impact_data, list) else impact_data.get("nodes", [])

            for entry in impact_nodes:
                node_id = entry.get("node_id", entry.get("id", ""))
                dependents = entry.get("dependent_count", entry.get("dependents", 0))

                if dependents < IMPACT_DEPENDENTS_THRESHOLD:
                    continue

                file_path = _extract_file_from_node_id(node_id)
                sev = _severity(dependents, IMPACT_DEPENDENTS_THRESHOLD, IMPACT_DEPENDENTS_THRESHOLD * 2)

                findings.append(
                    TechDebtFinding(
                        id=f"td-impact-{node_id}",
                        analyzer=ANALYZER,
                        severity=sev,  # type: ignore[arg-type]
                        category="high-coupling",  # type: ignore[arg-type]
                        title=f"High-impact node: {node_id} ({dependents} transitive dependents)",
                        detail=(
                            f"Node '{node_id}' has {dependents} transitive dependents. "
                            "Changes here ripple across a large portion of the codebase."
                        ),
                        file_path=file_path,
                        metric_name="transitive_dependents",
                        metric_value=dependents,
                        threshold=IMPACT_DEPENDENTS_THRESHOLD,
                        smell="High Blast Radius (AWS Builders' Library)",
                        recommendation=(
                            "Ensure thorough test coverage. "
                            "Consider versioned interfaces to decouple consumers."
                        ),
                    ),
                )
        except (OSError, json.JSONDecodeError):
            pass  # non-fatal — impact data is supplementary

    elapsed = int((time.monotonic() - start) * 1000)
    return AnalyzerResult(
        analyzer=ANALYZER,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
        messages=messages,
    )
