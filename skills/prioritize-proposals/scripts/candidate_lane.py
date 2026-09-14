#!/usr/bin/env python3
"""Deterministic candidate-work ranking as a lane distinct from proposals."""

from __future__ import annotations

import argparse
import copy
import heapq
import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SHARED = Path(__file__).resolve().parents[2] / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from candidate_work import (  # type: ignore[import-untyped]
    CandidateWorkValidationError,
    LifecycleRecord,
    load_candidate_work_files,
    resolve_dependency,
    validate_candidate_work_batch,
)

_EFFORT_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}
_ARCHIVE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")
_MARKDOWN_SPECIAL = frozenset("\\`*_{}[]<>()#+-.!|>")


class CandidateLaneError(ValueError):
    """Raised when a candidate lane cannot be ranked deterministically."""


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One ranked candidate with readiness and dependency evidence."""

    rank: int
    candidate: dict[str, Any]
    blocked: bool
    blocked_reasons: tuple[str, ...]
    in_batch_dependencies: tuple[str, ...]
    lane: str = "candidate_work"

    @property
    def change_id(self) -> str:
        return self.candidate["suggested_change_id"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "lane": self.lane,
            "status": "blocked" if self.blocked else "ready",
            "blocked_reasons": list(self.blocked_reasons),
            "in_batch_dependencies": list(self.in_batch_dependencies),
            "candidate": copy.deepcopy(self.candidate),
        }


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    """Complete ordered candidate-work lane."""

    items: tuple[RankedCandidate, ...]
    lane: str = "candidate_work"

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "count": len(self.items),
            "candidates": [item.to_dict() for item in self.items],
        }


def load_candidate_inputs(paths: Sequence[Path]) -> list[dict[str, Any]]:
    """Validate and concatenate repeatable candidate inputs in argument order."""

    if not paths:
        raise CandidateLaneError("at least one --candidate-work input is required")
    try:
        return load_candidate_work_files(Path(path) for path in paths)
    except CandidateWorkValidationError as exc:
        raise CandidateLaneError(str(exc)) from exc


def _archive_change_id(name: str) -> str:
    match = _ARCHIVE_PREFIX.fullmatch(name)
    return match.group(1) if match else name


def _roadmap_records(path: Path, repo_root: Path) -> list[LifecycleRecord]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CandidateLaneError(
            f"roadmap {path.relative_to(repo_root)} could not be loaded: {exc}"
        ) from exc
    if not isinstance(data, Mapping):
        raise CandidateLaneError(
            f"roadmap {path.relative_to(repo_root)} must contain a mapping"
        )
    roadmap_id = data.get("roadmap_id")
    items = data.get("items")
    if not isinstance(roadmap_id, str) or not isinstance(items, list):
        raise CandidateLaneError(
            f"roadmap {path.relative_to(repo_root)} requires roadmap_id and items"
        )

    records: list[LifecycleRecord] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CandidateLaneError(
                f"roadmap {path.relative_to(repo_root)} item #{index} must be a mapping"
            )
        change_id = item.get("change_id")
        if not change_id:
            continue
        item_id = item.get("item_id")
        status = item.get("status")
        if not isinstance(change_id, str) or not isinstance(item_id, str) or not isinstance(status, str):
            raise CandidateLaneError(
                f"roadmap {path.relative_to(repo_root)} item #{index} has invalid lifecycle fields"
            )
        records.append(
            LifecycleRecord(
                change_id=change_id,
                source="roadmap",
                status=status,
                roadmap_id=roadmap_id,
                item_id=item_id,
            )
        )
    return records


def collect_lifecycle_records(repo_root: Path) -> list[LifecycleRecord]:
    """Read roadmap, active-change, and archive observations without precedence."""

    root = Path(repo_root)
    roadmaps = root / "openspec/roadmaps"
    paths: list[Path] = []
    if roadmaps.is_dir():
        paths.extend(sorted(roadmaps.glob("*/roadmap.yaml")))
        archive_roadmaps = roadmaps / "archive"
        if archive_roadmaps.is_dir():
            paths.extend(sorted(archive_roadmaps.glob("*/roadmap.yaml")))
    records = [
        record
        for path in paths
        for record in _roadmap_records(path, root)
    ]

    changes = root / "openspec/changes"
    if not changes.is_dir():
        return records
    for path in sorted(changes.iterdir()):
        if path.is_dir() and path.name != "archive":
            records.append(LifecycleRecord(path.name, "active_change", "active"))
    archive = changes / "archive"
    if archive.is_dir():
        for path in sorted(archive.iterdir()):
            if path.is_dir():
                records.append(
                    LifecycleRecord(
                        _archive_change_id(path.name), "archive", "completed"
                    )
                )
    return records


def _validated_candidates(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        return validate_candidate_work_batch(list(candidates))
    except CandidateWorkValidationError as exc:
        raise CandidateLaneError(str(exc)) from exc


def _dependency_graph(
    candidates: list[dict[str, Any]],
    lifecycle_records: Sequence[LifecycleRecord],
) -> tuple[
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    by_id = {candidate["suggested_change_id"]: candidate for candidate in candidates}
    records = list(lifecycle_records)
    records.extend(
        LifecycleRecord(change_id, "candidate", "candidate")
        for change_id in by_id
    )
    prerequisites = {change_id: set() for change_id in by_id}
    dependents = {change_id: set() for change_id in by_id}
    blocked_reasons = {change_id: set() for change_id in by_id}

    for change_id, candidate in by_id.items():
        for dependency in candidate.get("depends_on", []):
            resolution = resolve_dependency(dependency, records)
            if resolution.outcome == "ambiguous":
                raise CandidateLaneError(
                    f"dependency {dependency!r} for {change_id!r} is ambiguous: "
                    f"{resolution.reason}"
                )
            owner = resolution.live_record
            if (
                resolution.outcome == "live"
                and owner is not None
                and owner.source == "candidate"
                and owner.change_id in by_id
            ):
                prerequisites[change_id].add(owner.change_id)
                dependents[owner.change_id].add(change_id)
            elif resolution.outcome != "satisfied":
                blocked_reasons[change_id].add(
                    f"{dependency}: {resolution.reason}"
                )
    return prerequisites, dependents, blocked_reasons


def _propagate_blocked(
    dependents: dict[str, set[str]],
    blocked_reasons: dict[str, set[str]],
) -> None:
    queue = sorted(change_id for change_id, reasons in blocked_reasons.items() if reasons)
    visited = set(queue)
    while queue:
        blocked = queue.pop(0)
        for dependent in sorted(dependents[blocked]):
            blocked_reasons[dependent].add(
                f"{blocked}: depends on blocked in-batch candidate"
            )
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)


def _tie_key(
    candidate: dict[str, Any],
    *,
    blocked: bool,
) -> tuple[int, int, int, str, str]:
    return (
        1 if blocked else 0,
        candidate["priority"],
        _EFFORT_ORDER[candidate["effort"]],
        candidate["provenance"].get("generator") or "",
        candidate["suggested_change_id"],
    )


def rank_candidate_work(
    candidates: Iterable[dict[str, Any]],
    *,
    lifecycle_records: Sequence[LifecycleRecord] = (),
) -> CandidateRanking:
    """Rank candidates by dependency-safe Kahn traversal and the fixed tie key."""

    validated = _validated_candidates(candidates)
    prerequisites, dependents, blocked_reasons = _dependency_graph(
        validated, lifecycle_records
    )
    _propagate_blocked(dependents, blocked_reasons)
    by_id = {candidate["suggested_change_id"]: candidate for candidate in validated}
    indegree = {
        change_id: len(dependencies)
        for change_id, dependencies in prerequisites.items()
    }
    ready: list[tuple[tuple[int, int, int, str, str], str]] = []
    for change_id, degree in indegree.items():
        if degree == 0:
            heapq.heappush(
                ready,
                (
                    _tie_key(by_id[change_id], blocked=bool(blocked_reasons[change_id])),
                    change_id,
                ),
            )

    ordered: list[str] = []
    while ready:
        _, change_id = heapq.heappop(ready)
        ordered.append(change_id)
        for dependent in sorted(dependents[change_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(
                    ready,
                    (
                        _tie_key(
                            by_id[dependent],
                            blocked=bool(blocked_reasons[dependent]),
                        ),
                        dependent,
                    ),
                )

    if len(ordered) != len(validated):
        cycle = sorted(change_id for change_id, degree in indegree.items() if degree)
        raise CandidateLaneError(
            "candidate dependency cycle includes: " + ", ".join(cycle)
        )

    items = tuple(
        RankedCandidate(
            rank=index,
            candidate=copy.deepcopy(by_id[change_id]),
            blocked=bool(blocked_reasons[change_id]),
            blocked_reasons=tuple(sorted(blocked_reasons[change_id])),
            in_batch_dependencies=tuple(sorted(prerequisites[change_id])),
        )
        for index, change_id in enumerate(ordered, start=1)
    )
    return CandidateRanking(items)


def escape_inert_text(value: object) -> str:
    """Make untrusted candidate text inert in Markdown and terminals."""

    escaped: list[str] = []
    for character in str(value):
        codepoint = ord(character)
        category = unicodedata.category(character)
        if category.startswith("C") or category in {"Zl", "Zp"}:
            width = 4 if codepoint <= 0xFFFF else 8
            prefix = "u" if width == 4 else "U"
            escaped.append(f"\\{prefix}{codepoint:0{width}x}")
        elif character in _MARKDOWN_SPECIAL:
            escaped.append("\\" + character)
        else:
            escaped.append(character)
    return "".join(escaped)


def render_candidate_markdown(ranking: CandidateRanking) -> str:
    """Render the separate candidate lane without interpreting source text."""

    lines = [
        "# Candidate Work Prioritization",
        "",
        f"**Candidates Analyzed**: {len(ranking.items)}",
        "",
    ]
    for item in ranking.items:
        candidate = item.candidate
        provenance = candidate["provenance"]
        generator = provenance.get("generator") or ""
        tags = ", ".join(escape_inert_text(tag) for tag in candidate.get("tags", []))
        reasons = "; ".join(
            escape_inert_text(reason) for reason in item.blocked_reasons
        )
        lines.extend(
            [
                f"## {item.rank}\\. {escape_inert_text(candidate['title'])}",
                f"- **Lane**: {item.lane}",
                f"- **Change ID**: `{escape_inert_text(item.change_id)}`",
                f"- **Status**: {'blocked' if item.blocked else 'ready'}",
                f"- **Priority / Effort**: {candidate['priority']} / {candidate['effort']}",
                f"- **Generator**: {escape_inert_text(generator)}",
                "- **Source**: "
                + escape_inert_text(provenance["source_artifact"]),
                "- **Findings**: "
                + ", ".join(
                    escape_inert_text(value)
                    for value in provenance["finding_ids"]
                ),
                f"- **Rationale**: {escape_inert_text(candidate['rationale'])}",
            ]
        )
        if tags:
            lines.append(f"- **Tags**: {tags}")
        if reasons:
            lines.append(f"- **Blocked By**: {reasons}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_and_rank_candidate_work(
    paths: Sequence[Path],
    *,
    repo_root: Path,
) -> CandidateRanking:
    """Load repeatable inputs and rank them against the repository lifecycle."""

    candidates = load_candidate_inputs(paths)
    lifecycle = collect_lifecycle_records(repo_root)
    return rank_candidate_work(candidates, lifecycle_records=lifecycle)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank candidate work as a lane separate from active proposals."
    )
    parser.add_argument(
        "--candidate-work",
        action="append",
        type=Path,
        required=True,
        help="Candidate-work object or array; repeat for multiple files.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("md", "json"), default="md")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    """Run the repeatable candidate-work ranking CLI."""

    args = _parser().parse_args(argv)
    try:
        ranking = load_and_rank_candidate_work(
            args.candidate_work,
            repo_root=args.repo_root.resolve(),
        )
    except (CandidateLaneError, CandidateWorkValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(ranking.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_candidate_markdown(ranking), end="")
    return 0


__all__ = [
    "CandidateLaneError",
    "CandidateRanking",
    "LifecycleRecord",
    "RankedCandidate",
    "cli",
    "collect_lifecycle_records",
    "escape_inert_text",
    "load_and_rank_candidate_work",
    "load_candidate_inputs",
    "rank_candidate_work",
    "render_candidate_markdown",
]


if __name__ == "__main__":
    raise SystemExit(cli())
