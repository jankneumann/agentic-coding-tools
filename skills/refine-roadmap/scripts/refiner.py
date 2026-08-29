"""Preview and atomically apply safe refinements to an active roadmap.

Semantic decisions belong in a human-reviewed refinement request. This module
is the deterministic boundary: it applies typed operations to a copy, reports
schedule and DAG effects, validates the candidate, and only then mutates the
roadmap plus newly introduced OpenSpec change scaffolds. Existing change
directories, checkpoints, completion records, and learning logs are never
rewritten.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

_SKILL_DIR = Path(__file__).resolve().parent.parent
_PLAN_SCRIPTS = _SKILL_DIR.parent / "plan-roadmap" / "scripts"
_RUNTIME_SCRIPTS = _SKILL_DIR.parent / "roadmap-runtime" / "scripts"
for _scripts_dir in (_PLAN_SCRIPTS, _RUNTIME_SCRIPTS):
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))

from decomposer import (  # type: ignore[import-untyped]
    scan_archive_state,
    validate_cross_roadmap,
    validate_roadmap,
)
from models import Roadmap, RoadmapItem  # type: ignore[import-untyped]
from renderer import render_roadmap  # type: ignore[import-untyped]
from scaffolder import (  # type: ignore[import-untyped]
    derive_change_id,
    scaffold_change,
    validate_change_id,
)


class RefinementValidationError(ValueError):
    """Raised when a refinement cannot pass every required validation layer."""


class BaseRoadmapChangedError(RefinementValidationError):
    """Raised when apply no longer targets the bytes that were previewed."""


StrictValidator = Callable[[Path], list[str]]


@dataclass
class RefinementPreview:
    base_sha256: str
    candidate: dict[str, Any]
    errors: list[str]
    operation_summaries: list[str]
    new_item_ids: list[str]
    scaffold_change_ids: list[str]
    schedule_before: list[list[str]]
    schedule_after: list[list[str]]
    dependency_edges_added: list[tuple[str, str]]
    dependency_edges_removed: list[tuple[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_sha256": self.base_sha256,
            "valid": not self.errors,
            "errors": self.errors,
            "operations": self.operation_summaries,
            "new_item_ids": self.new_item_ids,
            "scaffold_change_ids": self.scaffold_change_ids,
            "schedule_before": self.schedule_before,
            "schedule_after": self.schedule_after,
            "dependency_edges_added": [list(edge) for edge in self.dependency_edges_added],
            "dependency_edges_removed": [list(edge) for edge in self.dependency_edges_removed],
            "candidate": self.candidate,
        }


@dataclass
class ApplyResult:
    base_sha256: str
    result_sha256: str
    scaffolded_change_ids: list[str]
    operation_summaries: list[str]
    rendered_markdown_updated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_sha256": self.base_sha256,
            "result_sha256": self.result_sha256,
            "scaffolded_change_ids": self.scaffolded_change_ids,
            "operations": self.operation_summaries,
            "rendered_markdown_updated": self.rendered_markdown_updated,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _item_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["item_id"]: item for item in data.get("items", [])}


def _checkpoint_refs(workspace: Path) -> set[str]:
    checkpoint = workspace / "checkpoint.json"
    if not checkpoint.exists():
        return set()
    try:
        data = json.loads(checkpoint.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefinementValidationError(
            f"checkpoint.json cannot be read safely ({exc}); refinement fails closed."
        ) from exc
    refs: set[str] = set()
    current = data.get("current_item_id")
    if isinstance(current, str):
        refs.add(current)
    refs.update(value for value in data.get("completed_items", []) if isinstance(value, str))
    for failed in data.get("failed_items", []):
        if isinstance(failed, dict) and isinstance(failed.get("item_id"), str):
            refs.add(failed["item_id"])
    return refs


def _assert_not_checkpointed(item_id: str, workspace: Path) -> None:
    if item_id in _checkpoint_refs(workspace):
        raise RefinementValidationError(
            f"Item {item_id!r} is referenced by checkpoint.json; split/supersede would "
            "invalidate resumable execution state."
        )


def _default_new_status(roadmap: dict[str, Any]) -> str:
    if roadmap.get("status") in {"approved", "in_progress", "blocked"}:
        return "approved"
    return "candidate"


def _normalize_new_item(
    raw: Any,
    roadmap: dict[str, Any],
    *,
    default_status: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RefinementValidationError("New roadmap item must be a mapping.")
    item = copy.deepcopy(raw)
    for required in ("item_id", "title", "effort", "acceptance_outcomes"):
        if not item.get(required):
            raise RefinementValidationError(f"New roadmap item is missing {required!r}.")
    item.setdefault("description", "")
    item.setdefault("rationale", "")
    item.setdefault("status", default_status or _default_new_status(roadmap))
    item.setdefault("priority", max((i.get("priority", 0) for i in roadmap["items"]), default=0) + 1)
    item.setdefault("depends_on", [])
    if item["status"] not in {"candidate", "approved"}:
        raise RefinementValidationError(
            f"New item {item['item_id']!r} must start as candidate or approved."
        )
    return item


def _assign_change_id(item: dict[str, Any], roadmap: dict[str, Any]) -> str:
    taken = {
        existing.get("change_id")
        for existing in roadmap["items"]
        if existing is not item and existing.get("change_id")
    }
    explicit = item.get("change_id")
    if explicit:
        error = validate_change_id(explicit)
        if error:
            raise RefinementValidationError(f"Item {item['item_id']!r}: {error}")
        if explicit in taken:
            raise RefinementValidationError(
                f"New item {item['item_id']!r} duplicates change_id {explicit!r}."
            )
        return explicit

    model_item = RoadmapItem.from_dict(item)
    base = derive_change_id(model_item)
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    item["change_id"] = candidate
    return candidate


def _insertion_index(items: list[dict[str, Any]], operation: dict[str, Any]) -> int:
    before = operation.get("before")
    after = operation.get("after")
    if before and after:
        raise RefinementValidationError("An operation cannot specify both before and after.")
    ids = [item["item_id"] for item in items]
    if before:
        if before not in ids:
            raise RefinementValidationError(f"before target {before!r} does not exist.")
        return ids.index(before)
    if after:
        if after not in ids:
            raise RefinementValidationError(f"after target {after!r} does not exist.")
        return ids.index(after) + 1
    return len(items)


def _renumber_priorities(items: list[dict[str, Any]]) -> None:
    for priority, item in enumerate(items, start=1):
        item["priority"] = priority


def _replace_local_dependency(
    items: list[dict[str, Any]],
    old_id: str,
    local_successors: list[str],
    external_successors: list[str],
) -> None:
    for item in items:
        if item["item_id"] == old_id or old_id not in (item.get("depends_on") or []):
            continue
        rewritten: list[str] = []
        for dep in item.get("depends_on", []):
            replacements = local_successors if dep == old_id else [dep]
            for replacement in replacements:
                if replacement not in rewritten:
                    rewritten.append(replacement)
        item["depends_on"] = rewritten
        external = list(item.get("external_depends_on") or [])
        for successor in external_successors:
            if successor not in external:
                external.append(successor)
        if external:
            item["external_depends_on"] = external


def _apply_add(
    candidate: dict[str, Any], operation: dict[str, Any], new_ids: list[str]
) -> str:
    item = _normalize_new_item(operation.get("item"), candidate)
    if item["item_id"] in _item_map(candidate):
        raise RefinementValidationError(f"item_id {item['item_id']!r} already exists.")
    index = _insertion_index(candidate["items"], operation)
    candidate["items"].insert(index, item)
    _assign_change_id(item, candidate)
    new_ids.append(item["item_id"])
    return f"add:{item['item_id']}"


_PROTECTED_EDIT_FIELDS = {
    "item_id",
    "change_id",
    "status",
    "learning_refs",
    "failure_reason",
    "blocked_by",
    "superseded_by",
}


def _apply_edit(candidate: dict[str, Any], operation: dict[str, Any]) -> str:
    item_id = operation.get("item_id")
    item = _item_map(candidate).get(item_id)
    if item is None:
        raise RefinementValidationError(f"edit target {item_id!r} does not exist.")
    updates = operation.get("set")
    if not isinstance(updates, dict) or not updates:
        raise RefinementValidationError("edit requires a non-empty set mapping.")
    protected = sorted(_PROTECTED_EDIT_FIELDS.intersection(updates))
    if protected:
        raise RefinementValidationError(
            "edit contains protected lifecycle/provenance fields: " + ", ".join(protected)
        )
    item.update(copy.deepcopy(updates))
    return f"edit:{item_id}"


def _apply_split(
    candidate: dict[str, Any],
    operation: dict[str, Any],
    new_ids: list[str],
    workspace: Path,
) -> str:
    item_id = operation.get("item_id")
    items = candidate["items"]
    original = _item_map(candidate).get(item_id)
    if original is None:
        raise RefinementValidationError(f"split target {item_id!r} does not exist.")
    if original.get("status") not in {"candidate", "approved", "blocked", "replan_required"}:
        raise RefinementValidationError(
            f"split target {item_id!r} has protected status {original.get('status')!r}."
        )
    _assert_not_checkpointed(item_id, workspace)
    raw_parts = operation.get("items")
    if not isinstance(raw_parts, list) or len(raw_parts) < 2:
        raise RefinementValidationError("split requires at least two replacement items.")
    strategy = operation.get("strategy", "parallel")
    if strategy not in {"parallel", "chain"}:
        raise RefinementValidationError("split strategy must be 'parallel' or 'chain'.")

    part_items: list[dict[str, Any]] = []
    existing_ids = set(_item_map(candidate))
    for raw in raw_parts:
        part = _normalize_new_item(
            raw,
            candidate,
            default_status=(original.get("status") if original.get("status") in {"candidate", "approved"} else "candidate"),
        )
        if part["item_id"] in existing_ids:
            raise RefinementValidationError(f"split item_id {part['item_id']!r} already exists.")
        existing_ids.add(part["item_id"])
        if original.get("learning_refs") and "learning_refs" not in part:
            part["learning_refs"] = list(original["learning_refs"])
        part_items.append(part)

    upstream = list(original.get("depends_on") or [])
    external_upstream = list(original.get("external_depends_on") or [])
    for index, part in enumerate(part_items):
        part["depends_on"] = upstream if strategy == "parallel" or index == 0 else [part_items[index - 1]["item_id"]]
        if external_upstream and (strategy == "parallel" or index == 0):
            part["external_depends_on"] = external_upstream

    insert_at = [item["item_id"] for item in items].index(item_id) + 1
    for offset, part in enumerate(part_items):
        items.insert(insert_at + offset, part)
        _assign_change_id(part, candidate)
        new_ids.append(part["item_id"])

    successors = [part["item_id"] for part in part_items]
    original["status"] = "superseded"
    original["superseded_by"] = [f"{candidate['roadmap_id']}:{part_id}" for part_id in successors]
    downstream = successors if strategy == "parallel" else successors[-1:]
    _replace_local_dependency(items, item_id, downstream, [])
    _renumber_priorities(items)
    return f"split:{item_id}->{','.join(successors)}"


def _apply_reorder(candidate: dict[str, Any], operation: dict[str, Any]) -> str:
    item_id = operation.get("item_id")
    items = candidate["items"]
    item = _item_map(candidate).get(item_id)
    if item is None:
        raise RefinementValidationError(f"reorder target {item_id!r} does not exist.")
    if not operation.get("before") and not operation.get("after"):
        raise RefinementValidationError("reorder requires before or after.")
    items.remove(item)
    index = _insertion_index(items, operation)
    items.insert(index, item)
    _renumber_priorities(items)
    return f"reorder:{item_id}"


def _apply_supersede(
    candidate: dict[str, Any], operation: dict[str, Any], workspace: Path
) -> str:
    item_id = operation.get("item_id")
    item = _item_map(candidate).get(item_id)
    if item is None:
        raise RefinementValidationError(f"supersede target {item_id!r} does not exist.")
    if item.get("status") not in {"candidate", "approved", "blocked", "replan_required"}:
        raise RefinementValidationError(
            f"supersede target {item_id!r} has protected status {item.get('status')!r}."
        )
    _assert_not_checkpointed(item_id, workspace)
    successors = operation.get("by")
    if not isinstance(successors, list) or not successors or not all(isinstance(ref, str) for ref in successors):
        raise RefinementValidationError("supersede requires a non-empty by list of item refs.")
    if f"{candidate['roadmap_id']}:{item_id}" in successors:
        raise RefinementValidationError("An item cannot supersede itself.")

    local: list[str] = []
    external: list[str] = []
    for ref in successors:
        parts = ref.split(":")
        if len(parts) == 2 and parts[0] == candidate["roadmap_id"]:
            local.append(parts[1])
        else:
            external.append(ref)
    item["status"] = "superseded"
    item["superseded_by"] = list(successors)
    _replace_local_dependency(candidate["items"], item_id, local, external)
    return f"supersede:{item_id}->{','.join(successors)}"


def _apply_operations(
    original: dict[str, Any], request: dict[str, Any], workspace: Path
) -> tuple[dict[str, Any], list[str], list[str]]:
    if not isinstance(request, dict):
        raise RefinementValidationError("Refinement request must be a mapping.")
    for field in ("rationale", "actor", "source"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            raise RefinementValidationError(f"Refinement request requires non-empty {field!r}.")
    operations = request.get("operations")
    if not isinstance(operations, list) or not operations:
        raise RefinementValidationError("Refinement request requires at least one operation.")

    candidate = copy.deepcopy(original)
    summaries: list[str] = []
    new_ids: list[str] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise RefinementValidationError("Each refinement operation must be a mapping.")
        op = operation.get("op")
        if op == "add":
            summaries.append(_apply_add(candidate, operation, new_ids))
        elif op == "edit":
            summaries.append(_apply_edit(candidate, operation))
        elif op == "split":
            summaries.append(_apply_split(candidate, operation, new_ids, workspace))
        elif op == "reorder":
            summaries.append(_apply_reorder(candidate, operation))
        elif op == "supersede":
            summaries.append(_apply_supersede(candidate, operation, workspace))
        else:
            raise RefinementValidationError(
                f"Unknown refinement operation {op!r}; expected add, edit, split, reorder, or supersede."
            )
    return candidate, summaries, new_ids


def _dependency_edges(data: dict[str, Any]) -> set[tuple[str, str]]:
    roadmap_id = data["roadmap_id"]
    edges: set[tuple[str, str]] = set()
    for item in data.get("items", []):
        node = f"{roadmap_id}:{item['item_id']}"
        for dep in item.get("depends_on") or []:
            dep_id = dep["id"] if isinstance(dep, dict) else dep
            edges.add((node, f"{roadmap_id}:{dep_id}"))
        for dep in item.get("external_depends_on") or []:
            edges.add((node, dep))
    return edges


def _global_statuses(repo_root: Path, candidate: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    roadmaps_dir = repo_root / "openspec" / "roadmaps"
    for path in sorted(roadmaps_dir.glob("*/roadmap.yaml")) if roadmaps_dir.is_dir() else []:
        try:
            data = yaml.safe_load(path.read_text())
            for item in data.get("items", []):
                statuses[f"{data['roadmap_id']}:{item['item_id']}"] = item["status"]
        except (OSError, TypeError, KeyError, yaml.YAMLError):
            continue
    for item in candidate.get("items", []):
        statuses[f"{candidate['roadmap_id']}:{item['item_id']}"] = item["status"]
    return statuses


def _schedule_waves(data: dict[str, Any], repo_root: Path) -> list[list[str]]:
    statuses = _global_statuses(repo_root, data)
    roadmap_id = data["roadmap_id"]
    by_id = _item_map(data)
    completed = {item_id for item_id, item in by_id.items() if item.get("status") == "completed"}
    remaining = {
        item_id
        for item_id, item in by_id.items()
        if item.get("status") in {"approved", "in_progress"} and not item.get("superseded_by")
    }
    order = {item["item_id"]: index for index, item in enumerate(data.get("items", []))}
    waves: list[list[str]] = []
    while remaining:
        ready = []
        for item_id in remaining:
            item = by_id[item_id]
            local_ready = all(
                (dep.get("id") if isinstance(dep, dict) else dep) in completed
                for dep in (item.get("depends_on") or [])
            )
            external_ready = all(statuses.get(ref) == "completed" for ref in item.get("external_depends_on") or [])
            if local_ready and external_ready:
                ready.append(item_id)
        if not ready:
            break
        ready.sort(key=lambda item_id: (by_id[item_id].get("priority", 10**9), order[item_id]))
        waves.append(ready)
        completed.update(ready)
        remaining.difference_update(ready)
        for item_id in ready:
            statuses[f"{roadmap_id}:{item_id}"] = "completed"
    return waves


def _shadow_cross_validate(
    repo_root: Path, roadmap_path: Path, candidate: dict[str, Any]
) -> list[str]:
    try:
        target_rel = roadmap_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return [f"Roadmap path {roadmap_path} is outside repository root {repo_root}."]
    with tempfile.TemporaryDirectory(prefix="refine-roadmap-preview-") as temp:
        shadow = Path(temp)
        roadmaps_dir = repo_root / "openspec" / "roadmaps"
        if roadmaps_dir.is_dir():
            for source in roadmaps_dir.glob("*/roadmap.yaml"):
                relative = source.relative_to(repo_root)
                destination = shadow / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
        target = shadow / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(candidate, sort_keys=False))
        return validate_cross_roadmap(shadow)


def preview_refinement(
    roadmap_path: Path, request: dict[str, Any], repo_root: Path
) -> RefinementPreview:
    """Build and validate a refinement candidate without mutating the repository."""
    base_bytes = roadmap_path.read_bytes()
    base_sha256 = _sha256(base_bytes)
    original = yaml.safe_load(base_bytes)
    errors: list[str] = []
    candidate = copy.deepcopy(original)
    summaries: list[str] = []
    new_ids: list[str] = []
    try:
        relative = roadmap_path.resolve().relative_to(repo_root.resolve())
        if relative.parts[:3] == ("openspec", "roadmaps", "archive"):
            errors.append(
                f"Archived roadmap workspaces are immutable: {relative}. Restore it through "
                "an explicitly approved recovery workflow before refinement."
            )
    except ValueError:
        errors.append(f"Roadmap path {roadmap_path} is outside repository root {repo_root}.")

    if not errors:
        try:
            candidate, summaries, new_ids = _apply_operations(original, request, roadmap_path.parent)
        except (RefinementValidationError, KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))

    if not errors:
        errors.extend(validate_roadmap(candidate, repo_root))
        errors.extend(_shadow_cross_validate(repo_root, roadmap_path, candidate))

    state = scan_archive_state(repo_root)
    candidate_items = _item_map(candidate)
    scaffold_ids: list[str] = []
    for item_id in new_ids:
        change_id = candidate_items[item_id].get("change_id")
        if not change_id:
            errors.append(f"New item {item_id!r} has no change_id after derivation.")
            continue
        scaffold_ids.append(change_id)
        if change_id in state:
            label = "archived" if state[change_id] == "completed" else "active"
            errors.append(
                f"New item {item_id!r} uses change_id {change_id!r}, but that change is already {label}."
            )

    before_edges = _dependency_edges(original)
    after_edges = _dependency_edges(candidate)
    return RefinementPreview(
        base_sha256=base_sha256,
        candidate=candidate,
        errors=errors,
        operation_summaries=summaries,
        new_item_ids=new_ids,
        scaffold_change_ids=scaffold_ids,
        schedule_before=_schedule_waves(original, repo_root),
        schedule_after=_schedule_waves(candidate, repo_root),
        dependency_edges_added=sorted(after_edges - before_edges),
        dependency_edges_removed=sorted(before_edges - after_edges),
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _preserved_workspace_files(workspace: Path) -> dict[Path, bytes]:
    paths = [workspace / "checkpoint.json", workspace / "learning-log.md"]
    learnings = workspace / "learnings"
    if learnings.is_dir():
        paths.extend(path for path in learnings.rglob("*") if path.is_file())
    return {path: path.read_bytes() for path in paths if path.is_file()}


def _default_strict_validator(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["openspec", "validate", "--strict", "--all"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return [output or f"openspec validate exited {result.returncode}"]


def apply_refinement(
    roadmap_path: Path,
    request: dict[str, Any],
    repo_root: Path,
    *,
    expected_base_sha256: str,
    strict_validator: StrictValidator = _default_strict_validator,
    now: datetime | None = None,
) -> ApplyResult:
    """Apply a previously previewed refinement and roll back on any failure."""
    current_bytes = roadmap_path.read_bytes()
    current_sha256 = _sha256(current_bytes)
    if current_sha256 != expected_base_sha256:
        raise BaseRoadmapChangedError(
            "roadmap.yaml changed after preview; preview again before applying. "
            f"expected {expected_base_sha256}, found {current_sha256}."
        )

    preview = preview_refinement(roadmap_path, request, repo_root)
    if preview.base_sha256 != expected_base_sha256:
        raise BaseRoadmapChangedError("roadmap.yaml changed while rebuilding the preview.")
    if preview.errors:
        raise RefinementValidationError("Refinement preview is invalid: " + "; ".join(preview.errors))

    candidate = copy.deepcopy(preview.candidate)
    applied_at = now or datetime.now(timezone.utc)
    timestamp = applied_at.astimezone(timezone.utc).isoformat()
    candidate.setdefault("refinements", []).append({
        "timestamp": timestamp,
        "actor": request["actor"].strip(),
        "source": request["source"].strip(),
        "rationale": request["rationale"].strip(),
        "base_sha256": expected_base_sha256,
        "operations": preview.operation_summaries,
    })
    candidate["updated_at"] = timestamp
    candidate_errors = validate_roadmap(candidate, repo_root)
    if candidate_errors:
        raise RefinementValidationError(
            "Candidate failed validation after provenance was appended: " + "; ".join(candidate_errors)
        )

    workspace = roadmap_path.parent
    preserved = _preserved_workspace_files(workspace)
    rendered_path = workspace / "roadmap.md"
    rendered_before = rendered_path.read_bytes() if rendered_path.is_file() else None
    created_dirs: list[Path] = []
    scaffolded: list[str] = []
    roadmap_written = False

    try:
        roadmap = Roadmap.from_dict(candidate)
        for item_id in preview.new_item_ids:
            item = roadmap.get_item(item_id)
            if item is None or not item.change_id:
                raise RefinementValidationError(f"New item {item_id!r} cannot be scaffolded.")
            destination = repo_root / "openspec" / "changes" / item.change_id
            if destination.exists():
                raise RefinementValidationError(
                    f"New change destination appeared after preview: {destination}."
                )
            # Register the exact rollback target before scaffolding: a disk or
            # permission failure can occur after mkdir but before return.
            created_dirs.append(destination)
            scaffold_change(roadmap, repo_root, item_id)
            scaffolded.append(item.change_id)

        serialized = yaml.safe_dump(candidate, sort_keys=False).encode()
        _atomic_write(roadmap_path, serialized)
        roadmap_written = True

        if rendered_before is not None:
            source_path = repo_root / candidate["source_proposal"]
            source_text = source_path.read_text() if source_path.is_file() else None
            rendered = render_roadmap(
                Roadmap.from_dict(candidate),
                source_proposal_text=source_text,
                existing_md=rendered_before.decode(),
            )
            _atomic_write(rendered_path, rendered.encode())

        errors = []
        errors.extend(validate_roadmap(yaml.safe_load(roadmap_path.read_text()), repo_root))
        errors.extend(validate_cross_roadmap(repo_root))
        strict_errors = strict_validator(repo_root)
        if strict_errors:
            errors.extend(f"strict OpenSpec: {error}" for error in strict_errors)
        for path, expected in preserved.items():
            if not path.is_file() or path.read_bytes() != expected:
                errors.append(f"Preserved workspace artifact changed unexpectedly: {path}")
        if errors:
            raise RefinementValidationError("; ".join(errors))
    except BaseException:
        if roadmap_written:
            _atomic_write(roadmap_path, current_bytes)
        if rendered_before is not None:
            _atomic_write(rendered_path, rendered_before)
        for created in reversed(created_dirs):
            if created.is_dir():
                shutil.rmtree(created)
        raise

    result_bytes = roadmap_path.read_bytes()
    return ApplyResult(
        base_sha256=expected_base_sha256,
        result_sha256=_sha256(result_bytes),
        scaffolded_change_ids=scaffolded,
        operation_summaries=preview.operation_summaries,
        rendered_markdown_updated=rendered_before is not None,
    )


def _load_request(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise RefinementValidationError(f"Refinement request {path} is not a YAML mapping.")
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "apply"):
        sub = subparsers.add_parser(command)
        sub.add_argument("roadmap", type=Path)
        sub.add_argument("request", type=Path)
        sub.add_argument("--repo-root", type=Path, default=Path.cwd())
        if command == "apply":
            sub.add_argument("--expect-base-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        request = _load_request(args.request)
        if args.command == "preview":
            preview = preview_refinement(args.roadmap, request, args.repo_root)
            print(yaml.safe_dump(preview.to_dict(), sort_keys=False))
            return 0 if not preview.errors else 1
        result = apply_refinement(
            args.roadmap,
            request,
            args.repo_root,
            expected_base_sha256=args.expect_base_sha256,
        )
        print(yaml.safe_dump(result.to_dict(), sort_keys=False))
        return 0
    except (OSError, RefinementValidationError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
