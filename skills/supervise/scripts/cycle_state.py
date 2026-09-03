#!/usr/bin/env python3
"""Deterministic state for the supervise cycle (supervisor roadmap ri-02).

Everything here answers a question with exactly one right answer — what is ready,
what did a previous cycle already surface, has anything changed, is this write
allowed. Sensing, ranking and sizing are model work performed by the *session*;
this module never calls an LLM and never reaches the network, mirroring the
host-assisted invariant enforced for ``autopilot-roadmap``.

The two idempotency mechanisms live here, because a scheduled cycle fires on
whatever tree it finds — including an unchanged one:

* **Cycle fingerprint** — a digest over the tracked tree content (excluding this
  skill's own ledger surface, so recording a cycle never changes the fingerprint),
  the active change-ids, and every ``(roadmap_id, item_id, status, change_id)``
  tuple. No wall clock and no mtime, so the same tree always fingerprints the
  same and a re-run is detectable.
* **Stub keys** — a stable identity per candidate-work stub, so a stub already
  surfaced by an earlier cycle (or already tracked as a change or roadmap item) is
  suppressed instead of re-proposed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml
from jsonschema import Draft202012Validator, FormatChecker

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME = _SKILLS_ROOT / "roadmap-runtime" / "scripts"
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared.trust_posture import Disposition as _Disposition  # noqa: E402
from shared.trust_posture import Gate as _Gate  # noqa: E402


def _load_runtime_models():
    """Load roadmap-runtime's models under a collision-proof module name.

    Several skill trees ship a module literally named ``models`` and load it via
    ``sys.path`` insertion; whichever test collects first wins ``sys.modules``
    and every later bare ``import models`` silently gets the wrong file. Loading
    by explicit path under a unique name makes this module independent of
    collection order. models.py is self-contained (stdlib + yaml), so file-based
    loading is safe.
    """
    name = "supervise_roadmap_runtime_models"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _RUNTIME / "models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_models = _load_runtime_models()
ItemStatus = _models.ItemStatus
Roadmap = _models.Roadmap
completed_external_refs = _models.completed_external_refs
load_all_roadmaps = _models.load_all_roadmaps

#: Tracked so a rehydrated session on another machine inherits what has already
#: been surfaced. The supervisor is a rehydratable role, not a resident process.
LEDGER_PATH = "openspec/supervise/cycle-ledger.json"

#: Tracked durable subset of the supervisor handoff record. Active changes are
#: deliberately absent: they are a projection of loop state and are rebuilt.
MIRROR_PATH = "openspec/supervise/supervisor-record.json"

LEDGER_SCHEMA_VERSION = 1
SUPERVISOR_RECORD_SCHEMA_VERSION = 1

# D1 (ri-04): tracks shared.trust_posture.Gate/Disposition rather than a
# hand-copied literal, so a gate added to the enum (e.g. `roadmap_approval`)
# is accepted here with no separate edit.
_GATES = frozenset(g.value for g in _Gate)
_DISPOSITIONS = frozenset(d.value for d in _Disposition)
_GATE_SOURCES = frozenset({"autopilot", "supervise", "escalation"})
_STUB_DECISIONS = frozenset({"approved", "deferred", "rejected", "pending"})
_CHANGE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ROADMAP_REF_RE = re.compile(r"^[a-z0-9-]+:ri-[0-9]{2,}$")

#: Statuses in which an item no longer owns its change_id (mirrors decomposer's
#: ceded-status rule): a stub naming such a change is NOT considered a duplicate.
_CEDED = frozenset({ItemStatus.SKIPPED, ItemStatus.SUPERSEDED})

#: Path prefixes a supervise run may write. Everything else is implementation and
#: belongs to a dispatched write-capable worker.
_ALLOWED_WRITE_PREFIXES = (
    "openspec/roadmaps/",
    "openspec/changes/",
    "openspec/priorities/",
    "openspec/supervise/",
    "docs/proposals/",
)

#: Never writable by the supervisor even though they sit under an allowed prefix
#: — spec deltas and implementation live behind a worker's review, not a digest.
_FORBIDDEN_WRITE_SUFFIXES = ("/specs/",)


# --------------------------------------------------------------------------- #
# Git / repository facts
# --------------------------------------------------------------------------- #
def _tree_listing(repo_root: Path) -> str:
    """Committed blobs plus tracked changes, minus supervisor-owned state.

    Deliberately NOT the HEAD commit sha. The ledger under ``openspec/supervise/``
    is tracked, so recording a cycle and committing it advances HEAD; a fingerprint
    over the commit sha would therefore differ on every cycle-after-a-cycle and the
    unchanged-tree early exit could never fire once a recorded ledger was pushed.
    Hashing the tree *content* and the binary-safe diff from HEAD, excluding
    :data:`LEDGER_PATH` and :data:`MIRROR_PATH`, makes a supervisor-state-only
    commit or edit invisible while any real tracked change still lands in it.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    lines = [
        line
        for line in completed.stdout.splitlines()
        # ls-tree format: "<mode> <type> <object>\t<path>"
        if "\t" in line
        and line.split("\t", 1)[1] not in {LEDGER_PATH, MIRROR_PATH}
    ]
    worktree = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--binary",
            "--no-ext-diff",
            "HEAD",
            "--",
            ".",
            f":(exclude){LEDGER_PATH}",
            f":(exclude){MIRROR_PATH}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    diff = worktree.stdout if worktree.returncode == 0 else ""
    return "\n".join(sorted(lines)) + "\nworktree-diff:\n" + diff


