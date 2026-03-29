"""Consensus synthesizer for multi-vendor review findings.

Matches findings from multiple vendor reviews, classifies them as
confirmed/unconfirmed/disagreement, and produces a consensus report
conforming to consensus-report.schema.json.

Usage:
    from consensus_synthesizer import ConsensusSynthesizer

    synth = ConsensusSynthesizer()
    report = synth.synthesize(
        review_type="plan",
        target="my-feature",
        vendor_results=[
            VendorResult(vendor="codex", findings=codex_findings),
            VendorResult(vendor="gemini", findings=gemini_findings),
        ],
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single finding from a vendor review."""

    id: int
    type: str
    criticality: str
    description: str
    disposition: str
    resolution: str = ""
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    vendor: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], vendor: str) -> "Finding":
        line_range = data.get("line_range", {})
        return cls(
            id=data["id"],
            type=data["type"],
            criticality=data["criticality"],
            description=data["description"],
            disposition=data["disposition"],
            resolution=data.get("resolution", ""),
            file_path=data.get("file_path"),
            line_start=line_range.get("start") if line_range else None,
            line_end=line_range.get("end") if line_range else None,
            vendor=vendor,
        )


@dataclass
class VendorResult:
    """Findings from a single vendor."""

    vendor: str
    findings: list[Finding]
    success: bool = True
    elapsed_seconds: float = 0.0
    error: str | None = None


@dataclass
class FindingMatch:
    """A match between findings from different vendors."""

    primary: Finding
    matched: list[Finding] = field(default_factory=list)
    score: float = 0.0
    basis: str = ""


@dataclass
class ConsensusFinding:
    """A consensus finding after cross-vendor matching."""

    id: int
    status: str  # confirmed, unconfirmed, disagreement
    primary_vendor: str
    primary_finding_id: int
    matched_findings: list[dict[str, Any]]
    match_score: float
    agreed_type: str
    agreed_criticality: str
    recommended_disposition: str
    description: str
    vendor_dispositions: dict[str, str] | None = None


@dataclass
class ConsensusReport:
    """Complete consensus report."""

    review_type: str
    target: str
    reviewers: list[dict[str, Any]]
    quorum_met: bool
    quorum_requested: int
    quorum_received: int
    consensus_findings: list[ConsensusFinding]
    total_unique: int = 0
    confirmed_count: int = 0
    unconfirmed_count: int = 0
    disagreement_count: int = 0
    blocking_count: int = 0


# ---------------------------------------------------------------------------
# Matching algorithm
# ---------------------------------------------------------------------------

_CRITICALITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _tokenize(text: str) -> set[str]:
    """Tokenize text for Jaccard similarity."""
    return {w.lower().strip(".,;:!?()[]{}\"'") for w in text.split() if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def match_score(a: Finding, b: Finding) -> tuple[float, str]:
    """Compute match score and basis between two findings.

    Returns:
        (score, basis) where score is 0.0-1.0 and basis describes
        the matching criteria used.
    """
    # Same type is a prerequisite for any match
    if a.type != b.type:
        return 0.0, ""

    # Exact location match: same file + overlapping lines + same type
    if (
        a.file_path
        and b.file_path
        and a.file_path == b.file_path
        and a.line_start is not None
        and b.line_start is not None
    ):
        # Check line overlap
        a_end = a.line_end or a.line_start
        b_end = b.line_end or b.line_start
        if a.line_start <= b_end and b.line_start <= a_end:
            return 0.95, "location+type"

    # Same file + same type + similar description
    if a.file_path and b.file_path and a.file_path == b.file_path:
        desc_sim = _jaccard(_tokenize(a.description), _tokenize(b.description))
        if desc_sim >= 0.3:
            return min(0.5 + desc_sim * 0.4, 0.85), "file+type+description"

    # Same type + similar description (no file match)
    desc_sim = _jaccard(_tokenize(a.description), _tokenize(b.description))
    if desc_sim >= 0.4:
        return min(0.3 + desc_sim * 0.3, 0.7), "type+description"

    return 0.0, ""


def _higher_criticality(a: str, b: str) -> str:
    """Return the higher criticality level."""
    return a if _CRITICALITY_ORDER.get(a, 0) >= _CRITICALITY_ORDER.get(b, 0) else b


# ---------------------------------------------------------------------------
# Synthesizer
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 0.6


class ConsensusSynthesizer:
    """Synthesize consensus from multi-vendor review findings."""

    def __init__(self, match_threshold: float = MATCH_THRESHOLD, quorum: int = 2) -> None:
        self.match_threshold = match_threshold
        self.quorum = quorum

    def synthesize(
        self,
        review_type: str,
        target: str,
        vendor_results: list[VendorResult],
    ) -> ConsensusReport:
        """Produce a consensus report from multiple vendor results."""
        successful = [vr for vr in vendor_results if vr.success]
        quorum_met = len(successful) >= self.quorum

        # Build reviewer metadata
        reviewers = [
            {
                "vendor": vr.vendor,
                "agent_id": vr.vendor,
                "success": vr.success,
                "findings_count": len(vr.findings),
                "elapsed_seconds": vr.elapsed_seconds,
                "error": vr.error,
            }
            for vr in vendor_results
        ]

        # Collect all findings across vendors
        all_findings: list[Finding] = []
        for vr in successful:
            all_findings.extend(vr.findings)

        # Match findings cross-vendor
        matches = self._match_all(all_findings)

        # Classify matches into consensus findings
        consensus_findings = self._classify(matches)

        # Compute summary counts
        confirmed = sum(1 for cf in consensus_findings if cf.status == "confirmed")
        unconfirmed = sum(1 for cf in consensus_findings if cf.status == "unconfirmed")
        disagreement = sum(1 for cf in consensus_findings if cf.status == "disagreement")
        blocking = sum(
            1
            for cf in consensus_findings
            if (cf.status == "confirmed" and cf.recommended_disposition == "fix")
            or cf.status == "disagreement"
        )

        return ConsensusReport(
            review_type=review_type,
            target=target,
            reviewers=reviewers,
            quorum_met=quorum_met,
            quorum_requested=len(vendor_results),
            quorum_received=len(successful),
            consensus_findings=consensus_findings,
            total_unique=len(consensus_findings),
            confirmed_count=confirmed,
            unconfirmed_count=unconfirmed,
            disagreement_count=disagreement,
            blocking_count=blocking,
        )

    def _match_all(self, findings: list[Finding]) -> list[FindingMatch]:
        """Match findings across vendors using greedy best-match."""
        used: set[tuple[str, int]] = set()
        matches: list[FindingMatch] = []

        # Group findings by vendor
        by_vendor: dict[str, list[Finding]] = {}
        for f in findings:
            by_vendor.setdefault(f.vendor, []).append(f)

        vendors = list(by_vendor.keys())

        # For each finding, find best matches from other vendors
        for f in findings:
            key = (f.vendor, f.id)
            if key in used:
                continue

            match = FindingMatch(primary=f)
            used.add(key)

            # Find matches from other vendors
            for other_vendor in vendors:
                if other_vendor == f.vendor:
                    continue
                best_score = 0.0
                best_match: Finding | None = None
                best_basis = ""
                for candidate in by_vendor[other_vendor]:
                    ckey = (candidate.vendor, candidate.id)
                    if ckey in used:
                        continue
                    s, basis = match_score(f, candidate)
                    if s > best_score:
                        best_score = s
                        best_match = candidate
                        best_basis = basis

                if best_match and best_score >= self.match_threshold:
                    match.matched.append(best_match)
                    match.score = max(match.score, best_score)
                    match.basis = best_basis
                    used.add((best_match.vendor, best_match.id))

            matches.append(match)

        return matches

    def _classify(self, matches: list[FindingMatch]) -> list[ConsensusFinding]:
        """Classify matches into confirmed/unconfirmed/disagreement."""
        results: list[ConsensusFinding] = []

        for i, m in enumerate(matches, 1):
            if not m.matched:
                # Single vendor finding — unconfirmed
                results.append(ConsensusFinding(
                    id=i,
                    status="unconfirmed",
                    primary_vendor=m.primary.vendor,
                    primary_finding_id=m.primary.id,
                    matched_findings=[],
                    match_score=0.0,
                    agreed_type=m.primary.type,
                    agreed_criticality=m.primary.criticality,
                    recommended_disposition="accept",
                    description=m.primary.description,
                ))
                continue

            # Multi-vendor match — check for disposition agreement
            all_dispositions = {m.primary.vendor: m.primary.disposition}
            for matched in m.matched:
                all_dispositions[matched.vendor] = matched.disposition

            unique_dispositions = set(all_dispositions.values())

            # Determine agreed criticality (take highest)
            agreed_crit = m.primary.criticality
            for matched in m.matched:
                agreed_crit = _higher_criticality(agreed_crit, matched.criticality)

            if len(unique_dispositions) == 1:
                # All vendors agree on disposition
                results.append(ConsensusFinding(
                    id=i,
                    status="confirmed",
                    primary_vendor=m.primary.vendor,
                    primary_finding_id=m.primary.id,
                    matched_findings=[
                        {"vendor": mf.vendor, "finding_id": mf.id}
                        for mf in m.matched
                    ],
                    match_score=m.score,
                    agreed_type=m.primary.type,
                    agreed_criticality=agreed_crit,
                    recommended_disposition=m.primary.disposition,
                    description=m.primary.description,
                ))
            else:
                # Disposition disagreement
                results.append(ConsensusFinding(
                    id=i,
                    status="disagreement",
                    primary_vendor=m.primary.vendor,
                    primary_finding_id=m.primary.id,
                    matched_findings=[
                        {"vendor": mf.vendor, "finding_id": mf.id}
                        for mf in m.matched
                    ],
                    match_score=m.score,
                    agreed_type=m.primary.type,
                    agreed_criticality=agreed_crit,
                    recommended_disposition="escalate",
                    description=m.primary.description,
                    vendor_dispositions=all_dispositions,
                ))

        return results

    def to_dict(self, report: ConsensusReport) -> dict[str, Any]:
        """Convert report to dict conforming to consensus-report.schema.json."""
        return {
            "schema_version": 1,
            "review_type": report.review_type,
            "target": report.target,
            "reviewers": report.reviewers,
            "quorum_met": report.quorum_met,
            "quorum_requested": report.quorum_requested,
            "quorum_received": report.quorum_received,
            "consensus_findings": [
                {
                    "id": cf.id,
                    "status": cf.status,
                    "primary_vendor": cf.primary_vendor,
                    "primary_finding_id": cf.primary_finding_id,
                    "matched_findings": cf.matched_findings,
                    "match_score": cf.match_score,
                    "agreed_type": cf.agreed_type,
                    "agreed_criticality": cf.agreed_criticality,
                    "recommended_disposition": cf.recommended_disposition,
                    "description": cf.description,
                    **({"vendor_dispositions": cf.vendor_dispositions} if cf.vendor_dispositions else {}),
                }
                for cf in report.consensus_findings
            ],
            "summary": {
                "total_unique_findings": report.total_unique,
                "confirmed_count": report.confirmed_count,
                "unconfirmed_count": report.unconfirmed_count,
                "disagreement_count": report.disagreement_count,
                "blocking_count": report.blocking_count,
            },
        }

    def write_report(self, report: ConsensusReport, output_path: Path) -> None:
        """Write consensus report to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(self.to_dict(report), f, indent=2)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Synthesize consensus from per-vendor findings files.

    Usage:
        python consensus_synthesizer.py \\
            --review-type plan --target my-feature \\
            --findings findings-codex.json findings-gemini.json \\
            --output consensus.json
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Synthesize multi-vendor review consensus",
    )
    parser.add_argument(
        "--review-type", required=True,
        choices=["plan", "implementation"],
    )
    parser.add_argument("--target", required=True, help="Feature or package ID")
    parser.add_argument(
        "--findings", nargs="+", required=True,
        help="Per-vendor findings JSON files",
    )
    parser.add_argument("--output", required=True, help="Output consensus JSON path")
    parser.add_argument("--quorum", type=int, default=2, help="Minimum reviewers")
    parser.add_argument(
        "--threshold", type=float, default=MATCH_THRESHOLD,
        help="Match score threshold for confirmed status",
    )
    args = parser.parse_args()

    # Load per-vendor findings
    vendor_results: list[VendorResult] = []
    for fpath in args.findings:
        p = Path(fpath)
        if not p.exists():
            print(f"Warning: {fpath} not found, skipping", file=__import__("sys").stderr)
            vendor_results.append(VendorResult(
                vendor=p.stem, findings=[], success=False,
                error=f"File not found: {fpath}",
            ))
            continue
        data = json.loads(p.read_text())
        vendor = data.get("reviewer_vendor", p.stem.split("-")[-1])
        findings = [
            Finding.from_dict(f, vendor=vendor)
            for f in data.get("findings", [])
        ]
        vendor_results.append(VendorResult(vendor=vendor, findings=findings))

    synth = ConsensusSynthesizer(
        match_threshold=args.threshold, quorum=args.quorum,
    )
    report = synth.synthesize(
        review_type=args.review_type,
        target=args.target,
        vendor_results=vendor_results,
    )
    synth.write_report(report, Path(args.output))

    # Print summary
    print(f"Consensus: {report.total_unique} findings "
          f"({report.confirmed_count} confirmed, "
          f"{report.unconfirmed_count} unconfirmed, "
          f"{report.disagreement_count} disagreement)")
    print(f"Blocking: {report.blocking_count}")
    print(f"Quorum: {'met' if report.quorum_met else 'NOT met'} "
          f"({report.quorum_received}/{report.quorum_requested})")
    print(f"Written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
