"""Shared validation, persistence, and dependency resolution for candidate work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SCHEMA_FILENAME = "candidate-work.schema.json"
_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped", "superseded"})
_ROADMAP_ITEM_STATUSES = frozenset(
    {
        "candidate",
        "approved",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "replan_required",
        "skipped",
        "superseded",
    }
)
_SUPPORTED_GENERATORS = frozenset(
    {"bug-scrub", "explore-feature", "improve-harness"}
)
_CANONICAL_CHANGE_PREFIXES = ("add", "update", "remove", "refactor")

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


class LifecycleCollectionError(ValueError):
    """Raised when repository lifecycle records cannot be read consistently."""


def normalize_source_identity(generator: str, source_id: str) -> str:
    """Return the producer-specific immutable source identity."""
    if generator not in _SUPPORTED_GENERATORS:
        raise ValueError(f"unsupported candidate-work generator: {generator!r}")
    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    normalized = (
        " ".join(source_id.split()).lower()
        if generator == "improve-harness"
        else source_id
    )
    if not normalized.strip():
        raise ValueError("source_id must not be blank")
    return normalized


def _ascii_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def normalize_suggested_change_id(suggested_id: str) -> str:
    """Normalize a suggested ID to an ASCII slug and canonical prefix."""
    if not isinstance(suggested_id, str):
        raise TypeError("suggested_id must be a string")
    slug = _ascii_slug(suggested_id)
    if slug.startswith("fix-"):
        return f"update-{slug.removeprefix('fix-')}"
    if slug.startswith(tuple(f"{prefix}-" for prefix in _CANONICAL_CHANGE_PREFIXES)):
        return slug
    return f"update-{slug}"


def derive_suggested_change_id(
    generator: str,
    source_id: str,
    explicit_hint: str | None = None,
) -> str:
    """Derive a stable suggested ID from immutable producer identity."""
    normalized_source_id = normalize_source_identity(generator, source_id)
    if explicit_hint is not None:
        return normalize_suggested_change_id(explicit_hint)
    identity = {"generator": generator, "source_id": normalized_source_id}
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    identity_hash = hashlib.sha256(encoded).hexdigest()[:8]
    base = normalize_suggested_change_id(normalized_source_id)
    return f"{base}-{identity_hash}"


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



_ARCHIVE_CHANGE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")


def _archive_change_id(directory_name: str) -> str:
    match = _ARCHIVE_CHANGE_PREFIX.fullmatch(directory_name)
    return match.group(1) if match else directory_name


def _lifecycle_path_label(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _roadmap_lifecycle_records(
    path: Path, repo_root: Path
) -> list[LifecycleRecord]:
    """Read only stable lifecycle fields, tolerating legacy roadmap schemas."""
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LifecycleCollectionError(
            f"roadmap {_lifecycle_path_label(path, repo_root)} could not be loaded: {exc}"
        ) from exc
    if not isinstance(data, Mapping):
        raise LifecycleCollectionError(
            f"roadmap {_lifecycle_path_label(path, repo_root)} must contain a mapping"
        )
    roadmap_id = data.get("roadmap_id")
    items = data.get("items")
    if not isinstance(roadmap_id, str) or not isinstance(items, list):
        raise LifecycleCollectionError(
            f"roadmap {_lifecycle_path_label(path, repo_root)} requires roadmap_id and items"
        )

    records: list[LifecycleRecord] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise LifecycleCollectionError(
                f"roadmap {_lifecycle_path_label(path, repo_root)} item #{index} "
                "must be a mapping"
            )
        change_id = item.get("change_id")
        if not change_id:
            continue
        item_id = item.get("item_id")
        status = item.get("status")
        if not all(
            isinstance(value, str) for value in (change_id, item_id, status)
        ):
            raise LifecycleCollectionError(
                f"roadmap {_lifecycle_path_label(path, repo_root)} item #{index} "
                "has invalid lifecycle fields"
            )
        if status not in _ROADMAP_ITEM_STATUSES:
            raise LifecycleCollectionError(
                f"roadmap {_lifecycle_path_label(path, repo_root)} item #{index} "
                f"has unknown roadmap item status {status!r}"
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


def collect_lifecycle_records(
    repo_root: Path,
    *,
    additional_roadmap_paths: Iterable[Path] = (),
) -> list[LifecycleRecord]:
    """Collect one exact lifecycle model for ranking, intake, and producers.

    Roadmaps are intentionally decoded against the stable lifecycle field subset
    instead of today's full roadmap schema. This keeps archived history readable
    across schema revisions while rejecting malformed identity or status fields.
    Additional explicit roadmap paths use the same lifecycle parser and are
    deduplicated by resolved path against canonical and earlier explicit paths.
    """
    root = Path(repo_root)
    roadmaps = root / "openspec" / "roadmaps"
    roadmap_paths: list[Path] = []
    if roadmaps.is_dir():
        roadmap_paths.extend(sorted(roadmaps.glob("*/roadmap.yaml")))
        archived_roadmaps = roadmaps / "archive"
        if archived_roadmaps.is_dir():
            roadmap_paths.extend(
                sorted(archived_roadmaps.glob("*/roadmap.yaml"))
            )
    roadmap_paths.extend(Path(path) for path in additional_roadmap_paths)

    unique_roadmap_paths: list[Path] = []
    seen_roadmap_paths: set[Path] = set()
    for path in roadmap_paths:
        resolved = path.resolve()
        if resolved in seen_roadmap_paths:
            continue
        seen_roadmap_paths.add(resolved)
        unique_roadmap_paths.append(path)

    records = [
        record
        for path in unique_roadmap_paths
        for record in _roadmap_lifecycle_records(path, root)
    ]

    changes = root / "openspec" / "changes"
    if not changes.is_dir():
        return records
    records.extend(
        LifecycleRecord(path.name, "active_change", "active")
        for path in sorted(changes.iterdir())
        if path.is_dir() and path.name != "archive"
    )
    archive = changes / "archive"
    if archive.is_dir():
        records.extend(
            LifecycleRecord(
                _archive_change_id(path.name), "archive", "completed"
            )
            for path in sorted(archive.iterdir())
            if path.is_dir()
        )
    return records


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
        try:
            loaded = load_candidate_work(Path(path), schema=active_schema)
        except CandidateWorkValidationError as exc:
            local_index = exc.index if exc.index is not None else 0
            raise CandidateWorkValidationError(
                exc.errors, index=len(merged) + local_index
            ) from exc
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


def _existing_generators(
    path: Path, *, schema: dict[str, Any] | None = None
) -> set[str | None]:
    if not path.is_file():
        return set()
    try:
        loaded = load_candidate_work(path, schema=schema)
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
    conflicting = _existing_generators(destination, schema=schema) - {generator}
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
    "LifecycleCollectionError",
    "LifecycleRecord",
    "canonical_candidate_work_bytes",
    "cli",
    "collect_lifecycle_records",
    "derive_suggested_change_id",
    "find_schema_path",
    "group_lifecycle_records",
    "load_candidate_work",
    "load_candidate_work_files",
    "load_schema",
    "normalize_source_identity",
    "normalize_suggested_change_id",
    "resolve_dependency",
    "validate_candidate_work",
    "validate_candidate_work_batch",
    "write_candidate_work",
]