def active_change_ids(repo_root: Path) -> set[str]:
    """Change-ids with a directory under ``openspec/changes/`` (excluding archive)."""
    changes = repo_root / "openspec" / "changes"
    if not changes.is_dir():
        return set()
    return {
        d.name for d in changes.iterdir() if d.is_dir() and d.name != "archive"
    }


def claimed_change_ids(roadmaps: dict[str, Roadmap]) -> set[str]:
    """Change-ids claimed by a roadmap item that has not ceded ownership."""
    return {
        item.change_id
        for roadmap in roadmaps.values()
        for item in roadmap.items
        if item.change_id and item.status not in _CEDED
    }


# --------------------------------------------------------------------------- #
# Supervisor handoff record
# --------------------------------------------------------------------------- #
def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _now_value(now: str | datetime | None) -> tuple[str, datetime]:
    if now is None:
        current = datetime.now(timezone.utc).replace(microsecond=0)
        return current.isoformat().replace("+00:00", "Z"), current
    if isinstance(now, datetime):
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")
        return now.isoformat().replace("+00:00", "Z"), now
    parsed = _parse_datetime(now)
    if parsed is None:
        raise ValueError("now must be an RFC3339 date-time with a timezone")
    return now, parsed


def _validate_record(repo_root: Path, record: dict[str, Any], schema_name: str) -> None:
    schema_path = repo_root / "openspec" / "schemas" / schema_name
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load supervisor record schema {schema_path}: {exc}") from exc
    Draft202012Validator(
        schema, format_checker=FormatChecker()
    ).validate(record)


def _sanitize_text(value: str) -> str:
    return "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")


def _clean_optional_text(value: Any) -> str | None:
    return _sanitize_text(value) if isinstance(value, str) else None


