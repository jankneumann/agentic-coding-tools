#!/usr/bin/env python3
"""Resolve one deterministic, checkpoint-aware ready-now list across roadmaps."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from readiness import _get_ready_items


_HARD_ERROR_CODES = frozenset(
    {
        "roadmap_invalid",
        "duplicate_roadmap_id",
        "checkpoint_invalid",
        "checkpoint_roadmap_mismatch",
        "checkpoint_unknown_item",
        "checkpoint_terminal_conflict",
    }
)


def _load_models() -> Any:
    """Load sibling models.py under a collision-proof module name."""
    name = "roadmap_runtime_readiness_models"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).with_name("models.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_models = _load_models()


@dataclass
class _Failed:
    item_id: str


@dataclass
class _EffectiveCheckpoint:
    completed_items: list[str]
    failed_items: list[_Failed]


@dataclass
class _Workspace:
    path: Path
    label: str
    roadmap: Any | None
    roadmap_raw: bytes
    checkpoint_path: Path
    checkpoint: Any | None = None
    checkpoint_raw: bytes | None = None
    effective: _EffectiveCheckpoint | Any | None = None
    hard_invalid: bool = False


def _detail(text: str) -> str:
    """Bound diagnostic details to the public result contract."""
    return text[:512]


def _diagnostic(
    roadmap_id: str, code: str, *, stale: bool, detail: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "roadmap_id": roadmap_id,
        "code": code,
        "stale": stale,
    }
    if detail:
        result["detail"] = _detail(detail)
    return result


def _read_roadmap(path: Path, repo_root: Path, raw: bytes) -> Any:
    data = yaml.safe_load(raw.decode("utf-8"))
    errors = _models.validate_against_schema(data, _models.ROADMAP_SCHEMA, repo_root)
    if errors:
        raise ValueError("; ".join(errors))
    return _models.Roadmap.from_dict(data)


def _read_checkpoint(path: Path, repo_root: Path, raw: bytes) -> Any:
    data = json.loads(raw.decode("utf-8"))
    errors = _models.validate_against_schema(data, _models.CHECKPOINT_SCHEMA, repo_root)
    if errors:
        raise ValueError("; ".join(errors))
    return _models.Checkpoint.from_dict(data)


def _canonical_roadmap(workspace: _Workspace) -> dict[str, Any]:
    relative = workspace.path.as_posix()
    roadmap = workspace.roadmap
    if roadmap is None:
        return {
            "path": relative,
            "kind": "roadmap",
            "invalid_sha256": hashlib.sha256(workspace.roadmap_raw).hexdigest(),
        }
    return {
        "path": relative,
        "roadmap_id": roadmap.roadmap_id,
        "items": [
            {
                "item_id": item.item_id,
                "status": str(item.status.value),
                "priority": item.priority,
                "effort": str(item.effort.value),
                "depends_on": sorted(item.depends_on),
                "external_depends_on": sorted(item.external_depends_on),
                "superseded_by": sorted(item.superseded_by),
                "change_id": item.change_id,
                "title": item.title,
            }
            for item in sorted(roadmap.items, key=lambda item: item.item_id)
        ],
    }


def _canonical_checkpoint(workspace: _Workspace) -> dict[str, Any]:
    if workspace.checkpoint_raw is None:
        return {"state": "absent"}
    relative = workspace.checkpoint_path.as_posix()
    checkpoint = workspace.checkpoint
    if checkpoint is None:
        return {
            "path": relative,
            "kind": "checkpoint",
            "invalid_sha256": hashlib.sha256(workspace.checkpoint_raw).hexdigest(),
        }
    return {
        "path": relative,
        "roadmap_id": checkpoint.roadmap_id,
        "current_item_id": checkpoint.current_item_id,
        "completed_items": sorted(checkpoint.completed_items),
        "failed_items": sorted(failed.item_id for failed in checkpoint.failed_items),
    }


def _source_fingerprint(repo_root: Path, workspaces: list[_Workspace]) -> str:
    projection = [
        {
            "roadmap": {
                **_canonical_roadmap(workspace),
                "path": workspace.path.relative_to(repo_root).as_posix(),
            },
            "checkpoint": {
                **_canonical_checkpoint(workspace),
                **(
                    {"path": workspace.checkpoint_path.relative_to(repo_root).as_posix()}
                    if workspace.checkpoint_raw is not None
                    else {}
                ),
            },
        }
        for workspace in workspaces
    ]
    canonical = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _definition_checkpoint(roadmap: Any) -> _EffectiveCheckpoint:
    return _EffectiveCheckpoint(
        completed_items=sorted(
            item.item_id for item in roadmap.items if item.status.value == "completed"
        ),
        failed_items=[
            _Failed(item.item_id)
            for item in sorted(roadmap.items, key=lambda item: item.item_id)
            if item.status.value == "failed"
        ],
    )


def _checkpoint_diagnostics(workspace: _Workspace) -> list[dict[str, Any]]:
    roadmap = workspace.roadmap
    checkpoint = workspace.checkpoint
    assert roadmap is not None and checkpoint is not None
    roadmap_id = roadmap.roadmap_id
    known = {item.item_id for item in roadmap.items}

    if checkpoint.roadmap_id != roadmap_id:
        workspace.hard_invalid = True
        return [
            _diagnostic(
                roadmap_id,
                "checkpoint_roadmap_mismatch",
                stale=True,
                detail=f"checkpoint roadmap_id={checkpoint.roadmap_id!r}",
            )
        ]

    completed = list(checkpoint.completed_items)
    failed = [entry.item_id for entry in checkpoint.failed_items]
    overlap = sorted(set(completed) & set(failed))
    if overlap:
        workspace.hard_invalid = True
        return [
            _diagnostic(
                roadmap_id,
                "checkpoint_terminal_conflict",
                stale=True,
                detail=f"items in completed and failed: {','.join(overlap)}",
            )
        ]

    if len(completed) != len(set(completed)) or len(failed) != len(set(failed)):
        workspace.hard_invalid = True
        return [
            _diagnostic(
                roadmap_id,
                "checkpoint_invalid",
                stale=True,
                detail="duplicate terminal item ids",
            )
        ]

    unknown = sorted(({checkpoint.current_item_id} | set(completed) | set(failed)) - known)
    if unknown:
        workspace.hard_invalid = True
        return [
            _diagnostic(
                roadmap_id,
                "checkpoint_unknown_item",
                stale=True,
                detail=f"unknown item ids: {','.join(unknown)}",
            )
        ]

    effective_status = {item_id: "completed" for item_id in completed}
    effective_status.update({item_id: "failed" for item_id in failed})
    divergent = []
    for item in sorted(roadmap.items, key=lambda item: item.item_id):
        definition = item.status.value if item.status.value in {"completed", "failed"} else None
        effective = effective_status.get(item.item_id)
        if definition != effective and (definition is not None or effective is not None):
            divergent.append(f"{item.item_id}:{definition or 'open'}->{effective or 'open'}")
    if divergent:
        return [
            _diagnostic(
                roadmap_id,
                "roadmap_checkpoint_divergence",
                stale=True,
                detail="terminal status differs: " + ",".join(divergent),
            )
        ]
    return []


def _load_workspaces(repo_root: Path) -> tuple[list[_Workspace], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    workspaces: list[_Workspace] = []
    roadmaps_root = repo_root / "openspec" / "roadmaps"
    if not roadmaps_root.is_dir():
        return workspaces, diagnostics

    for path in sorted(roadmaps_root.glob("*/roadmap.yaml")):
        raw = path.read_bytes()
        workspace = _Workspace(
            path=path,
            label=path.parent.name,
            roadmap=None,
            roadmap_raw=raw,
            checkpoint_path=path.with_name("checkpoint.json"),
        )
        try:
            workspace.roadmap = _read_roadmap(path, repo_root, raw)
        except Exception as exc:  # noqa: BLE001 - converted to bounded diagnostic
            workspace.hard_invalid = True
            diagnostics.append(
                _diagnostic(
                    workspace.label,
                    "roadmap_invalid",
                    stale=True,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
        if workspace.checkpoint_path.is_file():
            workspace.checkpoint_raw = workspace.checkpoint_path.read_bytes()
            try:
                workspace.checkpoint = _read_checkpoint(
                    workspace.checkpoint_path, repo_root, workspace.checkpoint_raw
                )
            except Exception as exc:  # noqa: BLE001 - converted to bounded diagnostic
                if workspace.roadmap is not None:
                    workspace.hard_invalid = True
                    diagnostics.append(
                        _diagnostic(
                            workspace.roadmap.roadmap_id,
                            "checkpoint_invalid",
                            stale=True,
                            detail=f"{type(exc).__name__}: {exc}",
                        )
                    )
        workspaces.append(workspace)

    by_id: dict[str, list[_Workspace]] = {}
    for workspace in workspaces:
        if workspace.roadmap is not None:
            by_id.setdefault(workspace.roadmap.roadmap_id, []).append(workspace)
    for roadmap_id, duplicates in sorted(by_id.items()):
        if len(duplicates) < 2:
            continue
        paths = ",".join(
            workspace.path.relative_to(repo_root).as_posix() for workspace in duplicates
        )
        for workspace in duplicates:
            workspace.hard_invalid = True
            diagnostics.append(
                _diagnostic(
                    roadmap_id,
                    "duplicate_roadmap_id",
                    stale=True,
                    detail=f"declared by: {paths}",
                )
            )

    return workspaces, diagnostics


def resolve_readiness(repo_root: Path) -> dict[str, Any]:
    """Return deterministic checkpoint-aware readiness for active workspaces."""
    repo_root = Path(repo_root).resolve()
    workspaces, diagnostics = _load_workspaces(repo_root)

    for workspace in workspaces:
        if workspace.roadmap is None or workspace.hard_invalid:
            continue
        if workspace.checkpoint_raw is None:
            workspace.effective = _definition_checkpoint(workspace.roadmap)
            diagnostics.append(
                _diagnostic(workspace.roadmap.roadmap_id, "checkpoint_absent", stale=False)
            )
        elif workspace.checkpoint is not None:
            diagnostics.extend(_checkpoint_diagnostics(workspace))
            if not workspace.hard_invalid:
                workspace.effective = workspace.checkpoint

    external_completed: set[str] = set()
    for workspace in workspaces:
        if workspace.roadmap is None or workspace.effective is None or workspace.hard_invalid:
            continue
        external_completed.update(
            f"{workspace.roadmap.roadmap_id}:{item_id}"
            for item_id in workspace.effective.completed_items
        )

    ready: list[dict[str, Any]] = []
    for workspace in workspaces:
        if workspace.roadmap is None or workspace.effective is None or workspace.hard_invalid:
            continue
        for item in _get_ready_items(
            workspace.roadmap, workspace.effective, external_completed
        ):
            ready.append(
                {
                    "roadmap_id": workspace.roadmap.roadmap_id,
                    "item_id": item.item_id,
                    "priority": item.priority,
                    "effort": item.effort.value,
                    "change_id": item.change_id,
                    "title": item.title,
                }
            )

    ready.sort(key=lambda row: (row["priority"], row["roadmap_id"], row["item_id"]))
    diagnostics.sort(
        key=lambda row: (row["roadmap_id"], row["code"], row.get("detail", ""))
    )
    return {
        "schema_version": 1,
        "source_fingerprint": _source_fingerprint(repo_root, workspaces),
        "stale": any(row["stale"] for row in diagnostics),
        "diagnostics": diagnostics,
        "ready": ready,
    }


def readiness_exit_code(result: dict[str, Any]) -> int:
    """Return non-zero only for hard-invalid canonical input."""
    return 2 if any(row["code"] in _HARD_ERROR_CODES for row in result["diagnostics"]) else 0


def render_readiness(repo_root: Path) -> str:
    """Render byte-stable JSON with a trailing newline."""
    return json.dumps(
        resolve_readiness(repo_root), sort_keys=True, separators=(",", ":")
    ) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    result = resolve_readiness(Path(args.repo_root))
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return readiness_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
