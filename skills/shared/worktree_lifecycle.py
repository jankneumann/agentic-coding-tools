"""Portable authority for the repository-owned worktree lifecycle registry.

The module deliberately uses only the Python standard library.  Registry reads
accept the legacy v1 document, while every successful mutation writes v2 under
one advisory lock and one atomic replace.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

try:  # POSIX is the supported local execution environment.
    import fcntl
except ImportError:  # pragma: no cover - defensive import for isolated Windows harnesses
    fcntl = None  # type: ignore[assignment]


DEFAULT_LEASE_TTL_SECONDS = 1800
DEFAULT_SETUP_TTL_SECONDS = 1800
LEGACY_ACTIVITY_SECONDS = 3600
DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
REGISTRY_RELATIVE_PATH = Path(".git-worktrees/.registry.json")
LOCK_RELATIVE_PATH = Path(".git-worktrees/.registry.lock")
EVIDENCE_RELATIVE_PATH = Path(".git-worktrees/.lifecycle-processes")


class LifecycleError(RuntimeError):
    exit_code = 1


class RegistryCorrupt(LifecycleError):
    exit_code = 2


class LeaseOwnedByAnother(LifecycleError):
    exit_code = 3


class OwnerConflict(LifecycleError):
    exit_code = 4


class LockTimeout(LifecycleError):
    exit_code = 5


class FenceConflict(LifecycleError):
    exit_code = 6


class RecoveryRequired(LifecycleError):
    exit_code = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def registry_path(repo_root: Path) -> Path:
    return Path(repo_root) / REGISTRY_RELATIVE_PATH


def lock_path(repo_root: Path) -> Path:
    return Path(repo_root) / LOCK_RELATIVE_PATH


def evidence_directory(repo_root: Path) -> Path:
    return Path(repo_root) / EVIDENCE_RELATIVE_PATH


def empty_registry(*, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "entries": copy.deepcopy(entries or []),
        "setup_reservations": [],
        "recovery_audit": [],
    }


def _length_prefix(parts: tuple[object, ...]) -> bytes:
    encoded: list[bytes] = [b"worktree-lifecycle-v1"]
    for part in parts:
        if part is None:
            value = b"\xffNULL"
        else:
            value = str(part).encode("utf-8")
        encoded.extend((str(len(value)).encode("ascii"), b":", value, b";"))
    return b"".join(encoded)


def legacy_entry_generation(entry: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        _length_prefix(
            (
                entry.get("change_id"),
                entry.get("agent_id"),
                entry.get("branch"),
                entry.get("worktree_path"),
                entry.get("created_at"),
            )
        )
    ).hexdigest()
    return f"legacy-v1-entry:{digest}"


def legacy_lease_id(entry: dict[str, Any]) -> str:
    agent = entry.get("agent_id") or "parent"
    digest = hashlib.sha256(
        f"{entry.get('change_id')}|{agent}|{entry.get('created_at')}".encode()
    ).hexdigest()
    return f"legacy-v1:{digest}"


def _legacy_lease(entry: dict[str, Any]) -> dict[str, Any] | None:
    heartbeat = parse_timestamp(entry.get("last_heartbeat"))
    if heartbeat is None:
        return None
    created = parse_timestamp(entry.get("created_at")) or heartbeat
    acquired = min(created, heartbeat)
    agent = entry.get("agent_id") or "parent"
    return {
        "owner": f"legacy:{entry.get('change_id')}:{agent}",
        "lease_id": legacy_lease_id(entry),
        "controller_instance_id": None,
        "session_id": None,
        "phase": "LEGACY",
        "reason": "legacy-heartbeat-migration",
        "lifecycle_mode": "manual",
        "acquired_at": acquired.isoformat(),
        "last_heartbeat": heartbeat.isoformat(),
        "expires_at": (heartbeat + timedelta(seconds=LEGACY_ACTIVITY_SECONDS)).isoformat(),
        "ttl_seconds": LEGACY_ACTIVITY_SECONDS,
    }


_V1_FIELDS = {
    "change_id",
    "agent_id",
    "branch",
    "worktree_path",
    "created_at",
    "last_heartbeat",
    "pinned",
}


def normalize_registry(data: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return a canonical v2 interpretation without mutating *data*."""
    del now  # liveness is evaluated by callers; normalization is time-stable.
    if not isinstance(data, dict):
        raise RegistryCorrupt("registry root must be an object")
    if data.get("schema_version") == 2:
        normalized = copy.deepcopy(data)
        _validate_v2(normalized)
        return normalized
    if data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise RegistryCorrupt("registry is neither schema v1 nor schema v2")
    entries: list[dict[str, Any]] = []
    for raw in data["entries"]:
        if not isinstance(raw, dict):
            raise RegistryCorrupt("legacy registry entry must be an object")
        required = ("change_id", "branch", "worktree_path", "created_at", "pinned")
        if any(key not in raw for key in required):
            raise RegistryCorrupt("legacy registry entry is missing required fields")
        extensions = {
            key: copy.deepcopy(value) for key, value in raw.items() if key not in _V1_FIELDS
        }
        if (
            raw.get("last_heartbeat") is not None
            and parse_timestamp(raw.get("last_heartbeat")) is None
        ):
            extensions["legacy_last_heartbeat"] = raw.get("last_heartbeat")
        retained = bool(raw.get("pinned"))
        entries.append(
            {
                "change_id": raw["change_id"],
                "agent_id": raw.get("agent_id"),
                "branch": raw["branch"],
                "worktree_path": raw["worktree_path"],
                "created_at": raw["created_at"],
                "entry_generation": legacy_entry_generation(raw),
                "setup_id": None,
                "durability_target": None,
                "last_heartbeat": raw.get("last_heartbeat"),
                "retained": retained,
                "retention_reason": "legacy-pin" if retained else None,
                "recovery_required": False,
                "recovery_reason": None,
                "recovery_context": None,
                "activity_lease": _legacy_lease(raw),
                **({"extensions": extensions} if extensions else {}),
            }
        )
    top_extensions = {
        key: copy.deepcopy(value)
        for key, value in data.items()
        if key not in {"version", "entries"}
    }
    result = empty_registry(entries=entries)
    if top_extensions:
        result["extensions"] = top_extensions
    _validate_v2(result)
    return result


