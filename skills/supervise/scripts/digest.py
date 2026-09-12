#!/usr/bin/env python3
"""Deterministic candidate-work storage, ranking, and approval routing.

This module is deliberately host assisted: it validates and transforms files, but
never calls a model, a network service, or a roadmap writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import importlib.util
import os
import subprocess
import sys
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from cycle_state import _durable_sections, stub_key, write_mirror

CANDIDATE_DIR = Path("openspec/supervise/candidates")
CACHE_DIR = Path("openspec/supervise/rubric-cache")
DIGEST_PATH = Path("openspec/supervise/digest.json")
JOURNAL_PATH = Path("openspec/supervise/.digest-transaction.json")
MIRROR_PATH = Path("openspec/supervise/supervisor-record.json")
MAX_CANDIDATES = 20
MAX_MANIFEST_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = 2 * 1024
MAX_JOURNAL_BYTES = 1024 * 1024
MAX_JOURNAL_OPERATIONS = 2 * MAX_CANDIDATES + 2

_CHANGE_KEY = re.compile(
    r"^change:(?P<value>(?:add|update|remove|refactor)-[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
_PROV_KEY = re.compile(r"^prov:(?P<value>[0-9a-f]{32})$")
_ROADMAP_REF = re.compile(r"^[a-z0-9-]+:ri-[0-9]{2,}$")


class CandidateCapacityError(ValueError):
    """Raised when a store union would exceed the bounded scoring backlog."""

    def __init__(self, unpersisted_keys: Sequence[str]) -> None:
        self.unpersisted_keys = sorted(unpersisted_keys)
        super().__init__(
            "candidate capacity exceeded; unpersisted=" + ",".join(self.unpersisted_keys)
        )


class OversizedManifestError(ValueError):
    """Raised before dispatch when the canonical prompt manifest exceeds 64 KiB."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        super().__init__(marker)


