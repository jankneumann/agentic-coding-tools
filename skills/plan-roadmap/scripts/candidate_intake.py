#!/usr/bin/env python3
"""Validated intake of one approved candidate-work stub into a roadmap."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
for _directory in (
    _SKILLS_ROOT / "shared",
    _SKILLS_ROOT / "roadmap-runtime" / "scripts",
    _SKILLS_ROOT / "refine-roadmap" / "scripts",
):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from candidate_work import (  # type: ignore[import-untyped]
    CandidateWorkValidationError,
    collect_lifecycle_records,
    LifecycleCollectionError,
    LifecycleRecord,
    load_candidate_work,
    resolve_dependency,
    validate_candidate_work,
)
from decomposer import validate_roadmap
from models import (  # type: ignore[import-untyped]
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    load_all_roadmaps_strict,
    load_roadmap,
    save_roadmap,
)
from refiner import RefinementPreview, preview_refinement  # type: ignore[import-untyped]
from scaffolder import scaffold_change

_KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ITEM_ID = re.compile(r"^ri-(\d+)$")
_PREVIEW_ATTEMPTS = 3


class CandidateIntakeError(ValueError):
    """Raised when approved candidate work cannot be mapped without ambiguity."""


@dataclass(frozen=True, slots=True)
class NewRoadmapIntakeResult:
    """Artifacts written by a successful new-roadmap intake."""

    roadmap: Roadmap
    roadmap_path: Path
    change_dir: Path


@dataclass(frozen=True, slots=True)
class ExistingRoadmapIntakePreview:
    """Refine request and its read-only validation preview."""

    request: dict[str, Any]
    preview: RefinementPreview


def _schema(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "openspec" / "schemas" / "candidate-work.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateIntakeError(f"candidate-work schema could not be loaded: {exc}") from exc


def _validated_stub(candidate: object, repo_root: Path) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        raise CandidateIntakeError("candidate intake requires exactly one stub, not an array")
    try:
        return validate_candidate_work(dict(candidate), schema=_schema(repo_root))
    except CandidateWorkValidationError as exc:
        raise CandidateIntakeError(str(exc)) from exc


def _validated_outcomes(outcomes: Sequence[str]) -> list[str]:
    if isinstance(outcomes, (str, bytes)) or not outcomes:
        raise CandidateIntakeError(
            "candidate intake requires at least one nonblank acceptance outcome"
        )
    normalized: list[str] = []
    for outcome in outcomes:
        if not isinstance(outcome, str) or not outcome.strip():
            raise CandidateIntakeError(
                "candidate intake requires only nonblank acceptance outcomes"
            )
        normalized.append(outcome.strip())
    return normalized


def _kebab_case(value: str, field: str) -> str:
    if not isinstance(value, str) or not _KEBAB_CASE.fullmatch(value):
        raise CandidateIntakeError(f"{field} must be a non-empty kebab-case identifier")
    return value


def _active_roadmaps(repo_root: Path) -> dict[str, Roadmap]:
    roadmaps, errors = load_all_roadmaps_strict(repo_root)
    if errors:
        raise CandidateIntakeError(
            "roadmap lifecycle registry could not be loaded: " + "; ".join(errors)
        )
    return roadmaps


def _lifecycle_records(repo_root: Path) -> list[LifecycleRecord]:
    """Compatibility seam delegating to the shared lifecycle collector."""
    try:
        return collect_lifecycle_records(repo_root)
    except LifecycleCollectionError as exc:
        raise CandidateIntakeError(
            "roadmap lifecycle registry could not be loaded: " + str(exc)
        ) from exc


def _assert_roadmap_id_available(roadmap_id: str, repo_root: Path) -> None:
    if roadmap_id in _active_roadmaps(repo_root):
        raise CandidateIntakeError(
            f"roadmap ID {roadmap_id!r} already exists in another workspace"
        )


def _assert_available(change_id: str, records: Sequence[LifecycleRecord]) -> None:
    matches = [record for record in records if record.change_id == change_id]
    if matches:
        locations = ", ".join(
            sorted(
                f"{record.source}:{record.roadmap_id or record.item_id or record.status}"
                for record in matches
            )
        )
        raise CandidateIntakeError(
            f"change ID {change_id!r} already exists in lifecycle registry ({locations})"
        )


def _description(stub: Mapping[str, Any]) -> str:
    provenance = stub["provenance"]
    generator = provenance.get("generator") or "unspecified"
    finding_ids = ", ".join(provenance["finding_ids"]) or "none"
    return (
        f"{stub['description']}\n\n"
        "Candidate provenance: "
        f"generator={generator}; source_artifact={provenance['source_artifact']}; "
        f"finding_ids={finding_ids}."
    )


def _mapped_dependencies(
    stub: Mapping[str, Any],
    *,
    target_roadmap_id: str,
    records: Sequence[LifecycleRecord],
) -> tuple[list[str], list[str], list[str], list[str]]:
    local: list[str] = []
    external: list[str] = []
    resolved: list[str] = []
    satisfied: list[str] = []
    for change_id in stub.get("depends_on", []):
        resolution = resolve_dependency(change_id, records)
        if resolution.outcome == "satisfied":
            satisfied.append(f"Satisfied dependency: {change_id} (completed)")
            continue
        if resolution.outcome != "live" or resolution.live_record is None:
            raise CandidateIntakeError(
                f"dependency {change_id!r} is {resolution.outcome}: {resolution.reason}"
            )
        owner = resolution.live_record
        if owner.source != "roadmap" or not owner.roadmap_id or not owner.item_id:
            raise CandidateIntakeError(
                f"dependency {change_id!r} is unresolved: no unique roadmap item"
            )
        if owner.roadmap_id == target_roadmap_id:
            local.append(owner.item_id)
            item_ref = owner.item_id
        else:
            item_ref = f"{owner.roadmap_id}:{owner.item_id}"
            external.append(item_ref)
        resolved.append(f"Resolved dependency: {change_id} -> {item_ref}")
    return local, external, resolved, satisfied


def _mapped_item(
    stub: Mapping[str, Any],
    *,
    item_id: str,
    target_roadmap_id: str,
    outcomes: list[str],
    records: Sequence[LifecycleRecord],
    capability: str | None,
    include_priority: bool,
) -> RoadmapItem:
    local, external, resolved, satisfied = _mapped_dependencies(
        stub, target_roadmap_id=target_roadmap_id, records=records
    )
    rationale = stub["rationale"]
    if annotations := resolved + satisfied:
        rationale += "\n\n" + "\n".join(annotations)
    return RoadmapItem(
        item_id=item_id,
        title=stub["title"],
        description=_description(stub),
        rationale=rationale,
        status=ItemStatus.APPROVED,
        effort=Effort(stub["effort"]),
        priority=stub["priority"] if include_priority else 1,
        depends_on=local,
        external_depends_on=external,
        change_id=stub["suggested_change_id"],
        capability=capability,
        acceptance_outcomes=outcomes,
    )


def next_free_item_id(roadmap: Roadmap) -> str:
    """Return one greater than the largest canonical ri-NN in a fresh roadmap."""

    maximum = max(
        (
            int(match.group(1))
            for item in roadmap.items
            if (match := _ITEM_ID.fullmatch(item.item_id))
        ),
        default=0,
    )
    return f"ri-{maximum + 1:02d}"


def build_new_roadmap(
    candidate: object,
    *,
    repo_root: Path,
    roadmap_id: str,
    capability: str,
    acceptance_outcomes: Sequence[str],
) -> Roadmap:
    """Validate and map one approved stub into a complete one-item roadmap."""

    root = Path(repo_root)
    stub = _validated_stub(candidate, root)
    target = _kebab_case(roadmap_id, "roadmap_id")
    approved_capability = _kebab_case(capability, "capability")
    outcomes = _validated_outcomes(acceptance_outcomes)
    _assert_roadmap_id_available(target, root)
    records = _lifecycle_records(root)
    _assert_available(stub["suggested_change_id"], records)
    item = _mapped_item(
        stub,
        item_id="ri-01",
        target_roadmap_id=target,
        outcomes=outcomes,
        records=records,
        capability=approved_capability,
        include_priority=True,
    )
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id=target,
        source_proposal=stub["provenance"]["source_artifact"],
        status=RoadmapStatus.APPROVED,
        items=[item],
    )
    errors = validate_roadmap(roadmap.to_dict(), root)
    if errors:
        raise CandidateIntakeError("new roadmap is invalid: " + "; ".join(errors))
    return roadmap


def _remove_owned_directories(paths: Sequence[Path]) -> None:
    for path in reversed(paths):
        if path.is_dir():
            shutil.rmtree(path)


def _install_staged_new_roadmap(
    *,
    staged_roadmap_path: Path,
    staged_change_dir: Path,
    roadmap_path: Path,
    change_dir: Path,
) -> None:
    owned: list[Path] = []
    try:
        for destination in (change_dir, roadmap_path.parent):
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                destination.mkdir()
            except FileExistsError as exc:
                raise CandidateIntakeError(
                    f"candidate intake destination already exists at {destination}"
                ) from exc
            owned.append(destination)
        shutil.copytree(staged_change_dir, change_dir, dirs_exist_ok=True)
        shutil.copy2(staged_roadmap_path, roadmap_path)
    except BaseException:
        _remove_owned_directories(owned)
        raise


def _new_change_id(roadmap: Roadmap) -> str:
    item = roadmap.get_item("ri-01")
    if item is None or not item.change_id:
        raise CandidateIntakeError("new roadmap ri-01 has no change ID")
    return item.change_id


def create_new_roadmap(
    candidate: object,
    *,
    repo_root: Path,
    roadmap_id: str,
    capability: str,
    acceptance_outcomes: Sequence[str],
) -> NewRoadmapIntakeResult:
    """Validate, save without overwrite, and scaffold one new-roadmap candidate."""

    root = Path(repo_root)
    roadmap_path = root / "openspec" / "roadmaps" / roadmap_id / "roadmap.yaml"
    if roadmap_path.exists():
        raise CandidateIntakeError(f"roadmap already exists at {roadmap_path}")
    roadmap = build_new_roadmap(
        candidate,
        repo_root=root,
        roadmap_id=roadmap_id,
        capability=capability,
        acceptance_outcomes=acceptance_outcomes,
    )
    change_dir = root / "openspec" / "changes" / _new_change_id(roadmap)
    staging_parent = root / "openspec"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".candidate-intake-", dir=staging_parent
    ) as temporary_name:
        staging_root = Path(temporary_name)
        staged_roadmap_path = staging_root / "roadmap.yaml"
        save_roadmap(roadmap, staged_roadmap_path, overwrite=False)
        staged_change_dir = scaffold_change(roadmap, staging_root, "ri-01")
        _install_staged_new_roadmap(
            staged_roadmap_path=staged_roadmap_path,
            staged_change_dir=staged_change_dir,
            roadmap_path=roadmap_path,
            change_dir=change_dir,
        )
    return NewRoadmapIntakeResult(roadmap, roadmap_path, change_dir)


def preview_existing_roadmap(
    candidate: object,
    *,
    repo_root: Path,
    roadmap_path: Path,
    acceptance_outcomes: Sequence[str],
    actor: str = "operator",
) -> ExistingRoadmapIntakePreview:
    """Freshly load an existing roadmap and preview exactly one refine add."""

    root = Path(repo_root)
    stub = _validated_stub(candidate, root)
    outcomes = _validated_outcomes(acceptance_outcomes)
    if not isinstance(actor, str) or not actor.strip():
        raise CandidateIntakeError("actor must be nonblank")
    target_path = Path(roadmap_path)
    for _attempt in range(_PREVIEW_ATTEMPTS):
        base_bytes = target_path.read_bytes()
        roadmap = load_roadmap(target_path, root)
        if target_path.read_bytes() != base_bytes:
            continue
        records = _lifecycle_records(root)
        if target_path.read_bytes() != base_bytes:
            continue
        _assert_available(stub["suggested_change_id"], records)
        item = _mapped_item(
            stub,
            item_id=next_free_item_id(roadmap),
            target_roadmap_id=roadmap.roadmap_id,
            outcomes=outcomes,
            records=records,
            capability=None,
            include_priority=False,
        )
        item_data = item.to_dict()
        item_data.pop("priority")
        item_data.pop("capability", None)
        request = {
            "rationale": (
                f"Approved candidate intake for {stub['suggested_change_id']}.\n"
                f"Candidate priority: {stub['priority']}"
            ),
            "actor": actor.strip(),
            "source": stub["provenance"]["source_artifact"],
            "operations": [{"op": "add", "item": item_data}],
        }
        preview = preview_refinement(target_path, request, root)
        expected_base = hashlib.sha256(base_bytes).hexdigest()
        if preview.base_sha256 != expected_base:
            continue
        if preview.errors:
            raise CandidateIntakeError(
                "candidate refinement preview is invalid: "
                + "; ".join(preview.errors)
            )
        return ExistingRoadmapIntakePreview(request, preview)
    raise CandidateIntakeError(
        "roadmap changed repeatedly during candidate intake; preview again"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map one approved candidate-work stub into plan-roadmap."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--outcome", required=True, action="append")
    parser.add_argument("--actor", default="operator")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--new-roadmap-id")
    target.add_argument("--existing-roadmap", type=Path)
    parser.add_argument("--capability")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    """Run new-roadmap creation or emit a read-only existing-roadmap preview."""

    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    try:
        candidate = load_candidate_work(
            args.candidate, schema=_schema(root)
        )
        if args.new_roadmap_id:
            if not args.capability:
                raise CandidateIntakeError(
                    "--capability is required with --new-roadmap-id"
                )
            result = create_new_roadmap(
                candidate,
                repo_root=root,
                roadmap_id=args.new_roadmap_id,
                capability=args.capability,
                acceptance_outcomes=args.outcome,
            )
            print(result.roadmap_path)
        else:
            result = preview_existing_roadmap(
                candidate,
                repo_root=root,
                roadmap_path=args.existing_roadmap,
                acceptance_outcomes=args.outcome,
                actor=args.actor,
            )
            print(json.dumps(
                {"request": result.request, "preview": result.preview.to_dict()},
                indent=2,
                sort_keys=True,
            ))
    except (CandidateIntakeError, CandidateWorkValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
