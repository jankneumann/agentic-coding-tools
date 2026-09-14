"""Shared validation, persistence, and dependency resolution for candidate work."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SCHEMA_FILENAME = "candidate-work.schema.json"
_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped", "superseded"})

LifecycleSource = Literal["candidate", "roadmap", "active_change", "archive"]
DependencyOutcome = Literal["satisfied", "live", "unresolved", "ambiguous"]


class CandidateWorkValidationError(ValueError):
    """Raised when candidate work violates the canonical contract."""

    def __init__(self, errors: list[str], *, index: int | None = None) -> None:
        self.errors = errors
        self.index = index
        where = "" if index is None else f" (item #{index})"
        joined = "\n  - ".join(errors)
        super().__init__(
            f"candidate-work stub failed schema validation{where}:\n  - {joined}"
        )


class CandidateWorkCollisionError(ValueError):
    """Raised when an explicit destination belongs to another generator."""


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    """One exact change-ID observation from a lifecycle registry."""

    change_id: str
    source: LifecycleSource
    status: str
    roadmap_id: str | None = None
    item_id: str | None = None


@dataclass(frozen=True, slots=True)
class DependencyResolution:
    """Deterministic resolution of all exact matches for one dependency."""

    change_id: str
    outcome: DependencyOutcome
    live_record: LifecycleRecord | None
    matches: tuple[LifecycleRecord, ...]
    reason: str


def _record_key(record: LifecycleRecord) -> tuple[str, str, str, str]:
    return (
        record.source,
        record.roadmap_id or "",
        record.item_id or "",
        record.status,
    )


def group_lifecycle_records(
    records: Iterable[LifecycleRecord],
) -> dict[str, tuple[LifecycleRecord, ...]]:
    """Group records by exact change ID with stable key and record ordering."""
    grouped: dict[str, list[LifecycleRecord]] = {}
    for record in records:
        grouped.setdefault(record.change_id, []).append(record)
    return {
        change_id: tuple(sorted(grouped[change_id], key=_record_key))
        for change_id in sorted(grouped)
    }


def resolve_dependency(
    change_id: str, records: Iterable[LifecycleRecord]
) -> DependencyResolution:
    """Resolve one dependency without source-order precedence.

    Only completed roadmap and completed archive records satisfy a dependency.
    Failed, skipped, and superseded records remain unresolved.  An active-change
    observation and its sole live roadmap item represent one lineage; other
    multiple live owners are ambiguous.
    """
    matches = group_lifecycle_records(records).get(change_id, ())
    if not matches:
        return DependencyResolution(
            change_id, "unresolved", None, (), "no exact lifecycle match"
        )

    live_roadmaps = tuple(
        record
        for record in matches
        if record.source == "roadmap" and record.status not in _TERMINAL_STATUSES
    )
    live_candidates = tuple(
        record
        for record in matches
        if record.source == "candidate" and record.status not in _TERMINAL_STATUSES
    )
    active_changes = tuple(
        record
        for record in matches
        if record.source == "active_change" and record.status not in _TERMINAL_STATUSES
    )

    if active_changes:
        if len(active_changes) == 1 and len(live_roadmaps) == 1 and not live_candidates:
            return DependencyResolution(
                change_id,
                "live",
                live_roadmaps[0],
                matches,
                "active change is represented by one live roadmap item",
            )
        if len(active_changes) == 1 and not live_roadmaps and not live_candidates:
            return DependencyResolution(
                change_id,
                "unresolved",
                None,
                matches,
                "active change exists without a live roadmap item",
            )
        return DependencyResolution(
            change_id, "ambiguous", None, matches, "multiple live lifecycle owners"
        )

    live_owners = live_candidates + live_roadmaps
    if len(live_owners) == 1:
        return DependencyResolution(
            change_id, "live", live_owners[0], matches, "one unique live owner"
        )
    if len(live_owners) > 1:
        return DependencyResolution(
            change_id, "ambiguous", None, matches, "multiple live lifecycle owners"
        )

    completed = all(
        record.status == "completed" and record.source in {"roadmap", "archive"}
        for record in matches
    )
    if completed:
        return DependencyResolution(
            change_id,
            "satisfied",
            None,
            matches,
            "all matching lifecycle records are completed",
        )
    return DependencyResolution(
        change_id,
        "unresolved",
        None,
        matches,
        "matching lifecycle records are terminal but not completed",
    )


def find_schema_path(start: Path | None = None) -> Path:
    """Locate the repository's canonical candidate-work schema."""
    here = (start or Path(__file__)).resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "openspec" / "schemas" / SCHEMA_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate openspec/schemas/{SCHEMA_FILENAME} above {here}"
    )


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the canonical candidate-work JSON Schema."""
    return json.loads((schema_path or find_schema_path()).read_text(encoding="utf-8"))


def _format_error(exc: Any) -> str:
    pointer = "/".join(str(part) for part in exc.absolute_path)
    location = f"$.{pointer}" if pointer else "$ (root)"
    return f"{location}: {exc.message}"


def validate_candidate_work(
    instance: Any,
    *,
    schema: dict[str, Any] | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    """Validate one candidate-work stub and return it unchanged."""
    import jsonschema

    active_schema = schema if schema is not None else load_schema()
    validator = jsonschema.Draft202012Validator(active_schema)
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        raise CandidateWorkValidationError(
            [_format_error(error) for error in errors], index=index
        )
    return instance


def _reject_duplicate_ids(instances: Sequence[dict[str, Any]]) -> None:
    first_indices: dict[str, int] = {}
    for index, instance in enumerate(instances):
        candidate_id = instance["suggested_change_id"]
        if candidate_id in first_indices:
            first = first_indices[candidate_id]
            raise CandidateWorkValidationError(
                [
                    "duplicate suggested_change_id "
                    f"{candidate_id!r} at items #{first} and #{index}"
                ],
                index=index,
            )
        first_indices[candidate_id] = index


def validate_candidate_work_batch(
    instances: Iterable[Any],
    *,
    schema: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate a complete batch and reject duplicate final IDs."""
    active_schema = schema if schema is not None else load_schema()
    validated = [
        validate_candidate_work(instance, schema=active_schema, index=index)
        for index, instance in enumerate(instances)
    ]
    _reject_duplicate_ids(validated)
    return validated


