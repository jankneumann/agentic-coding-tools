"""Pilot report renderer (spec: Pilot Report With Open Decisions; design D13).

``render_report`` turns an analysis document (``analysis-report.schema.json``) into Markdown. It
only reads its input: rendering changes no coverage-ratchet baseline, spec or skill, and the same
document always renders to the same text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .disagreement import ok_record
from .records import StageRecord

DISAGREEMENT_MEANING: dict[str, str] = {
    "weak_assertions": "intent-derived but kill rate in the bottom tercile (right oracle, assertions too loose)",
    "static_blind_spot": "no static flag but `current_impl_output` (a restatement the AST rules cannot see)",
    "coupled_spec_test": "intent-derived but broken by the rename (reaches through private names)",
    "judge_vs_human": "judged and human binary classes differ (calibration evidence)",
    "rubber_stamp": "co-change ratio above threshold while kill rate is not bottom tercile (inspect)",
}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|")


def _num(value: float) -> str:
    return f"{value:.3f}"


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def boundaries_from_joined(joined: Mapping[str, Mapping[str, StageRecord]]) -> dict[str, str]:
    """Node id to the judged top ``boundary`` label, for tests with an ok judged record."""
    out: dict[str, str] = {}
    for node_id, stages in joined.items():
        judged = ok_record(stages, "judged")
        dist = judged.payload.get("boundary") if judged is not None else None
        if isinstance(dist, Mapping) and dist:
            out[node_id] = max(sorted(dist), key=lambda label: float(dist[label]))
    return out


def _coverage_lines(coverage: Mapping[str, Mapping[str, Any]]) -> list[str]:
    rows = [
        (
            approach,
            "not run" if c["not_run"] else "ran",
            c["ok"],
            c["degraded"],
            c["insufficient"],
        )
        for approach, c in coverage.items()
    ]
    return [
        "## Approach coverage",
        "",
        *_table(["approach", "state", "ok", "degraded", "insufficient"], rows),
    ]


def _metric_row(m: Mapping[str, Any]) -> list[object]:
    if m["status"] != "ok":
        return [m["subject"], m["comparison"], m["metric"], m["n"], "insufficient", "-", "-"]
    lo, hi = m["ci95"]
    threshold = "-"
    if "threshold" in m:
        threshold = _num(m["threshold"]) + (" (provisional)" if m.get("provisional") else "")
    return [
        m["subject"],
        m["comparison"],
        m["metric"],
        m["n"],
        _num(m["value"]),
        f"[{_num(lo)}, {_num(hi)}]",
        threshold,
    ]


def _candidate_lines(title: str, items: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        return [*lines, "None."]
    return [*lines, *(f"- `{c['subject']}` ({c['kind']}): {c['reason']}" for c in items)]


def _disagreement_lines(
    disagreements: Mapping[str, Sequence[str]], boundaries: Mapping[str, str]
) -> list[str]:
    lines = ["## Disagreements", ""]
    for name, ids in disagreements.items():
        lines += [f"### {name} ({len(ids)})", "", DISAGREEMENT_MEANING.get(name, ""), ""]
        if not ids:
            lines += ["None.", ""]
            continue
        for node_id in ids:
            boundary = boundaries.get(node_id)
            lines.append(f"- `{node_id}`" + (f" (boundary: {boundary})" if boundary else ""))
        lines.append("")
    return lines[:-1]


def _cutpoint_lines(cutpoints: Mapping[str, Sequence[float]]) -> list[str]:
    if not cutpoints:
        return []
    lines = ["## Kill-rate tercile cut-points", ""]
    for suite, (t1, t2) in cutpoints.items():
        lines.append(f"- {suite}: bottom <= {_num(t1)} < middle <= {_num(t2)} < top")
    return lines


def _decision_lines(decisions: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = ["## Open decisions", "", "Nothing below is decided or changed by this report.", ""]
    for d in decisions:
        lines += [f"### {d['question']}", ""]
        lines += [f"- {option}" for option in d["options"]]
        lines += ["", f"Evidence: {d['evidence']}", ""]
    return lines[:-1]


def render_report(analysis: Mapping[str, Any], *, boundaries: Mapping[str, str] | None = None) -> str:
    """Markdown for an analysis document; the first line says it is advisory and not a gate."""
    boundaries = boundaries or {}
    suites = ", ".join(analysis["suites"])
    stamp = f"Suites: {suites}. Seed: {analysis['seed']}. Generated: {analysis['generated_at']}."
    if analysis.get("source_revision"):
        stamp += f" Source revision: {analysis['source_revision']}."

    metric_header = ["subject", "comparison", "metric", "n", "value", "95% CI", "threshold"]
    sections: list[list[str]] = [
        ["Advisory only: this report is not a gate and changes no ratchet baseline, spec or skill.", ""],
        ["# Test-oracle audit pilot report", "", stamp],
        _coverage_lines(analysis["approach_coverage"]),
        ["## Analysis tables", "", *_table(metric_header, [_metric_row(m) for m in analysis["metrics"]])],
        _candidate_lines("Linter candidates", analysis["linter_candidates"]),
        _candidate_lines("Excluded", analysis["excluded"]),
        _disagreement_lines(analysis["disagreements"], boundaries),
        _cutpoint_lines(analysis.get("tercile_cutpoints", {})),
        _decision_lines(analysis["open_decisions"]),
    ]
    return "\n\n".join("\n".join(s) for s in sections if s) + "\n"


__all__ = ["boundaries_from_joined", "render_report"]
