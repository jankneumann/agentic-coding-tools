"""Project bug-scrub findings into canonical candidate-work stubs."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from candidate_work import derive_suggested_change_id, write_candidate_work
from models import BugScrubReport, Finding

_PRIORITY = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
_EFFORT = {
    "lint": "XS",
    "type-error": "XS",
    "code-marker": "XS",
    "test-failure": "S",
    "deferred-issue": "S",
    "architecture": "M",
    "security": "M",
    "spec-violation": "M",
}


def _normalized_text(value: object) -> str:
    return " ".join(str(value).split())


def _normalized_path(value: object) -> str:
    return _normalized_text(value).replace("\\", "/")


def _source_key(finding: Finding) -> str:
    """Retain stable collector identity while stripping known ordinals."""
    source = _normalized_text(finding.source).lower()
    key = _normalized_text(finding.id)
    if source in {"ruff", "mypy", "markers"}:
        return re.sub(r":\d+$", "", key)
    if source == "architecture" or source.startswith("deferred:"):
        return re.sub(r"-\d+$", "", key)
    if source == "openspec":
        return "openspec"
    return key


def _semantic_detail(finding: Finding) -> str:
    """Normalize meaning while removing a leading volatile line coordinate."""
    detail = _normalized_text(finding.detail)
    if finding.line is None or not detail:
        return detail
    paths = {_normalized_path(finding.file_path)}
    paths.add(Path(_normalized_path(finding.file_path)).name)
    for path in sorted(paths, key=len, reverse=True):
        prefix = f"{path}:{finding.line}:"
        if path and detail.startswith(prefix):
            return detail.removeprefix(prefix).strip()
    return detail


def _semantic_fingerprint(finding: Finding) -> str:
    """Serialize the stable semantic identity of one bug-scrub finding."""
    origin_change_id = ""
    origin_artifact_path = ""
    if finding.origin is not None:
        origin_change_id = _normalized_text(finding.origin.change_id)
        origin_artifact_path = _normalized_path(finding.origin.artifact_path)
    identity = {
        "category": _normalized_text(finding.category).lower(),
        "detail": _semantic_detail(finding),
        "file_path": _normalized_path(finding.file_path),
        "origin_artifact_path": origin_artifact_path,
        "origin_change_id": origin_change_id,
        "source": _normalized_text(finding.source).lower(),
        "source_key": _source_key(finding),
    }
    return json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _compact_source_id(fingerprint: str) -> str:
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return f"bug-finding-{digest}"


def _severity(value: object) -> str:
    severity = _normalized_text(value).lower()
    if severity not in _PRIORITY:
        raise ValueError(f"unsupported bug-scrub severity: {severity!r}")
    return severity


def _candidate(
    finding: Finding, source_artifact: str, source_id: str
) -> dict[str, Any]:
    try:
        effort = _EFFORT[finding.category]
    except KeyError as exc:
        raise ValueError(
            f"unsupported bug-scrub category: {finding.category!r}"
        ) from exc
    severity = _severity(finding.severity)
    detail = finding.detail.strip() or (
        f"Resolve the {finding.category} finding reported by {finding.source}."
    )
    location = finding.file_path or "the project"
    return {
        "schema_version": 1,
        "title": finding.title,
        "description": detail,
        "rationale": (
            f"Bug-scrub classified finding {finding.id} as {severity} "
            f"at {location}."
        ),
        "provenance": {
            "source_artifact": source_artifact,
            "finding_ids": [finding.id],
            "generator": "bug-scrub",
        },
        "effort": effort,
        "priority": _PRIORITY[severity],
        "suggested_change_id": derive_suggested_change_id(
            "bug-scrub", source_id
        ),
        "tags": [finding.category, f"severity-{severity}"],
    }


def project_candidate_work(
    report: BugScrubReport, source_artifact: str
) -> list[dict[str, Any]]:
    """Return one candidate for every finding retained in the rich report."""
    candidates: list[dict[str, Any]] = []
    fingerprints_by_source_id: dict[str, str] = {}
    for finding in report.findings:
        fingerprint = _semantic_fingerprint(finding)
        source_id = _compact_source_id(fingerprint)
        previous = fingerprints_by_source_id.get(source_id)
        if previous is not None and previous != fingerprint:
            raise ValueError(
                f"bug-scrub semantic source ID collision: {source_id}"
            )
        fingerprints_by_source_id[source_id] = fingerprint
        candidates.append(_candidate(finding, source_artifact, source_id))
    return candidates


def write_projection(
    report: BugScrubReport, destination: Path, source_artifact: str
) -> Path:
    """Validate the complete projection, then atomically replace its sidecar."""
    return write_candidate_work(
        destination,
        project_candidate_work(report, source_artifact),
        generator="bug-scrub",
    )