def _load_sanitizer():
    name = "supervise_roadmap_sanitizer"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parents[2] / "roadmap-runtime/scripts/sanitizer.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_sanitize_string = _load_sanitizer().sanitize_string


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("as_of must be an RFC3339 date-time with a timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError("as_of must be an RFC3339 date-time with a timezone")
    return parsed


def _recover_then_require_rehydrate(repo_root: Path) -> None:
    recover_transaction(repo_root)
    raise ValueError("recovered pending digest transaction; rehydrate and retry")


def _literal_pathspec(source: str) -> str:
    return f":(literal){source}"


def encode_stub_key(key: str) -> str:
    """Encode a validated canonical stub key for safe filename construction."""
    change = _CHANGE_KEY.fullmatch(key)
    if change:
        return f"change--{change.group('value')}"
    provenance = _PROV_KEY.fullmatch(key)
    if provenance:
        return f"prov--{provenance.group('value')}"
    raise ValueError(f"not a canonical stub key: {key!r}")


def decode_stub_key(filename_key: str) -> str:
    """Reverse :func:`encode_stub_key`, rejecting non-canonical spellings."""
    if filename_key.startswith("change--"):
        candidate = "change:" + filename_key.removeprefix("change--")
    elif filename_key.startswith("prov--"):
        candidate = "prov:" + filename_key.removeprefix("prov--")
    else:
        raise ValueError(f"not an encoded canonical stub key: {filename_key!r}")
    if encode_stub_key(candidate) != filename_key:
        raise ValueError(f"not an encoded canonical stub key: {filename_key!r}")
    return candidate


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _schema(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / "openspec" / "schemas" / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load schema {path}: {exc}") from exc


def _validate(repo_root: Path, name: str, value: Any) -> None:
    Draft202012Validator(_schema(repo_root, name), format_checker=FormatChecker()).validate(value)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _candidate_path(repo_root: Path, key: str) -> Path:
    return repo_root / CANDIDATE_DIR / f"{encode_stub_key(key)}.json"


def _cache_path(repo_root: Path, key: str) -> Path:
    return repo_root / CACHE_DIR / f"{encode_stub_key(key)}.rubric.json"


def _stored_candidates(repo_root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    directory = repo_root / CANDIDATE_DIR
    if not directory.is_dir():
        return {}
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe candidate file: {path}")
        key = decode_stub_key(path.stem)
        try:
            stub = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"invalid candidate file {path}: {exc}") from exc
        _validate(repo_root, "candidate-work.schema.json", stub)
        if stub_key(stub) != key:
            raise ValueError(f"candidate filename/key mismatch: {path}")
        result[key] = (path, stub)
    return result


def _decision_index(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(record, dict):
        return {}
    back_edge = record.get("back_edge")
    entries = back_edge.get("digested_stubs") if isinstance(back_edge, dict) else None
    if not isinstance(entries, list):
        return {}
    return {
        entry["stub_key"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("stub_key"), str)
    }


@dataclass(frozen=True)
class _Maintenance:
    decisions: dict[str, dict[str, Any]]
    pruned: tuple[str, ...]
    woken: tuple[str, ...]


def _maintenance(
    stored: dict[str, tuple[Path, dict[str, Any]]],
    record: dict[str, Any] | None,
    *,
    as_of: str,
) -> _Maintenance:
    current = _parse_time(as_of)
    decisions = _decision_index(record)
    pruned: list[str] = []
    woken: list[str] = []
    for key in sorted(stored):
        entry = decisions.get(key)
        if not entry:
            continue
        decision = entry.get("decision")
        if decision in {"approved", "rejected"}:
            pruned.append(key)
        elif decision == "deferred":
            until = entry.get("until")
            try:
                due = datetime.fromisoformat(until).date() <= current.date()
            except (TypeError, ValueError):
                due = False
            if due:
                updated = dict(entry)
                updated["decision"] = "pending"
                updated.pop("until", None)
                decisions[key] = updated
                woken.append(key)
    return _Maintenance(decisions, tuple(pruned), tuple(woken))


def store_candidates(
    repo_root: Path,
    fresh_stubs: Iterable[dict[str, Any]],
    *,
    record: dict[str, Any] | None,
    as_of: str,
    prune_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Maintain and atomically admit one bounded fresh candidate set.

    Lifecycle pruning is committed before fresh capacity is evaluated. This lets a
    terminal decision free capacity immediately and makes that maintained baseline
    survive a later overflow failure.
    """
    del force
    root = Path(repo_root).resolve()
    pending_recovery = (root / JOURNAL_PATH).is_file()
    if pending_recovery:
        if dry_run:
            raise ValueError("pending digest transaction recovery")
        _recover_then_require_rehydrate(root)
    stored = _stored_candidates(root)
    maintenance = _maintenance(stored, record, as_of=as_of)

    rebuilt_digest = _lifecycle_rebuild(
        root, stored, maintenance, record=record, as_of=as_of, dry_run=dry_run
    )
    for key in maintenance.pruned:
        del stored[key]

    fresh_by_key: dict[str, dict[str, Any]] = {}
    if not prune_only:
        for stub in fresh_stubs:
            _validate(root, "candidate-work.schema.json", stub)
            key = stub_key(stub)
            encode_stub_key(key)
            prior_fresh = fresh_by_key.get(key)
            if prior_fresh is not None and _canonical_bytes(prior_fresh) != _canonical_bytes(stub):
                raise ValueError(f"conflicting fresh candidates for {key}")
            fresh_by_key[key] = stub
    terminal_readmissions = sorted(
        key
        for key in fresh_by_key
        if maintenance.decisions.get(key, {}).get("decision") in {"approved", "rejected"}
    )
    if terminal_readmissions:
        raise ValueError(
            "terminal decision already exists for " + ",".join(terminal_readmissions)
        )

    retained_keys = sorted(stored)
    new_keys = sorted(key for key in fresh_by_key if key not in stored)
    updated_keys = sorted(
        key
        for key in fresh_by_key
        if key in stored and _canonical_bytes(fresh_by_key[key]) != _canonical_bytes(stored[key][1])
    )
    if len(retained_keys) + len(new_keys) > MAX_CANDIDATES:
        raise CandidateCapacityError(new_keys)

    written: list[dict[str, str]] = []
    if not dry_run:
        operations: list[dict[str, Any]] = []
        for key in [*new_keys, *updated_keys]:
            path = _candidate_path(root, key)
            operations.append(
                {
                    "op": "replace",
                    "target": path.relative_to(root).as_posix(),
                    "bytes": _canonical_bytes(fresh_by_key[key]).decode("utf-8"),
                }
            )
            if key in updated_keys:
                operations.append(
                    {
                        "op": "delete",
                        "target": _cache_path(root, key).relative_to(root).as_posix(),
                    }
                )
            written.append({"stub_key": key, "path": path.relative_to(root).as_posix()})
        if operations:
            publish_transaction(root, operations)

    return {
        "stored": written,
        "retained_keys": retained_keys,
        "fresh_keys": sorted([*new_keys, *updated_keys]),
        "pruned_keys": list(maintenance.pruned),
        "woken_keys": list(maintenance.woken),
        "lifecycle_changed": bool(maintenance.pruned or maintenance.woken or rebuilt_digest),
        "pending_recovery": pending_recovery,
        "dry_run": dry_run,
        "rebuilt_digest": rebuilt_digest,
    }


def _safe_target(repo_root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe transaction target: {relative}")
    target = repo_root / candidate
    current = repo_root
    for part in candidate.parent.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"transaction target contains symlink: {relative}")
    if not target.resolve(strict=False).is_relative_to(repo_root):
        raise ValueError(f"transaction target escapes repository: {relative}")
    return target


def _authorize_transaction_target(operation: str, relative: str) -> None:
    """Restrict recovery to artifacts owned by the candidate-digest runtime."""
    candidate = Path(relative)
    allowed = False
    if candidate == DIGEST_PATH or candidate == MIRROR_PATH:
        allowed = operation == "replace"
    elif candidate.parent == CANDIDATE_DIR and candidate.suffix == ".json":
        try:
            decode_stub_key(candidate.stem)
        except ValueError:
            pass
        else:
            allowed = operation in {"replace", "delete"}
    elif candidate.parent == CACHE_DIR and candidate.name.endswith(".rubric.json"):
        encoded_key = candidate.name.removesuffix(".rubric.json")
        try:
            decode_stub_key(encoded_key)
        except ValueError:
            pass
        else:
            allowed = operation in {"replace", "delete"}
    if not allowed:
        raise ValueError(f"unauthorized digest transaction target: {operation} {relative}")


def publish_transaction(
    repo_root: Path,
    operations: Sequence[dict[str, Any]],
    *,
    apply: bool = True,
) -> None:
    """Durably journal replacements/deletes and optionally roll them forward."""
    root = Path(repo_root).resolve()
    if len(operations) > MAX_JOURNAL_OPERATIONS:
        raise ValueError("too many digest transaction operations")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in operations:
        op = raw.get("op")
        target = raw.get("target")
        if op not in {"replace", "delete"} or not isinstance(target, str):
            raise ValueError("invalid digest transaction operation")
        _safe_target(root, target)
        _authorize_transaction_target(op, target)
        if target in seen:
            raise ValueError(f"duplicate transaction target: {target}")
        seen.add(target)
        item: dict[str, Any] = {"op": op, "target": target}
        if op == "replace":
            content = raw.get("bytes")
            if not isinstance(content, str):
                raise ValueError(f"replacement bytes must be UTF-8 text: {target}")
            item["bytes"] = content
            item["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        normalized.append(item)
    normalized.sort(key=lambda item: (item["target"] == DIGEST_PATH.as_posix(), item["target"]))
    journal = {"schema_version": 1, "operations": normalized}
    journal_bytes = _canonical_bytes(journal)
    if len(journal_bytes) > MAX_JOURNAL_BYTES:
        raise ValueError("digest transaction journal exceeds size limit")
    path = root / JOURNAL_PATH
    _atomic_write(path, journal_bytes)
    if apply:
        recover_transaction(root)


def recover_transaction(repo_root: Path) -> bool:
    """Idempotently roll a durable publication journal forward, digest last."""
    root = Path(repo_root).resolve()
    path = root / JOURNAL_PATH
    if not path.is_file():
        return False
    if path.stat().st_size > MAX_JOURNAL_BYTES:
        raise ValueError("digest transaction journal exceeds size limit")
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid digest transaction journal: {exc}") from exc
    if journal.get("schema_version") != 1:
        raise ValueError("invalid digest transaction schema version")
    operations = journal.get("operations")
    if not isinstance(operations, list):
        raise ValueError("invalid digest transaction operations")
    if len(operations) > MAX_JOURNAL_OPERATIONS:
        raise ValueError("too many digest transaction operations")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in operations:
        if not isinstance(item, dict):
            raise ValueError("invalid digest transaction operation")
        op = item.get("op")
        target_value = item.get("target")
        if op not in {"replace", "delete"} or not isinstance(target_value, str):
            raise ValueError("invalid digest transaction operation")
        _safe_target(root, target_value)
        _authorize_transaction_target(op, target_value)
        if target_value in seen:
            raise ValueError(f"duplicate transaction target: {target_value}")
        seen.add(target_value)
        if op == "replace":
            content = item.get("bytes")
            checksum = item.get("sha256")
            if not isinstance(content, str) or not isinstance(checksum, str):
                raise ValueError(f"invalid replacement operation: {target_value}")
            if hashlib.sha256(content.encode("utf-8")).hexdigest() != checksum:
                raise ValueError(f"replacement checksum mismatch: {target_value}")
        validated.append(item)
    ordered = sorted(
        validated,
        key=lambda item: (
            item.get("target") == DIGEST_PATH.as_posix(),
            str(item.get("target")),
        ),
    )
    for item in ordered:
        op = item["op"]
        target_value = item["target"]
        target = _safe_target(root, target_value)
        target.parent.mkdir(parents=True, exist_ok=True)
        if op == "delete":
            target.unlink(missing_ok=True)
            _fsync_directory(target.parent)
            continue
        content = item["bytes"]
        checksum = item["sha256"]
        encoded = content.encode("utf-8")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            _atomic_write(target, encoded)
        _fsync_directory(target.parent)
    path.unlink()
    _fsync_directory(path.parent)
    return True


_WEIGHTS = {
    "relevance": 3,
    "value": 3,
    "readiness": 2,
    "scope_fit": 1,
    "risk": 1,
    "staleness_penalty_per_30d": 1,
    "staleness_penalty_cap": 5,
    "risk_higher_is_safer": True,
    "decision_bucket_order": ["pending", "future_deferred"],
    "dependency_bucket_order": ["ready", "blocked"],
    "tie_breaker": "stub_key:asc",
}


def _validate_score_join(
    repo_root: Path, manifest: dict[str, Any], scores: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    fingerprint = manifest.get("fingerprint")
    if scores.get("fingerprint") != fingerprint:
        raise ValueError("score fingerprint does not match manifest fingerprint")
    as_of = manifest.get("as_of")
    if scores.get("scored_at") != as_of:
        raise ValueError("scored_at must exactly match manifest as_of")
    _parse_time(as_of)
    requested = manifest.get("requested_keys")
    if not isinstance(requested, list) or len(set(requested)) != len(requested):
        raise ValueError("manifest requested_keys must be unique")
    score_rows = scores.get("scores")
    if not isinstance(score_rows, list):
        raise ValueError("scores must be an array")
    actual = [row.get("stub_key") for row in score_rows if isinstance(row, dict)]
    duplicates = sorted({key for key in actual if actual.count(key) > 1})
    missing = sorted(set(requested) - set(actual))
    unknown = sorted(set(actual) - set(requested))
    defects: list[str] = []
    if duplicates:
        defects.append("duplicate=" + ",".join(duplicates))
    if missing:
        defects.append("missing=" + ",".join(missing))
    if unknown:
        defects.append("unknown=" + ",".join(unknown))
    if defects:
        raise ValueError("; ".join(defects))
    _validate(repo_root, "supervise-rubric-score.schema.json", scores)
    return {row["stub_key"]: row for row in score_rows}


def _merge_terminal_history(
    record: dict[str, Any] | None, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    active_keys = {entry["stub_key"] for entry in entries}
    terminal = [
        dict(entry)
        for key, entry in sorted(_decision_index(record).items())
        if key not in active_keys and entry.get("decision") in {"approved", "rejected"}
    ]
    return [*entries, *terminal]


def _mirror_document(
    repo_root: Path,
    record: dict[str, Any] | None,
    entries: list[dict[str, Any]],
    *,
    as_of: str,
    fingerprint: str,
) -> dict[str, Any]:
    current = _parse_time(as_of)
    entries = _merge_terminal_history(record, entries)
    source = dict(record or {})
    back_edge = dict(source.get("back_edge") or {})
    back_edge.update(
        {
            "last_digest_at": as_of,
            "last_fingerprint": fingerprint,
            "digested_stubs": entries,
        }
    )
    source["back_edge"] = back_edge
    durable = _durable_sections(source, now=current)
    mirror = {"schema_version": 1, "written_at": as_of, **durable}
    _validate(repo_root, "supervisor-record-mirror.schema.json", mirror)
    return mirror


def _validate_manifest_current_store(
    repo_root: Path, manifest: dict[str, Any], by_candidate: dict[str, dict[str, Any]], *, dry_run: bool
) -> None:
    if dry_run:
        return
    stored = _stored_candidates(repo_root)
    requested = set(manifest["requested_keys"])
    if set(stored) != requested:
        raise ValueError("manifest candidate keys do not match current store")
    for key, candidate in by_candidate.items():
        stub = candidate.get("stub")
        if not isinstance(stub, dict):
            raise ValueError(f"invalid manifest candidate: {key}")
        if _canonical_bytes(stored[key][1]) != _canonical_bytes(stub):
            raise ValueError(f"manifest candidate does not match current store for {key}")


def _prior_digest_reuse_probe(
    repo_root: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    prior = _load_prior_digest(repo_root)
    if prior is None:
        return None, "prior digest unavailable"
    if prior.get("fingerprint") != manifest.get("fingerprint"):
        return None, "prior digest fingerprint mismatch"
    requested = set(manifest.get("requested_keys") or [])
    prior_keys = {item["stub_key"] for item in prior.get("ranked", [])}
    if prior_keys != requested:
        return None, "prior digest key composition mismatch"
    generated_at = prior["generated_at"]
    for key in sorted(requested):
        path = _cache_path(repo_root, key)
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
            _validate(repo_root, "supervise-rubric-score.schema.json", cache)
        except (OSError, ValueError, ValidationError):
            return None, f"missing valid cache for {key}"
        if (
            cache.get("fingerprint") != manifest.get("fingerprint")
            or cache.get("scored_at") != generated_at
            or len(cache["scores"]) != 1
            or cache["scores"][0].get("stub_key") != key
        ):
            return None, f"cache identity mismatch for {key}"
    return prior, None


def _valid_prior_digest_for_reuse(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    prior, _ = _prior_digest_reuse_probe(repo_root, manifest)
    return prior


def _reuse_unavailable(reason: str | None, requested: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "reuse_available": False,
        "reason": reason or "reuse unavailable",
        "requested_keys": sorted(requested),
    }


def _publish_empty_digest(
    repo_root: Path, manifest: dict[str, Any], record: dict[str, Any] | None, *, dry_run: bool
) -> dict[str, Any]:
    digest = {
        "schema_version": 1,
        "fingerprint": manifest["fingerprint"],
        "generated_at": manifest["as_of"],
        "state_updated_at": manifest["as_of"],
        "weights": dict(_WEIGHTS),
        "sections": {"needs_decision": [], "new_this_cycle": [], "degraded": []},
        "ranked": [],
    }
    _validate(repo_root, "supervise-digest.schema.json", digest)
    mirror = _mirror_document(
        repo_root, record, [], as_of=manifest["as_of"], fingerprint=manifest["fingerprint"]
    )
    operations = [
        {
            "op": "replace",
            "target": "openspec/supervise/supervisor-record.json",
            "bytes": _canonical_bytes(mirror).decode("utf-8"),
        },
        {
            "op": "replace",
            "target": DIGEST_PATH.as_posix(),
            "bytes": _canonical_bytes(digest).decode("utf-8"),
        },
    ]
    if not dry_run:
        publish_transaction(repo_root, operations)
    return digest


def rank_candidates(
    repo_root: Path,
    manifest: dict[str, Any],
    scores: dict[str, Any] | None,
    *,
    record: dict[str, Any] | None,
    fresh_keys: Iterable[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate a complete rubric result, deterministically rank, and publish."""
    root = Path(repo_root).resolve()
    if (root / JOURNAL_PATH).is_file():
        if dry_run:
            raise ValueError("pending digest transaction recovery")
        _recover_then_require_rehydrate(root)
    _parse_time(manifest.get("as_of"))
    requested = manifest.get("requested_keys")
    if not isinstance(requested, list) or len(set(requested)) != len(requested):
        raise ValueError("manifest requested_keys must be unique")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("manifest candidates must be an array")
    by_candidate = {
        row["stub_key"]: row
        for row in candidates
        if isinstance(row, dict) and isinstance(row.get("stub_key"), str)
    }
    if set(by_candidate) != set(requested) or len(by_candidate) != len(requested):
        raise ValueError("manifest candidate keys do not exactly match requested_keys")
    _validate_manifest_current_store(root, manifest, by_candidate, dry_run=dry_run)

    if scores is None:
        reused, reuse_reason = _prior_digest_reuse_probe(root, manifest)
        if reused is not None:
            return reused
        if not requested:
            return _publish_empty_digest(root, manifest, record, dry_run=dry_run)
        return _reuse_unavailable(reuse_reason, requested)
    by_score = _validate_score_join(root, manifest, scores)

    manifest_stored = {
        key: (Path(), candidate["stub"])
        for key, candidate in by_candidate.items()
        if isinstance(candidate.get("stub"), dict)
    }
    prior = _maintenance(manifest_stored, record, as_of=manifest["as_of"]).decisions
    ranked: list[dict[str, Any]] = []
    degraded: set[str] = set()
    for key in requested:
        candidate = by_candidate[key]
        stub = candidate.get("stub")
        signals = candidate.get("signals")
        if not isinstance(stub, dict) or not isinstance(signals, dict):
            raise ValueError(f"invalid manifest candidate: {key}")
        _validate(root, "candidate-work.schema.json", stub)
        decision = prior.get(key, {}).get("decision", "pending")
        if decision == "rejected":
            continue
        score_row = by_score[key]
        factors = {
            factor: score_row[factor]["score"]
            for factor in ("relevance", "value", "readiness", "scope_fit", "risk")
        }
        justifications = {factor: score_row[factor]["justification"] for factor in factors}
        staleness = signals.get("staleness_days")
        penalty = min(staleness // 30, 5) if isinstance(staleness, int) else 0
        total = (
            3 * factors["relevance"]
            + 3 * factors["value"]
            + 2 * factors["readiness"]
            + factors["scope_fit"]
            + factors["risk"]
            - penalty
        )
        provenance = dict(stub["provenance"])
        provenance.setdefault("generator", None)
        output_signals = {
            "dependency_ready": bool(signals.get("dependency_ready")),
            "staleness_days": staleness if isinstance(staleness, int) else None,
            "prior_decision": decision
            if decision in {"approved", "deferred", "rejected"}
            else None,
            "deferred_until": prior.get(key, {}).get("until"),
        }
        ranked.append(
            {
                "stub_key": key,
                "rank": 0,
                "score": total,
                "decision": decision,
                "suggested_change_id": stub.get("suggested_change_id"),
                "title": stub["title"],
                "effort": stub["effort"],
                "factors": factors,
                "justifications": justifications,
                "signals": output_signals,
                "provenance": provenance,
            }
        )
        for marker in candidate.get("degraded") or []:
            if isinstance(marker, str):
                degraded.add(marker)
    ranked.sort(
        key=lambda item: (
            item["decision"] == "deferred" and item["signals"]["deferred_until"] is not None,
            not item["signals"]["dependency_ready"],
            -item["score"],
            item["stub_key"],
        )
    )
    fresh = set(fresh_keys)
    for index, item in enumerate(ranked, 1):
        item["rank"] = index
    digest = {
        "schema_version": 1,
        "fingerprint": manifest["fingerprint"],
        "generated_at": manifest["as_of"],
        "state_updated_at": manifest["as_of"],
        "weights": dict(_WEIGHTS),
        "sections": {
            "needs_decision": [
                item["stub_key"] for item in ranked if item["stub_key"] not in fresh
            ],
            "new_this_cycle": [item["stub_key"] for item in ranked if item["stub_key"] in fresh],
            "degraded": sorted(degraded),
        },
        "ranked": ranked,
    }
    _validate(root, "supervise-digest.schema.json", digest)

    entries: list[dict[str, Any]] = []
    for item in ranked:
        old = prior.get(item["stub_key"], {})
        entry = {
            "stub_key": item["stub_key"],
            "rank": item["rank"],
            "decision": item["decision"],
            "decided_at": old.get("decided_at", manifest["as_of"]),
        }
        if item["suggested_change_id"] is not None:
            entry["suggested_change_id"] = item["suggested_change_id"]
        for field in ("roadmap_ref", "route", "until", "reason"):
            if field in old:
                entry[field] = old[field]
        entries.append(entry)
    mirror = _mirror_document(
        root,
        record,
        entries,
        as_of=manifest["as_of"],
        fingerprint=manifest["fingerprint"],
    )
    operations: list[dict[str, Any]] = []
    for key in sorted(by_score):
        singleton = {field: value for field, value in scores.items() if field != "scores"}
        singleton["scores"] = [by_score[key]]
        _validate(root, "supervise-rubric-score.schema.json", singleton)
        operations.append(
            {
                "op": "replace",
                "target": _cache_path(root, key).relative_to(root).as_posix(),
                "bytes": _canonical_bytes(singleton).decode("utf-8"),
            }
        )
    operations.extend(
        [
            {
                "op": "replace",
                "target": "openspec/supervise/supervisor-record.json",
                "bytes": _canonical_bytes(mirror).decode("utf-8"),
            },
            {
                "op": "replace",
                "target": DIGEST_PATH.as_posix(),
                "bytes": _canonical_bytes(digest).decode("utf-8"),
            },
        ]
    )
    if not dry_run:
        publish_transaction(root, operations)
    return digest

def _git_output(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _artifact_evidence(
    repo_root: Path, source: str, *, as_of: datetime
) -> tuple[str | None, int | None, list[str]]:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", source):
        return None, None, [f"evidence_uri:{source}"]
    relative = Path(source)
    if relative.is_absolute() or ".." in relative.parts:
        return None, None, [f"evidence_traversal:{source}"]
    candidate = repo_root / relative
    current = repo_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, None, [f"evidence_symlink:{source}"]
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, None, [f"evidence_missing:{source}"]
    if not resolved.is_relative_to(repo_root) or not resolved.is_file():
        return None, None, [f"evidence_traversal:{source}"]
    literal = _literal_pathspec(source)
    tracked = _git_output(repo_root, ["ls-files", "--error-unmatch", "--", literal])
    if tracked.returncode != 0:
        return None, None, [f"evidence_untracked:{source}"]
    modified = _git_output(repo_root, ["diff", "--quiet", "HEAD", "--", literal])
    if modified.returncode != 0:
        return None, None, [f"evidence_modified:{source}"]
    with candidate.open("rb") as handle:
        raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    if b"\x00" in raw:
        return None, None, [f"evidence_binary:{source}"]
    try:
        excerpt = raw[:MAX_EVIDENCE_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return None, None, [f"evidence_binary:{source}"]
    committed = _git_output(repo_root, ["log", "-1", "--format=%cI", "--", literal])
    if committed.returncode != 0 or not committed.stdout.strip():
        return None, None, [f"evidence_untracked:{source}"]
    source_time = _parse_time(committed.stdout.strip())
    source_utc = source_time.astimezone(timezone.utc)
    as_of_utc = as_of.astimezone(timezone.utc)
    if source_utc > as_of_utc:
        return None, None, [f"clock_skew:{source}"]
    staleness = max(0, (as_of_utc.date() - source_utc.date()).days)
    sanitized = _sanitize_string(excerpt)
    framed = (
        f"--- BEGIN UNTRUSTED PROVENANCE {source} ---\n"
        f"{sanitized}\n"
        f"--- END UNTRUSTED PROVENANCE {source} ---"
    )
    return framed, staleness, []


def _manifest_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")


def _manifest_size(value: dict[str, Any]) -> int:
    return len(_manifest_bytes(value))


def prepare_batch(
    repo_root: Path,
    *,
    fingerprint: str,
    as_of: str,
    record: dict[str, Any] | None,
    fresh_stubs: Iterable[dict[str, Any]] = (),
    ready_set: Any = None,
) -> dict[str, Any]:
    """Build one deterministic, bounded, read-only rubric prompt manifest."""
    root = Path(repo_root).resolve()
    if (root / JOURNAL_PATH).is_file():
        raise ValueError("pending digest transaction recovery")
    current = _parse_time(as_of)
    stored = _stored_candidates(root)
    for stub in fresh_stubs:
        _validate(root, "candidate-work.schema.json", stub)
        key = stub_key(stub)
        encode_stub_key(key)
        stored[key] = (_candidate_path(root, key), stub)
    if len(stored) > MAX_CANDIDATES:
        raise CandidateCapacityError(sorted(stored)[MAX_CANDIDATES:])
    decisions = _maintenance(stored, record, as_of=as_of).decisions
    status_index = build_status_index(root)
    candidates: list[dict[str, Any]] = []
    for key, (_, stub) in sorted(stored.items()):
        decision = decisions.get(key, {})
        if decision.get("decision") in {"approved", "rejected"}:
            continue
        source = stub["provenance"]["source_artifact"]
        evidence, staleness, degraded = _artifact_evidence(root, source, as_of=current)
        dependencies = stub.get("depends_on") or []
        dependencies_ready = all(status_index.resolve(dep).completed for dep in dependencies)
        candidates.append(
            {
                "stub_key": key,
                "stub": stub,
                "signals": {
                    "dependency_ready": dependencies_ready,
                    "staleness_days": staleness,
                    "prior_decision": (
                        decision.get("decision")
                        if decision.get("decision") in {"approved", "deferred", "rejected"}
                        else None
                    ),
                    "deferred_until": decision.get("until"),
                },
                "evidence": evidence,
                "degraded": degraded,
            }
        )
    manifest = {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "as_of": as_of,
        "requested_keys": [candidate["stub_key"] for candidate in candidates],
        "candidates": candidates,
        "ready_set": ready_set if ready_set is not None else [],
    }
    if _manifest_size(manifest) > MAX_MANIFEST_BYTES:
        if len(candidates) == 1:
            raise OversizedManifestError(f"oversized:{candidates[0]['stub_key']}")
        for candidate in candidates:
            singleton = {
                **manifest,
                "requested_keys": [candidate["stub_key"]],
                "candidates": [candidate],
            }
            if _manifest_size(singleton) > MAX_MANIFEST_BYTES:
                raise OversizedManifestError(f"oversized:{candidate['stub_key']}")
        raise OversizedManifestError("oversized:batch")
    return manifest


@dataclass(frozen=True)
class DependencyStatus:
    reference: str
    status: str
    roadmap_id: str | None = None
    item_id: str | None = None
    change_id: str | None = None
    archived: bool = False

    @property
    def completed(self) -> bool:
        return self.status == "completed"


@dataclass(frozen=True)
class StatusIndex:
    by_reference: dict[str, DependencyStatus]
    by_change: dict[str, DependencyStatus]

    def resolve(self, dependency: str) -> DependencyStatus:
        change_key = _CHANGE_KEY.fullmatch(dependency)
        normalized = change_key.group("value") if change_key else dependency
        return (
            self.by_reference.get(dependency)
            or self.by_change.get(normalized)
            or DependencyStatus(dependency, "unresolved")
        )


def _archived_change_id(directory_name: str) -> str:
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}-(.+)", directory_name)
    return match.group(1) if match else directory_name


def build_status_index(repo_root: Path) -> StatusIndex:
    """Build the strict all-status index used for ranking and approval routing."""
    root = Path(repo_root).resolve()
    by_reference: dict[str, DependencyStatus] = {}
    by_change: dict[str, DependencyStatus] = {}
    roadmaps = root / "openspec/roadmaps"
    if roadmaps.is_dir():
        for path in sorted(roadmaps.glob("*/roadmap.yaml")):
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                raise ValueError(f"cannot index roadmap {path}: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ValueError(f"malformed roadmap: {path}")
            roadmap_id = payload.get("roadmap_id")
            if not isinstance(roadmap_id, str):
                raise ValueError(f"malformed roadmap id: {path}")
            for item in payload["items"]:
                if not isinstance(item, dict):
                    raise ValueError(f"malformed roadmap item: {path}")
                item_id = item.get("item_id")
                status = item.get("status")
                if not isinstance(item_id, str) or not isinstance(status, str):
                    raise ValueError(f"malformed roadmap item: {path}")
                change_id = (
                    item.get("change_id") if isinstance(item.get("change_id"), str) else None
                )
                ref = f"{roadmap_id}:{item_id}"
                resolved = DependencyStatus(ref, status, roadmap_id, item_id, change_id)
                by_reference[ref] = resolved
                if change_id:
                    if change_id in by_change:
                        raise ValueError(f"ambiguous dependency change id: {change_id}")
                    by_change[change_id] = resolved
    changes = root / "openspec/changes"
    if changes.is_dir():
        for directory in sorted(path for path in changes.iterdir() if path.is_dir()):
            if directory.name == "archive":
                continue
            by_change.setdefault(
                directory.name,
                DependencyStatus(directory.name, "pending-stub", change_id=directory.name),
            )
    archive = root / "openspec/changes/archive"
    if archive.is_dir():
        for directory in sorted(path for path in archive.iterdir() if path.is_dir()):
            change_id = _archived_change_id(directory.name)
            tasks = directory / "tasks.md"
            if not tasks.is_file():
                continue
            text = tasks.read_text(encoding="utf-8")
            status = "completed" if not re.search(r"^\s*- \[ \]", text, re.MULTILINE) else "pending"
            by_change.setdefault(
                change_id,
                DependencyStatus(change_id, status, change_id=change_id, archived=True),
            )
    return StatusIndex(by_reference, by_change)


def _roadmap_payload(repo_root: Path, roadmap_id: str) -> tuple[Path, dict[str, Any]]:
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", roadmap_id) is None:
        raise ValueError(f"invalid roadmap id: {roadmap_id}")
    path = repo_root / "openspec/roadmaps" / roadmap_id / "roadmap.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load roadmap {roadmap_id}: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("roadmap_id") != roadmap_id
        or not isinstance(payload.get("items"), list)
    ):
        raise ValueError(f"malformed roadmap: {roadmap_id}")
    return path, payload


def stub_to_request(
    repo_root: Path,
    key: str,
    *,
    roadmap_id: str,
    acceptance: Sequence[str],
    after: str | None = None,
) -> dict[str, Any]:
    """Render one pure refiner add request; never write a roadmap."""
    root = Path(repo_root).resolve()
    if (root / JOURNAL_PATH).is_file():
        raise ValueError("pending digest transaction recovery")
    encode_stub_key(key)
    outcomes = [value.strip() for value in acceptance if isinstance(value, str) and value.strip()]
    if len(outcomes) != len(acceptance) or not outcomes:
        raise ValueError("refine-roadmap requires at least one acceptance outcome")
    _, roadmap = _roadmap_payload(root, roadmap_id)
    stored = _stored_candidates(root)
    if key not in stored:
        raise ValueError(f"unknown stored stub: {key}")
    stub = stored[key][1]
    index = build_status_index(root)
    change_id = stub["suggested_change_id"]
    if index.resolve(change_id).status != "unresolved":
        raise ValueError(f"change-ID collision: {change_id}")

    item_numbers = []
    item_ids: set[str] = set()
    for item in roadmap["items"]:
        item_id = item.get("item_id") if isinstance(item, dict) else None
        if not isinstance(item_id, str):
            raise ValueError(f"malformed roadmap item in {roadmap_id}")
        item_ids.add(item_id)
        match = re.fullmatch(r"ri-(\d+)", item_id)
        if match:
            item_numbers.append(int(match.group(1)))
    if after is not None and after not in item_ids:
        raise ValueError(f"unknown --after item: {after}")
    next_id = f"ri-{max(item_numbers, default=0) + 1:02d}"
    local: list[str] = []
    external: list[str] = []
    for dependency in stub.get("depends_on") or []:
        resolved = index.resolve(dependency)
        if resolved.status == "unresolved":
            raise ValueError(f"unresolved dependency: {dependency}")
        if resolved.archived and resolved.completed:
            continue
        if resolved.roadmap_id == roadmap_id and resolved.item_id:
            local.append(resolved.item_id)
        elif resolved.roadmap_id and resolved.item_id:
            external.append(f"{resolved.roadmap_id}:{resolved.item_id}")
        else:
            raise ValueError(f"unresolved dependency: {dependency}")
    provenance = stub["provenance"]
    finding_ids = ", ".join(provenance["finding_ids"])
    item = {
        "item_id": next_id,
        "title": stub["title"],
        "description": (
            f"{stub['description']}\n\nProvenance: {provenance['source_artifact']} ({finding_ids})"
        ),
        "rationale": stub["rationale"],
        "effort": stub["effort"],
        "priority": stub["priority"],
        "status": "approved",
        "change_id": change_id,
        "depends_on": sorted(set(local)),
        "external_depends_on": sorted(set(external)),
        "acceptance_outcomes": outcomes,
    }
    operation: dict[str, Any] = {"op": "add", "item": item}
    if after is not None:
        operation["after"] = after
    return {
        "rationale": stub["rationale"],
        "actor": "supervise",
        "source": f"candidate-digest:{key}",
        "operations": [operation],
    }


def decide(
    repo_root: Path,
    key: str,
    *,
    decision: str,
    record: dict[str, Any],
    as_of: str,
    roadmap_ref: str | None = None,
    route: str | None = None,
    until: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Replace one digested-stub decision in the rehydrated durable record."""
    root = Path(repo_root).resolve()
    if (root / JOURNAL_PATH).is_file():
        _recover_then_require_rehydrate(root)
    encode_stub_key(key)
    _parse_time(as_of)
    if decision not in {"pending", "approved", "deferred", "rejected"}:
        raise ValueError(f"invalid decision: {decision}")
    if decision == "approved":
        if route not in {"refine-roadmap", "plan-roadmap"}:
            raise ValueError("approved decision requires route")
        if route == "refine-roadmap":
            if roadmap_ref is None:
                raise ValueError("refine-roadmap approval requires roadmap_ref")
            if not isinstance(roadmap_ref, str) or _ROADMAP_REF.fullmatch(roadmap_ref) is None:
                raise ValueError("malformed roadmap_ref: expected <roadmap-id>:ri-<nn>")
        if route == "plan-roadmap" and roadmap_ref is not None:
            raise ValueError("plan-roadmap approval requires null roadmap_ref")
    if decision == "rejected" and not (isinstance(reason, str) and reason.strip()):
        raise ValueError("rejected decision requires reason")
    if until is not None:
        try:
            date.fromisoformat(until)
        except (TypeError, ValueError) as exc:
            raise ValueError("until must be a calendar date") from exc

    source = dict(record)
    back_edge = dict(source.get("back_edge") or {})
    raw_entries = back_edge.get("digested_stubs")
    if not isinstance(raw_entries, list):
        raise ValueError("record has no digested stubs")
    entries = [dict(entry) for entry in raw_entries if isinstance(entry, dict)]
    matches = [index for index, entry in enumerate(entries) if entry.get("stub_key") == key]
    if len(matches) != 1:
        raise ValueError(f"unknown digested stub: {key}")
    selected = entries[matches[0]]
    for field in ("roadmap_ref", "route", "until", "reason"):
        selected.pop(field, None)
    selected.update({"decision": decision, "decided_at": as_of})
    if decision == "approved":
        selected.update({"route": route, "roadmap_ref": roadmap_ref})
    elif decision == "deferred" and until is not None:
        selected["until"] = until
    elif decision == "rejected":
        selected["reason"] = reason.strip()
    entries[matches[0]] = selected
    back_edge["digested_stubs"] = entries
    source["back_edge"] = back_edge
    return write_mirror(root, source, now=as_of)


def _load_prior_digest(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / DIGEST_PATH
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid prior digest: {exc}") from exc
    _validate(repo_root, "supervise-digest.schema.json", value)
    return value


def _decision_drift_keys(
    prior_digest: dict[str, Any] | None,
    remaining: set[str],
    maintenance: _Maintenance,
) -> tuple[str, ...]:
    if prior_digest is None:
        return ()
    drifted: list[str] = []
    prior_by_key = {
        item["stub_key"]: item
        for item in prior_digest.get("ranked", [])
        if isinstance(item, dict) and isinstance(item.get("stub_key"), str)
    }
    for key in sorted(remaining):
        prior = prior_by_key.get(key)
        if prior is None:
            drifted.append(key)
            continue
        source = maintenance.decisions.get(key) or {}
        decision = source.get("decision", "pending")
        if decision not in {"pending", "deferred"}:
            continue
        prior_until = None
        signals = prior.get("signals")
        if isinstance(signals, dict):
            prior_until = signals.get("deferred_until")
        expected_until = source.get("until") if decision == "deferred" else None
        if prior.get("decision") != decision or prior_until != expected_until:
            drifted.append(key)
    return tuple(drifted)


def _lifecycle_rebuild(
    repo_root: Path,
    stored: dict[str, tuple[Path, dict[str, Any]]],
    maintenance: _Maintenance,
    *,
    record: dict[str, Any] | None,
    as_of: str,
    dry_run: bool,
) -> dict[str, Any] | None:
    remaining = {key for key in stored if key not in maintenance.pruned}
    prior_digest = _load_prior_digest(repo_root)
    drifted = _decision_drift_keys(prior_digest, remaining, maintenance)
    if not (maintenance.pruned or maintenance.woken or drifted):
        return None
    operations: list[dict[str, Any]] = []
    for key in maintenance.pruned:
        operations.extend(
            [
                {
                    "op": "delete",
                    "target": _candidate_path(repo_root, key).relative_to(repo_root).as_posix(),
                },
                {
                    "op": "delete",
                    "target": _cache_path(repo_root, key).relative_to(repo_root).as_posix(),
                },
            ]
        )
    rebuilt: dict[str, Any] | None = None
    ranked: list[dict[str, Any]] = []
    if prior_digest is not None:
        generated_at = prior_digest["generated_at"]
        prior_ranked_keys = {item["stub_key"] for item in prior_digest["ranked"]}
        for key in sorted(remaining & prior_ranked_keys):
            cache_path = _cache_path(repo_root, key)
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"lifecycle rebuild requires cache for {key}: {exc}") from exc
            _validate(repo_root, "supervise-rubric-score.schema.json", cache)
            if (
                cache.get("fingerprint") != prior_digest["fingerprint"]
                or cache.get("scored_at") != generated_at
                or len(cache["scores"]) != 1
                or cache["scores"][0].get("stub_key") != key
            ):
                raise ValueError(f"lifecycle cache identity mismatch for {key}")
        for prior_item in prior_digest["ranked"]:
            key = prior_item["stub_key"]
            if key not in remaining:
                continue
            item = json.loads(json.dumps(prior_item))
            decision = maintenance.decisions.get(key, {}).get("decision", item["decision"])
            item["decision"] = decision
            item["signals"]["prior_decision"] = (
                decision if decision in {"approved", "deferred", "rejected"} else None
            )
            item["signals"]["deferred_until"] = maintenance.decisions.get(key, {}).get("until")
            ranked.append(item)
        ranked.sort(
            key=lambda item: (
                item["decision"] == "deferred" and item["signals"]["deferred_until"] is not None,
                not item["signals"]["dependency_ready"],
                -item["score"],
                item["stub_key"],
            )
        )
        for rank, item in enumerate(ranked, 1):
            item["rank"] = rank
        rebuilt = {
            **prior_digest,
            "state_updated_at": as_of,
            "sections": {
                "needs_decision": [item["stub_key"] for item in ranked],
                "new_this_cycle": [],
                "degraded": prior_digest["sections"]["degraded"],
            },
            "ranked": ranked,
        }
        _validate(repo_root, "supervise-digest.schema.json", rebuilt)
        operations.append(
            {
                "op": "replace",
                "target": DIGEST_PATH.as_posix(),
                "bytes": _canonical_bytes(rebuilt).decode("utf-8"),
            }
        )
    entries: list[dict[str, Any]] = []
    prior_entries = _decision_index(record)
    order = [item["stub_key"] for item in ranked]
    order.extend(key for key in sorted(remaining) if key not in set(order))
    for rank, key in enumerate(order, 1):
        source = dict(maintenance.decisions.get(key) or prior_entries.get(key) or {})
        entry = {
            "stub_key": key,
            "rank": rank,
            "decision": source.get("decision", "pending"),
            "decided_at": source.get("decided_at", as_of),
        }
        stub = stored[key][1]
        if stub.get("suggested_change_id") is not None:
            entry["suggested_change_id"] = stub["suggested_change_id"]
        for field in ("roadmap_ref", "route", "until", "reason"):
            if field in source:
                entry[field] = source[field]
        entries.append(entry)
    back_edge = record.get("back_edge") if isinstance(record, dict) else {}
    if not isinstance(back_edge, dict):
        back_edge = {}
    mirror = _mirror_document(
        repo_root,
        record,
        entries,
        as_of=as_of,
        fingerprint=(prior_digest or {}).get("fingerprint") or back_edge.get("last_fingerprint"),
    )
    operations.append(
        {
            "op": "replace",
            "target": "openspec/supervise/supervisor-record.json",
            "bytes": _canonical_bytes(mirror).decode("utf-8"),
        }
    )
    if not dry_run:
        publish_transaction(repo_root, operations)
    return rebuilt


def digest_document(repo_root: Path, *, fingerprint: str | None = None) -> dict[str, Any]:
    """Validate and return the prior candidate digest without mutating state."""
    root = Path(repo_root).resolve()
    if (root / JOURNAL_PATH).is_file():
        raise ValueError("pending digest transaction recovery")
    value = _load_prior_digest(root)
    if value is None:
        raise ValueError("candidate digest does not exist")
    if fingerprint is not None and value.get("fingerprint") != fingerprint:
        raise ValueError("prior digest fingerprint mismatch")
    return value


def _read_json(path: str | None, *, default: Any = None) -> Any:
    if path is None:
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    store = commands.add_parser("store")
    store.add_argument("--stubs")
    store.add_argument("--record")
    store.add_argument("--as-of", required=True)
    store.add_argument("--prune-only", action="store_true")
    store.add_argument("--dry-run", action="store_true")
    store.add_argument("--force", action="store_true")
    prepare = commands.add_parser("prepare-batch")
    prepare.add_argument("--fingerprint", required=True)
    prepare.add_argument("--record")
    prepare.add_argument("--stubs")
    prepare.add_argument("--ready-set")
    prepare.add_argument("--as-of", required=True)
    rank = commands.add_parser("rank")
    rank.add_argument("--manifest", required=True)
    rank.add_argument("--scores")
    rank.add_argument("--record")
    rank.add_argument("--fresh-key", action="append", default=[])
    rank.add_argument("--dry-run", action="store_true")
    show = commands.add_parser("digest")
    show.add_argument("--fingerprint")
    route_parser = commands.add_parser("stub-to-request")
    route_parser.add_argument("stub_key")
    route_parser.add_argument("--roadmap", required=True)
    route_parser.add_argument("--acceptance", action="append", required=True)
    route_parser.add_argument("--after")
    decision_parser = commands.add_parser("decide")
    decision_parser.add_argument("stub_key")
    decision_parser.add_argument(
        "--decision", choices=["pending", "approved", "deferred", "rejected"], required=True
    )
    decision_parser.add_argument("--record", required=True)
    decision_parser.add_argument("--as-of", required=True)
    decision_parser.add_argument("--roadmap-ref")
    decision_parser.add_argument("--route", choices=["refine-roadmap", "plan-roadmap"])
    decision_parser.add_argument("--until")
    decision_parser.add_argument("--reason")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.command == "store":
        raw = _read_json(args.stubs, default=[])
        stubs = raw.get("fresh", []) if isinstance(raw, dict) else raw
        result = store_candidates(
            root,
            stubs,
            record=_read_json(args.record),
            as_of=args.as_of,
            prune_only=args.prune_only,
            dry_run=args.dry_run,
            force=args.force,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "prepare-batch":
        raw = _read_json(args.stubs, default=[])
        stubs = raw.get("fresh", []) if isinstance(raw, dict) else raw
        print(
            json.dumps(
                prepare_batch(
                    root,
                    fingerprint=args.fingerprint,
                    as_of=args.as_of,
                    record=_read_json(args.record),
                    fresh_stubs=stubs,
                    ready_set=_read_json(args.ready_set, default=[]),
                ),
                sort_keys=True,
            )
        )
    elif args.command == "rank":
        result = rank_candidates(
            root,
            _read_json(args.manifest),
            _read_json(args.scores),
            record=_read_json(args.record),
            fresh_keys=args.fresh_key,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "digest":
        print(json.dumps(digest_document(root, fingerprint=args.fingerprint), sort_keys=True))
    elif args.command == "stub-to-request":
        request = stub_to_request(
            root,
            args.stub_key,
            roadmap_id=args.roadmap,
            acceptance=args.acceptance,
            after=args.after,
        )
        print(yaml.safe_dump(request, sort_keys=False), end="")
    elif args.command == "decide":
        result = decide(
            root,
            args.stub_key,
            decision=args.decision,
            record=_read_json(args.record),
            as_of=args.as_of,
            roadmap_ref=args.roadmap_ref,
            route=args.route,
            until=args.until,
            reason=args.reason,
        )
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