def _clean_pending_gate(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    gate = value.get("gate")
    change_id = value.get("change_id")
    requested_at = value.get("requested_at")
    deadline = value.get("deadline")
    if (
        gate not in _GATES
        or not isinstance(change_id, str)
        or _CHANGE_ID_RE.fullmatch(change_id) is None
        or _parse_datetime(requested_at) is None
        or _parse_datetime(deadline) is None
    ):
        return None
    cleaned: dict[str, Any] = {
        "gate": gate, "change_id": change_id,
        "requested_at": requested_at, "deadline": deadline,
    }
    disposition = value.get("disposition")
    if disposition is None or disposition in _DISPOSITIONS:
        if "disposition" in value:
            cleaned["disposition"] = disposition
    approval_id = value.get("approval_id")
    if approval_id is None or isinstance(approval_id, str):
        if "approval_id" in value:
            cleaned["approval_id"] = _clean_optional_text(approval_id)
    source = value.get("source", "supervise")
    cleaned["source"] = source if source in _GATE_SOURCES else "supervise"
    # D7: the router's gate-decision record id this pending entry projects, so a
    # rehydrated session can resolve `gate-decision:<decision_id>` back to its
    # record. Without this passthrough the allowlist cleaner silently strips it
    # on every write_mirror call.
    decision_id = value.get("decision_id")
    if decision_id is None or isinstance(decision_id, str):
        if "decision_id" in value:
            cleaned["decision_id"] = _clean_optional_text(decision_id)
    return cleaned


def _clean_standing_decision(value: Any, *, now: datetime) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    required_text = {
        key: _clean_optional_text(value.get(key))
        for key in ("id", "scope", "decision")
    }
    if not all(required_text.values()):
        return None
    decided_at = value.get("decided_at")
    if _parse_datetime(decided_at) is None:
        return None
    expires_at = value.get("expires_at")
    expiry = _parse_datetime(expires_at) if expires_at is not None else None
    if expires_at is not None and expiry is None:
        return None
    if expiry is not None and expiry <= now:
        return None
    cleaned: dict[str, Any] = {
        "id": required_text["id"],
        "decided_at": decided_at,
        "scope": required_text["scope"],
        "decision": required_text["decision"],
    }
    rationale = value.get("rationale")
    if rationale is None or isinstance(rationale, str):
        if "rationale" in value:
            cleaned["rationale"] = _clean_optional_text(rationale)
    if "expires_at" in value:
        cleaned["expires_at"] = expires_at
    return cleaned


def _clean_digested_stub(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    stub_key_value = value.get("stub_key")
    rank = value.get("rank")
    decision = value.get("decision")
    decided_at = value.get("decided_at")
    cleaned_stub_key = _clean_optional_text(stub_key_value)
    if (
        cleaned_stub_key is None
        or re.fullmatch(r"^(change|prov):.+$", cleaned_stub_key) is None
        or not isinstance(rank, int) or isinstance(rank, bool) or rank < 1
        or decision not in _STUB_DECISIONS
        or _parse_datetime(decided_at) is None
    ):
        return None
    cleaned: dict[str, Any] = {
        "stub_key": cleaned_stub_key, "rank": rank,
        "decision": decision, "decided_at": decided_at,
    }
    suggested = value.get("suggested_change_id")
    if suggested is None or isinstance(suggested, str):
        if "suggested_change_id" in value:
            cleaned["suggested_change_id"] = _clean_optional_text(suggested)
    return cleaned


def _clean_back_edge(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    last_digest = value.get("last_digest_at")
    if _parse_datetime(last_digest) is None:
        last_digest = None
    fingerprint = value.get("last_fingerprint")
    if not isinstance(fingerprint, str):
        fingerprint = None
    stubs = value.get("digested_stubs")
    cleaned_stubs = (
        [cleaned for item in stubs if (cleaned := _clean_digested_stub(item))]
        if isinstance(stubs, list) else []
    )
    return {
        "last_digest_at": last_digest,
        "last_fingerprint": _clean_optional_text(fingerprint),
        "digested_stubs": cleaned_stubs,
    }


def _require_supported_record_version(record: dict[str, Any]) -> None:
    version = record.get("schema_version")
    if version is not None and version != SUPERVISOR_RECORD_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported supervisor record schema_version: {version}"
        )


def _extract_supervisor_record(value: Any) -> dict[str, Any] | None:
    """Normalize a full record, mirror, handoff row, or bridge read envelope."""
    if not isinstance(value, dict):
        return None
    embedded = value.get("supervisor_record")
    if isinstance(embedded, dict):
        _require_supported_record_version(embedded)
        return embedded
    data = value.get("data")
    if isinstance(data, dict):
        handoffs = data.get("handoffs")
        if isinstance(handoffs, list):
            for handoff in handoffs:
                extracted = _extract_supervisor_record(handoff)
                if extracted is not None:
                    return extracted
    if all(
        key in value
        for key in ("written_at", "pending_gates", "standing_decisions", "back_edge")
    ):
        _require_supported_record_version(value)
        return value
    return None


def _durable_sections(prior: Any, *, now: datetime) -> dict[str, Any]:
    normalized = _extract_supervisor_record(prior) or {}
    gates = normalized.get("pending_gates")
    decisions = normalized.get("standing_decisions")
    return {
        "pending_gates": (
            [cleaned for item in gates if (cleaned := _clean_pending_gate(item))]
            if isinstance(gates, list) else []
        ),
        "standing_decisions": (
            [cleaned for item in decisions if (cleaned := _clean_standing_decision(item, now=now))]
            if isinstance(decisions, list) else []
        ),
        "back_edge": _clean_back_edge(normalized.get("back_edge")),
    }


def _roadmap_refs(repo_root: Path, degraded: list[str]) -> dict[str, str | None]:
    matches: dict[str, list[str]] = {}
    roadmaps = repo_root / "openspec" / "roadmaps"
    if not roadmaps.is_dir():
        return {}
    for path in sorted(roadmaps.glob("*/roadmap.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            degraded.append(f"malformed roadmap {path.relative_to(repo_root)}: {exc}")
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            degraded.append(f"malformed roadmap {path.relative_to(repo_root)}")
            continue
        roadmap_id = payload.get("roadmap_id")
        if not isinstance(roadmap_id, str):
            degraded.append(f"malformed roadmap id in {path.relative_to(repo_root)}")
            continue
        for item in payload["items"]:
            if not isinstance(item, dict):
                degraded.append(f"malformed roadmap item in {path.relative_to(repo_root)}")
                continue
            change_id = item.get("change_id")
            item_id = item.get("item_id")
            if not isinstance(change_id, str) or not isinstance(item_id, str):
                continue
            ref = f"{roadmap_id}:{item_id}"
            if _ROADMAP_REF_RE.fullmatch(ref) is None:
                degraded.append(f"malformed roadmap reference {ref} for {change_id}")
                continue
            matches.setdefault(change_id, []).append(ref)
    resolved: dict[str, str | None] = {}
    for change_id, refs in matches.items():
        unique = sorted(set(refs))
        if len(unique) == 1:
            resolved[change_id] = unique[0]
        else:
            resolved[change_id] = None
            degraded.append(f"ambiguous roadmap matches for {change_id}: {', '.join(unique)}")
    return resolved


def _registry_location(repo_root: Path) -> tuple[Path, Path]:
    direct = repo_root / ".git-worktrees" / ".registry.json"
    if direct.is_file():
        return direct, repo_root
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode == 0:
        common = Path(completed.stdout.strip()).resolve()
        main_repo = common.parent
        return main_repo / ".git-worktrees" / ".registry.json", main_repo
    return direct, repo_root


def _registry_entries(repo_root: Path, degraded: list[str]) -> tuple[dict[str, list[dict[str, Any]]], Path]:
    path, registry_root = _registry_location(repo_root)
    if not path.is_file():
        return {}, registry_root
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        degraded.append(f"malformed worktree registry: {exc}")
        return {}, registry_root
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        degraded.append("malformed worktree registry entries")
        return {}, registry_root
    by_change: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("change_id"), str):
            degraded.append("malformed worktree registry entry")
            continue
        if entry.get("agent_id") is not None:
            continue
        by_change.setdefault(entry["change_id"], []).append(entry)
    return by_change, registry_root


def _relative_worktree(raw: Any, *, registry_root: Path, change_id: str, degraded: list[str]) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(registry_root.resolve()).as_posix()
        except ValueError:
            degraded.append(f"worktree for {change_id} is outside the repository")
            return None
    normalized = posixpath.normpath(raw.replace("\\", "/"))
    if normalized in {".", ".."} or normalized.startswith("../"):
        degraded.append(f"worktree for {change_id} is not repository-relative")
        return None
    return normalized


def _active_changes(repo_root: Path, degraded: list[str]) -> list[dict[str, Any]]:
    roadmap_refs = _roadmap_refs(repo_root, degraded)
    registry, registry_root = _registry_entries(repo_root, degraded)
    changes_root = repo_root / "openspec" / "changes"
    if not changes_root.is_dir():
        return []
    active: list[dict[str, Any]] = []
    for change_dir in sorted(changes_root.iterdir(), key=lambda path: path.name):
        if not change_dir.is_dir() or change_dir.name == "archive":
            continue
        change_id = change_dir.name
        if _CHANGE_ID_RE.fullmatch(change_id) is None:
            degraded.append(f"malformed change id {change_id}")
            continue
        state_path = change_dir / "loop-state.json"
        if not state_path.is_file():
            degraded.append(f"missing loop-state for {change_id}")
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            degraded.append(f"malformed loop-state for {change_id}: {exc}")
            continue
        phase = state.get("current_phase") if isinstance(state, dict) else None
        if not isinstance(phase, str) or not phase:
            degraded.append(f"malformed loop-state phase for {change_id}")
            continue
        if phase == "DONE":
            continue
        phase_since = state.get("phase_started_at")
        if phase_since is not None and _parse_datetime(phase_since) is None:
            degraded.append(f"malformed phase_started_at for {change_id}")
            phase_since = None
        pending = state.get("pending_gate")
        active_pending = None
        if pending is not None:
            if (isinstance(pending, dict) and pending.get("gate") in _GATES
                    and _parse_datetime(pending.get("requested_at")) is not None):
                active_pending = {"gate": pending["gate"], "requested_at": pending["requested_at"]}
            else:
                degraded.append(f"malformed pending gate for {change_id}")
        entries = registry.get(change_id, [])
        branch = None
        worktree = None
        if len(entries) > 1:
            degraded.append(f"ambiguous-registry entries for {change_id}")
        elif entries:
            selected = entries[0]
            if isinstance(selected.get("branch"), str):
                branch = _sanitize_text(selected["branch"])
            elif selected.get("branch") is not None:
                degraded.append(f"malformed registry branch for {change_id}")
            worktree = _relative_worktree(
                selected.get("worktree_path"), registry_root=registry_root,
                change_id=change_id, degraded=degraded,
            )
        last_handoff = state.get("last_handoff_id")
        if not isinstance(last_handoff, str):
            last_handoff = None
        active.append({
            "change_id": change_id, "current_phase": phase,
            "phase_since": phase_since, "branch": branch, "worktree": worktree,
            "pending_gate": active_pending, "roadmap_ref": roadmap_refs.get(change_id),
            "last_handoff_id": last_handoff,
        })
    return active


def build_supervisor_record(repo_root: Path, prior: dict[str, Any] | None = None, *, now: str | datetime | None = None) -> dict[str, Any]:
    """Build a full record from fresh repository facts plus durable prior state."""
    root = Path(repo_root).resolve()
    written_at, current = _now_value(now)
    degraded: list[str] = []
    record = {
        "schema_version": SUPERVISOR_RECORD_SCHEMA_VERSION,
        "written_at": written_at,
        "written_by": {"agent_name": "supervisor", "session_id": None},
        "active_changes": _active_changes(root, degraded),
        **_durable_sections(prior, now=current),
    }
    for message in sorted(set(degraded)):
        print(f"Degraded: {message}", file=sys.stderr)
    _validate_record(root, record, "supervisor-record.schema.json")
    return record


def _select_prior_with_source(
    handoff: Any, mirror: Any
) -> tuple[dict[str, Any] | None, str]:
    handoff_record = _extract_supervisor_record(handoff)
    mirror_record = _extract_supervisor_record(mirror)
    if handoff_record is None:
        return mirror_record, "mirror" if mirror_record is not None else "empty"
    if mirror_record is None:
        return handoff_record, "handoff"
    handoff_time = _parse_datetime(handoff_record.get("written_at"))
    mirror_time = _parse_datetime(mirror_record.get("written_at"))
    if handoff_time is None:
        return mirror_record, "mirror"
    if mirror_time is not None and mirror_time > handoff_time:
        return mirror_record, "mirror"
    return handoff_record, "handoff"


def select_prior(handoff: Any, mirror: Any) -> dict[str, Any] | None:
    """Choose the newer normalized durable source; ties prefer the handoff."""
    return _select_prior_with_source(handoff, mirror)[0]


def _safe_mirror_path(repo_root: Path) -> Path:
    relative = Path(MIRROR_PATH)
    current = repo_root
    for part in relative.parent.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"mirror path contains symlink: {current}")
        current.mkdir(exist_ok=True)
    if not current.resolve().is_relative_to(repo_root):
        raise ValueError("mirror path escapes repository root")
    path = repo_root / relative
    if path.is_symlink():
        raise ValueError(f"mirror path is a symlink: {path}")
    return path


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        temporary.chmod(0o644)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_mirror(
    repo_root: Path,
    record: dict[str, Any],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Persist the sanitized durable subset, preserving time on a no-op write."""
    root = Path(repo_root).resolve()
    source = _extract_supervisor_record(record) or {}
    clock_input: str | datetime | None = now
    if clock_input is None and isinstance(source.get("written_at"), str):
        clock_input = source["written_at"]
    written_at, current = _now_value(clock_input)
    candidate = {
        "schema_version": SUPERVISOR_RECORD_SCHEMA_VERSION,
        "written_at": written_at,
        **_durable_sections(source, now=current),
    }
    _validate_record(root, candidate, "supervisor-record-mirror.schema.json")
    path = _safe_mirror_path(root)
    existing_raw: Any = None
    try:
        existing_raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    existing = _extract_supervisor_record(existing_raw)
    if existing is not None and _parse_datetime(existing.get("written_at")) is not None:
        sanitized_existing = {
            "schema_version": SUPERVISOR_RECORD_SCHEMA_VERSION,
            "written_at": existing["written_at"],
            **_durable_sections(existing, now=current),
        }
        old = {k: v for k, v in sanitized_existing.items() if k != "written_at"}
        new = {k: v for k, v in candidate.items() if k != "written_at"}
        if old == new and existing_raw == sanitized_existing:
            return sanitized_existing
    _atomic_write_text(path, json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    return candidate


# --------------------------------------------------------------------------- #
# Cycle fingerprint
# --------------------------------------------------------------------------- #
def compute_fingerprint(repo_root: Path) -> str:
    """Digest of the repository state a discovery cycle would reason over.

    Deterministic by construction: every component is sorted, and none of them is
    a timestamp. Two cycles over an unchanged tree therefore produce the same
    fingerprint, which is what lets a scheduled re-run detect that it has nothing
    new to do rather than re-proposing the same work.

    The ledger file is excluded from the tree component (see
    :func:`_tree_listing`), so the record-commit-push of cycle N does not make
    cycle N+1 look like a changed tree.
    """
    roadmaps = load_all_roadmaps(repo_root)
    tree = _tree_listing(repo_root)
    parts: list[str] = [f"tree:{hashlib.sha256(tree.encode('utf-8')).hexdigest()}"]
    parts += [f"change:{cid}" for cid in sorted(active_change_ids(repo_root))]
    parts += [
        f"item:{roadmap_id}:{item.item_id}:{item.status.value}:{item.change_id or ''}"
        for roadmap_id, roadmap in sorted(roadmaps.items())
        for item in sorted(roadmap.items, key=lambda i: i.item_id)
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Candidate-work stub identity
# --------------------------------------------------------------------------- #
def stub_key(stub: dict[str, Any]) -> str:
    """Stable identity for a candidate-work stub.

    Prefers ``suggested_change_id`` — two generators proposing the same change are
    proposing the same work, whatever their wording. Falls back to a digest of the
    provenance (source artifact + sorted finding ids), so a stub without a suggested
    id is still deduplicable against its own re-discovery.
    """
    suggested = (stub.get("suggested_change_id") or "").strip()
    if suggested:
        return f"change:{suggested}"
    provenance = stub.get("provenance") or {}
    source = str(provenance.get("source_artifact", "")).strip()
    findings = sorted(str(f) for f in provenance.get("finding_ids", []) or [])
    payload = json.dumps({"source": source, "findings": findings}, sort_keys=True)
    return "prov:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class DedupeResult:
    """Outcome of suppressing already-tracked or already-surfaced stubs."""

    fresh: list[dict[str, Any]] = field(default_factory=list)
    suppressed: list[tuple[dict[str, Any], str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fresh": self.fresh,
            "suppressed": [
                {"key": stub_key(stub), "reason": reason}
                for stub, reason in self.suppressed
            ],
            "fresh_count": len(self.fresh),
            "suppressed_count": len(self.suppressed),
        }


def dedupe_stubs(
    stubs: Sequence[dict[str, Any]],
    *,
    seen_keys: Iterable[str] = (),
    existing_change_ids: Iterable[str] = (),
    claimed_ids: Iterable[str] = (),
) -> DedupeResult:
    """Split *stubs* into genuinely new work and work already tracked.

    Four suppression reasons, in precedence order — the most specific first, so the
    digest can explain *why* something was dropped rather than silently shrinking:

    ``already-surfaced``  a previous cycle recorded this key
    ``change-exists``     a directory under openspec/changes/ already has this id
    ``roadmap-claimed``   a non-ceded roadmap item already owns this change_id
    ``duplicate-in-batch`` two generators produced the same key this cycle
    """
    seen = set(seen_keys)
    existing = set(existing_change_ids)
    claimed = set(claimed_ids)

    fresh: list[dict[str, Any]] = []
    suppressed: list[tuple[dict[str, Any], str]] = []
    batch_keys: set[str] = set()

    for stub in stubs:
        key = stub_key(stub)
        change_id = (stub.get("suggested_change_id") or "").strip()
        if key in seen:
            suppressed.append((stub, "already-surfaced"))
        elif change_id and change_id in existing:
            suppressed.append((stub, "change-exists"))
        elif change_id and change_id in claimed:
            suppressed.append((stub, "roadmap-claimed"))
        elif key in batch_keys:
            suppressed.append((stub, "duplicate-in-batch"))
        else:
            batch_keys.add(key)
            fresh.append(stub)
    return DedupeResult(fresh=fresh, suppressed=suppressed)


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
def load_ledger(repo_root: Path) -> dict[str, Any]:
    """Read the cycle ledger, returning an empty ledger when absent or malformed.

    A malformed ledger degrades to "nothing surfaced yet" rather than raising: the
    worst case is one cycle re-proposing work, which the operator sees and can
    dismiss. Failing the cycle outright would be the more damaging outcome.
    """
    empty = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "last_fingerprint": None,
        "seen_keys": [],
    }
    path = repo_root / LEDGER_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    # Shape-validate the fields this module consumes; a wrong-typed value is as
    # malformed as bad JSON. Without this, seen_keys="change:x" would be iterated
    # character-by-character by dedupe and permanently exploded into one-character
    # keys by record_cycle's set() merge — degradation to garbage, not to empty.
    keys = data.get("seen_keys")
    if not (isinstance(keys, list) and all(isinstance(k, str) for k in keys)):
        data["seen_keys"] = []
    fingerprint = data.get("last_fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        data["last_fingerprint"] = None
    data.setdefault("schema_version", LEDGER_SCHEMA_VERSION)
    data.setdefault("last_fingerprint", None)
    data.setdefault("seen_keys", [])
    return data


def record_cycle(
    repo_root: Path, fingerprint: str, new_keys: Iterable[str]
) -> dict[str, Any]:
    """Merge *new_keys* into the ledger and stamp *fingerprint*.

    Keys are stored sorted and de-duplicated so a repeat run over an unchanged tree
    rewrites byte-identical content — no spurious repository diff.
    """
    ledger = load_ledger(repo_root)
    merged = sorted(set(ledger.get("seen_keys", [])) | set(new_keys))
    ledger.update(
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "last_fingerprint": fingerprint,
            "seen_keys": merged,
        }
    )
    path = repo_root / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ledger


def is_unchanged(repo_root: Path, fingerprint: str | None = None) -> bool:
    """True when the tree has not changed since the last recorded cycle."""
    fp = fingerprint or compute_fingerprint(repo_root)
    return load_ledger(repo_root).get("last_fingerprint") == fp


# --------------------------------------------------------------------------- #
# Ready set across roadmaps
# --------------------------------------------------------------------------- #
def ready_across_roadmaps(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Ready items per roadmap, honoring in-roadmap deps and typed external edges.

    Mirrors the orchestrator's admission rule (approved / in_progress with every
    dependency completed) and adds ri-17's external resolution, so an item blocked
    only by another roadmap's prerequisite disappears from the ready set until that
    prerequisite completes — and reappears with no manual status edit.
    """
    roadmaps = load_all_roadmaps(repo_root)
    external_done = completed_external_refs(repo_root)
    out: dict[str, list[dict[str, Any]]] = {}
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        # Delegate to the shared admission rule rather than hand-rolling a copy.
        # The first draft of this function WAS such a copy, and it had already
        # drifted: it admitted items carrying a superseded_by edge, which both
        # Roadmap.ready_items and the orchestrator exclude — the digest would
        # have listed work another roadmap's item owns as "Ready now".
        ready = roadmap.ready_items(external_done, include_in_progress=True)
        ready.sort(key=lambda i: (i.priority, i.item_id))
        out[roadmap_id] = [
            {
                "item_id": i.item_id,
                "title": i.title,
                "priority": i.priority,
                "effort": i.effort.value,
                "change_id": i.change_id,
            }
            for i in ready
        ]
    return out


# --------------------------------------------------------------------------- #
# Write-boundary audit
# --------------------------------------------------------------------------- #
def classify_write(path: str) -> str:
    """``allowed`` or ``forbidden`` for a repo-relative path a supervise run wrote.

    The supervisor archetype is ``write_capable: false``; this makes that structural
    rather than aspirational. Coordination artifacts are allowed; source code, specs,
    and everything outside the coordination surface are a worker's job.

    Paths are normalized before the prefix check, because the check is only as
    strong as its canonical form: the first draft used ``lstrip("./")`` (a
    character strip, not a prefix strip) and no ``..`` resolution, so both
    ``../openspec/roadmaps/x.yaml`` and
    ``openspec/roadmaps/../../agent-coordinator/src/x.py`` classified as allowed
    — a traversal that defeats the entire audit. Anything absolute, or escaping
    the repository root after normalization, is forbidden outright.
    """
    candidate = path.strip()
    if not candidate or candidate.startswith(("/", "\\")) or ":" in candidate.split("/", 1)[0]:
        return "forbidden"
    normalized = posixpath.normpath(candidate.replace("\\", "/"))
    if normalized == "." or normalized == ".." or normalized.startswith("../"):
        return "forbidden"
    if any(suffix in f"/{normalized}/" for suffix in _FORBIDDEN_WRITE_SUFFIXES):
        return "forbidden"
    return (
        "allowed"
        if normalized.startswith(_ALLOWED_WRITE_PREFIXES)
        else "forbidden"
    )


def audit_writes(paths: Iterable[str]) -> list[str]:
    """Repo-relative paths a supervise run must not have written (empty = clean)."""
    return sorted(p for p in paths if classify_write(p) == "forbidden")


def _changed_paths(repo_root: Path) -> dict[str, str]:
    """Return porcelain status codes for every changed repository path."""
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return {}

    records = completed.stdout.split(b"\0")
    changed: dict[str, str] = {}
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        text = record.decode("utf-8", errors="surrogateescape")
        status = text[:2]
        path = text[3:]
        changed[path] = status
        if "R" in status or "C" in status:
            if index < len(records) and records[index]:
                source = records[index].decode("utf-8", errors="surrogateescape")
                changed[source] = status
                index += 1
    return changed


def _path_state(repo_root: Path, path: str, status: str) -> str:
    """Digest index, worktree, and file content state for one changed path."""
    components = [f"status:{status}"]
    for args in (
        ["diff", "--binary", "--cached", "HEAD", "--", path],
        ["diff", "--binary", "--", path],
    ):
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
        )
        components.append(completed.stdout.decode("utf-8", errors="surrogateescape"))

    full_path = repo_root / path
    if full_path.is_symlink():
        components.append(f"symlink:{full_path.readlink()}")
    elif full_path.is_file():
        components.append("content:" + hashlib.sha256(full_path.read_bytes()).hexdigest())
    else:
        components.append("missing")
    return hashlib.sha256("\n".join(components).encode("utf-8", errors="surrogateescape")).hexdigest()


def repository_snapshot(repo_root: Path) -> dict[str, str]:
    """Snapshot every currently changed path without modifying the checkout."""
    return {
        path: _path_state(repo_root, path, status)
        for path, status in sorted(_changed_paths(repo_root).items())
    }


def audit_since_snapshot(repo_root: Path, before: dict[str, str]) -> list[str]:
    """Audit paths whose repository state changed after *before* was captured."""
    after = repository_snapshot(repo_root)
    written = sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )
    return audit_writes(written)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_fingerprint(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    fp = compute_fingerprint(repo)
    print(json.dumps({"fingerprint": fp, "unchanged": is_unchanged(repo, fp)}, indent=2))
    return 0


def _cmd_ready(args: argparse.Namespace) -> int:
    print(json.dumps(ready_across_roadmaps(Path(args.repo_root).resolve()), indent=2))
    return 0


def _cmd_dedupe(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    raw = json.loads(Path(args.stubs).read_text(encoding="utf-8"))
    stubs = raw if isinstance(raw, list) else [raw]
    roadmaps = load_all_roadmaps(repo)
    result = dedupe_stubs(
        stubs,
        seen_keys=load_ledger(repo).get("seen_keys", []),
        existing_change_ids=active_change_ids(repo),
        claimed_ids=claimed_change_ids(roadmaps),
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    keys = json.loads(Path(args.keys).read_text(encoding="utf-8")) if args.keys else []
    ledger = record_cycle(repo, compute_fingerprint(repo), keys)
    print(json.dumps({"recorded": len(ledger["seen_keys"])}, indent=2))
    return 0


def _cmd_audit_writes(args: argparse.Namespace) -> int:
    violations = audit_writes(args.paths)
    print(json.dumps({"violations": violations}, indent=2))
    return 1 if violations else 0


def _cmd_snapshot_writes(args: argparse.Namespace) -> int:
    snapshot = repository_snapshot(Path(args.repo_root).resolve())
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


def _cmd_audit_since(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    before = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    if not isinstance(before, dict) or not all(
        isinstance(path, str) and isinstance(state, str)
        for path, state in before.items()
    ):
        raise ValueError("snapshot must be a JSON object mapping paths to state digests")
    violations = audit_since_snapshot(repo, before)
    print(json.dumps({"violations": violations}, indent=2))
    return 1 if violations else 0


def _read_json_file(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _cmd_supervisor_record(args: argparse.Namespace) -> int:
    record = build_supervisor_record(
        Path(args.repo_root).resolve(), _read_json_file(args.prior), now=args.now
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def _cmd_mirror(args: argparse.Namespace) -> int:
    record = _read_json_file(args.record)
    if record is None:
        raise ValueError("--record must name a JSON object")
    mirror = write_mirror(Path(args.repo_root).resolve(), record, now=args.now)
    print(json.dumps(mirror, indent=2, sort_keys=True))
    return 0


def _cmd_rehydrate(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    handoff = _read_json_file(args.handoff)
    mirror_path = Path(args.mirror) if args.mirror else repo / MIRROR_PATH
    mirror = _read_json_file(str(mirror_path))
    handoff_record = _extract_supervisor_record(handoff)
    prior, source = _select_prior_with_source(handoff, mirror)
    if handoff_record is None:
        print("Degraded: handoff", file=sys.stderr)
    elif source == "mirror":
        print("Degraded: handoff (newer mirror selected)", file=sys.stderr)
    record = build_supervisor_record(repo, prior, now=args.now)
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- #
# gate-check / gate-answer / gate-log (D5, D6) -- gate_router imported lazily
# per-handler: cycle_state does heavy import-time work of its own
# (_load_runtime_models) and gate_router imports cycle_state.write_mirror, so
# a module-level import in either direction is a cycle.
# --------------------------------------------------------------------------- #

# Exit codes (D5): 3 mirrors runner.py's EXIT_NO_PENDING_GATE (proceed,
# including a reused decision -- nothing to ask); 0 = parked on posture_block
# (prints the pending entry; the SKILL renders it and stops); 4 = terminal
# block (rejected / timeout_default_block / coordinator_unreachable) -- the
# entry stays answerable via gate-answer, unlike runner.py's EXIT_GATE_PARKED
# (4), which clears pending_gate and enters ESCALATE. That divergence is
# deliberate: the supervisor has no ESCALATE state to fall into.
GATE_EXIT_PROCEED = 3
GATE_EXIT_PARKED = 0
GATE_EXIT_TERMINAL_BLOCK = 4

_TERMINAL_BLOCK_RESOLUTIONS = frozenset(
    {"rejected", "console_rejected", "timeout_default_block", "coordinator_unreachable"}
)


def _roadmap_workspace(repo_root: Path, roadmap_id: str) -> Path:
    return repo_root / "openspec" / "roadmaps" / roadmap_id


def _gate_decision_exit_code(decision: Any) -> int:
    if decision.proceed:
        return GATE_EXIT_PROCEED
    if decision.resolution.value == "posture_block":
        return GATE_EXIT_PARKED
    return GATE_EXIT_TERMINAL_BLOCK


def _pending_entry_for(mirror_repo_root: Path, decision_id: str | None) -> dict[str, Any] | None:
    """Read back the `pending_gates` entry `evaluate`/`answer` just projected
    into the mirror (D7), by `decision_id` -- the entry shape is the router's
    own, not duplicated here."""
    if decision_id is None:
        return None
    mirror_path = mirror_repo_root / MIRROR_PATH
    try:
        mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in _extract_supervisor_record(mirror).get("pending_gates", []) if mirror else []:
        if entry.get("decision_id") == decision_id:
            return entry
    return None


def _cmd_gate_check(args: argparse.Namespace) -> int:
    import gate_router  # lazy (see module preamble)
    from shared.trust_posture import Gate

    repo = Path(args.repo_root).resolve()
    workspace = _roadmap_workspace(repo, args.roadmap)
    roadmap = load_all_roadmaps(repo).get(args.roadmap)
    item_count = len(roadmap.items) if roadmap is not None else None
    context = {"item_count": item_count, "verb": "cycle"}
    for pair in args.context or []:
        key, _, value = pair.partition("=")
        context[key] = value

    routed = gate_router.evaluate(Gate.ROADMAP_APPROVAL, context, workspace=workspace, repo_root=repo)
    exit_code = _gate_decision_exit_code(routed.decision)
    if exit_code == GATE_EXIT_PROCEED:
        payload = dict(routed.record)
        payload["roadmap_approval_ref"] = f"gate-decision:{routed.record['decision_id']}"
    else:
        payload = _pending_entry_for(repo, routed.record.get("decision_id")) or dict(routed.record)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


def _cmd_gate_answer(args: argparse.Namespace) -> int:
    import gate_router  # lazy
    from shared.trust_posture import Gate

    repo = Path(args.repo_root).resolve()
    workspace = _roadmap_workspace(repo, args.roadmap)
    gate_enum = Gate(args.gate)
    approved = args.decision == "approved"
    context: dict[str, Any] = {"verb": "cycle"}
    if args.dispatch_id:
        context["dispatch_id"] = args.dispatch_id

    try:
        routed = gate_router.answer(
            gate_enum, workspace=workspace, repo_root=repo, approved=approved, note=args.note, context=context
        )
    except gate_router.GateRefusalError as exc:
        print(f"cycle_state: {exc}", file=sys.stderr)
        return 2

    payload = dict(routed.record)
    if gate_enum is Gate.ROADMAP_APPROVAL and routed.decision.proceed:
        payload["roadmap_approval_ref"] = f"gate-decision:{routed.record['decision_id']}"
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_gate_log(args: argparse.Namespace) -> int:
    import gate_router  # lazy

    repo = Path(args.repo_root).resolve()
    workspace = _roadmap_workspace(repo, args.roadmap)
    print(json.dumps(gate_router.gate_log(workspace, repo), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic supervise-cycle state.")
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fingerprint", help="Print the cycle fingerprint and whether it is unchanged.")
    sub.add_parser("ready", help="Print ready items per roadmap, resolving external edges.")

    p_dedupe = sub.add_parser("dedupe", help="Suppress already-tracked or already-surfaced stubs.")
    p_dedupe.add_argument("--stubs", required=True)

    p_record = sub.add_parser("record", help="Stamp the ledger with this cycle's fingerprint and keys.")
    p_record.add_argument("--keys", help="JSON file containing a list of stub keys.")

    p_audit = sub.add_parser("audit-writes", help="Fail if any path is outside the coordination surface.")
    p_audit.add_argument("paths", nargs="*")
    sub.add_parser("snapshot-writes", help="Print current changed-path state for a before/after audit.")
    p_since = sub.add_parser("audit-since", help="Fail on forbidden writes made after a snapshot.")
    p_since.add_argument("--snapshot", required=True)

    p_supervisor = sub.add_parser("supervisor-record", help="Build a supervisor handoff record.")
    p_supervisor.add_argument("--prior", help="Prior handoff response, record, or mirror JSON.")
    p_supervisor.add_argument("--now", help="Explicit RFC3339 clock input (tests/replay).")

    p_mirror = sub.add_parser("mirror", help="Write the tracked non-derivable mirror.")
    p_mirror.add_argument("--record", required=True, help="Full supervisor record JSON.")
    p_mirror.add_argument("--now", help="Explicit RFC3339 clock input (tests/replay).")

    p_rehydrate = sub.add_parser("rehydrate", help="Select durable state and freshly derive active changes.")
    p_rehydrate.add_argument("--handoff", help="Bridge handoff-read JSON response.")
    p_rehydrate.add_argument("--mirror", help=f"Mirror JSON (default: {MIRROR_PATH}).")
    p_rehydrate.add_argument("--now", help="Explicit RFC3339 clock input (tests/replay).")

    p_gate_check = sub.add_parser(
        "gate-check",
        help="Evaluate roadmap_approval (D5). Exit 3 proceed, 0 parked (posture_block), 4 terminal block.",
    )
    p_gate_check.add_argument("--roadmap", required=True)
    p_gate_check.add_argument(
        "--context", action="append", metavar="KEY=VALUE",
        help="Additional context key=value (repeatable).",
    )

    p_gate_answer = sub.add_parser(
        "gate-answer", help="Record a console decision for a gate (originates roadmap_approval)."
    )
    p_gate_answer.add_argument("--roadmap", required=True)
    p_gate_answer.add_argument("--gate", required=True)
    p_gate_answer.add_argument("--decision", required=True, choices=["approved", "rejected"])
    p_gate_answer.add_argument("--note")
    p_gate_answer.add_argument("--dispatch-id", dest="dispatch_id")

    p_gate_log = sub.add_parser("gate-log", help="Print the sidecar + child gate_decisions for a roadmap (D6).")
    p_gate_log.add_argument("--roadmap", required=True)

    args = parser.parse_args(argv)
    return {
        "fingerprint": _cmd_fingerprint,
        "ready": _cmd_ready,
        "dedupe": _cmd_dedupe,
        "record": _cmd_record,
        "audit-writes": _cmd_audit_writes,
        "snapshot-writes": _cmd_snapshot_writes,
        "audit-since": _cmd_audit_since,
        "supervisor-record": _cmd_supervisor_record,
        "mirror": _cmd_mirror,
        "rehydrate": _cmd_rehydrate,
        "gate-check": _cmd_gate_check,
        "gate-answer": _cmd_gate_answer,
        "gate-log": _cmd_gate_log,
    }[args.command](args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
