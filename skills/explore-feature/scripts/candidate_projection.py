#!/usr/bin/env python3
"""Project explore-feature opportunities into candidate-work sidecars."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from candidate_work import derive_suggested_change_id, write_candidate_work

_CHANGE_ID = re.compile(r"^(?:add|update|remove|refactor)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_ARCHIVE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")
_LEVEL = {"low": 1, "med": 2, "medium": 2, "high": 3}
_EFFORT_SCORE = {"XS": 1, "S": 1, "M": 2, "L": 3, "XL": 3}


def _items(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in ("items", "opportunities", "ranked_opportunities", "candidates", "ranked"):
            value = document.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("opportunities document must contain a ranked opportunity array")


def _marked_existing(item: dict[str, Any]) -> bool:
    status = str(item.get("status", "untracked")).lower()
    return (
        status in {"active", "archived", "existing", "scaffolded", "tracked"}
        or bool(item.get("tracked"))
        or bool(item.get("existing_change_id"))
        or bool(item.get("scaffolded_change_id"))
    )


def _priority(item: dict[str, Any]) -> int:
    impact = _LEVEL[str(item.get("impact", "med")).lower()]
    strategic = _LEVEL[str(item.get("strategic_fit", "med")).lower()]
    effort = _EFFORT_SCORE[str(item.get("effort", "M")).upper()]
    risk = _LEVEL[str(item.get("risk", "med")).lower()]
    focus = float(item.get("focus_match", 0))
    score = impact * 0.4 + strategic * 0.25 + (4 - effort) * 0.2
    score += (4 - risk) * 0.15 + focus * 0.1
    if score >= 2.75:
        return 2
    if score >= 2.0:
        return 3
    if score >= 1.5:
        return 4
    return 5


def _blockers(item: dict[str, Any]) -> list[str]:
    values = item.get("blockers")
    if values is None:
        values = item.get("blocked_by", item.get("blocked-by", []))
    return [str(value) for value in values]


def _tags(item: dict[str, Any], prose_blockers: list[str]) -> list[str]:
    tags = [f"lens-{lens}" for lens in item.get("lenses_applied", [])]
    if item.get("hmw_reframe"):
        tags.append("hmw-reframed")
    tags.extend(f"blocker:{blocker}" for blocker in prose_blockers)
    return tags


def _candidate_id(item: dict[str, Any]) -> str:
    source_id = str(item.get("id", ""))
    if not source_id:
        raise ValueError("untracked opportunity requires a stable non-empty id")
    return derive_suggested_change_id(
        "explore-feature",
        source_id,
        item.get("suggested_change_id") or item.get("change_id_hint"),
    )


def project_candidate_work(
    document: Any,
    source_artifact: str,
    *,
    known_change_ids: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Project untracked opportunities absent from known lifecycle records."""
    items = _items(document)
    projected_ids = {
        _candidate_id(item)
        for item in items
        if not _marked_existing(item)
    }
    candidates: list[dict[str, Any]] = []
    resolvable = set(known_change_ids) | projected_ids
    for item in items:
        if _marked_existing(item):
            continue
        source_id = str(item["id"])
        suggested_id = _candidate_id(item)
        if suggested_id in known_change_ids:
            continue
        blockers = _blockers(item)
        depends_on = [
            blocker
            for blocker in blockers
            if _CHANGE_ID.fullmatch(blocker) and blocker in resolvable
        ]
        prose_blockers = [blocker for blocker in blockers if blocker not in depends_on]
        rationale = str(
            item.get("rationale")
            or item.get("why_now")
            or item.get("why-now")
            or "Opportunity evidence"
        )
        if item.get("hmw_reframe"):
            rationale += f" HMW: {item['hmw_reframe']}"
        candidate: dict[str, Any] = {
            "schema_version": 1,
            "title": str(item.get("title") or item.get("name") or source_id),
            "description": str(
                item.get("description")
                or item.get("problem_statement")
                or item.get("problem-statement")
                or rationale
            ),
            "rationale": rationale,
            "provenance": {
                "source_artifact": source_artifact,
                "finding_ids": [source_id],
                "generator": "explore-feature",
            },
            "effort": str(item.get("effort", "M")).upper(),
            "priority": _priority(item),
            "suggested_change_id": suggested_id,
            "tags": _tags(item, prose_blockers),
        }
        if depends_on:
            candidate["depends_on"] = depends_on
        candidates.append(candidate)
    return candidates


def _find_repo_root(source: Path) -> Path | None:
    for start in (source.resolve().parent, Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            if (candidate / "openspec" / "changes").is_dir():
                return candidate
    return None


def _lifecycle_change_ids(repo_root: Path | None) -> set[str]:
    if repo_root is None:
        return set()
    changes = repo_root / "openspec" / "changes"
    identifiers = {
        path.name
        for path in changes.iterdir()
        if path.is_dir() and path.name != "archive"
    }
    archive = changes / "archive"
    if archive.is_dir():
        for path in archive.iterdir():
            if not path.is_dir():
                continue
            match = _ARCHIVE_NAME.fullmatch(path.name)
            identifiers.add(match.group(1) if match else path.name)
    return identifiers


def run(source: Path, destination: Path | None = None) -> Path:
    """Read rich opportunities JSON and atomically write its projection."""
    source = Path(source)
    document = json.loads(source.read_text(encoding="utf-8"))
    target = destination or source.with_name(
        "explore-feature-candidate-work.json"
    )
    repo_root = _find_repo_root(source)
    return write_candidate_work(
        target,
        project_candidate_work(
            document,
            str(source),
            known_change_ids=_lifecycle_change_ids(repo_root),
        ),
        generator="explore-feature",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("opportunities", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    print(run(args.opportunities, args.output))


if __name__ == "__main__":
    main()
