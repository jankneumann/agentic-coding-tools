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
    return str(value).replace("\\", "/")


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


def _detail_and_line(finding: Finding) -> tuple[str, int | None]:
    """Normalize detail and remove only an exact full-path numeric prefix."""
    detail = str(finding.detail).replace("\\", "/")
    path = _normalized_path(finding.file_path)
    if path:
        match = re.fullmatch(
            rf"{re.escape(path)}:(\d+):(.*)", detail, flags=re.DOTALL
        )
        if match is not None:
            return _normalized_text(match.group(2)), int(match.group(1))
    return _normalized_text(detail), None


def _semantic_detail(finding: Finding) -> str:
    return _detail_and_line(finding)[0]


def _source_position(finding: Finding) -> tuple[bool, int, str, str, str]:
    detail_line = _detail_and_line(finding)[1]
    explicit_line = (
        finding.line
        if isinstance(finding.line, int) and not isinstance(finding.line, bool)
        else None
    )
    line = explicit_line if explicit_line is not None else detail_line
    origin_path = ""
    origin_task = ""
    if finding.origin is not None:
        origin_path = _normalized_path(finding.origin.artifact_path)
        origin_task = _normalized_text(finding.origin.task_number or "")
    return (
        line is None,
        line if line is not None else 0,
        origin_path,
        origin_task,
        _normalized_text(finding.id),
    )


def _base_semantic_identity(finding: Finding) -> dict[str, str]:
    """Return stable semantic fields before occurrence disambiguation."""
    origin_change_id = ""
    origin_artifact_path = ""
    if finding.origin is not None:
        origin_change_id = _normalized_text(finding.origin.change_id)
        origin_artifact_path = _normalized_path(finding.origin.artifact_path)
    return {
        "category": _normalized_text(finding.category).lower(),
        "detail": _semantic_detail(finding),
        "file_path": _normalized_path(finding.file_path),
        "origin_artifact_path": origin_artifact_path,
        "origin_change_id": origin_change_id,
        "source": _normalized_text(finding.source).lower(),
        "source_key": _source_key(finding),
    }


def _canonical_fingerprint(identity: dict[str, Any]) -> str:
    return json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _base_semantic_fingerprint(finding: Finding) -> str:
    return _canonical_fingerprint(_base_semantic_identity(finding))


def _semantic_fingerprint(finding: Finding, occurrence: int) -> str:
    """Serialize semantic identity with its deterministic occurrence."""
    identity: dict[str, Any] = _base_semantic_identity(finding)
    identity["occurrence"] = occurrence
    return _canonical_fingerprint(identity)


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
    indexed_findings = list(enumerate(report.findings))
    groups: dict[str, list[tuple[int, Finding]]] = {}
    for index, finding in indexed_findings:
        base = _base_semantic_fingerprint(finding)
        groups.setdefault(base, []).append((index, finding))

    occurrences: dict[int, int] = {}
    for members in groups.values():
        ordered = sorted(
            members, key=lambda item: (_source_position(item[1]), item[0])
        )
        for occurrence, (index, _finding) in enumerate(ordered, start=1):
            occurrences[index] = occurrence

    candidates: list[dict[str, Any]] = []
    fingerprints_by_source_id: dict[str, str] = {}
    for index, finding in indexed_findings:
        fingerprint = _semantic_fingerprint(finding, occurrences[index])
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