def load_candidate_work(
    path: Path, *, schema: dict[str, Any] | None = None
) -> dict[str, Any] | list[dict[str, Any]]:
    """Load one object or array and validate it before returning."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return validate_candidate_work_batch(raw, schema=schema)
    return validate_candidate_work(raw, schema=schema)


def load_candidate_work_files(
    paths: Iterable[Path], *, schema: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Validate files independently, then concatenate them in caller order."""
    active_schema = schema if schema is not None else load_schema()
    merged: list[dict[str, Any]] = []
    for path in paths:
        loaded = load_candidate_work(Path(path), schema=active_schema)
        merged.extend(loaded if isinstance(loaded, list) else [loaded])
    _reject_duplicate_ids(merged)
    return merged


def canonical_candidate_work_bytes(
    instances: Iterable[Any], *, schema: dict[str, Any] | None = None
) -> bytes:
    """Return validated, deterministically ordered candidate-work JSON bytes."""
    validated = validate_candidate_work_batch(instances, schema=schema)
    ordered = sorted(
        validated, key=lambda item: (item["priority"], item["suggested_change_id"])
    )
    text = json.dumps(ordered, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def _existing_generators(path: Path) -> set[str | None]:
    if not path.is_file():
        return set()
    try:
        loaded = load_candidate_work(path)
    except (json.JSONDecodeError, CandidateWorkValidationError):
        return set()
    batch = loaded if isinstance(loaded, list) else [loaded]
    return {item["provenance"].get("generator") for item in batch}


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def write_candidate_work(
    path: Path,
    instances: Iterable[Any],
    *,
    generator: str,
    schema: dict[str, Any] | None = None,
) -> Path:
    """Validate and atomically replace one producer-owned candidate sidecar."""
    destination = Path(path)
    batch = validate_candidate_work_batch(list(instances), schema=schema)
    incoming_owners = {item["provenance"].get("generator") for item in batch}
    incoming_conflicts = incoming_owners - {generator}
    if incoming_conflicts:
        labels = ", ".join(
            sorted(owner or "unknown" for owner in incoming_conflicts)
        )
        raise CandidateWorkCollisionError(
            f"candidate-work input belongs to {labels}, not {generator}"
        )

    content = canonical_candidate_work_bytes(batch, schema=schema)
    conflicting = _existing_generators(destination) - {generator}
    if conflicting:
        labels = ", ".join(sorted(owner or "unknown" for owner in conflicting))
        raise CandidateWorkCollisionError(
            f"candidate-work destination {destination} belongs to {labels}, "
            f"not {generator}"
        )
    _atomic_replace(destination, content)
    return destination


def cli(argv: Sequence[str] | None = None) -> int:
    """Validate a candidate-work file for the compatibility CLI."""
    import sys

    parser = argparse.ArgumentParser(
        description="Validate candidate-work stub(s) against candidate-work.schema.json"
    )
    parser.add_argument("path", help="Candidate-work JSON object or array.")
    args = parser.parse_args(argv)
    try:
        result = load_candidate_work(Path(args.path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args.path} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except CandidateWorkValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    count = len(result) if isinstance(result, list) else 1
    print(f"ok: {count} candidate-work stub(s) valid")
    return 0


__all__ = [
    "SCHEMA_FILENAME",
    "CandidateWorkCollisionError",
    "CandidateWorkValidationError",
    "DependencyResolution",
    "LifecycleRecord",
    "canonical_candidate_work_bytes",
    "cli",
    "find_schema_path",
    "group_lifecycle_records",
    "load_candidate_work",
    "load_candidate_work_files",
    "load_schema",
    "resolve_dependency",
    "validate_candidate_work",
    "validate_candidate_work_batch",
    "write_candidate_work",
]