def _require_nonempty(obj: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    for name in names:
        if not isinstance(obj.get(name), str) or not obj[name]:
            raise RegistryCorrupt(f"{label}.{name} must be a non-empty string")


def _validate_v2(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 2:
        raise RegistryCorrupt("schema_version must equal 2")
    for name in ("entries", "setup_reservations", "recovery_audit"):
        if not isinstance(data.get(name), list):
            raise RegistryCorrupt(f"{name} must be an array")
    keys: set[tuple[str, str | None]] = set()
    generations: set[str] = set()
    for entry in data["entries"]:
        if not isinstance(entry, dict):
            raise RegistryCorrupt("entry must be an object")
        _require_nonempty(
            entry,
            ("change_id", "branch", "worktree_path", "created_at", "entry_generation"),
            "entry",
        )
        key = (entry["change_id"], entry.get("agent_id"))
        if key in keys:
            raise RegistryCorrupt(f"duplicate registry entry {key!r}")
        keys.add(key)
        generations.add(entry["entry_generation"])
        for required in (
            "setup_id",
            "durability_target",
            "retained",
            "retention_reason",
            "recovery_required",
            "recovery_reason",
            "recovery_context",
            "activity_lease",
        ):
            if required not in entry:
                raise RegistryCorrupt(f"entry missing {required}")
        if entry["retained"] and not entry["retention_reason"]:
            raise RegistryCorrupt("retained entry requires retention_reason")
        if not entry["retained"] and entry["retention_reason"] is not None:
            raise RegistryCorrupt("unretained entry must have null retention_reason")
        if entry["recovery_required"] and (
            not entry["recovery_reason"] or not isinstance(entry["recovery_context"], dict)
        ):
            raise RegistryCorrupt("recovery entry requires reason and context")
        if not entry["recovery_required"] and (
            entry["recovery_reason"] is not None or entry["recovery_context"] is not None
        ):
            raise RegistryCorrupt("ordinary entry cannot retain recovery metadata")
        lease = entry["activity_lease"]
        if lease is not None:
            _validate_lease(lease)
    setup_ids: set[str] = set()
    for reservation in data["setup_reservations"]:
        if not isinstance(reservation, dict):
            raise RegistryCorrupt("setup reservation must be an object")
        _require_nonempty(
            reservation,
            (
                "setup_id",
                "change_id",
                "branch",
                "worktree_path",
                "entry_generation",
                "created_at",
                "updated_at",
                "expires_at",
            ),
            "reservation",
        )
        if reservation["setup_id"] in setup_ids:
            raise RegistryCorrupt("duplicate setup id")
        setup_ids.add(reservation["setup_id"])
        if reservation["state"] not in {"reserved", "checkout-created", "evidence-created"}:
            raise RegistryCorrupt("invalid reservation state")
        if reservation["entry_generation"] in generations:
            raise RegistryCorrupt("reservation and entry share a generation")
        created = parse_timestamp(reservation["created_at"])
        expires = parse_timestamp(reservation["expires_at"])
        ttl = reservation.get("ttl_seconds")
        if created is None or expires is None or not isinstance(ttl, int) or not 60 <= ttl <= 86400:
            raise RegistryCorrupt("invalid reservation timing")
        if expires != created + timedelta(seconds=ttl):
            raise RegistryCorrupt("reservation expiry does not match fixed ttl")
    audit_ids: set[str] = set()
    for event in data["recovery_audit"]:
        if not isinstance(event, dict) or not event.get("event_id"):
            raise RegistryCorrupt("invalid recovery audit event")
        if event["event_id"] in audit_ids:
            raise RegistryCorrupt("duplicate recovery audit event id")
        audit_ids.add(event["event_id"])


def _validate_lease(lease: dict[str, Any]) -> None:
    _require_nonempty(
        lease,
        (
            "owner",
            "lease_id",
            "phase",
            "reason",
            "lifecycle_mode",
            "acquired_at",
            "last_heartbeat",
            "expires_at",
        ),
        "lease",
    )
    if lease.get("controller_instance_id") is None:
        if lease.get("phase") != "LEGACY" or lease.get("lifecycle_mode") != "manual":
            raise RegistryCorrupt("only normalized manual LEGACY lease may have a null controller")
    elif (
        not isinstance(lease.get("controller_instance_id"), str)
        or not lease["controller_instance_id"]
    ):
        raise RegistryCorrupt("invalid lease controller")
    if lease.get("session_id") is not None and (
        not isinstance(lease["session_id"], str) or not lease["session_id"]
    ):
        raise RegistryCorrupt("empty session id is invalid")
    ttl = lease.get("ttl_seconds")
    if not isinstance(ttl, int) or not 60 <= ttl <= 86400:
        raise RegistryCorrupt("invalid lease ttl")
    for field in ("acquired_at", "last_heartbeat", "expires_at"):
        if parse_timestamp(lease[field]) is None:
            raise RegistryCorrupt(f"invalid lease {field}")


@contextlib.contextmanager
def registry_lock(
    repo_root: Path,
    *,
    exclusive: bool,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    path = lock_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    if fcntl is None:  # pragma: no cover
        handle.close()
        raise LockTimeout("advisory file locking is unavailable")
    operation = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), operation)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"timed out acquiring {path}")
                time.sleep(0.02)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _read_unlocked(repo_root: Path) -> dict[str, Any]:
    path = registry_path(repo_root)
    if not path.exists():
        return empty_registry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryCorrupt(f"cannot parse registry: {exc}") from exc
    return normalize_registry(raw)


