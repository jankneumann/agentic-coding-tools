"""Neutral, fail-closed scope scheduler for delegated roadmap dispatch.

This module performs no orchestration and imports no host adapter.  It turns
dependency-ready item identities into a deterministic maximal batch whose members
are admitted together only when every pair is proven scope-disjoint.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal, Sequence

import yaml
from jsonschema import Draft202012Validator

from scope_overlap import lock_key_overlap, write_write_overlap


_CHANGE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_WILDCARD_CHARS = frozenset("*?[")
_WORK_PACKAGE_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "openspec"
    / "schemas"
    / "work-packages.schema.json"
)

ScopeProof = Literal["proven_disjoint", "serial_indeterminate"]


class ScopeRelation(str, Enum):
    """Conservative relationship between two effective write scopes."""

    OVERLAP = "overlap"
    PROVEN_DISJOINT = "proven_disjoint"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ScopeEvidence:
    """Exact all-package evidence carried into a dispatch request."""

    change_id: str
    proof: ScopeProof
    write_allow: tuple[str, ...]
    lock_keys: tuple[str, ...]
    package_ids: tuple[str, ...]
    reason: str | None = None

    def to_request_scope(self) -> dict[str, object]:
        """Return the scope fragment defined by the frozen request contract."""
        return {
            "proof": self.proof,
            "write_allow": list(self.write_allow),
            "lock_keys": list(self.lock_keys),
        }


@dataclass(frozen=True, slots=True)
class ReadyDispatchItem:
    """Minimal scheduler input, independent of the roadmap orchestrator."""

    item_id: str
    change_id: str | None
    priority: int


@dataclass(frozen=True, slots=True)
class SelectedDispatchItem:
    """A ready item paired with its exact effective scope evidence."""

    item_id: str
    change_id: str
    priority: int
    scope: ScopeEvidence


@dataclass(frozen=True, slots=True)
class SchedulingFailure:
    """A deterministic non-dispatch result for an invalid item identity."""

    item_id: str
    reason: Literal["invalid_change_id"]


@dataclass(frozen=True, slots=True)
class DispatchBatch:
    """One deterministic maximal safe batch and the items left ready."""

    items: tuple[SelectedDispatchItem, ...]
    deferred_item_ids: tuple[str, ...]
    failures: tuple[SchedulingFailure, ...]


def is_valid_change_id(change_id: object) -> bool:
    """Return whether *change_id* exactly satisfies the request contract."""
    return (
        isinstance(change_id, str)
        and len(change_id) <= 160
        and _CHANGE_ID_RE.fullmatch(change_id) is not None
    )


def _serial_scope(
    change_id: str,
    reason: str,
    *,
    write_allow: tuple[str, ...] = (),
    lock_keys: tuple[str, ...] = (),
    package_ids: tuple[str, ...] = (),
) -> ScopeEvidence:
    return ScopeEvidence(
        change_id=change_id,
        proof="serial_indeterminate",
        write_allow=write_allow,
        lock_keys=lock_keys,
        package_ids=package_ids,
        reason=reason,
    )


def _literal_prefix(glob: str) -> tuple[str, ...]:
    prefix: list[str] = []
    for component in glob.split("/"):
        if any(character in component for character in _WILDCARD_CHARS):
            break
        prefix.append(component)
    return tuple(prefix)


def _is_boundless(glob: str) -> bool:
    return not _literal_prefix(glob)


@lru_cache(maxsize=1)
def _work_package_validator() -> Draft202012Validator:
    schema = json.loads(_WORK_PACKAGE_SCHEMA.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def aggregate_change_scope(repo_root: Path, change_id: str) -> ScopeEvidence:
    """Load and aggregate exact write/lock evidence from every work package.

    A valid change identifier with missing or malformed package evidence is still
    representable as a schema-valid serial scope.  Invalid identifiers are rejected
    by :func:`select_safe_ready_batch` before this loader is called.
    """
    path = repo_root / "openspec" / "changes" / change_id / "work-packages.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return _serial_scope(change_id, "work_packages_missing_or_invalid")

    if not isinstance(document, dict) or not _work_package_validator().is_valid(document):
        return _serial_scope(change_id, "work_packages_invalid")
    feature = document.get("feature")
    packages = document.get("packages")
    if (
        not isinstance(feature, dict)
        or feature.get("id") != change_id
        or not isinstance(packages, list)
        or not packages
    ):
        return _serial_scope(change_id, "work_packages_invalid")

    writes: list[str] = []
    lock_keys: list[str] = []
    package_ids: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            return _serial_scope(change_id, "work_packages_invalid")
        package_id = package.get("package_id")
        scope = package.get("scope")
        locks = package.get("locks", {})
        if (
            not isinstance(package_id, str)
            or not package_id
            or not isinstance(scope, dict)
            or not isinstance(locks, dict)
        ):
            return _serial_scope(change_id, "work_packages_invalid")
        package_writes = scope.get("write_allow")
        package_locks = locks.get("keys", [])
        if (
            not isinstance(package_writes, list)
            or not all(isinstance(value, str) and value for value in package_writes)
            or not isinstance(package_locks, list)
            or not all(isinstance(value, str) and value for value in package_locks)
        ):
            return _serial_scope(change_id, "work_packages_invalid")
        writes.extend(package_writes)
        lock_keys.extend(package_locks)
        package_ids.append(package_id)

    exact_writes = tuple(sorted(set(writes)))
    exact_locks = tuple(sorted(set(lock_keys)))
    exact_packages = tuple(package_ids)
    if not exact_writes:
        return _serial_scope(
            change_id,
            "write_scope_empty",
            lock_keys=exact_locks,
            package_ids=exact_packages,
        )
    if any(_is_boundless(glob) for glob in exact_writes):
        return _serial_scope(
            change_id,
            "write_scope_boundless",
            write_allow=exact_writes,
            lock_keys=exact_locks,
            package_ids=exact_packages,
        )
    return ScopeEvidence(
        change_id=change_id,
        proof="proven_disjoint",
        write_allow=exact_writes,
        lock_keys=exact_locks,
        package_ids=exact_packages,
    )


def _glob_pair_proven_disjoint(first: str, second: str) -> bool:
    first_prefix = _literal_prefix(first)
    second_prefix = _literal_prefix(second)
    for first_part, second_part in zip(first_prefix, second_prefix, strict=False):
        if first_part != second_part:
            return True
    if len(first_prefix) == len(first.split("/")) and len(second_prefix) == len(
        second.split("/")
    ):
        return first != second
    return False


def classify_scope_relationship(
    first: ScopeEvidence,
    second: ScopeEvidence,
) -> ScopeRelation:
    """Classify a pair without treating absence of overlap as independence."""
    if first.proof != "proven_disjoint" or second.proof != "proven_disjoint":
        return ScopeRelation.AMBIGUOUS
    if lock_key_overlap(list(first.lock_keys), list(second.lock_keys)):
        return ScopeRelation.OVERLAP
    if write_write_overlap(list(first.write_allow), list(second.write_allow)):
        return ScopeRelation.OVERLAP
    if all(
        _glob_pair_proven_disjoint(first_glob, second_glob)
        for first_glob in first.write_allow
        for second_glob in second.write_allow
    ):
        return ScopeRelation.PROVEN_DISJOINT
    return ScopeRelation.AMBIGUOUS


def select_safe_ready_batch(
    repo_root: Path,
    ready_items: Sequence[ReadyDispatchItem],
) -> DispatchBatch:
    """Select the priority/item-id ordered maximal pairwise-safe ready batch."""
    ordered = sorted(ready_items, key=lambda item: (item.priority, item.item_id))
    candidates: list[SelectedDispatchItem] = []
    failures: list[SchedulingFailure] = []
    for item in ordered:
        if not is_valid_change_id(item.change_id):
            failures.append(SchedulingFailure(item.item_id, "invalid_change_id"))
            continue
        assert item.change_id is not None
        candidates.append(
            SelectedDispatchItem(
                item_id=item.item_id,
                change_id=item.change_id,
                priority=item.priority,
                scope=aggregate_change_scope(repo_root, item.change_id),
            )
        )

    if not candidates:
        return DispatchBatch((), (), tuple(failures))

    first = candidates[0]
    if first.scope.proof == "serial_indeterminate":
        return DispatchBatch(
            (first,),
            tuple(candidate.item_id for candidate in candidates[1:]),
            tuple(failures),
        )

    selected = [first]
    deferred: list[str] = []
    for candidate in candidates[1:]:
        if candidate.scope.proof == "proven_disjoint" and all(
            classify_scope_relationship(candidate.scope, admitted.scope)
            is ScopeRelation.PROVEN_DISJOINT
            for admitted in selected
        ):
            selected.append(candidate)
        else:
            deferred.append(candidate.item_id)

    if len(selected) == 1 and deferred:
        selected[0] = replace(
            selected[0],
            scope=replace(
                selected[0].scope,
                proof="serial_indeterminate",
                reason="no_parallel_scope_proof",
            ),
        )
    return DispatchBatch(tuple(selected), tuple(deferred), tuple(failures))


__all__ = [
    "DispatchBatch",
    "ReadyDispatchItem",
    "ScopeEvidence",
    "ScopeRelation",
    "SchedulingFailure",
    "SelectedDispatchItem",
    "aggregate_change_scope",
    "classify_scope_relationship",
    "is_valid_change_id",
    "select_safe_ready_batch",
]
