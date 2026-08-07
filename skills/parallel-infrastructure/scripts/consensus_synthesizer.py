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
            VendorResult(vendor="grok", findings=grok_findings),
        ],
    )
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from consensus_policy import TrustedApprovalResolver, evaluate_blocking, is_valid_non_blocking_adjudication
from review_result_policy import is_quorum_eligible

logger = logging.getLogger(__name__)


class ConsensusInputError(ValueError):
    """Raised when a per-vendor findings file fails schema validation."""


def _consensus_schema_path() -> Path:
    """Find the portable consensus schema installed with this skill."""
    portable = Path(__file__).resolve().parent.parent / "install_assets" / "openspec" / "schemas" / "consensus-report.schema.json"
    if portable.is_file():
        return portable
    for root in (Path.cwd(), *Path(__file__).resolve().parents):
        for relative in (
            Path("skills/parallel-infrastructure/install_assets/openspec/schemas/consensus-report.schema.json"),
            Path("install_assets/openspec/schemas/consensus-report.schema.json"),
            Path("openspec/schemas/consensus-report.schema.json"),
        ):
            candidate = root / relative
            if candidate.is_file():
                return candidate
    raise ConsensusInputError("consensus-report schema is unavailable")


def validate_consensus_payload(
    payload: dict[str, Any],
    *,
    trusted_approval_resolver: TrustedApprovalResolver | None = None,
) -> None:
    """Validate schema plus all producer/consumer trust aliases."""
    try:
        schema = json.loads(_consensus_schema_path().read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)
    except Exception as exc:  # jsonschema exposes a broad hierarchy
        raise ConsensusInputError(f"invalid consensus report: {exc}") from exc

    quorum = payload.get("quorum")
    findings = payload.get("consensus_findings")
    summary = payload.get("summary")
    reviewers = payload.get("reviewers")
    if (
        not isinstance(quorum, dict)
        or not isinstance(findings, list)
        or not isinstance(summary, dict)
        or not isinstance(reviewers, list)
    ):
        raise ConsensusInputError("consensus report is missing canonical sections")
    if payload.get("quorum_requested") != quorum.get("requested") or payload.get("quorum_received") != quorum.get("received") or payload.get("quorum_met") != quorum.get("met"):
        raise ConsensusInputError("consensus quorum aliases disagree")
    vendors = quorum.get("eligible_vendors")
    if (not isinstance(vendors, list) or len(vendors) != len(set(vendors))
            or quorum.get("received") != len(vendors)
            or quorum.get("received") > quorum.get("requested")
            or quorum.get("met") != (quorum.get("received") >= quorum.get("minimum_required"))):
        raise ConsensusInputError("consensus quorum is inconsistent")
    reviewer_vendors = [reviewer.get("vendor") for reviewer in reviewers if isinstance(reviewer, dict)]
    successful_vendors = [
        reviewer.get("vendor")
        for reviewer in reviewers
        if isinstance(reviewer, dict) and reviewer.get("success") is True
    ]
    source_eligible_vendors = {
        reviewer.get("vendor")
        for reviewer in reviewers
        if isinstance(reviewer, dict)
        and reviewer.get("source_eligible", reviewer.get("success")) is True
    }
    if (
        len(reviewer_vendors) != len(reviewers)
        or any(not isinstance(vendor, str) or not vendor for vendor in reviewer_vendors)
        or len(reviewer_vendors) != len(set(reviewer_vendors))
        or set(vendors) != set(successful_vendors)
    ):
        raise ConsensusInputError("consensus eligible vendors disagree with reviewer success")
    if summary.get("total_unique_findings") != len(findings) or summary.get("provisional_count") != summary.get("unconfirmed_count") or summary.get("blocking_count") != summary.get("effective_blocking_count"):
        raise ConsensusInputError("consensus summary aliases disagree")
    expected = {"confirmed_count": 0, "unconfirmed_count": 0, "disagreement_count": 0,
                "integration_blocking_count": 0, "convergence_blocking_count": 0,
                "effective_blocking_count": 0}
    finding_groups: dict[str, tuple[list[str], dict[str, Any]]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            raise ConsensusInputError("consensus finding is invalid")
        status = finding.get("status")
        policy_status = finding.get("policy_status")
        if {"confirmed": "confirmed", "unconfirmed": "provisional", "disagreement": "disagreement"}.get(status) != policy_status:
            raise ConsensusInputError("consensus finding status aliases disagree")
        if finding.get("criticality") != finding.get("agreed_criticality"):
            raise ConsensusInputError("consensus finding criticality aliases disagree")
        match = finding.get("match")
        if not isinstance(match, dict) or match.get("score") != finding.get("match_score"):
            raise ConsensusInputError("consensus finding match aliases disagree")
        source = finding.get("source_findings")
        dispositions = finding.get("vendor_dispositions")
        if not isinstance(source, list) or not source or not isinstance(dispositions, dict):
            raise ConsensusInputError("consensus source dispositions disagree")
        if any(not isinstance(item, dict) for item in source):
            raise ConsensusInputError("consensus source membership is invalid")
        source_pairs = [(item.get("vendor"), item.get("finding_id")) for item in source]
        if (
            len(source_pairs) != len(set(source_pairs))
            or any(not isinstance(vendor, str) or not isinstance(finding_id, int) for vendor, finding_id in source_pairs)
            or set(dispositions) != {vendor for vendor, _finding_id in source_pairs}
            or any(item.get("disposition") != dispositions.get(item.get("vendor")) for item in source)
            or not {vendor for vendor, _finding_id in source_pairs}.issubset(source_eligible_vendors)
        ):
            raise ConsensusInputError("consensus source membership or dispositions disagree")
        primary = (finding.get("primary_vendor"), finding.get("primary_finding_id"))
        matched = finding.get("matched_findings")
        matched_pairs = [
            (item.get("vendor"), item.get("finding_id"))
            for item in matched if isinstance(item, dict)
        ] if isinstance(matched, list) else []
        if (
            primary not in source_pairs
            or not isinstance(matched, list)
            or len(matched_pairs) != len(matched)
            or sorted(source_pairs) != sorted([primary, *matched_pairs])
        ):
            raise ConsensusInputError("consensus source membership aliases disagree")
        unique_dispositions = set(dispositions.values())
        canonical_recommendation = (
            next(iter(unique_dispositions)) if len(unique_dispositions) == 1 else "escalate"
        )
        if finding.get("recommended_disposition") != canonical_recommendation:
            raise ConsensusInputError("consensus recommended disposition disagrees with sources")
        policy = finding.get("policy")
        adjudication = finding.get("adjudication")
        if not isinstance(policy, dict) or not isinstance(adjudication, dict):
            raise ConsensusInputError("consensus canonical blocking policy is missing")
        decision = evaluate_blocking(
            policy_status=str(policy_status),
            criticality=str(finding.get("agreed_criticality")),
            vendor_dispositions={str(key): str(value) for key, value in dispositions.items()},
            adjudication=adjudication,
            trusted_approval_resolver=trusted_approval_resolver,
        )
        canonical_policy = {
            "integration_blocking": decision.integration_blocking,
            "convergence_blocking": decision.convergence_blocking,
            "effective_blocking": decision.effective_blocking,
        }
        if policy != canonical_policy:
            raise ConsensusInputError("consensus canonical blocking policy disagrees with evidence")
        expected[f"{status}_count"] += 1
        for key in ("integration_blocking_count", "convergence_blocking_count", "effective_blocking_count"):
            expected[key] += int(canonical_policy[key.removesuffix("_count")])
        group_id = finding.get("group_id")
        fingerprints = sorted(item.get("concern_fingerprint") for item in source)
        if (
            not isinstance(group_id, str)
            or not group_id
            or any(not isinstance(value, str) or not value for value in fingerprints)
            or group_id in finding_groups
        ):
            raise ConsensusInputError("consensus group or source fingerprints are invalid")
        finding_groups[group_id] = (fingerprints, adjudication)
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ConsensusInputError("consensus summary counts are inconsistent")

    applied = payload.get("applied_adjudications")
    if not isinstance(applied, list) or any(not isinstance(entry, dict) for entry in applied):
        raise ConsensusInputError("applied adjudications are invalid")
    seen_adjudications: set[tuple[str, tuple[str, ...]]] = set()
    applied_groups: set[str] = set()
    for entry in applied:
        group_id = entry.get("group_id")
        fingerprints = entry.get("concern_fingerprints")
        key = (
            group_id if isinstance(group_id, str) else "",
            tuple(fingerprints) if isinstance(fingerprints, list) else (),
        )
        if (
            key in seen_adjudications
            or key[0] in applied_groups
            or key[0] not in finding_groups
            or list(key[1]) != finding_groups[key[0]][0]
            or entry.get("adjudication") != finding_groups[key[0]][1]
            or not isinstance(entry.get("recorded_at"), str)
        ):
            raise ConsensusInputError("duplicate or inconsistent applied adjudication")
        seen_adjudications.add(key)
        applied_groups.add(key[0])
    for group_id, (_fingerprints, adjudication) in finding_groups.items():
        if adjudication.get("status") != "unreviewed" and group_id not in applied_groups:
            raise ConsensusInputError("consensus adjudication lacks an applied ledger entry")


def _coerce_line_number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_line_range(line_range: Any) -> tuple[int | None, int | None]:
    if isinstance(line_range, dict):
        return (
            _coerce_line_number(line_range.get("start")),
            _coerce_line_number(line_range.get("end")),
        )

    if isinstance(line_range, str):
        match = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", line_range)
        if not match:
            return None, None
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        return start, end

    return None, None


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
    affected_symbol: str | None = None
    requirement_id: str | None = None
    vendor: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], vendor: str) -> "Finding":
        line_start, line_end = _parse_line_range(data.get("line_range"))
        return cls(
            id=data["id"],
            type=data["type"],
            criticality=data["criticality"],
            description=data["description"],
            disposition=data["disposition"],
            resolution=data.get("resolution", ""),
            file_path=data.get("file_path"),
            line_start=line_start,
            line_end=line_end,
            affected_symbol=data.get("affected_symbol") or data.get("symbol"),
            requirement_id=data.get("requirement_id") or data.get("requirement"),
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
    logical_result: object | None = None
    trusted_internal: bool = False


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
    vendor_dispositions: dict[str, str] = field(default_factory=dict)
    group_id: str = ""
    policy_status: str = "provisional"
    integration_blocking: bool = False
    convergence_blocking: bool = False
    effective_blocking: bool = False
    match_method: str = "single"
    match_evidence: list[str] = field(default_factory=list)
    concern_fingerprints: list[str] = field(default_factory=list)
    source_fingerprints: dict[str, str] = field(default_factory=dict)
    adjudication: dict[str, Any] = field(default_factory=lambda: {"status": "unreviewed"})


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
    integration_blocking_count: int = 0
    convergence_blocking_count: int = 0
    applied_adjudications: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Matching algorithm
# ---------------------------------------------------------------------------

_CRITICALITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Vendors label the same defect with different type vocabularies
# ("correctness" vs "bug", "security" vs "vulnerability"). Matching on
# raw string equality zeroes every cross-vendor pair, so types are
# canonicalized before comparison.
_TYPE_ALIASES = {
    "bug": "correctness",
    "logic": "correctness",
    "defect": "correctness",
    "error": "correctness",
    "functional": "correctness",
    "vulnerability": "security",
    "vuln": "security",
    "perf": "performance",
    "efficiency": "performance",
    "lint": "style",
    "formatting": "style",
    "convention": "style",
    "design": "architecture",
    "structure": "architecture",
}


def _canonical_type(type_str: str) -> str:
    normalized = type_str.strip().lower().replace("-", "_")
    return _TYPE_ALIASES.get(normalized, normalized)


def _types_compatible(a: str, b: str) -> bool:
    return _canonical_type(a) == _canonical_type(b)


def _paths_match(a: str | None, b: str | None) -> bool:
    """True when two vendor-reported paths plausibly name the same file.

    Vendors emit the same file as repo-relative, absolute, or diff-prefixed
    (``a/``/``b/``) paths. Beyond normalized equality, accept a
    component-boundary suffix match in either direction so
    ``/repo/skills/foo.py`` pairs with ``skills/foo.py``.
    """
    if not a or not b:
        return False
    na, nb = _normalize_path(a), _normalize_path(b)
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return longer.endswith("/" + shorter)


# Classifications vary by reviewer. Families retain useful taxonomy evidence
# without letting it veto an otherwise exact source-location match.
_TYPE_FAMILIES = {
    "correctness": "correctness", "contract_mismatch": "correctness",
    "compatibility": "correctness", "resilience": "correctness",
    "security": "security", "performance": "performance",
    "architecture": "architecture", "spec_gap": "architecture",
    "style": "style", "observability": "observability",
}

_SYNONYMS = {
    "absent": "missing", "omitted": "missing", "lacks": "missing",
    "rejects": "refuse", "rejected": "refuse", "refuses": "refuse",
    "blocker": "blocking", "blockers": "blocking", "blocked": "blocking",
    "persisted": "write", "persists": "write", "writes": "write", "written": "write",
    "duplicate": "repeated", "duplicates": "repeated", "duplicated": "repeated",
    "different": "paraphrase", "differently": "paraphrase", "reworded": "paraphrase",
    "contract": "schema", "validation": "validate", "validator": "validate",
}
_STOP_WORDS = {
    "the", "and", "for", "from", "with", "that", "this", "into", "only",
    "after", "before", "when", "while", "than", "then", "every", "still",
}


def _type_family(value: str) -> str:
    canonical = _canonical_type(value)
    return _TYPE_FAMILIES.get(canonical, canonical)


def _tokenize(text: str) -> set[str]:
    """Tokenize text for Jaccard similarity."""
    tokens = {
        re.sub(r"[^a-z0-9_-]", "", word.lower())
        for word in text.split()
    }
    return {
        _SYNONYMS.get(token, token) for token in tokens
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _normalize_path(value: str | None) -> str | None:
    if not value:
        return None
    parts: list[str] = []
    for part in value.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    if len(parts) > 1 and parts[0] in {"a", "b"}:
        parts = parts[1:]
    return "/".join(parts)


def _normalize_identity(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9_.:-]", "", value.lower())
    return normalized or None


def _canonical_fingerprint_path(value: str | None) -> str:
    """Return a location suffix stable across absolute and repo-relative paths."""
    normalized = _normalize_path(value)
    if not normalized:
        return ""
    parts = normalized.split("/")
    return "/".join(parts[-3:])


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def match_score(a: Finding, b: Finding) -> tuple[float, str]:
    """Compute match score and basis between two findings.

    Score bands are calibrated so each is reachable at the default 0.6
    threshold with realistic inputs — independent LLMs never produce
    verbatim-identical descriptions, so every band must clear the
    threshold on paraphrased agreement.

    Returns:
        (score, basis) where score is 0.0-1.0 and basis describes
        the matching criteria used.
    """
    same_family = _type_family(a.type) == _type_family(b.type)
    same_file = _paths_match(a.file_path, b.file_path)
    path_a, path_b = _normalize_path(a.file_path), _normalize_path(b.file_path)
    symbol_a, symbol_b = _normalize_identity(a.affected_symbol), _normalize_identity(b.affected_symbol)
    requirement_a, requirement_b = _normalize_identity(a.requirement_id), _normalize_identity(b.requirement_id)

    if requirement_a and requirement_a == requirement_b:
        return 0.94, "requirement"
    if symbol_a and symbol_a == symbol_b and (not path_a or not path_b or same_file):
        return 0.93, "symbol"

    # Location match: same file + overlapping lines. Two vendors pointing
    # at the same lines almost certainly describe the same issue even
    # when their type labels differ.
    if same_file and a.line_start is not None and b.line_start is not None:
        a_end = a.line_end or a.line_start
        b_end = b.line_end or b.line_start
        if a.line_start <= b_end and b.line_start <= a_end:
            if same_family:
                return 0.95, "location+type"
            return 0.88, "location+cross-family"
        distance = max(a.line_start - b_end, b.line_start - a_end, 0)
        if distance <= 20 and (same_family or (symbol_a and symbol_a == symbol_b)):
            return 0.86, "nearby-location"

    # Different type families need deterministic structural evidence; text
    # similarity alone is too weak to merge unrelated categories.
    if not same_family:
        return 0.0, ""

    desc_sim = _jaccard(_tokenize(a.description), _tokenize(b.description))

    if same_file and desc_sim >= 0.25:
        return min(0.5 + desc_sim * 0.4, 0.85), "file+type+description"

    if desc_sim >= 0.4:
        return min(0.45 + desc_sim * 0.4, 0.8), "type+description"

    return 0.0, ""


def _higher_criticality(a: str, b: str) -> str:
    """Return the higher criticality level."""
    return a if _CRITICALITY_ORDER.get(a, 0) >= _CRITICALITY_ORDER.get(b, 0) else b


# ---------------------------------------------------------------------------
# Synthesizer
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 0.6
MAX_FINDINGS_PER_VENDOR = 500
MAX_VENDOR_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_TOTAL_FINDINGS = 2500
MAX_MATCH_COMPARISONS = 250_000


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
        adjudication_ledger: list[dict[str, Any]] | Path | None = None,
        trusted_approval_resolver: TrustedApprovalResolver | None = None,
    ) -> ConsensusReport:
        """Produce a consensus report from multiple vendor results."""
        for vendor_result in vendor_results:
            if len(vendor_result.findings) > MAX_FINDINGS_PER_VENDOR:
                raise ConsensusInputError(
                    f"{vendor_result.vendor}: exceeds {MAX_FINDINGS_PER_VENDOR} finding limit"
                )
            encoded = json.dumps(
                [asdict(finding) for finding in vendor_result.findings],
                ensure_ascii=False,
            ).encode("utf-8")
            if len(encoded) > MAX_VENDOR_PAYLOAD_BYTES:
                raise ConsensusInputError(
                    f"{vendor_result.vendor}: exceeds {MAX_VENDOR_PAYLOAD_BYTES} byte limit"
                )
        if sum(len(result.findings) for result in vendor_results) > MAX_TOTAL_FINDINGS:
            raise ConsensusInputError(f"review exceeds {MAX_TOTAL_FINDINGS} total findings")

        def logical_id(result: VendorResult) -> str:
            value = result.logical_result
            if isinstance(value, Mapping):
                identifier = value.get("logical_request_id")
            else:
                identifier = getattr(value, "logical_request_id", None)
            return identifier if isinstance(identifier, str) else ""

        def logical_terminal_vendor(result: VendorResult) -> str | None:
            value = result.logical_result
            if isinstance(value, Mapping):
                terminal = value.get("terminal_vendor")
            else:
                terminal = getattr(value, "terminal_vendor", None)
            return terminal if isinstance(terminal, str) and terminal else None

        eligible_by_vendor: dict[str, VendorResult] = {}
        requested_slot_ids: set[str] = set()
        duplicate_slot_ids: set[str] = set()
        for result in sorted(vendor_results, key=lambda item: (item.vendor, logical_id(item))):
            if not result.trusted_internal:
                slot_id = logical_id(result) or f"audit-only:{result.vendor}"
                if slot_id in requested_slot_ids and logical_id(result):
                    duplicate_slot_ids.add(slot_id)
                requested_slot_ids.add(slot_id)
            if is_quorum_eligible(result.logical_result):
                terminal_vendor = logical_terminal_vendor(result)
                if terminal_vendor is None:
                    continue
                if any(finding.vendor != terminal_vendor for finding in result.findings):
                    raise ConsensusInputError(
                        "eligible findings must belong to the validated terminal vendor"
                    )
                eligible_by_vendor.setdefault(terminal_vendor, result)
        if duplicate_slot_ids:
            raise ConsensusInputError("duplicate logical review request id")
        for result in vendor_results:
            if result.trusted_internal and any(
                finding.vendor != result.vendor for finding in result.findings
            ):
                raise ConsensusInputError("trusted internal findings must retain source identity")
        eligible = list(eligible_by_vendor.values())
        included = [*eligible, *(
            result for result in vendor_results
            if result.trusted_internal and result.vendor not in eligible_by_vendor
        )]
        quorum_met = len(eligible) >= self.quorum and len(eligible) <= len(requested_slot_ids)

        # Build reviewer metadata
        reviewers = [
            {
                "vendor": vendor,
                "agent_id": vendor,
                "success": vendor in eligible_by_vendor,
                "source_eligible": selected is not None and (
                    vendor in eligible_by_vendor or selected.trusted_internal
                ),
                "findings_count": len(selected.findings) if selected else 0,
                "elapsed_seconds": selected.elapsed_seconds if selected else 0.0,
                "error": None if vendor in eligible_by_vendor else next(
                    (result.error for result in vendor_results if result.vendor == vendor and result.error),
                    "ineligible or missing terminal attempt provenance",
                ),
            }
            for vendor in sorted({
                *(result.vendor for result in vendor_results),
                *eligible_by_vendor,
            })
            for selected in [eligible_by_vendor.get(vendor) or next(
                (result for result in vendor_results if result.vendor == vendor and result.trusted_internal),
                None,
            )]
        ]

        # Collect all findings across vendors
        all_findings: list[Finding] = []
        for vr in included:
            all_findings.extend(vr.findings)

        # Match findings cross-vendor
        matches = self._match_all(all_findings)

        # Classify matches into consensus findings
        consensus_findings = self._classify(matches)
        applied_adjudications = self._apply_adjudications(
            consensus_findings,
            adjudication_ledger=adjudication_ledger,
            trusted_approval_resolver=trusted_approval_resolver,
        )

        # Compute summary counts
        confirmed = sum(1 for cf in consensus_findings if cf.status == "confirmed")
        unconfirmed = sum(1 for cf in consensus_findings if cf.status == "unconfirmed")
        disagreement = sum(1 for cf in consensus_findings if cf.status == "disagreement")
        integration_blocking = sum(cf.integration_blocking for cf in consensus_findings)
        convergence_blocking = sum(cf.convergence_blocking for cf in consensus_findings)
        blocking = sum(cf.effective_blocking for cf in consensus_findings)

        report = ConsensusReport(
            review_type=review_type,
            target=target,
            reviewers=reviewers,
            quorum_met=quorum_met,
            quorum_requested=len(requested_slot_ids),
            quorum_received=len(eligible),
            consensus_findings=consensus_findings,
            total_unique=len(consensus_findings),
            confirmed_count=confirmed,
            unconfirmed_count=unconfirmed,
            disagreement_count=disagreement,
            blocking_count=blocking,
            integration_blocking_count=integration_blocking,
            convergence_blocking_count=convergence_blocking,
        )
        report.applied_adjudications = applied_adjudications
        return report

    def _match_all(self, findings: list[Finding]) -> list[FindingMatch]:
        """Build vendor-independent complete-link groups from bounded edges."""

        def stable_key(finding: Finding) -> tuple[str, str, str, str, int, int]:
            return (
                self._concern_fingerprint(finding),
                _type_family(finding.type),
                _canonical_fingerprint_path(finding.file_path),
                " ".join(finding.description.lower().split()),
                finding.line_start or 0,
                finding.line_end or 0,
            )

        ordered = sorted(findings, key=lambda finding: (*stable_key(finding), finding.vendor, finding.id))
        buckets: dict[str, list[int]] = {}
        candidate_pairs: set[tuple[int, int]] = set()
        score_cache: dict[tuple[int, int], tuple[float, str]] = {}
        comparisons = 0

        def keys(finding: Finding) -> set[str]:
            family = _type_family(finding.type)
            result = {f"term:{family}:{token}" for token in _tokenize(finding.description)}
            path = _canonical_fingerprint_path(finding.file_path)
            symbol = _normalize_identity(finding.affected_symbol)
            requirement = _normalize_identity(finding.requirement_id)
            if path:
                result.add(f"path:{path}")
            if symbol:
                result.add(f"symbol:{symbol}")
            if requirement:
                result.add(f"requirement:{requirement}")
            return result

        for index, candidate in enumerate(ordered):
            for key in sorted(keys(candidate)):
                for other in buckets.get(key, []):
                    if ordered[other].vendor != candidate.vendor:
                        candidate_pairs.add((other, index))
                buckets.setdefault(key, []).append(index)

        def score_for(left: int, right: int) -> tuple[float, str]:
            nonlocal comparisons
            pair = (left, right) if left < right else (right, left)
            if pair not in score_cache:
                comparisons += 1
                if comparisons > MAX_MATCH_COMPARISONS:
                    raise ConsensusInputError("consensus matching exceeded bounded work budget")
                score_cache[pair] = match_score(ordered[pair[0]], ordered[pair[1]])
            return score_cache[pair]

        edges = [
            (*score_for(left, right), left, right)
            for left, right in sorted(candidate_pairs)
            if score_for(left, right)[0] >= self.match_threshold
        ]
        edges.sort(key=lambda edge: (
            -edge[0], stable_key(ordered[edge[2]]), stable_key(ordered[edge[3]]),
        ))

        groups: dict[int, set[int]] = {index: {index} for index in range(len(ordered))}
        group_of = {index: index for index in range(len(ordered))}
        for _score, _basis, left, right in edges:
            left_group = group_of[left]
            right_group = group_of[right]
            if left_group == right_group:
                continue
            left_members = groups[left_group]
            right_members = groups[right_group]
            if {ordered[index].vendor for index in left_members}.intersection(
                ordered[index].vendor for index in right_members
            ):
                continue
            if not all(
                score_for(left_index, right_index)[0] >= self.match_threshold
                for left_index in left_members
                for right_index in right_members
            ):
                continue
            merged = left_members | right_members
            target = min(merged, key=lambda index: stable_key(ordered[index]))
            groups.pop(left_group)
            groups.pop(right_group)
            groups[target] = merged
            for index in merged:
                group_of[index] = target

        matches: list[FindingMatch] = []
        grouped = sorted(
            groups.values(),
            key=lambda members: tuple(sorted(stable_key(ordered[index]) for index in members)),
        )
        for indexes in grouped:
            members = sorted(indexes, key=lambda index: (*stable_key(ordered[index]), ordered[index].vendor, ordered[index].id))
            primary = ordered[members[0]]
            edges = [
                (*score_for(left, right), left, right)
                for offset, left in enumerate(members)
                for right in members[offset + 1:]
            ]
            best = max(edges, default=(0.0, "", 0, 0), key=lambda edge: edge[0])
            matches.append(FindingMatch(
                primary=primary,
                matched=[ordered[index] for index in members[1:]],
                score=best[0],
                basis=best[1],
            ))
        return matches

    def _classify(self, matches: list[FindingMatch]) -> list[ConsensusFinding]:
        """Classify matches into confirmed/unconfirmed/disagreement."""
        results: list[ConsensusFinding] = []

        for i, m in enumerate(matches, 1):
            members = [m.primary, *m.matched]
            all_dispositions = {finding.vendor: finding.disposition for finding in members}
            agreed_crit = m.primary.criticality
            for matched in m.matched:
                agreed_crit = _higher_criticality(agreed_crit, matched.criticality)
            if not m.matched:
                status, policy_status = "unconfirmed", "provisional"
                recommended = m.primary.disposition
            elif len(set(all_dispositions.values())) == 1:
                status = policy_status = "confirmed"
                recommended = m.primary.disposition
            else:
                status = policy_status = "disagreement"
                recommended = "escalate"
            source_fingerprints = {
                f"{finding.vendor}:{finding.id}": self._concern_fingerprint(finding)
                for finding in members
            }
            fingerprints = sorted(set(source_fingerprints.values()))
            group_id = "cg-" + hashlib.sha256("\n".join(fingerprints).encode()).hexdigest()[:16]
            decision = evaluate_blocking(
                policy_status=policy_status,
                criticality=agreed_crit,
                vendor_dispositions=all_dispositions,
                adjudication={"status": "unreviewed"},
            )
            results.append(ConsensusFinding(
                id=i,
                status=status,
                policy_status=policy_status,
                primary_vendor=m.primary.vendor,
                primary_finding_id=m.primary.id,
                matched_findings=[{"vendor": item.vendor, "finding_id": item.id} for item in m.matched],
                match_score=m.score,
                agreed_type=m.primary.type,
                agreed_criticality=agreed_crit,
                recommended_disposition=recommended,
                description=m.primary.description,
                vendor_dispositions=all_dispositions,
                group_id=group_id,
                integration_blocking=decision.integration_blocking,
                convergence_blocking=decision.convergence_blocking,
                effective_blocking=decision.effective_blocking,
                match_method="single" if not m.matched else ("structured" if "location" in m.basis else "description"),
                match_evidence=[m.basis] if m.basis else [],
                concern_fingerprints=fingerprints,
                source_fingerprints=source_fingerprints,
            ))

        return results

    @staticmethod
    def _concern_fingerprint(finding: Finding) -> str:
        """Return a stable fingerprint for one source concern, not its group."""
        normalized_description = re.sub(
            r"^(critical|nit|optional|fyi|none):\s*", "",
            " ".join(finding.description.lower().split()),
        )
        value = "\0".join((
            _type_family(finding.type),
            _canonical_fingerprint_path(finding.file_path),
            str(finding.line_start or ""),
            str(finding.line_end or ""),
            _normalize_identity(finding.affected_symbol) or "",
            _normalize_identity(finding.requirement_id) or "",
            normalized_description,
        ))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _load_adjudication_ledger(
        adjudication_ledger: list[dict[str, Any]] | Path | None,
    ) -> list[dict[str, Any]]:
        if adjudication_ledger is None:
            return []
        if isinstance(adjudication_ledger, Path):
            try:
                payload = json.loads(adjudication_ledger.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConsensusInputError(
                    f"cannot load adjudication ledger {adjudication_ledger}: {exc}"
                ) from exc
        else:
            payload = adjudication_ledger
        if isinstance(payload, dict):
            payload = payload.get("entries")
        if not isinstance(payload, list) or not all(isinstance(entry, dict) for entry in payload):
            raise ConsensusInputError("adjudication ledger must be a list of entries")
        return list(payload)

    def _apply_adjudications(
        self,
        findings: list[ConsensusFinding],
        *,
        adjudication_ledger: list[dict[str, Any]] | Path | None,
        trusted_approval_resolver: TrustedApprovalResolver | None,
    ) -> list[dict[str, Any]]:
        entries = self._load_adjudication_ledger(adjudication_ledger)
        by_group = {finding.group_id: finding for finding in findings}
        prepared: list[tuple[dict[str, Any], ConsensusFinding, dict[str, Any]]] = []
        seen_groups: set[str] = set()
        seen_keys: set[tuple[str, tuple[str, ...]]] = set()
        for entry in entries:
            group_id = entry.get("group_id")
            fingerprints = entry.get("concern_fingerprints")
            adjudication = entry.get("adjudication")
            if (
                not isinstance(group_id, str)
                or group_id not in by_group
                or not isinstance(fingerprints, list)
                or fingerprints != sorted(fingerprints)
                or fingerprints != by_group[group_id].concern_fingerprints
                or not isinstance(adjudication, dict)
                or not isinstance(entry.get("recorded_at"), str)
            ):
                raise ConsensusInputError("stale or malformed adjudication ledger entry")
            key = (group_id, tuple(fingerprints))
            if group_id in seen_groups or key in seen_keys:
                raise ConsensusInputError("duplicate adjudication ledger key")
            seen_groups.add(group_id)
            seen_keys.add(key)
            status = adjudication.get("status")
            if status not in {"unreviewed", "fixed", "false_positive", "accepted_risk", "deferred"}:
                raise ConsensusInputError("adjudication ledger contains an unknown status")
            if status in {"fixed", "false_positive", "accepted_risk"} and not is_valid_non_blocking_adjudication(
                adjudication,
                trusted_approval_resolver=trusted_approval_resolver,
            ):
                raise ConsensusInputError("adjudication ledger entry lacks valid evidence or authorization")
            finding = by_group[group_id]
            prepared.append((entry, finding, adjudication))

        applied: list[dict[str, Any]] = []
        for entry, finding, adjudication in prepared:
            finding.adjudication = dict(adjudication)
            decision = evaluate_blocking(
                policy_status=finding.policy_status,
                criticality=finding.agreed_criticality,
                vendor_dispositions=finding.vendor_dispositions,
                adjudication=finding.adjudication,
                trusted_approval_resolver=trusted_approval_resolver,
            )
            finding.integration_blocking = decision.integration_blocking
            finding.convergence_blocking = decision.convergence_blocking
            finding.effective_blocking = decision.effective_blocking
            applied.append(dict(entry))
        return applied

    def to_dict(self, report: ConsensusReport) -> dict[str, Any]:
        """Convert report to dict conforming to consensus-report.schema.json."""
        eligible_vendors = [reviewer["vendor"] for reviewer in report.reviewers if reviewer["success"]]

        def source_fingerprint(cf: ConsensusFinding, vendor: str, finding_id: int) -> str:
            key = f"{vendor}:{finding_id}"
            # Compatibility fixtures may construct ConsensusFinding directly.
            # Keep them serializable while production synthesis always retains
            # the exact source fingerprint calculated before grouping.
            return cf.source_fingerprints.get(
                key,
                hashlib.sha256(f"{cf.group_id}\0{key}".encode("utf-8")).hexdigest(),
            )

        return {
            "schema_version": 2,
            "review_type": report.review_type,
            "target": report.target,
            "reviewers": [dict(reviewer) for reviewer in report.reviewers],
            "quorum_met": report.quorum_met,
            "quorum_requested": report.quorum_requested,
            "quorum_received": report.quorum_received,
            "quorum": {
                "requested": report.quorum_requested,
                "received": report.quorum_received,
                "minimum_required": self.quorum,
                "eligible_vendors": eligible_vendors,
                "met": report.quorum_met,
            },
            "consensus_findings": [
                {
                    "id": cf.id,
                    "group_id": cf.group_id,
                    "algorithm_version": "structured-v2",
                    "status": cf.status,
                    "policy_status": cf.policy_status,
                    "primary_vendor": cf.primary_vendor,
                    "primary_finding_id": cf.primary_finding_id,
                    "matched_findings": cf.matched_findings,
                    "match_score": cf.match_score,
                    "agreed_type": cf.agreed_type,
                    "agreed_criticality": cf.agreed_criticality,
                    "recommended_disposition": cf.recommended_disposition,
                    "criticality": cf.agreed_criticality,
                    "description": cf.description,
                    "vendor_dispositions": cf.vendor_dispositions,
                    "source_findings": [
                        {
                            "vendor": cf.primary_vendor,
                            "finding_id": cf.primary_finding_id,
                            "concern_fingerprint": source_fingerprint(
                                cf, cf.primary_vendor, cf.primary_finding_id,
                            ),
                            "disposition": cf.vendor_dispositions.get(cf.primary_vendor, cf.recommended_disposition),
                        },
                        *[
                            {
                                "vendor": item["vendor"],
                                "finding_id": item["finding_id"],
                                "concern_fingerprint": source_fingerprint(
                                    cf, item["vendor"], item["finding_id"],
                                ),
                                "disposition": cf.vendor_dispositions.get(item["vendor"], cf.recommended_disposition),
                            }
                            for item in cf.matched_findings
                        ],
                    ],
                    "match": {"method": cf.match_method, "score": cf.match_score, "evidence": cf.match_evidence},
                    "adjudication": cf.adjudication,
                    **({
                        "policy": {
                            "integration_blocking": cf.integration_blocking,
                            "convergence_blocking": cf.convergence_blocking,
                            "effective_blocking": cf.effective_blocking,
                        },
                    } if cf.group_id else {}),
                }
                for cf in report.consensus_findings
            ],
            "summary": {
                "total_unique_findings": report.total_unique,
                "confirmed_count": report.confirmed_count,
                "provisional_count": report.unconfirmed_count,
                "unconfirmed_count": report.unconfirmed_count,
                "disagreement_count": report.disagreement_count,
                "integration_blocking_count": report.integration_blocking_count,
                "convergence_blocking_count": report.convergence_blocking_count,
                "effective_blocking_count": report.blocking_count,
                "blocking_count": report.blocking_count,
            },
            "applied_adjudications": list(report.applied_adjudications),
        }

    def write_report(
        self,
        report: ConsensusReport,
        output_path: Path,
        *,
        trusted_approval_resolver: TrustedApprovalResolver | None = None,
    ) -> None:
        """Validate then atomically persist a consensus report."""
        payload = self.to_dict(report)
        validate_consensus_payload(
            payload,
            trusted_approval_resolver=trusted_approval_resolver,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, output_path)
        except (OSError, TypeError, ValueError):
            temporary.unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------------------
# Behavioral / gen-eval vendor source (additive — see WP5 of
# factory-missions-architecture-alignment)
# ---------------------------------------------------------------------------

# Lower-numbered values rank first when sorting ascending.
# critical < high < medium < low in the spec contract.
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_behavioral_findings(
    input_dir: Path,
    *,
    schema_path: Path | None = None,
    vendor: str = "gen-eval",
    log_stream: Any = None,
) -> list[Finding]:
    """Load behavioral findings from ``findings-<vendor>.json``.

    Returns an empty list when the file is missing — gen-eval may
    legitimately not have run for changes without descriptors. When the
    file exists, validates it against the review-findings schema (if a
    schema path is provided or jsonschema is available) and raises
    :class:`ConsensusInputError` on schema-violation.

    Args:
        input_dir: directory in which to look for ``findings-<vendor>.json``.
        schema_path: optional path to ``review-findings.schema.json``.
            When None, attempts to locate it at
            ``openspec/schemas/review-findings.schema.json`` relative to
            the repo root (best-effort).
        vendor: vendor name (default ``gen-eval``).
        log_stream: file-like object to write the "no gen-eval findings"
            log line to. Defaults to ``sys.stdout`` so the synthesizer's
            stdout vendor-count log is consistent.

    Returns:
        A list of :class:`Finding` objects with ``vendor=<vendor>``.
    """
    if log_stream is None:
        log_stream = sys.stdout

    findings_path = input_dir / f"findings-{vendor}.json"
    if not findings_path.exists():
        # Per spec: "Missing gen-eval findings file is not an error."
        msg = f"no {vendor} findings (skipping behavioral source)"
        print(msg, file=log_stream)
        logger.info(msg)
        return []

    try:
        data = json.loads(findings_path.read_text())
    except json.JSONDecodeError as exc:
        raise ConsensusInputError(
            f"{findings_path}: invalid JSON: {exc}"
        ) from exc

    # Optional schema validation. We tolerate jsonschema being unavailable
    # since the synthesizer's existing flow doesn't require it.
    if schema_path is None:
        # Best-effort lookup: walk up from this file looking for the
        # repo's openspec/schemas directory.
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "openspec" / "schemas" / "review-findings.schema.json"
            if candidate.exists():
                schema_path = candidate
                break

    if schema_path is not None and schema_path.exists():
        try:
            import jsonschema  # type: ignore[import-untyped]

            schema = json.loads(schema_path.read_text())
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as exc:
                raise ConsensusInputError(
                    f"{findings_path}: schema violation: {exc.message} "
                    f"(at {'/'.join(str(p) for p in exc.absolute_path)})"
                ) from exc
        except ImportError:
            # jsonschema not installed; skip validation gracefully.
            pass

    findings_data = data.get("findings", [])
    if not isinstance(findings_data, list):
        raise ConsensusInputError(
            f"{findings_path}: 'findings' must be a list"
        )

    return [Finding.from_dict(f, vendor=vendor) for f in findings_data]


def rank_findings(findings: list[Finding]) -> list[Finding]:
    """Rank findings uniformly by severity (critical → low).

    Ties are broken by source-file order (insertion order — the caller is
    responsible for passing findings already ordered by source file).
    Per the contract: ``critical < high < medium < low`` mapped to
    ascending sort, where lower ranks come first.

    The synthesizer MUST NOT introduce different ranking logic for
    behavioral vs scrutiny findings (per
    ``contracts/findings-vendor-source.md``). This helper enforces that
    by ranking purely on the schema's ``criticality`` field.
    """
    indexed = list(enumerate(findings))
    indexed.sort(
        key=lambda pair: (
            _SEVERITY_RANK.get(pair[1].criticality, 99),
            pair[0],  # stable tie-break by original index (source-file order)
        )
    )
    return [f for _, f in indexed]


def format_vendor_counts(per_vendor_counts: dict[str, int]) -> str:
    """Format per-vendor count log line per the contract.

    Matches the regex ``merged: .*claude=N.*codex=M.*gen-eval=K.*``
    expected by the "Synthesizer merges gen-eval and reviewer findings"
    spec scenario.
    """
    parts = [f"{name}={count}" for name, count in per_vendor_counts.items()]
    return "merged: " + ", ".join(parts)


def _load_manifest_logical_results(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Index validated terminal attempt chains by terminal vendor."""
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsensusInputError(f"cannot load review manifest {path}: {exc}") from exc
    dispatches = payload.get("dispatches") if isinstance(payload, dict) else None
    if not isinstance(dispatches, list):
        raise ConsensusInputError("review manifest is missing dispatch attempt chains")
    indexed: dict[str, list[dict[str, Any]]] = {}
    for dispatch in dispatches:
        if not isinstance(dispatch, dict) or not is_quorum_eligible(dispatch):
            continue
        terminal_vendor = dispatch.get("terminal_vendor")
        if isinstance(terminal_vendor, str) and terminal_vendor:
            indexed.setdefault(terminal_vendor, []).append(dispatch)
    for chains in indexed.values():
        chains.sort(key=lambda chain: str(chain.get("logical_request_id", "")))
    return indexed


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Synthesize consensus from per-vendor findings files.

    Usage:
        python consensus_synthesizer.py \\
            --review-type plan --target my-feature \\
            --findings findings-codex.json findings-grok.json \\
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
        "--findings", nargs="*", default=[],
        help="Per-vendor findings JSON files (use this OR --input-dir)",
    )
    parser.add_argument(
        "--input-dir",
        help=(
            "Directory containing findings-<vendor>.json files. When set, "
            "all findings-*.json in the directory are loaded (including "
            "findings-gen-eval.json as a behavioral source)."
        ),
    )
    parser.add_argument("--output", required=True, help="Output consensus JSON path")
    parser.add_argument(
        "--manifest",
        help="Review manifest containing validated terminal attempt chains",
    )
    parser.add_argument("--quorum", type=int, default=2, help="Minimum reviewers")
    parser.add_argument(
        "--threshold", type=float, default=MATCH_THRESHOLD,
        help="Match score threshold for confirmed status",
    )
    parser.add_argument(
        "--schema",
        help="Optional path to review-findings.schema.json for validation",
    )
    args = parser.parse_args()

    # Load per-vendor findings
    vendor_results: list[VendorResult] = []
    findings_paths: list[Path] = [Path(p) for p in args.findings]

    if args.input_dir:
        input_dir = Path(args.input_dir)
        # Discover all findings-*.json files in the directory, but defer
        # findings-gen-eval.json to the additive behavioral source path so
        # missing-file handling is identical to non-directory invocations.
        for path in sorted(input_dir.glob("findings-*.json")):
            if path.name == "findings-gen-eval.json":
                continue
            findings_paths.append(path)

    manifest_path = Path(args.manifest) if args.manifest else None
    if manifest_path is None and args.input_dir:
        candidate = Path(args.input_dir) / "review-manifest.json"
        manifest_path = candidate if candidate.is_file() else None
    if manifest_path is None and findings_paths:
        parents = {path.parent.resolve() for path in findings_paths}
        if len(parents) == 1:
            candidate = next(iter(parents)) / "review-manifest.json"
            manifest_path = candidate if candidate.is_file() else None
    logical_results = _load_manifest_logical_results(manifest_path)
    manifest_loaded = manifest_path is not None and manifest_path.is_file()
    seen_findings_vendors: set[str] = set()

    for p in findings_paths:
        if not p.exists():
            print(f"Warning: {p} not found, skipping", file=sys.stderr)
            vendor_results.append(VendorResult(
                vendor=p.stem, findings=[], success=False,
                error=f"File not found: {p}",
            ))
            continue
        data = json.loads(p.read_text())
        # findings-claude.json -> "claude" (drop the "findings-" prefix)
        default_vendor = p.stem
        if default_vendor.startswith("findings-"):
            default_vendor = default_vendor[len("findings-"):]
        vendor = data.get("reviewer_vendor", default_vendor)
        if not isinstance(vendor, str) or not vendor:
            raise ConsensusInputError(f"{p}: reviewer_vendor must be a non-empty string")
        if vendor in seen_findings_vendors:
            raise ConsensusInputError(f"duplicate findings association for terminal vendor {vendor}")
        seen_findings_vendors.add(vendor)
        findings = [
            Finding.from_dict(f, vendor=vendor)
            for f in data.get("findings", [])
        ]
        chains = logical_results.get(vendor, [])
        if manifest_loaded and len(chains) != 1:
            raise ConsensusInputError(
                f"findings for {vendor} require exactly one eligible manifest attempt chain"
            )
        logical_result = chains.pop(0) if chains else None
        vendor_results.append(VendorResult(
            vendor=vendor,
            findings=findings,
            success=logical_result is not None,
            logical_result=logical_result,
            error=None if logical_result is not None else "missing eligible manifest attempt chain",
        ))

    for terminal_vendor, chains in sorted(logical_results.items()):
        if not chains:
            continue
        if len(chains) != 1:
            raise ConsensusInputError(
                f"terminal vendor {terminal_vendor} has duplicate eligible manifest attempt chains"
            )
        vendor_results.append(VendorResult(
            vendor=terminal_vendor,
            findings=[],
            success=True,
            logical_result=chains[0],
        ))

    # Additive behavioral source: load findings-gen-eval.json from
    # --input-dir (if provided). Missing file is not an error.
    behavioral_findings: list[Finding] = []
    if args.input_dir:
        schema_path = Path(args.schema) if args.schema else None
        behavioral_findings = load_behavioral_findings(
            Path(args.input_dir),
            schema_path=schema_path,
        )
        if behavioral_findings:
            vendor_results.append(VendorResult(
                vendor="gen-eval", findings=behavioral_findings,
                success=False, trusted_internal=True,
            ))

    synth = ConsensusSynthesizer(
        match_threshold=args.threshold, quorum=args.quorum,
    )
    report = synth.synthesize(
        review_type=args.review_type,
        target=args.target,
        vendor_results=vendor_results,
    )

    # Sort consensus_findings uniformly by severity ascending (critical
    # first), with ties broken by original (source-file) order. This
    # matches the contract that scrutiny and behavioral findings are
    # ranked by the same key. Stable sort preserves source-file order.
    report.consensus_findings.sort(
        key=lambda cf: _SEVERITY_RANK.get(cf.agreed_criticality, 99),
    )
    # Re-id after sort for stable output ordering.
    for new_id, cf in enumerate(report.consensus_findings, start=1):
        cf.id = new_id

    synth.write_report(report, Path(args.output))

    # Per-vendor count log (regex `merged: .*claude=N.*codex=M.*gen-eval=K`)
    counts = {vr.vendor: len(vr.findings) for vr in vendor_results}
    print(format_vendor_counts(counts))

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