def read_registry(repo_root: Path) -> dict[str, Any]:
    with registry_lock(repo_root, exclusive=False):
        return _read_unlocked(repo_root)


def _write_unlocked(repo_root: Path, registry: dict[str, Any]) -> None:
    _validate_v2(registry)
    path = registry_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:  # pragma: no cover - filesystem-dependent durability aid
            pass
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def write_registry(repo_root: Path, registry: dict[str, Any]) -> None:
    with registry_lock(repo_root, exclusive=True):
        _write_unlocked(repo_root, normalize_registry(registry))


T = TypeVar("T")


def mutate_registry(repo_root: Path, mutation: Callable[[dict[str, Any]], T]) -> T:
    with registry_lock(repo_root, exclusive=True):
        registry = _read_unlocked(repo_root)
        result = mutation(registry)
        _write_unlocked(repo_root, registry)
        return result


def find_entry(
    registry: dict[str, Any], change_id: str, agent_id: str | None = None
) -> dict[str, Any] | None:
    return next(
        (
            entry
            for entry in registry["entries"]
            if entry["change_id"] == change_id and entry.get("agent_id") == agent_id
        ),
        None,
    )


def find_reservation(registry: dict[str, Any], setup_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in registry["setup_reservations"] if item["setup_id"] == setup_id), None
    )


