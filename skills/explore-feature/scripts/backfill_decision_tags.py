"""Heuristic classifier that proposes `architectural:` tags for untagged
Decision bullets in archived session-log.md files.

Emits a JSON report of proposals for agent review before any file edits.
No markdown mutation happens here — task 3.4 handles the edit pass after
review.

Design: openspec/changes/add-decision-index/design.md §Backfill strategy
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Default keyword map ─────────────────────────────────────────────

DEFAULT_KEYWORD_MAP: dict[str, list[str]] = {
    "software-factory-tooling": [
        "worktree",
        "branch",
        "merge_worktrees",
        "git-worktree",
        "archive_index",
        "git worktree",
        "registry.json",
        "install.sh",
    ],
    "agent-coordinator": [
        "coordinator",
        "lock",
        "claim",
        "work_queue",
        "work queue",
        "agent registry",
        "mcp server",
        "handoff",
        "issue_service",
        "feature registry",
    ],
    "skill-workflow": [
        "session-log",
        "sanitize",
        "phase entry",
        "tasks.md",
        "proposal.md",
        "skill",
        "design.md",
        "work-packages.yaml",
        "openspec",
    ],
    "codebase-analysis": [
        "tree-sitter",
        "exemplar",
        "spec compliance",
        "archive intelligence",
        "normalization",
    ],
    "observability": [
        "metrics",
        "otel",
        "tracing",
        "logfire",
        "langfuse",
    ],
    "configuration": [
        "env var",
        "config",
        "secret",
        "openbao",
        "vault",
        "credential",
    ],
    "merge-pull-requests": [
        "merge queue",
        "rebase-merge",
        "squash",
        "pr triage",
        "review dispatcher",
    ],
}


# ── Patterns ────────────────────────────────────────────────────────

_PHASE_RE = re.compile(
    r"^##\s+Phase:\s+(?P<name>[^(]+?)\s+\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$",
    re.MULTILINE,
)

_UNTAGGED_DECISION_RE = re.compile(
    r"^(?P<index>\d+)\.\s+\*\*(?P<title>[^*]+)\*\*\s+—\s*(?P<rationale>.+)$",
    re.MULTILINE,
)


# ── Data model ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassificationProposal:
    change_id: str
    phase_name: str
    phase_date: date
    decision_index: int
    title: str
    rationale: str
    proposed_capability: str | None
    confidence: float
    alternatives: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "phase_name": self.phase_name,
            "phase_date": self.phase_date.isoformat(),
            "decision_index": self.decision_index,
            "title": self.title,
            "rationale": self.rationale,
            "proposed_capability": self.proposed_capability,
            "confidence": round(self.confidence, 3),
            "alternatives": [
                [cap, round(conf, 3)] for cap, conf in self.alternatives
            ],
        }


@dataclass
class ClassificationReport:
    archive_root: str
    total_decisions_scanned: int
    high_confidence: int
    medium_confidence: int
    low_confidence: int
    no_match: int
    proposals: list[ClassificationProposal]
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["proposals"] = [p.to_dict() for p in self.proposals]
        return d


# ── Classification ──────────────────────────────────────────────────


def classify_decision(
    title: str,
    rationale: str,
    keyword_map: dict[str, list[str]],
) -> list[tuple[str, float]]:
    """Return `[(capability, confidence), …]` sorted by descending confidence.

    Returns `[]` when no keyword from any capability matches.
    """
    text = f"{title} {rationale}".lower()

    hits_per_cap: dict[str, int] = {}
    for cap, keywords in keyword_map.items():
        hits = sum(1 for kw in keywords if kw.lower() in text)
        if hits > 0:
            hits_per_cap[cap] = hits

    if not hits_per_cap:
        return []

    sorted_hits = sorted(hits_per_cap.items(), key=lambda kv: (-kv[1], kv[0]))
    top_hits = sorted_hits[0][1]
    runner_up_hits = sorted_hits[1][1] if len(sorted_hits) > 1 else 0

    # Margin-based confidence:
    #   strong winner (runner-up trivial): high
    #   tie or near-tie: low
    margin_ratio = (top_hits - runner_up_hits) / top_hits
    base = 0.35 + 0.45 * margin_ratio + 0.1 * min(top_hits, 3)
    confidence = min(1.0, base)

    return [
        (cap, confidence if i == 0 else round(confidence * 0.6, 3))
        for i, (cap, _) in enumerate(sorted_hits[:3])
    ]


def _confidence_bucket(conf: float) -> str:
    if conf >= 0.8:
        return "high"
    if conf >= 0.5:
        return "medium"
    return "low"


# ── Archive walk + report ───────────────────────────────────────────


def _extract_untagged_decisions(
    session_log: Path,
) -> list[tuple[str, date, int, str, str]]:
    """Extract untagged Decision bullets from one session-log.

    Returns list of `(phase_name, phase_date, decision_index, title, rationale)`.
    Tagged decisions (those carrying `` `architectural:` ``) are excluded —
    the untagged-only regex handles this naturally.
    """
    content = session_log.read_text()
    phase_matches = list(_PHASE_RE.finditer(content))
    if not phase_matches:
        return []

    results: list[tuple[str, date, int, str, str]] = []
    for i, pm in enumerate(phase_matches):
        phase_name = pm.group("name").strip()
        try:
            phase_date = date.fromisoformat(pm.group("date"))
        except ValueError:
            continue

        block_start = pm.end()
        block_end = (
            phase_matches[i + 1].start() if i + 1 < len(phase_matches) else len(content)
        )
        block = content[block_start:block_end]

        for m in _UNTAGGED_DECISION_RE.finditer(block):
            # Use the 1-indexed bullet position, not the match-order counter,
            # so decision_index values align with the natural `N.` prefix in
            # session-log.md. This matches `decision_index.py`'s convention and
            # keeps `supersedes: <id>#D<n>` references resolvable.
            bullet = int(m.group("index"))
            title = m.group("title").strip()
            rationale = m.group("rationale").strip()
            results.append((phase_name, phase_date, bullet, title, rationale))

    return results


def propose_tags_for_archive(
    archive_root: Path,
    keyword_map: dict[str, list[str]] | None = None,
    output_path: Path | None = None,
) -> ClassificationReport:
    """Walk `archive_root` for session-logs, extract untagged Decisions, classify,
    and emit a JSON proposals report at `output_path`.

    No markdown files are modified — this is the "propose" half of the
    propose-review-edit backfill flow.
    """
    keyword_map = keyword_map or DEFAULT_KEYWORD_MAP

    proposals: list[ClassificationProposal] = []
    for session_log in sorted(archive_root.rglob("session-log.md")):
        change_id = session_log.parent.name
        for phase_name, phase_date, dec_index, title, rationale in _extract_untagged_decisions(session_log):
            ranked = classify_decision(title, rationale, keyword_map)
            if ranked:
                proposed_cap, confidence = ranked[0]
                alternatives = ranked[1:]
            else:
                proposed_cap, confidence, alternatives = None, 0.0, []

            proposals.append(
                ClassificationProposal(
                    change_id=change_id,
                    phase_name=phase_name,
                    phase_date=phase_date,
                    decision_index=dec_index,
                    title=title,
                    rationale=rationale,
                    proposed_capability=proposed_cap,
                    confidence=confidence,
                    alternatives=list(alternatives),
                )
            )

    # Deterministic ordering: by (change_id, phase_date, decision_index)
    proposals.sort(key=lambda p: (p.change_id, p.phase_date, p.decision_index))

    high = sum(1 for p in proposals if p.proposed_capability and p.confidence >= 0.8)
    medium = sum(
        1
        for p in proposals
        if p.proposed_capability and 0.5 <= p.confidence < 0.8
    )
    low = sum(
        1
        for p in proposals
        if p.proposed_capability and 0.0 < p.confidence < 0.5
    )
    no_match = sum(1 for p in proposals if p.proposed_capability is None)

    report = ClassificationReport(
        archive_root=str(archive_root),
        total_decisions_scanned=len(proposals),
        high_confidence=high,
        medium_confidence=medium,
        low_confidence=low,
        no_match=no_match,
        proposals=proposals,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=False))

    return report


# ── CLI ─────────────────────────────────────────────────────────────


def _cli_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Propose `architectural:` tags for untagged archived session-log decisions.",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path("openspec/changes/archive"),
        help="Root dir to walk for session-log.md files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openspec/changes/add-decision-index/backfill-proposals.json"),
        help="Output JSON proposals path.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    report = propose_tags_for_archive(
        archive_root=args.archive_root,
        output_path=args.output,
    )
    logger.info(
        "Scanned %d untagged decisions — high=%d medium=%d low=%d no-match=%d → %s",
        report.total_decisions_scanned,
        report.high_confidence,
        report.medium_confidence,
        report.low_confidence,
        report.no_match,
        args.output,
    )
    print(
        f"{report.total_decisions_scanned} untagged decisions scanned → {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
