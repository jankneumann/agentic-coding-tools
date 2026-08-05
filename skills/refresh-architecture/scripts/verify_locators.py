"""Verify behavior handbook evidence locators against the working tree (D3).

A synthesized handbook is only trustworthy if every claim it makes still points
at real code. Rather than trusting line numbers (which rot silently), each
evidence entry carries a content digest of its source span, and this resolver
re-computes that digest at check time.

Classification:

``verified``      digest matches — the claim is current
``drifted``       file and span resolve but content changed — warn, mark stale
``unresolvable``  file or span is gone — error, fail ``architecture-check``

Digests are computed over *normalized* span text (trailing whitespace stripped,
line endings unified) so reformatting churn does not thrash the whole handbook.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from arch_utils.diagnostics import DiagnosticCollector
from arch_utils.graph_io import load_graph, save_json
from handbook_schema import _iter_locators

logger = logging.getLogger(__name__)

VERIFIED = "verified"
DRIFTED = "drifted"
UNRESOLVABLE = "unresolvable"

#: Stale reason code surfaced to the freshness gate when narrative drifts.
STALE_REASON_LOCATOR_DRIFT = "handbook_locator_drift"

DIGEST_PREFIX = "sha256:"


def _normalize(lines: list[str]) -> str:
    """Return span text with trailing whitespace and line-ending noise removed."""
    return "\n".join(line.rstrip() for line in lines)


def normalized_span_digest(path: Path | str, start: int, end: int) -> str:
    """Return the ``sha256:`` digest of the normalized 1-indexed span [start, end].

    Raises ``FileNotFoundError`` if the file is missing and ``ValueError`` if the
    span falls outside the file — both surface as ``unresolvable``.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if start < 1 or end < start or start > len(lines):
        raise ValueError(f"span {start}-{end} outside {path} ({len(lines)} lines)")
    span = lines[start - 1 : end]
    digest = hashlib.sha256(_normalize(span).encode("utf-8")).hexdigest()
    return f"{DIGEST_PREFIX}{digest}"


def resolve_locator(
    locator: dict[str, Any], repo_root: Path | str
) -> tuple[str, str | None]:
    """Classify one locator against the working tree.

    Returns ``(status, detail)`` where *detail* explains a non-verified status.
    """
    repo_root = Path(repo_root)
    rel = locator.get("file")
    span = locator.get("span") or {}
    if not rel:
        return UNRESOLVABLE, "locator has no file"

    target = repo_root / rel
    if not target.is_file():
        return UNRESOLVABLE, f"file not found: {rel}"

    try:
        actual = normalized_span_digest(
            target, int(span.get("start", 0)), int(span.get("end", 0))
        )
    except (ValueError, TypeError) as exc:
        return UNRESOLVABLE, str(exc)
    except OSError as exc:  # pragma: no cover - unreadable file
        return UNRESOLVABLE, f"unreadable: {exc}"

    expected = locator.get("content_digest")
    if actual == expected:
        return VERIFIED, None
    return DRIFTED, f"digest {expected} != {actual}"


@dataclass
class VerificationReport:
    """Aggregate outcome of verifying every locator in a handbook."""

    counts: dict[str, int] = field(
        default_factory=lambda: {VERIFIED: 0, DRIFTED: 0, UNRESOLVABLE: 0}
    )
    diagnostics: DiagnosticCollector = field(default_factory=DiagnosticCollector)
    statuses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """Non-zero only when a locator is unresolvable (drift is a warning)."""
        return 1 if self.counts[UNRESOLVABLE] else 0

    @property
    def stale_reasons(self) -> list[str]:
        return [STALE_REASON_LOCATOR_DRIFT] if self.counts[DRIFTED] else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "stale_reasons": self.stale_reasons,
            "statuses": self.statuses,
        }


def verify_handbook(
    handbook: dict[str, Any], repo_root: Path | str
) -> VerificationReport:
    """Verify every evidence locator in *handbook* against *repo_root*."""
    report = VerificationReport()
    details = handbook.get("unit_details") or {}

    for unit_id in sorted(details):
        detail = details[unit_id]
        if not isinstance(detail, dict):
            continue
        unit_statuses: list[dict[str, Any]] = []
        for locator in _iter_locators(detail):
            status, why = resolve_locator(locator, repo_root)
            report.counts[status] += 1
            unit_statuses.append(
                {
                    "node_id": locator.get("node_id"),
                    "file": locator.get("file"),
                    "span": locator.get("span"),
                    "status": status,
                    "detail": why,
                }
            )
            if status == DRIFTED:
                report.diagnostics.warning(
                    "HANDBOOK_LOCATOR_DRIFT",
                    f"{unit_id}: evidence drifted in {locator.get('file')} — {why}",
                    node_id=locator.get("node_id"),
                    file=locator.get("file"),
                    details={"behavior_unit": unit_id, "reason": why},
                )
            elif status == UNRESOLVABLE:
                report.diagnostics.error(
                    "HANDBOOK_LOCATOR_UNRESOLVABLE",
                    f"{unit_id}: evidence unresolvable — {why}",
                    node_id=locator.get("node_id"),
                    file=locator.get("file"),
                    details={"behavior_unit": unit_id, "reason": why},
                )
        report.statuses[unit_id] = unit_statuses

    return report


def _merge_into_diagnostics(diag_path: Path, report: VerificationReport) -> None:
    """Append handbook findings to the shared diagnostics artifact."""
    existing = load_graph(diag_path, quiet=True) or {}
    findings = [
        f
        for f in (existing.get("findings") or [])
        if not str(f.get("code", "")).startswith("HANDBOOK_LOCATOR")
    ]
    findings.extend(report.diagnostics.to_list())
    existing["findings"] = findings
    existing["handbook_verification"] = report.to_dict()
    save_json(diag_path, existing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify behavior handbook evidence locators against the working tree"
    )
    parser.add_argument("--handbook", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--diagnostics", help="Diagnostics artifact to merge findings into")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    handbook_path = Path(args.handbook)
    if not handbook_path.is_file():
        # Fresh-by-absence: a repo without a committed handbook is not broken.
        logger.info("no handbook at %s — nothing to verify", handbook_path)
        return 0

    handbook = json.loads(handbook_path.read_text(encoding="utf-8"))
    report = verify_handbook(handbook, args.repo_root)

    if args.diagnostics:
        _merge_into_diagnostics(Path(args.diagnostics), report)

    if args.json:
        logger.info(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for item in report.diagnostics.items:
            logger.info("[%s] %s: %s", item.severity, item.code, item.message)
        logger.info(
            "Locators: %d verified, %d drifted, %d unresolvable",
            report.counts[VERIFIED],
            report.counts[DRIFTED],
            report.counts[UNRESOLVABLE],
        )

    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