def lease_is_live(lease: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if lease is None:
        return False
    expires = parse_timestamp(lease.get("expires_at"))
    return expires is not None and expires >= (now or utc_now())


def new_lease(
    *,
    owner: str,
    lease_id: str,
    controller_instance_id: str | None,
    session_id: str | None,
    phase: str,
    reason: str,
    mode: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or utc_now()
    lease = {
        "owner": owner,
        "lease_id": lease_id,
        "controller_instance_id": controller_instance_id,
        "session_id": session_id,
        "phase": phase,
        "reason": reason,
        "lifecycle_mode": mode,
        "acquired_at": when.isoformat(),
        "last_heartbeat": when.isoformat(),
        "expires_at": (when + timedelta(seconds=ttl_seconds)).isoformat(),
        "ttl_seconds": ttl_seconds,
    }
    _validate_lease(lease)
    return lease


def _entry_or_error(
    registry: dict[str, Any], change_id: str, agent_id: str | None
) -> dict[str, Any]:
    entry = find_entry(registry, change_id, agent_id)
    if entry is None:
        raise LifecycleError(f"no registry entry for {change_id}/{agent_id or 'parent'}")
    return entry


def _exact_fence(lease: dict[str, Any], owner: str, lease_id: str, controller: str | None) -> None:
    if lease.get("owner") != owner:
        raise OwnerConflict("lease owner mismatch")
    if lease.get("lease_id") != lease_id or lease.get("controller_instance_id") != controller:
        raise FenceConflict("lease fencing token mismatch")


def acquire_lease(
    repo_root: Path,
    change_id: str,
    agent_id: str | None,
    *,
    owner: str,
    lease_id: str,
    controller_instance_id: str,
    phase: str,
    reason: str,
    mode: str = "standalone",
    session_id: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
    allow_unleased: bool = False,
) -> dict[str, Any]:
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        if any(
            r["change_id"] == change_id and r.get("agent_id") == agent_id
            for r in registry["setup_reservations"]
        ):
            raise RecoveryRequired("setup reservation is unfinished")
        entry = _entry_or_error(registry, change_id, agent_id)
        if entry["recovery_required"]:
            raise RecoveryRequired(entry["recovery_reason"])
        lease = entry["activity_lease"]
        if lease is None:
            if not allow_unleased:
                _quarantine(
                    entry, source="legacy-adoption", reason="pre-existing-unleased-state", now=when
                )
                return copy.deepcopy(entry), "unleased state requires explicit recovery"
        elif lease_is_live(lease, now=when):
            if lease["owner"] != owner:
                raise LeaseOwnedByAnother(f"live lease owned by {lease['owner']}")
            if (
                lease["lease_id"] != lease_id
                or lease["controller_instance_id"] != controller_instance_id
            ):
                raise FenceConflict("live lease fence mismatch")
            lease["phase"] = phase
            lease["reason"] = reason
            lease["last_heartbeat"] = when.isoformat()
            lease["expires_at"] = (when + timedelta(seconds=ttl_seconds)).isoformat()
            lease["ttl_seconds"] = ttl_seconds
            return copy.deepcopy(entry), None
        else:
            if lease["lease_id"] == lease_id:
                raise FenceConflict("expired acquisition must rotate lease id")
            if not allow_unleased:
                _quarantine(
                    entry,
                    source="expired-takeover",
                    reason="expired-lease-requires-assessment",
                    now=when,
                )
                return copy.deepcopy(entry), "expired lease requires safe assessment"
        entry["activity_lease"] = new_lease(
            owner=owner,
            lease_id=lease_id,
            controller_instance_id=controller_instance_id,
            session_id=session_id,
            phase=phase,
            reason=reason,
            mode=mode,
            ttl_seconds=ttl_seconds,
            now=when,
        )
        return copy.deepcopy(entry), None

    entry, recovery_error = mutate_registry(repo_root, apply)
    if recovery_error:
        raise RecoveryRequired(recovery_error)
    return entry


def renew_lease(
    repo_root: Path,
    change_id: str,
    agent_id: str | None,
    *,
    owner: str,
    lease_id: str,
    controller_instance_id: str,
    phase: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_or_error(registry, change_id, agent_id)
        lease = entry["activity_lease"]
        if lease is None or not lease_is_live(lease, now=when):
            raise FenceConflict("lease is absent or expired")
        _exact_fence(lease, owner, lease_id, controller_instance_id)
        if phase:
            lease["phase"] = phase
        lease["last_heartbeat"] = when.isoformat()
        lease["expires_at"] = (when + timedelta(seconds=ttl_seconds)).isoformat()
        lease["ttl_seconds"] = ttl_seconds
        return copy.deepcopy(entry)

    return mutate_registry(repo_root, apply)


def assert_owned(
    repo_root: Path,
    change_id: str,
    agent_id: str | None,
    *,
    owner: str,
    lease_id: str,
    controller_instance_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    registry = read_registry(repo_root)
    entry = _entry_or_error(registry, change_id, agent_id)
    lease = entry["activity_lease"]
    if lease is None or not lease_is_live(lease, now=now):
        raise FenceConflict("lease is absent or expired")
    _exact_fence(lease, owner, lease_id, controller_instance_id)
    return copy.deepcopy(entry)


def _quarantine(
    entry: dict[str, Any], *, source: str, reason: str, now: datetime, clear_lease: bool = False
) -> None:
    lease = entry.get("activity_lease")
    entry["recovery_required"] = True
    entry["recovery_reason"] = reason
    entry["recovery_context"] = {
        "source": source,
        "prior_owner": lease.get("owner") if lease else None,
        "prior_lease_id": lease.get("lease_id") if lease else None,
        "prior_controller_instance_id": lease.get("controller_instance_id") if lease else None,
        "process_evidence_key": process_evidence_key(
            entry["change_id"], entry.get("agent_id"), entry["entry_generation"], lease["lease_id"]
        )
        if lease
        else None,
        "quarantined_at": now.isoformat(),
    }
    if clear_lease:
        entry["activity_lease"] = None


def release_lease(
    repo_root: Path,
    change_id: str,
    agent_id: str | None,
    *,
    owner: str,
    lease_id: str,
    controller_instance_id: str | None,
    now: datetime | None = None,
    checkout_present: bool = True,
    recovery_reason: str = "explicit-lease-release",
) -> dict[str, Any]:
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_or_error(registry, change_id, agent_id)
        lease = entry["activity_lease"]
        if lease is None:
            return {
                "released": False,
                "recovery_required": entry["recovery_required"],
                **copy.deepcopy(entry),
            }
        if controller_instance_id is None and not (
            lease["phase"] == "LEGACY"
            and lease["lifecycle_mode"] == "manual"
            and lease["controller_instance_id"] is None
        ):
            raise FenceConflict("controller id is required")
        _exact_fence(lease, owner, lease_id, controller_instance_id)
        if checkout_present:
            _quarantine(
                entry, source="explicit-release", reason=recovery_reason, now=when, clear_lease=True
            )
        else:
            entry["activity_lease"] = None
        return {"released": True, **copy.deepcopy(entry)}

    return mutate_registry(repo_root, apply)


def release_matching(
    repo_root: Path,
    *,
    owner: str | None = None,
    session_id: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if (owner is None) == (session_id is None):
        raise LifecycleError("exactly one owner or session_id selector is required")
    if session_id == "":
        raise LifecycleError("empty session id is not a wildcard")
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> list[dict[str, Any]]:
        released: list[dict[str, Any]] = []
        for entry in registry["entries"]:
            lease = entry["activity_lease"]
            if lease is None:
                continue
            matches = (
                lease["owner"] == owner
                if owner is not None
                else lease.get("session_id") == session_id
            )
            if not matches:
                continue
            source = "owner-release" if owner is not None else "session-release"
            _quarantine(
                entry, source=source, reason=f"{source}-recovery", now=when, clear_lease=True
            )
            released.append(copy.deepcopy(entry))
        return released

    return mutate_registry(repo_root, apply)


def set_retention(
    repo_root: Path, change_id: str, agent_id: str | None, *, reason: str
) -> dict[str, Any]:
    if not reason:
        raise LifecycleError("retention reason is required")

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_or_error(registry, change_id, agent_id)
        entry["retained"] = True
        entry["retention_reason"] = reason
        return copy.deepcopy(entry)

    return mutate_registry(repo_root, apply)


def clear_retention(repo_root: Path, change_id: str, agent_id: str | None) -> dict[str, Any]:
    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_or_error(registry, change_id, agent_id)
        entry["retained"] = False
        entry["retention_reason"] = None
        return copy.deepcopy(entry)

    return mutate_registry(repo_root, apply)


def reserve_setup(
    repo_root: Path,
    *,
    setup_id: str,
    change_id: str,
    agent_id: str | None,
    branch: str,
    worktree_path: str,
    entry_generation: str,
    durability_target: dict[str, Any],
    lease_intent: dict[str, Any],
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_SETUP_TTL_SECONDS,
) -> dict[str, Any]:
    when = now or utc_now()
    if not 60 <= ttl_seconds <= 86400:
        raise LifecycleError("setup reservation ttl must be between 60 and 86400 seconds")

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        existing = find_reservation(registry, setup_id)
        candidate = {
            "setup_id": setup_id,
            "change_id": change_id,
            "agent_id": agent_id,
            "branch": branch,
            "worktree_path": worktree_path,
            "entry_generation": entry_generation,
            "durability_target": copy.deepcopy(durability_target),
            "lease_intent": copy.deepcopy(lease_intent),
            "state": "reserved",
            "created_at": when.isoformat(),
            "updated_at": when.isoformat(),
            "ttl_seconds": ttl_seconds,
            "expires_at": (when + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        if existing is not None:
            identity_fields = (
                "setup_id",
                "change_id",
                "agent_id",
                "branch",
                "worktree_path",
                "entry_generation",
                "durability_target",
                "lease_intent",
                "ttl_seconds",
            )
            comparable = {key: existing[key] for key in identity_fields}
            expected = {key: candidate[key] for key in identity_fields}
            if comparable != expected:
                raise FenceConflict("setup id belongs to different intent")
            if parse_timestamp(existing["expires_at"]) < when:
                raise RecoveryRequired("setup reservation expired; reconcile explicitly")
            return copy.deepcopy(existing)
        if find_entry(registry, change_id, agent_id) is not None:
            raise RecoveryRequired("registry entry already exists")
        registry["setup_reservations"].append(candidate)
        return copy.deepcopy(candidate)

    return mutate_registry(repo_root, apply)


def advance_reservation(
    repo_root: Path,
    setup_id: str,
    entry_generation: str,
    state: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    order = {"reserved": 0, "checkout-created": 1, "evidence-created": 2}
    if state not in order:
        raise LifecycleError("invalid setup reservation state")
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        reservation = find_reservation(registry, setup_id)
        if reservation is None or reservation["entry_generation"] != entry_generation:
            raise FenceConflict("setup reservation fence mismatch")
        if parse_timestamp(reservation["expires_at"]) < when:
            raise RecoveryRequired("setup reservation expired")
        if order[state] < order[reservation["state"]]:
            raise FenceConflict("setup reservation cannot move backward")
        reservation["state"] = state
        reservation["updated_at"] = when.isoformat()
        return copy.deepcopy(reservation)

    return mutate_registry(repo_root, apply)


def publish_reservation(
    repo_root: Path, setup_id: str, entry_generation: str, *, now: datetime | None = None
) -> dict[str, Any]:
    when = now or utc_now()

    def apply(registry: dict[str, Any]) -> dict[str, Any]:
        reservation = find_reservation(registry, setup_id)
        if reservation is None or reservation["entry_generation"] != entry_generation:
            raise FenceConflict("setup reservation fence mismatch")
        if reservation["state"] != "evidence-created":
            raise RecoveryRequired("setup side effects are incomplete")
        if parse_timestamp(reservation["expires_at"]) < when:
            raise RecoveryRequired("setup reservation expired")
        intent = reservation["lease_intent"]
        lease = new_lease(
            owner=intent["owner"],
            lease_id=intent["lease_id"],
            controller_instance_id=intent["controller_instance_id"],
            session_id=intent["session_id"],
            phase=intent["phase"],
            reason=intent["reason"],
            mode=intent["lifecycle_mode"],
            ttl_seconds=intent["ttl_seconds"],
            now=when,
        )
        entry = {
            "change_id": reservation["change_id"],
            "agent_id": reservation["agent_id"],
            "branch": reservation["branch"],
            "worktree_path": reservation["worktree_path"],
            "created_at": reservation["created_at"],
            "entry_generation": entry_generation,
            "setup_id": setup_id,
            "durability_target": copy.deepcopy(reservation["durability_target"]),
            "retained": False,
            "retention_reason": None,
            "recovery_required": False,
            "recovery_reason": None,
            "recovery_context": None,
            "activity_lease": lease,
        }
        registry["entries"].append(entry)
        registry["setup_reservations"].remove(reservation)
        return copy.deepcopy(entry)

    return mutate_registry(repo_root, apply)


def completed_setup_replay(
    repo_root: Path,
    *,
    setup_id: str,
    change_id: str,
    agent_id: str | None,
    entry_generation: str,
    durability_target: dict[str, Any] | None,
    owner: str,
    lease_id: str,
    controller_instance_id: str,
) -> dict[str, Any]:
    entry = find_entry(read_registry(repo_root), change_id, agent_id)
    if entry is None:
        raise LifecycleError("completed setup entry not found")
    lease = entry["activity_lease"]
    if not (
        entry["setup_id"] == setup_id
        and entry["entry_generation"] == entry_generation
        and entry["durability_target"] == durability_target
        and lease
        and lease["owner"] == owner
        and lease["lease_id"] == lease_id
        and lease["controller_instance_id"] == controller_instance_id
    ):
        raise FenceConflict("completed setup does not match exact replay identity")
    return copy.deepcopy(entry)


def append_audit(registry: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    event = copy.deepcopy(event)
    event.setdefault("event_id", uuid.uuid4().hex)
    if any(item["event_id"] == event["event_id"] for item in registry["recovery_audit"]):
        raise FenceConflict("recovery audit event id already exists")
    registry["recovery_audit"].append(event)
    return event


def process_evidence_key(
    change_id: str, agent_id: str | None, entry_generation: str, lease_id: str
) -> str:
    return hashlib.sha256(
        _length_prefix((change_id, agent_id, entry_generation, lease_id))
    ).hexdigest()


def evidence_path(
    repo_root: Path, change_id: str, agent_id: str | None, entry_generation: str, lease_id: str
) -> Path:
    return (
        evidence_directory(repo_root)
        / f"{process_evidence_key(change_id, agent_id, entry_generation, lease_id)}.json"
    )


def _process_start_token(pid: int) -> str:
    proc = Path(f"/proc/{pid}/stat")
    if proc.is_file():
        try:
            return proc.read_text().split()[21]
        except (OSError, IndexError):
            pass
    result = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    token = result.stdout.strip()
    if result.returncode == 0 and token:
        return f"ps:{token}"
    raise LifecycleError("process start token unsupported")


def host_id() -> str:
    boot = Path("/proc/sys/kernel/random/boot_id")
    if boot.is_file():
        with contextlib.suppress(OSError):
            return f"{socket.gethostname()}:{boot.read_text().strip()}"
    return socket.gethostname()


def write_process_evidence(
    repo_root: Path,
    *,
    change_id: str,
    agent_id: str | None,
    entry_generation: str,
    lease_id: str,
    owner: str,
    controller_instance_id: str,
    pid: int | None = None,
    process_start_token: str | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    when = now or utc_now()
    actual_pid = pid or os.getpid()
    payload = {
        "schema_version": 1,
        "change_id": change_id,
        "agent_id": agent_id,
        "entry_generation": entry_generation,
        "lease_id": lease_id,
        "owner": owner,
        "pid": actual_pid,
        "process_start_token": process_start_token or _process_start_token(actual_pid),
        "host_id": host_id(),
        "controller_instance_id": controller_instance_id,
        "written_at": when.isoformat(),
        "last_seen_at": when.isoformat(),
    }
    directory = evidence_directory(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    key = process_evidence_key(change_id, agent_id, entry_generation, lease_id)
    path = directory / f"{key}.json"
    fd, temporary = tempfile.mkstemp(prefix=f".{key}.", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return key, payload


def read_process_evidence(
    repo_root: Path,
    *,
    change_id: str,
    agent_id: str | None,
    entry_generation: str,
    lease_id: str,
    owner: str,
    controller_instance_id: str | None,
) -> dict[str, Any]:
    path = evidence_path(repo_root, change_id, agent_id, entry_generation, lease_id)
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RecoveryRequired("process evidence missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryRequired("process evidence unreadable") from exc
    expected = {
        "change_id": change_id,
        "agent_id": agent_id,
        "entry_generation": entry_generation,
        "lease_id": lease_id,
        "owner": owner,
        "controller_instance_id": controller_instance_id,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RecoveryRequired("process evidence identity mismatch")
    return payload


def classify_process_evidence(payload: dict[str, Any]) -> str:
    if payload.get("host_id") != host_id():
        return "indeterminate"
    pid = payload.get("pid")
    if not isinstance(pid, int) or pid < 1:
        return "indeterminate"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "stale"
    except (PermissionError, OSError):
        return "indeterminate"
    try:
        current = _process_start_token(pid)
    except LifecycleError:
        return "indeterminate"
    return "live" if current == payload.get("process_start_token") else "stale"


def canonicalize_remote_url(url: str) -> str:
    """Strip credentials without otherwise normalizing a Git fetch URL."""
    if "://" in url:
        scheme, remainder = url.split("://", 1)
        authority, separator, suffix = remainder.partition("/")
        if "@" in authority:
            authority = authority.rsplit("@", 1)[1]
        return f"{scheme}://{authority}{separator}{suffix}"
    if "@" in url and ":" in url.split("@", 1)[1]:
        return url.split("@", 1)[1]
    return url


def remote_url_digest(url: str) -> str:
    return hashlib.sha256(canonicalize_remote_url(url).encode("utf-8")).hexdigest()


def make_durability_target(remote_name: str, ref_name: str, remote_url: str) -> dict[str, str]:
    prefix = f"refs/remotes/{remote_name}/"
    if not remote_name or not ref_name.startswith(prefix) or len(ref_name) == len(prefix):
        raise LifecycleError("durability ref remote component must match durability remote")
    return {
        "remote_name": remote_name,
        "remote_url_hash_algorithm": "git-remote-url-v1",
        "canonical_remote_url_sha256": remote_url_digest(remote_url),
        "ref_name": ref_name,
    }
