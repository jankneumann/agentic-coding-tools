"""Markdown report renderer and the freshness stamp (design D6).

The stamp is machine-readable: ``--check-freshness`` reads the newest report
back with ``parse_stamp`` and compares ``archetypes_sha256`` with the current
roster file.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from classifier import Section

KIND_RANK = {
    "tier_concentrated_failure": 0,
    "contract_unpinned": 1,
    "constraint_without_reason": 2,
    "procedure_without_probe": 3,
    "missing_deviation_protocol": 4,
    "convention_drift": 5,
    "teaching_inferable": 6,
}
_REVIEWED_RE = re.compile(r"reviewed:\s*[\"']?(\d{4}-\d{2}-\d{2})[\"']?")
_STAMP_RE = re.compile(r"^- (archetypes_sha256|reviewed_dates|evidence_window_days|generated_at): (.*)$", re.MULTILINE)


# --- freshness ---------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reviewed_dates(path: Path) -> list[str]:
    return sorted(set(_REVIEWED_RE.findall(Path(path).read_text(encoding="utf-8"))))


def freshness_stamp(archetypes_path: Path, *, evidence_window_days: int, generated_at: str) -> dict[str, Any]:
    return {
        "archetypes_sha256": sha256_file(archetypes_path),
        "reviewed_dates": reviewed_dates(archetypes_path),
        "evidence_window_days": int(evidence_window_days),
        "generated_at": generated_at,
    }


def parse_stamp(report_text: str) -> dict[str, Any]:
    stamp: dict[str, Any] = {}
    for key, value in _STAMP_RE.findall(report_text):
        value = value.strip()
        if key == "reviewed_dates":
            stamp[key] = [] if value in {"", "(none)"} else [v.strip() for v in value.split(",")]
        elif key == "evidence_window_days":
            stamp[key] = int(value) if value.isdigit() else value
        else:
            stamp[key] = value
    return stamp


def report_filename(skill: str, generated_at: str) -> str:
    return f"{skill}-{generated_at[:10]}.md"


def newest_report(output_dir: Path, skill: str) -> Path | None:
    candidates = sorted(Path(output_dir).glob(f"{skill}-????-??-??.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.name, p.stat().st_mtime))


# --- rendering ----------------------------------------------------------------


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return lines


def rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda f: (f["remediation"] == "keep", KIND_RANK.get(f["kind"], 99), f["id"]),
    )


def _evidence_summary(f: dict[str, Any]) -> str:
    ev = f.get("evidence") or {}
    parts = []
    if ev.get("tier"):
        parts.append(f"tier {ev['tier']}")
    if ev.get("count"):
        parts.append(f"count {ev['count']}")
    if ev.get("rule"):
        parts.append(f"rule `{ev['rule']}`")
    if ev.get("repo_specific_tokens"):
        parts.append("cites " + ", ".join(f"`{t}`" for t in ev["repo_specific_tokens"][:4]))
    return "; ".join(parts) or "—"


def render_report(
    *,
    ledger: dict[str, Any],
    sections: list[Section],
    evidence_reason: str | None,
    multi_source_count: int,
    evidence_total: int,
    model_calls: int,
    batch_size: int,
    warnings: list[str],
    context_cost: str = "n/a (ri-04 doctor baseline not available)",
) -> str:
    skill = ledger["skill"]
    evidence = ledger["evidence"]
    layers = ledger["layers"]
    lines: list[str] = [f"# Skill audit: {skill}", ""]

    status = evidence["status"]
    evidence_line = "available" if status == "available" else f"unavailable ({evidence_reason or evidence.get('reason') or 'unknown'})"
    lines += [
        f"- convention: {ledger['convention']}",
        f"- evidence: {evidence_line}",
        f"- evidence_window_days: {ledger['freshness']['evidence_window_days']}",
        f"- context_cost: {context_cost}",
        f"- model_calls: {model_calls} (batch of {batch_size} undecided section(s))",
        f"- generated_at: {ledger['generated_at']}",
        "",
    ]
    if warnings:
        lines += ["> " + w for w in warnings] + [""]

    lines += ["## Layer histogram", ""]
    counts: dict[str, int] = {}
    for label in layers:
        counts[label["layer"]] = counts.get(label["layer"], 0) + 1
    lines += _table(
        ["Layer", "Sections"],
        [[layer, counts.get(layer, 0)] for layer in ("contract", "constraint", "procedure", "teaching", "unclassified")],
    )
    lines += ["", "Legend: `references/layers.md` (design D2).", ""]

    lines += ["## Dispatch profile", ""]
    profile = ledger["dispatch_profile"]
    if profile:
        lines += _table(
            ["Archetype", "Tier", "Provider", "Model", "Thinking", "Procedure mode", "Degraded from", "Phases"],
            [
                [r["archetype"], r["tier"], r["provider"], r["model"], r.get("thinking"), r.get("procedure_mode"), r.get("degraded_from"), r.get("phases", [])]
                for r in profile
            ],
        )
    else:
        lines.append("No dispatch archetypes discovered for this skill (not in `references/dispatch-map.md` and no `Task(`/`Agent(` archetype tokens in SKILL.md).")
    lines.append("")

    lines += ["## Tier failure table", ""]
    lines += _table(
        ["Archetype", "Provider", "Model", "Thinking", "Count", "Sessions", "Max severity", "Sources", "Attributed by"],
        [
            [r["archetype"], r["provider"], r["model"], r.get("thinking"), r["count"], r["sessions"], r["max_severity"], r["sources"], r["attributed_by"]]
            for r in evidence["tier_rows"]
        ],
    )
    lines.append("")
    if status == "available":
        pct = (multi_source_count / evidence_total * 100) if evidence_total else 0.0
        lines.append(
            f"**Cross-source agreement**: {pct:.1f}% of findings surfaced in 2+ sources ({multi_source_count}/{evidence_total})"
        )
    else:
        lines.append(f"**Cross-source agreement**: n/a — evidence: unavailable ({evidence_reason or evidence.get('reason') or 'unknown'})")
    lines.append("")

    lines += ["## Ranked findings", ""]
    ranked = rank_findings(ledger["findings"])
    if ranked:
        lines += _table(
            ["#", "Id", "Kind", "Layer", "Section", "Remediation", "Evidence", "Rationale"],
            [
                [i, f["id"], f["kind"], f["layer"], f"`{f['section_id']}`", f["remediation"], _evidence_summary(f), f.get("rationale", "")]
                for i, f in enumerate(ranked, 1)
            ],
        )
    else:
        lines.append("No findings.")
    lines.append("")

    layer_by_id = {label["section_id"]: label["layer"] for label in layers}
    by_id = {s.section_id: s for s in sections}
    lines += ["## Proposed lean SKILL.md outline", ""]
    lines.append("Keep in SKILL.md (contract and constraint sections, in document order):")
    lines.append("")
    kept = [s for s in sections if s.file == "SKILL.md" and layer_by_id.get(s.section_id) in {"contract", "constraint"}]
    for s in kept:
        lines.append(f"- {s.heading} (`{layer_by_id[s.section_id]}`)")
    procedures = [s for s in sections if layer_by_id.get(s.section_id) == "procedure"]
    if procedures:
        lines.append("- Procedure: one line pointing at `references/procedure.md`")
    teaching = [s for s in sections if layer_by_id.get(s.section_id) == "teaching"]
    if teaching:
        lines.append("- Teaching moved out: " + ", ".join(s.heading for s in teaching))
    lines.append("")

    lines += ["## Proposed references/procedure.md outline", ""]
    if procedures:
        for s in procedures:
            steps = sum(len(b.items) for b in s.blocks if b.kind == "olist")
            lines.append(f"- {s.heading} ({steps} step(s), from `{s.section_id}`)")
    else:
        lines.append("No procedure sections; nothing to extract.")
    lines.append("")

    lines += ["## Layer table", ""]
    lines += _table(
        ["Section", "Heading", "Layer", "Decided by", "Rule"],
        [[f"`{label['section_id']}`", by_id[label["section_id"]].heading if label["section_id"] in by_id else label["heading"], label["layer"], label["decided_by"], label.get("rule")] for label in layers],
    )
    lines.append("")

    fresh = ledger["freshness"]
    lines += [
        "## Freshness stamp",
        "",
        f"- archetypes_sha256: {fresh['archetypes_sha256']}",
        f"- reviewed_dates: {', '.join(fresh['reviewed_dates']) or '(none)'}",
        f"- evidence_window_days: {fresh['evidence_window_days']}",
        f"- generated_at: {ledger['generated_at']}",
        "",
    ]
    return "\n".join(lines)


def utc_now_iso(now: datetime | None = None) -> str:
    from datetime import timezone

    stamp = now or datetime.now(timezone.utc)
    return stamp.replace(microsecond=0).isoformat()


__all__ = [
    "KIND_RANK",
    "freshness_stamp",
    "newest_report",
    "parse_stamp",
    "rank_findings",
    "render_report",
    "report_filename",
    "reviewed_dates",
    "sha256_file",
    "utc_now_iso",
]
