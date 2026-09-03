"""Provider-neutral host adapter for delegated roadmap execution.

The module owns durable launch arbitration around the roadmap orchestrator's
prepare/apply seam.  Host and liveness operations are injected; this file never
selects a provider or starts a model client.
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import functools
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

_SCRIPTS_ROOT = Path(__file__).resolve().parent
_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SCRIPTS = _SKILLS_ROOT / "roadmap-runtime" / "scripts"
_ORCHESTRATOR_SCRIPTS = _SKILLS_ROOT / "autopilot-roadmap" / "scripts"
for _directory in (_SCRIPTS_ROOT, _SKILLS_ROOT, _RUNTIME_SCRIPTS, _ORCHESTRATOR_SCRIPTS):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from checkpoint import CheckpointManager  # type: ignore[import-untyped]  # noqa: E402
from models import load_roadmap, validate_delegated_dispatch_attempt  # type: ignore[import-untyped]  # noqa: E402
from orchestrator import (  # type: ignore[import-untyped]  # noqa: E402
    apply_delegated_batch,
    prepare_delegated_batch,
)

import gate_router  # type: ignore[import-untyped]  # noqa: E402
from shared.trust_posture import Gate  # noqa: E402


Clock = Callable[[], datetime]
BranchResolver = Callable[[Path], str]
CommitResolver = Callable[[Path], str]
HostEntry = Callable[[str, dict[str, Any]], Any]
Liveness = Literal["live", "dead", "terminal", "unknown"]
LivenessProbe = Callable[[str], Liveness | Mapping[str, Any]]
IsolationResolver = Callable[[Any], Mapping[str, Any]]
DispatchFn = Callable[[str, str, dict[str, Any]], Any]

_CHANGE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SECRET_KEY = re.compile(
    r"secret|token|password|credential|api[_-]?key|private[_-]?key|auth|cookie|"
    r"raw[_-]?response|transcript",
    re.IGNORECASE,
)
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_RESULT_OUTCOME = re.compile(r"^(success|failed:.+|vendor_limit:[^:]+:.+|parked)$")
_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
_RESULT_REQUIRED = {
    "schema_version",
    "dispatch_id",
    "change_id",
    "attempt",
    "lease_generation",
    "outcome",
}
_RESULT_ALLOWED = _RESULT_REQUIRED | {
    "replan",
    "handoff_id",
    "worktree_path",
    "branch",
    "parked",
    "evidence",
}


class ExecutionStateError(ValueError):
    """A durable generation cannot make the requested state transition."""


class ResultFileObserver(Protocol):
    """Optional test/host observation seam for the bounded temporary result file."""

    def __call__(self, path: Path) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat()


def _contains(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


@contextlib.contextmanager
def _state_lock(workspace: Path) -> Iterator[None]:
    """Serialize checkpoint read-modify-write transitions across host tasks."""
    identity = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()
    lock_dir = Path(tempfile.gettempdir()) / "supervised-dispatch-state-locks"
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = lock_dir / f"{identity}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _serialized_transition(method: Callable[..., Any]) -> Callable[..., Any]:
    """Run one workspace state transition under the shared advisory lock."""

    @functools.wraps(method)
    def wrapped(self: Any, workspace: Path, *args: Any, **kwargs: Any) -> Any:
        with _state_lock(workspace):
            return method(self, workspace, *args, **kwargs)

    return wrapped


def _bounded_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep JSON copy after enforcing the frozen recursive bounds."""

    def visit(candidate: Any, *, depth: int) -> Any:
        if not isinstance(candidate, dict) or depth > 4 or len(candidate) > 32:
            raise ValueError("dispatch context must be an object bounded to four levels")
        result: dict[str, Any] = {}
        for key, child in candidate.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("dispatch context keys must be 1-64 character strings")
            if _SECRET_KEY.search(key):
                raise ValueError(f"dispatch context contains forbidden key: {key}")
            if isinstance(child, dict):
                result[key] = visit(child, depth=depth + 1)
            elif isinstance(child, list):
                if len(child) > 64 or any(isinstance(item, (dict, list)) for item in child):
                    raise ValueError("dispatch context arrays must contain at most 64 scalars")
                result[key] = [scalar(item) for item in child]
            else:
                result[key] = scalar(child)
        return result

    def scalar(candidate: Any) -> Any:
        if isinstance(candidate, str):
            if len(candidate) > 4096:
                raise ValueError("dispatch context strings must not exceed 4096 characters")
            return candidate
        if candidate is None or isinstance(candidate, (bool, int)):
            return candidate
        if isinstance(candidate, float) and math.isfinite(candidate):
            return candidate
        raise ValueError("dispatch context values must be finite JSON scalars")

    sanitized = visit(dict(value), depth=1)
    canonical = json.dumps(
        sanitized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(canonical) > 16 * 1024:
        raise ValueError("dispatch context canonical JSON must not exceed 16 KiB")
    return sanitized


def _load_attempt(
    workspace: Path,
    dispatch_id: str,
    *,
    repo_root: Path | None = None,
) -> tuple[CheckpointManager, Any, dict[str, Any]]:
    manager = CheckpointManager(workspace, repo_root)
    checkpoint = manager.load()
    matches = [
        attempt
        for attempt in checkpoint.dispatch_attempts
        if attempt.get("dispatch_id") == dispatch_id
    ]
    if len(matches) != 1:
        raise ExecutionStateError(f"unknown or duplicate dispatch attempt: {dispatch_id}")
    return manager, checkpoint, matches[0]


def _request(checkpoint: Any, attempt: Mapping[str, Any]) -> dict[str, Any]:
    request = {
        "schema_version": 1,
        "dispatch_id": attempt["dispatch_id"],
        "roadmap_id": checkpoint.roadmap_id,
        "item_id": attempt["item_id"],
        "change_id": attempt["change_id"],
        "phase": "autopilot",
        "attempt": attempt["attempt"],
        "launch_token": attempt["launch_token"],
        "lease_generation": attempt["lease_generation"],
        "launch_marker_path": attempt["launch_marker_path"],
        "scope": copy.deepcopy(attempt["scope"]),
        "isolation": copy.deepcopy(attempt["isolation"]),
        "context": copy.deepcopy(attempt["context"]),
    }
    if "continuation" in attempt:
        request["continuation"] = copy.deepcopy(attempt["continuation"])
    return request


def _history(
    attempt: dict[str, Any],
    *,
    state: str,
    observed_at: str,
    generation: int | None = None,
    owner_nonce: str | None = None,
    handle: str | None = None,
) -> None:
    lease = attempt.get("lease", {})
    entry: dict[str, Any] = {
        "generation": generation if generation is not None else attempt["lease_generation"],
        "owner_nonce": owner_nonce or lease.get("owner_nonce", "unknown-owner-0000"),
        "state": state,
        "marker_path": attempt["launch_marker_path"],
        "observed_at": observed_at,
    }
    if handle is not None:
        entry["handle"] = handle
    history = attempt["launch_history"]
    if len(history) >= 64:
        raise ExecutionStateError("dispatch launch history is full")
    history.append(entry)


def _marker(attempt: Mapping[str, Any]) -> Path:
    root = Path(attempt["isolation"]["worktree_path"]).resolve()
    marker = (root / attempt["launch_marker_path"]).resolve(strict=False)
    if not _contains(root, marker):
        raise ExecutionStateError("launch marker escapes verified worktree")
    return marker


def _write_marker_exclusive(
    attempt: Mapping[str, Any],
    *,
    generation: int,
    owner_nonce: str,
    continuation: Mapping[str, Any] | None = None,
) -> None:
    marker = _marker(attempt)
    marker.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "dispatch_id": attempt["dispatch_id"],
        "generation": generation,
        "owner_nonce": owner_nonce,
    }
    if continuation is not None:
        record["continuation"] = copy.deepcopy(dict(continuation))
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, (json.dumps(record, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _marker_record(
    attempt: Mapping[str, Any],
    *,
    generation: int,
    owner_nonce: str,
) -> dict[str, Any]:
    try:
        record = json.loads(_marker(attempt).read_text())
    except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
        raise ExecutionStateError("generation launch marker is missing or invalid") from exc
    if (
        not isinstance(record, dict)
        or record.get("dispatch_id") != attempt["dispatch_id"]
        or record.get("generation") != generation
        or record.get("owner_nonce") != owner_nonce
        or set(record) - {"dispatch_id", "generation", "owner_nonce", "continuation"}
    ):
        raise ExecutionStateError("generation launch marker identity mismatch")
    continuation = record.get("continuation")
    if continuation is not None and (
        not isinstance(continuation, dict)
        or set(continuation) != {"kind", "approval_ref"}
        or continuation.get("kind") not in {"pending_gate", "policy_pause"}
        or not isinstance(continuation.get("approval_ref"), str)
        or not 1 <= len(continuation["approval_ref"]) <= 256
    ):
        raise ExecutionStateError("generation continuation marker is invalid")
    return record


def _remove_owned_marker(attempt: Mapping[str, Any]) -> None:
    marker = _marker(attempt)
    try:
        record = json.loads(marker.read_text())
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return
    lease = attempt.get("lease", {})
    if (
        record.get("dispatch_id") == attempt["dispatch_id"]
        and record.get("generation") == lease.get("generation")
        and record.get("owner_nonce") == lease.get("owner_nonce")
    ):
        marker.unlink(missing_ok=True)


def _valid_nullable_string(value: Mapping[str, Any], field: str, limit: int) -> bool:
    candidate = value.get(field)
    return field not in value or candidate is None or (
        isinstance(candidate, str) and len(candidate) <= limit
    )


def _valid_nullable_date_time(value: Mapping[str, Any], field: str) -> bool:
    candidate = value.get(field)
    if field not in value or candidate is None:
        return True
    if not isinstance(candidate, str) or _DATE_TIME.fullmatch(candidate) is None:
        return False
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_result(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    if _RESULT_REQUIRED - result.keys() or result.keys() - _RESULT_ALLOWED:
        raise ValueError("result is not schema-valid")
    if (
        isinstance(result["schema_version"], bool)
        or not isinstance(result["schema_version"], int)
        or result["schema_version"] != 1
    ):
        raise ValueError("result is not schema-valid")
    if not isinstance(result["dispatch_id"], str) or not 1 <= len(result["dispatch_id"]) <= 256:
        raise ValueError("result is not schema-valid")
    if (
        not isinstance(result["change_id"], str)
        or len(result["change_id"]) > 160
        or _CHANGE_ID.fullmatch(result["change_id"]) is None
    ):
        raise ValueError("result is not schema-valid")
    for field in ("attempt", "lease_generation"):
        if isinstance(result[field], bool) or not isinstance(result[field], int) or result[field] < 1:
            raise ValueError("result is not schema-valid")
    outcome = result["outcome"]
    if (
        not isinstance(outcome, str)
        or len(outcome) > 1024
        or _RESULT_OUTCOME.fullmatch(outcome) is None
    ):
        raise ValueError("result is not schema-valid")
    if "replan" in result and not isinstance(result["replan"], bool):
        raise ValueError("result is not schema-valid")
    if "handoff_id" in result and result["handoff_id"] is not None and (
        not isinstance(result["handoff_id"], str) or len(result["handoff_id"]) > 256
    ):
        raise ValueError("result is not schema-valid")
    for field in ("worktree_path", "branch"):
        if field in result and (
            not isinstance(result[field], str) or not result[field]
        ):
            raise ValueError("result is not schema-valid")
    evidence = result.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, dict) or set(evidence) - {
            "loop_state_path",
            "commit",
            "loop_state_digest",
        }:
            raise ValueError("result is not schema-valid")
        if not isinstance(evidence.get("loop_state_path"), str) or not evidence["loop_state_path"]:
            raise ValueError("result is not schema-valid")
        if "commit" in evidence and (
            not isinstance(evidence["commit"], str) or _HEX_40.fullmatch(evidence["commit"]) is None
        ):
            raise ValueError("result is not schema-valid")
        if "loop_state_digest" in evidence and (
            not isinstance(evidence["loop_state_digest"], str)
            or _HEX_64.fullmatch(evidence["loop_state_digest"]) is None
        ):
            raise ValueError("result is not schema-valid")
    if outcome in {"success", "parked"}:
        if not {"worktree_path", "branch", "evidence"} <= result.keys():
            raise ValueError("result is not schema-valid")
        if not all(isinstance(result[field], str) and result[field] for field in ("worktree_path", "branch")):
            raise ValueError("result is not schema-valid")
        if not isinstance(evidence, dict) or not {"commit", "loop_state_digest"} <= evidence.keys():
            raise ValueError("result is not schema-valid")
    if outcome == "success" and (
        not isinstance(result.get("handoff_id"), str) or not result["handoff_id"]
    ):
        raise ValueError("result is not schema-valid")
    if outcome == "parked":
        parked = result.get("parked")
        if (
            not isinstance(parked, dict)
            or set(parked) - {"kind", "reason", "gate", "deadline", "resume_hint"}
            or parked.get("kind") not in {"pending_gate", "policy_pause"}
            or not isinstance(parked.get("reason"), str)
            or not parked["reason"]
            or len(parked["reason"]) > 1024
            or not _valid_nullable_string(parked, "gate", 128)
            or not _valid_nullable_date_time(parked, "deadline")
            or not _valid_nullable_string(parked, "resume_hint", 512)
        ):
            raise ValueError("result is not schema-valid")
    elif "parked" in result:
        raise ValueError("result is not schema-valid")
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(canonical) > 16 * 1024:
        raise ValueError("result is not schema-valid")
    return result


class ExecutionAdapter:
    """Durable, deterministic host adapter around delegated prepare/apply."""

    def __init__(
        self,
        *,
        managed_worktree_root: Path,
        clock: Clock = _utcnow,
        branch_resolver: BranchResolver,
        commit_resolver: CommitResolver,
        liveness_probe: LivenessProbe,
        host_entry: HostEntry,
        temp_dir: Path | None = None,
        result_file_observer: ResultFileObserver | None = None,
    ) -> None:
        self.managed_worktree_root = managed_worktree_root.resolve()
        self.clock = clock
        self.branch_resolver = branch_resolver
        self.commit_resolver = commit_resolver
        self.liveness_probe = liveness_probe
        self.host_entry = host_entry
        self.temp_dir = temp_dir
        self.result_file_observer = result_file_observer

    @_serialized_transition
    def prepare(
        self,
        workspace: Path,
        *,
        repo_root: Path,
        isolation_resolver: IsolationResolver,
        roadmap_approval_ref: str,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify roadmap-altitude approval, sanitize, verify isolation, then prepare a batch.

        `roadmap_approval_ref` must resolve to a `proceed` `roadmap_approval` gate-decision
        record whose stamped `roadmap_fingerprint` matches this roadmap's CURRENT shape
        (D3) -- raised via `gate_router.require_approval_ref` before any attempt is
        written, so a missing or stale approval never mutates roadmap execution state
        (supervise spec "Refuse unapproved roadmap execution").
        """
        # Pure context validation first, with zero I/O — an unsafe context is
        # rejected before this call touches the checkpoint at all.
        sanitized = _bounded_context(dict(context or {}))

        roadmap = load_roadmap(workspace / "roadmap.yaml", repo_root)
        approval_manager = CheckpointManager(workspace, repo_root)
        approval_checkpoint = (
            approval_manager.load() if approval_manager.exists() else approval_manager.create(roadmap)
        )
        gate_router.require_approval_ref(
            approval_checkpoint,
            roadmap_approval_ref,
            gate=Gate.ROADMAP_APPROVAL,
            roadmap_id=roadmap.roadmap_id,
            roadmap=roadmap,
        )

        seen_paths: set[Path] = set()
        seen_branches: set[str] = set()

        def verified(item: Any) -> dict[str, str]:
            change_id = item.change_id
            if not isinstance(change_id, str) or _CHANGE_ID.fullmatch(change_id) is None:
                raise ValueError("isolation requires an exact change_id")
            isolation = dict(isolation_resolver(item))
            if set(isolation) != {"mode", "worktree_path", "branch"}:
                raise ValueError("isolation must contain exactly mode, worktree_path, and branch")
            mode = isolation["mode"]
            if mode not in {"managed_worktree", "harness_provided"}:
                raise ValueError("unsupported isolation mode")
            worktree = Path(str(isolation["worktree_path"]))
            if not worktree.is_dir():
                raise ValueError("isolation worktree path does not exist")
            resolved = worktree.resolve()
            branch = str(isolation["branch"])
            actual_branch = self.branch_resolver(resolved)
            if mode == "managed_worktree":
                if not _contains(self.managed_worktree_root, resolved):
                    raise ValueError("managed worktree containment verification failed")
                expected_branch = f"openspec/{change_id}"
                if branch != expected_branch or actual_branch != expected_branch:
                    raise ValueError("managed worktree branch does not match exact change_id")
            elif actual_branch != branch:
                raise ValueError("harness-provided isolation branch mismatch")
            if resolved in seen_paths or branch in seen_branches:
                raise ValueError("delegated items require distinct verified isolation")
            seen_paths.add(resolved)
            seen_branches.add(branch)
            return {
                "mode": mode,
                "worktree_path": str(resolved),
                "branch": branch,
            }

        return prepare_delegated_batch(
            workspace,
            repo_root=repo_root,
            isolation_resolver=verified,
            context=sanitized,
        )

    @_serialized_transition
    def child_start(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
        launch_token: str,
        lease_generation: int,
        owner_nonce: str,
        lease_seconds: int = 60,
    ) -> dict[str, Any]:
        """CAS-claim a generation, create its marker, and wait for host ack."""
        if (
            not isinstance(owner_nonce, str)
            or re.fullmatch(r"[A-Za-z0-9._~-]{16,256}", owner_nonce) is None
        ):
            raise ValueError("lease owner nonce must be an opaque 16-256 character identifier")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
        if launch_token != attempt["launch_token"]:
            raise ExecutionStateError("launch token mismatch")
        now = self.clock()
        now_text = _iso(now)
        generation = attempt["lease_generation"]
        candidate = copy.deepcopy(attempt)
        if attempt["status"] == "claimed":
            lease = attempt["lease"]
            expires = datetime.fromisoformat(lease["expires_at"])
            if attempt["launch_gate"]["state"] != "waiting_ack" or now <= expires:
                raise ExecutionStateError("dispatch generation already has an active lease owner")
            if lease_generation != generation:
                raise ExecutionStateError("stale lease generation")
            old_generation = generation
            old_owner = lease["owner_nonce"]
            _remove_owned_marker(attempt)
            generation += 1
            candidate["lease_generation"] = generation
            _history(
                candidate,
                state="stale_takeover",
                observed_at=now_text,
                generation=old_generation,
                owner_nonce=old_owner,
            )
            for field in ("lease", "launch_evidence", "launch_gate"):
                candidate.pop(field, None)
        elif attempt["status"] == "prepared":
            if lease_generation != generation:
                raise ExecutionStateError("stale lease generation")
        else:
            raise ExecutionStateError(f"dispatch attempt is not claimable: {attempt['status']}")

        continuation = copy.deepcopy(candidate.get("continuation"))
        expires_text = _iso(now + timedelta(seconds=lease_seconds))
        candidate.update(
            status="claimed",
            lease={
                "generation": generation,
                "owner_nonce": owner_nonce,
                "state": "active",
                "acquired_at": now_text,
                "heartbeat_at": now_text,
                "expires_at": expires_text,
            },
            launch_evidence={
                "kind": "child_marker",
                "generation": generation,
                "marker_path": candidate["launch_marker_path"],
                "observed_at": now_text,
            },
            launch_gate={
                "generation": generation,
                "state": "waiting_ack",
                "handle": None,
                "go_released_at": None,
                "entered_at": None,
            },
        )
        _history(candidate, state="claimed", observed_at=now_text)
        validate_delegated_dispatch_attempt(candidate)
        original = copy.deepcopy(attempt)
        attempt.clear()
        attempt.update(candidate)
        manager.save(checkpoint)
        try:
            _write_marker_exclusive(
                candidate,
                generation=generation,
                owner_nonce=owner_nonce,
                continuation=continuation,
            )
        except BaseException:
            attempt.clear()
            attempt.update(original)
            manager.save(checkpoint)
            raise
        return copy.deepcopy(attempt)

    @_serialized_transition
    def heartbeat_waiting(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
        lease_generation: int,
        owner_nonce: str,
        lease_seconds: int = 60,
    ) -> dict[str, Any]:
        """Refresh only the child-owned pre-ack waiting lease."""
        manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
        lease = attempt.get("lease", {})
        if attempt["status"] != "claimed" or attempt.get("launch_gate", {}).get("state") != "waiting_ack":
            raise ExecutionStateError("dispatch attempt is not waiting for acknowledgement")
        if attempt["lease_generation"] != lease_generation:
            raise ExecutionStateError("stale lease generation")
        if lease.get("owner_nonce") != owner_nonce:
            raise ExecutionStateError("lease owner mismatch")
        now = self.clock()
        now_text = _iso(now)
        lease["heartbeat_at"] = now_text
        lease["expires_at"] = _iso(now + timedelta(seconds=lease_seconds))
        _history(attempt, state="heartbeat", observed_at=now_text)
        validate_delegated_dispatch_attempt(attempt)
        manager.save(checkpoint)
        return copy.deepcopy(attempt)

    @_serialized_transition
    def acknowledge(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
        lease_generation: int,
        handle: str,
    ) -> dict[str, Any]:
        """Atomically persist the durable host handle and release go."""
        if not isinstance(handle, str) or not handle or len(handle) > 256:
            raise ValueError("host handle must be a 1-256 character string")
        manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
        if attempt["status"] != "claimed" or attempt["lease_generation"] != lease_generation:
            raise ExecutionStateError("acknowledgement generation is not claimed")
        if attempt["launch_gate"]["state"] != "waiting_ack":
            raise ExecutionStateError("launch gate is not waiting for acknowledgement")
        now_text = _iso(self.clock())
        attempt.update(
            status="acknowledged",
            launch_evidence={
                "kind": "host_ack",
                "generation": lease_generation,
                "handle": handle,
                "observed_at": now_text,
            },
            launch_gate={
                "generation": lease_generation,
                "state": "go_released",
                "handle": handle,
                "go_released_at": now_text,
                "entered_at": None,
            },
        )
        _history(attempt, state="acknowledged", observed_at=now_text, handle=handle)
        _history(attempt, state="go_released", observed_at=now_text, handle=handle)
        validate_delegated_dispatch_attempt(attempt)
        manager.save(checkpoint)
        return copy.deepcopy(attempt)

    def _verify_current_isolation(self, attempt: Mapping[str, Any]) -> Path:
        isolation = attempt["isolation"]
        worktree = Path(isolation["worktree_path"])
        if not worktree.is_dir():
            raise ExecutionStateError("isolation worktree path no longer exists")
        resolved = worktree.resolve()
        if str(resolved) != isolation["worktree_path"]:
            raise ExecutionStateError("isolation worktree realpath changed")
        branch = isolation["branch"]
        actual_branch = self.branch_resolver(resolved)
        if isolation["mode"] == "managed_worktree":
            if not _contains(self.managed_worktree_root, resolved):
                raise ExecutionStateError("managed worktree containment verification failed")
            expected_branch = f"openspec/{attempt['change_id']}"
            if branch != expected_branch or actual_branch != expected_branch:
                raise ExecutionStateError("managed worktree branch does not match exact change_id")
        elif actual_branch != branch:
            raise ExecutionStateError("harness-provided isolation branch mismatch")
        return resolved

    def enter(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
        lease_generation: int,
        owner_nonce: str,
    ) -> dict[str, Any]:
        """Revalidate ownership and durable go immediately before host entry."""
        with _state_lock(workspace):
            manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
            lease = attempt.get("lease", {})
            gate = attempt.get("launch_gate", {})
            if attempt["status"] != "acknowledged" or gate.get("state") != "go_released":
                raise ExecutionStateError("go has not been released for this generation")
            if (
                attempt["lease_generation"] != lease_generation
                or lease.get("generation") != lease_generation
            ):
                raise ExecutionStateError("stale lease generation")
            if lease.get("owner_nonce") != owner_nonce or lease.get("state") != "active":
                raise ExecutionStateError("lease owner mismatch")
            self._verify_current_isolation(attempt)
            marker_record = _marker_record(
                attempt,
                generation=lease_generation,
                owner_nonce=owner_nonce,
            )
            now_text = _iso(self.clock())
            attempt["status"] = "launched"
            gate["state"] = "entered"
            gate["entered_at"] = now_text
            _history(attempt, state="entered", observed_at=now_text, handle=gate["handle"])
            validate_delegated_dispatch_attempt(attempt)
            manager.save(checkpoint)
            request = _request(checkpoint, attempt)
            if "continuation" in marker_record:
                request["continuation"] = copy.deepcopy(marker_record["continuation"])
            change_id = attempt["change_id"]
            entered_attempt = copy.deepcopy(attempt)
        self.host_entry(change_id, request)
        return entered_attempt

    @_serialized_transition
    def reconcile(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
    ) -> dict[str, Any]:
        """Reconcile positive liveness; quarantine uncertainty after durable go."""
        manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
        if attempt["status"] in {"completed", "failed", "parked"}:
            return copy.deepcopy(attempt)
        gate = attempt.get("launch_gate", {})
        handle = gate.get("handle")
        if not isinstance(handle, str) or not handle:
            return copy.deepcopy(attempt)
        observation = self.liveness_probe(handle)
        if isinstance(observation, Mapping):
            state = observation.get("state")
        else:
            state = observation
        if state == "live":
            return copy.deepcopy(attempt)
        if state == "terminal":
            result = observation.get("result") if isinstance(observation, Mapping) else None
            return {"state": "terminal", "attempt": copy.deepcopy(attempt), "result": copy.deepcopy(result)}
        if state not in {"dead", "unknown"}:
            state = "unknown"
        now_text = _iso(self.clock())
        if state == "unknown":
            if gate.get("state") not in {"go_released", "entered"}:
                return copy.deepcopy(attempt)
            attempt["status"] = "quarantined"
            attempt["lease"]["state"] = "uncertain"
            attempt["quarantine"] = {
                "kind": "unknown_liveness",
                "reason": "durable host handle liveness is unknown after go",
                "observed_at": now_text,
            }
            _history(attempt, state="quarantined", observed_at=now_text, handle=handle)
            validate_delegated_dispatch_attempt(attempt)
            manager.save(checkpoint)
            return copy.deepcopy(attempt)

        old_generation = attempt["lease_generation"]
        old_owner = attempt["lease"]["owner_nonce"]
        _remove_owned_marker(attempt)
        _history(
            attempt,
            state="stale_takeover",
            observed_at=now_text,
            generation=old_generation,
            owner_nonce=old_owner,
            handle=handle,
        )
        attempt["status"] = "prepared"
        attempt["lease_generation"] = old_generation + 1
        for field in (
            "lease",
            "launch_evidence",
            "launch_gate",
            "quarantine",
            "parked",
            "outcome",
            "resolved_at",
            "handoff_id",
        ):
            attempt.pop(field, None)
        validate_delegated_dispatch_attempt(attempt)
        manager.save(checkpoint)
        return copy.deepcopy(attempt)

    @_serialized_transition
    def resume(
        self,
        workspace: Path,
        *,
        dispatch_id: str,
        approval_ref: str,
        kind: str,
    ) -> dict[str, Any]:
        """CAS an authorized gate/policy parked attempt into a new generation."""
        if not isinstance(approval_ref, str) or not approval_ref or len(approval_ref) > 256:
            raise ValueError("approval reference must be a 1-256 character string")
        if kind not in {"pending_gate", "policy_pause"}:
            raise ValueError("continuation kind must be pending_gate or policy_pause")
        manager, checkpoint, attempt = _load_attempt(workspace, dispatch_id)
        if attempt["status"] == "quarantined":
            raise ExecutionStateError("quarantined dispatch cannot use approval resume")
        if attempt["status"] != "parked":
            raise ExecutionStateError("dispatch attempt is not parked")
        if attempt["parked"]["kind"] != kind:
            raise ExecutionStateError("parked continuation kind mismatch")
        # The expected gate is the parked attempt's own -- escalate_resume for a
        # policy_pause (resolve_parked's own mapping, D4), the child's recorded
        # gate for a pending_gate -- checked while "parked" is still present,
        # since it is popped below. Only roadmap_approval references carry a
        # fingerprint, and a parked child's gate is never that one, so no
        # `roadmap` is passed.
        expected_gate = (
            Gate.ESCALATE_RESUME if kind == "policy_pause" else Gate(attempt["parked"]["gate"])
        )
        gate_router.require_approval_ref(
            checkpoint, approval_ref, gate=expected_gate, dispatch_id=dispatch_id
        )
        _remove_owned_marker(attempt)
        attempt["status"] = "prepared"
        attempt["lease_generation"] += 1
        attempt["continuation"] = {"kind": kind, "approval_ref": approval_ref}
        for field in (
            "lease",
            "launch_evidence",
            "launch_gate",
            "parked",
            "quarantine",
            "outcome",
            "resolved_at",
            "handoff_id",
        ):
            attempt.pop(field, None)
        validate_delegated_dispatch_attempt(attempt)
        manager.save(checkpoint)
        return _request(checkpoint, attempt)

    @_serialized_transition
    def apply(
        self,
        workspace: Path,
        *,
        batch_id: str,
        results: Sequence[Mapping[str, Any]],
        dispatch_fn: DispatchFn,
        repo_root: Path,
    ) -> dict[str, Any]:
        """Validate exact bounded evidence via an OS temp file, then apply once."""
        manager = CheckpointManager(workspace, repo_root)
        checkpoint = manager.load()
        attempts = {attempt["dispatch_id"]: attempt for attempt in checkpoint.dispatch_attempts}
        validated = [_validate_result(result) for result in results]
        for result in validated:
            attempt = attempts.get(result["dispatch_id"])
            if attempt is None:
                raise ValueError("dispatch identity mismatch")
            for field in ("change_id", "attempt", "lease_generation"):
                if result[field] != attempt[field]:
                    raise ValueError(f"{field} mismatch")
            if result["outcome"] in {"success", "parked"}:
                self._validate_exact_evidence(attempt, result)

        self.temp_dir.mkdir(parents=True, exist_ok=True) if self.temp_dir else None
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="supervised-dispatch-",
                dir=self.temp_dir,
                delete=False,
            ) as temporary:
                json.dump(validated, temporary, sort_keys=True, separators=(",", ":"))
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            if self.result_file_observer is not None:
                self.result_file_observer(temporary_path)
            bounded_results = json.loads(temporary_path.read_text())
            return apply_delegated_batch(
                workspace,
                batch_id,
                bounded_results,
                dispatch_fn,
                repo_root=repo_root,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _validate_exact_evidence(
        self,
        attempt: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        isolation = attempt["isolation"]
        if result["worktree_path"] != isolation["worktree_path"]:
            raise ValueError("worktree mismatch")
        if result["branch"] != isolation["branch"]:
            raise ValueError("branch mismatch")
        worktree = self._verify_current_isolation(attempt)
        result_worktree = Path(result["worktree_path"]).resolve()
        if result_worktree != worktree:
            raise ValueError("worktree realpath mismatch")

        evidence = result["evidence"]
        expected_loop_path = (
            Path("openspec") / "changes" / attempt["change_id"] / "loop-state.json"
        )
        supplied_loop_path = Path(evidence["loop_state_path"])
        resolved_loop = (
            supplied_loop_path.resolve(strict=False)
            if supplied_loop_path.is_absolute()
            else (worktree / supplied_loop_path).resolve(strict=False)
        )
        expected_resolved = (worktree / expected_loop_path).resolve(strict=False)
        if resolved_loop != expected_resolved or not _contains(worktree, resolved_loop):
            raise ValueError("exact loop-state path mismatch; loop-state containment failure")
        if not resolved_loop.is_file():
            raise ValueError("loop-state evidence is missing")

        commit = evidence.get("commit")
        if commit != self.commit_resolver(worktree):
            raise ValueError("commit evidence mismatch")
        digest = evidence.get("loop_state_digest")
        if digest != hashlib.sha256(resolved_loop.read_bytes()).hexdigest():
            raise ValueError("loop-state digest mismatch")
        try:
            loop_state = json.loads(resolved_loop.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("loop-state evidence is invalid") from exc
        if not isinstance(loop_state, dict) or loop_state.get("change_id") != attempt["change_id"]:
            raise ValueError("loop-state change identity mismatch")

        if result["outcome"] == "success":
            handoff_id = result["handoff_id"]
            handoff_ids = loop_state.get("handoff_ids", [])
            if loop_state.get("current_phase") != "DONE":
                raise ValueError("loop-state phase is not terminal success")
            if loop_state.get("last_handoff_id") != handoff_id and (
                not isinstance(handoff_ids, list) or handoff_id not in handoff_ids
            ):
                raise ValueError("loop-state handoff evidence mismatch")
        elif result["parked"]["kind"] == "pending_gate":
            if not isinstance(loop_state.get("pending_gate"), dict):
                raise ValueError("loop-state pending gate evidence is missing")
        elif loop_state.get("current_phase") != "ESCALATE":
            raise ValueError("loop-state policy pause evidence is missing")
