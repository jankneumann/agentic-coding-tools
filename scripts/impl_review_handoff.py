#!/usr/bin/env python3
"""Build the IMPL_REVIEW handoff JSON from the convergence-result artifact.

Run AFTER impl_review_driver.py completes. Reads
.review-cache/round-N/* and impl-review-convergence-result.json,
then writes openspec/changes/<id>/handoffs/impl-review-0.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/Users/jankneumann/Coding/agentic-coding-tools/.git-worktrees/add-coordinator-kanban-viz").resolve()
CHANGE_ID = "add-coordinator-kanban-viz"
CHANGE_DIR = ROOT / "openspec" / "changes" / CHANGE_ID
HANDOFFS_DIR = CHANGE_DIR / "handoffs"
CACHE_DIR = CHANGE_DIR / ".review-cache"
RESULT_PATH = CHANGE_DIR / "impl-review-convergence-result.json"


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _read_round_summaries() -> list[dict[str, Any]]:
    rounds = []
    for round_dir in sorted(CACHE_DIR.glob("round-*")):
        if not round_dir.is_dir():
            continue
        manifest_path = round_dir / "review-manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        vendors = []
        total_findings = 0
        for v in manifest.get("vendors", []):
            findings_file = round_dir / v["findings_path"]
            count = v.get("finding_count", 0)
            total_findings += count
            vendors.append({
                "vendor": v["name"],
                "findings_count": count,
                "findings_path": str(findings_file.relative_to(ROOT)),
            })
        rounds.append({
            "round": int(round_dir.name.split("-")[-1]),
            "manifest_path": str(manifest_path.relative_to(ROOT)),
            "vendors": vendors,
            "total_findings_collected": total_findings,
            "dispatches": manifest.get("dispatches", []),
            "quorum_requested": manifest.get("quorum_requested"),
            "quorum_received": manifest.get("quorum_received"),
        })
    return rounds


def _classify_by_package(blocking: list[dict[str, Any]]) -> dict[str, int]:
    """Bucket findings by inferred package_id from file_path patterns."""
    counts: dict[str, int] = {}

    def _pkg_for_path(fp: str | None) -> str:
        if not fp:
            return "wp-unknown"
        if "agent-coordinator/src/sync_points" in fp:
            return "wp-coord-endpoints"
        if "agent-coordinator/src/event_stream" in fp:
            return "wp-coord-endpoints"
        if "agent-coordinator/src/" in fp:
            return "wp-coord-endpoints"
        if "agent-coordinator/tests/test_kanban_viz" in fp:
            return "wp-coord-endpoints"
        if "apps/kanban-viz/src/Vendor" in fp or "swimlane" in fp.lower():
            return "wp-frontend-swimlanes"
        if "apps/kanban-viz/src/SyncPoint" in fp or "Consent" in fp:
            return "wp-frontend-sync-banner"
        if "apps/kanban-viz/src/saveView" in fp:
            return "wp-saved-views"
        if "apps/kanban-viz/src/runtime" in fp or "src-tauri" in fp:
            return "wp-tauri-scaffold"
        if "apps/kanban-viz/" in fp:
            return "wp-frontend-skeleton"
        if "contracts/" in fp or fp.endswith(".schema.json"):
            return "wp-contracts"
        if "docs/" in fp or fp == "README.md":
            return "wp-integration"
        return "wp-unknown"

    for cf in blocking:
        fp = cf.get("file_path") or ""
        # consensus dicts may stash file_path inside primary_finding
        pid = cf.get("package_id") or _pkg_for_path(fp)
        counts[pid] = counts.get(pid, 0) + 1
    return counts


def main() -> int:
    if not RESULT_PATH.exists():
        print(f"ERROR: convergence-result not found at {RESULT_PATH}", file=sys.stderr)
        return 2

    result = json.loads(RESULT_PATH.read_text())
    summary = result.get("summary", {})
    converged = bool(summary.get("converged"))
    rounds_run = summary.get("rounds", 0)
    reason = summary.get("reason")
    blocking = result.get("blocking_findings") or []
    consensus = result.get("consensus") or {}
    validation_errors = summary.get("validation_errors") or []

    rounds_summary = _read_round_summaries()
    findings_trend = [r["total_findings_collected"] for r in rounds_summary]
    package_findings = _classify_by_package(blocking)

    if converged:
        outcome = "converged"
    elif reason == "max_rounds":
        outcome = "max_iter"
    else:
        outcome = "not_converged"

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    handoff_id = f"impl-review-0--{ts}"

    consensus_summary = consensus.get("summary") or {}

    handoff = {
        "handoff_id": handoff_id,
        "schema_version": 1,
        "change_id": CHANGE_ID,
        "phase": "IMPL_REVIEW",
        "summary": (
            f"IMPL_REVIEW for {CHANGE_ID} completed via multi-vendor convergence "
            f"(claude / codex / gemini) over {rounds_run} round(s). "
            f"Outcome: {outcome}. Blocking findings: {len(blocking)}. "
            f"Total unique findings (final round): "
            f"{consensus_summary.get('total_unique_findings', 'n/a')}. "
            f"Confirmed: {consensus_summary.get('confirmed_count', 0)}, "
            f"Unconfirmed: {consensus_summary.get('unconfirmed_count', 0)}."
        ),
        "outcome": outcome,
        "rounds": [
            {
                "round": r["round"],
                "vendor_participation": [v["vendor"] for v in r["vendors"]],
                "findings_count_per_vendor": {
                    v["vendor"]: v["findings_count"] for v in r["vendors"]
                },
                "total_findings": r["total_findings_collected"],
                "quorum_requested": r["quorum_requested"],
                "quorum_received": r["quorum_received"],
                "fixes_applied": [],  # filled below if a fixes log exists
                "manifest_path": r["manifest_path"],
            }
            for r in rounds_summary
        ],
        "findings_trend": findings_trend,
        "blocking_findings_remaining": blocking if not converged else [],
        "fixes_applied": [],  # filled in later if sub-agent applies fixes
        "package_findings": package_findings,
        "feature_branch": "openspec/add-coordinator-kanban-viz",
        "feature_branch_head": _git_head(),
        "remote_sync_status": "unknown_at_handoff_write",
        "convergence_reason": reason,
        "validation_errors": validation_errors,
        "consensus_summary": consensus_summary,
        "next_phase": "VALIDATE" if converged else "IMPL_FIX",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = HANDOFFS_DIR / "impl-review-0.json"
    out_path.write_text(json.dumps(handoff, indent=2))
    print(f"Wrote handoff: {out_path}")
    print(f"  handoff_id: {handoff_id}")
    print(f"  outcome: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
