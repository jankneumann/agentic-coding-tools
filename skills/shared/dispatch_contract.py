"""The supervisor-worker dispatch contract, loaded from its published schemas.

dispatch-contract (design D1-D4, D6, D7, D9, D10a). This module is the single
runtime definition of the delegated dispatch boundary:

- the request/result schemas are ``openspec/schemas/dispatch-request.schema.json``
  and ``dispatch-result.schema.json`` (version 2); the frozen version-1 reader
  schemas and the checkpoint attempt schema live under
  ``openspec/contracts/roadmap-orchestration/schemas/``. They are loaded at
  runtime (repo copy first, then the ``roadmap-runtime`` install_assets mirror)
  and resolved through one ``referencing.Registry`` keyed by ``$id``;
- :func:`validate_request` / :func:`validate_result` validate either version;
  :func:`upgrade_v1` upgrades a version-1 document in memory against explicit
  host context; writers emit only version 2;
- :func:`result_from_loop_state` is the normative loop-state -> result mapping
  (D4) behind ``runner.py emit-result``;
- :func:`read_launch_marker` is the child's only view of its dispatch (D10a).

Only the cross-field checks a schema cannot express live here as code.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Union

PathLike = Union[str, Path]

_HERE = Path(__file__).resolve()
_SKILLS_ROOT = _HERE.parents[1]
_INSTALL_ASSETS = _SKILLS_ROOT / "roadmap-runtime" / "install_assets" / "openspec"

SCHEMA_DIRS = ("schemas", "contracts/roadmap-orchestration/schemas")

REQUEST_V2 = "schemas/dispatch-request.schema.json"
RESULT_V2 = "schemas/dispatch-result.schema.json"
REQUEST_V1 = "contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json"
RESULT_V1 = "contracts/roadmap-orchestration/schemas/supervised-dispatch-result.schema.json"
ATTEMPT = "contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json"

#: ``runner.py emit-result`` exit code when the loop is neither terminal nor parked.
EXIT_NOT_TERMINAL = 5
NOT_TERMINAL_MESSAGE = "loop state is not terminal or parked"

MAX_RESULT_BYTES = 16 * 1024
MAX_REDACTED_COMMAND = 256
MARKER_DIRNAME = ".supervised-dispatch"
REVIEW_PHASES = ("PLAN_REVIEW", "IMPL_REVIEW", "VAL_REVIEW")

_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_DRIVE = re.compile(r"^[A-Za-z]:")


class DispatchContractError(ValueError):
    """A document violates the dispatch contract.

    ``pointer`` is the JSON pointer of the first failing location when the
    failure came from schema validation, else ``None``.
    """

    def __init__(self, message: str, *, pointer: Optional[str] = None) -> None:
        self.pointer = pointer
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Schema location and registry (D2)
# --------------------------------------------------------------------------- #


def _openspec_roots(repo_root: Optional[PathLike]) -> list[Path]:
    roots: list[Path] = []
    if repo_root is not None:
        roots.append(Path(repo_root) / "openspec")
    # The repository this module ships in, then the installed mirror.
    roots.append(_SKILLS_ROOT.parent / "openspec")
    roots.append(_INSTALL_ASSETS)
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def find_schema_path(rel: str, repo_root: Optional[PathLike] = None) -> Path:
    """Locate a contract schema: ``<repo_root>/openspec/<rel>`` first, then this
    repository's copy, then the ``roadmap-runtime`` install_assets mirror."""
    for root in _openspec_roots(repo_root):
        candidate = root / rel
        if candidate.is_file():
            return candidate
    raise DispatchContractError(f"dispatch contract schema not found: openspec/{rel}")


def _schema_files(repo_root: Optional[PathLike]) -> dict[str, Path]:
    """``$id`` -> file for every schema under the contract directories.

    Earlier roots win, so a consumer repository's own copy overrides the mirror.
    """
    found: dict[str, Path] = {}
    for root in _openspec_roots(repo_root):
        for directory in SCHEMA_DIRS:
            folder = root / directory
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                try:
                    contents = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                schema_id = contents.get("$id") if isinstance(contents, dict) else None
                if isinstance(schema_id, str) and schema_id not in found:
                    found[schema_id] = path
    return found


@functools.lru_cache(maxsize=8)
def _registry_for(key: Optional[str]) -> Any:
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for schema_id, path in _schema_files(key).items():
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (schema_id, Resource.from_contents(contents, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def schema_registry(repo_root: Optional[PathLike] = None) -> Any:
    """A ``referencing.Registry`` of every schema in ``openspec/schemas/`` and
    ``openspec/contracts/roadmap-orchestration/schemas/``, keyed by ``$id``."""
    return _registry_for(str(Path(repo_root).resolve()) if repo_root is not None else None)


def load_schema(rel: str, repo_root: Optional[PathLike] = None) -> dict[str, Any]:
    return json.loads(find_schema_path(rel, repo_root).read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=32)
def _validator_for(rel: str, key: Optional[str]) -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = load_schema(rel, key)
    return Draft202012Validator(
        schema, registry=_registry_for(key), format_checker=FormatChecker()
    )


def validator(rel: str, repo_root: Optional[PathLike] = None) -> Any:
    """A Draft 2020-12 validator for ``rel`` with the contract registry."""
    return _validator_for(rel, str(Path(repo_root).resolve()) if repo_root is not None else None)


def _pointer(error: Any) -> str:
    parts = [str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path]
    return "/" + "/".join(parts) if parts else "/"


def _check(rel: str, document: Any, label: str, repo_root: Optional[PathLike]) -> None:
    errors = sorted(
        validator(rel, repo_root).iter_errors(document),
        key=lambda error: (list(map(str, error.absolute_path)), error.message),
    )
    if errors:
        first = errors[0]
        pointer = _pointer(first)
        raise DispatchContractError(
            f"{label} is not schema-valid at {pointer}: {first.message}", pointer=pointer
        )


def _canonical(document: Any) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _version(document: Any, label: str) -> int:
    if not isinstance(document, Mapping):
        raise DispatchContractError(f"{label} must be a JSON object", pointer="/")
    version = document.get("schema_version")
    if isinstance(version, bool) or version not in (1, 2):
        raise DispatchContractError(
            f"{label} is not schema-valid at /schema_version: unsupported schema_version "
            f"{version!r}",
            pointer="/schema_version",
        )
    return int(version)


_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)


def _check_date_times(document: Mapping[str, Any], label: str) -> None:
    """``format: date-time`` is only asserted when an optional format package is
    installed, so the parked deadline is checked here unconditionally."""
    parked = document.get("parked")
    deadline = parked.get("deadline") if isinstance(parked, Mapping) else None
    if deadline is None:
        return
    valid = isinstance(deadline, str) and _RFC3339.fullmatch(deadline) is not None
    if valid:
        try:
            datetime.fromisoformat(deadline.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            valid = False
    if not valid:
        raise DispatchContractError(
            f"{label} is not schema-valid at /parked/deadline: {deadline!r} is not a date-time",
            pointer="/parked/deadline",
        )


def validate_request(document: Any, *, repo_root: Optional[PathLike] = None) -> dict[str, Any]:
    """Validate a v1 (frozen reader schema) or v2 request; return a deep copy.

    Host-independent: a v1 request is only schema-checked here, never upgraded.
    """
    version = _version(document, "dispatch request")
    _check(REQUEST_V1 if version == 1 else REQUEST_V2, document, "dispatch request", repo_root)
    if len(_canonical(document["context"])) > MAX_RESULT_BYTES:
        raise DispatchContractError(
            "dispatch request context canonical JSON exceeds 16 KiB", pointer="/context"
        )
    return copy.deepcopy(dict(document))


def validate_result(document: Any, *, repo_root: Optional[PathLike] = None) -> dict[str, Any]:
    """Validate a v1 (frozen reader schema) or v2 result; return a deep copy."""
    version = _version(document, "dispatch result")
    _check(RESULT_V1 if version == 1 else RESULT_V2, document, "dispatch result", repo_root)
    _check_date_times(document, "dispatch result")
    if len(_canonical(document)) > MAX_RESULT_BYTES:
        raise DispatchContractError("dispatch result canonical JSON exceeds 16 KiB", pointer="/")
    return copy.deepcopy(dict(document))


def validate_attempt(document: Any, *, repo_root: Optional[PathLike] = None) -> dict[str, Any]:
    """Validate one checkpoint attempt against the single attempt definition."""
    _check(ATTEMPT, document, "dispatch attempt", repo_root)
    return copy.deepcopy(dict(document))


# --------------------------------------------------------------------------- #
# Host-portable paths (D7)
# --------------------------------------------------------------------------- #


def is_portable_path(value: Any) -> bool:
    """A non-empty relative POSIX path that does not escape upward."""
    if not isinstance(value, str) or not value:
        return False
    if value.startswith(("/", "\\")) or _DRIVE.match(value):
        return False
    return ".." not in PurePosixPath(value.replace("\\", "/")).parts


def _relative_to(path: Path, root: Optional[PathLike]) -> Optional[str]:
    if root is None:
        return None
    try:
        relative = path.relative_to(Path(root))
    except ValueError:
        return None
    text = relative.as_posix()
    return text if text not in ("", ".") else None


def portable_ref(
    worktree: PathLike,
    *,
    mode: Optional[str],
    repo_root: Optional[PathLike],
    managed_root: Optional[PathLike],
) -> Optional[str]:
    """``worktree`` relative to the managed root (``managed_worktree``) or the
    repo root (``harness_provided``), or ``None`` when it lies outside both.

    With ``mode=None`` (a v1 document without a mode) the managed root is tried
    first, then the repo root. Lexical only: the path need not exist here.
    """
    path = Path(worktree)
    if mode == "managed_worktree":
        return _relative_to(path, managed_root)
    if mode == "harness_provided":
        return _relative_to(path, repo_root)
    return _relative_to(path, managed_root) or _relative_to(path, repo_root)


def resolve_worktree(
    isolation: Mapping[str, Any],
    *,
    repo_root: Optional[PathLike],
    managed_root: Optional[PathLike],
) -> Optional[Path]:
    """The absolute worktree for a portable isolation on this host (in memory only).

    Returns ``None`` when the reference is null or its root is unknown.
    """
    ref = isolation.get("worktree_ref")
    if not is_portable_path(ref):
        return None
    root = managed_root if isolation.get("mode") == "managed_worktree" else repo_root
    if root is None:
        return None
    return Path(root) / str(ref)


# --------------------------------------------------------------------------- #
# Version-1 upgrade (D1)
# --------------------------------------------------------------------------- #


def upgrade_v1(
    document: Mapping[str, Any],
    *,
    repo_root: PathLike,
    managed_root: Optional[PathLike],
    host_id: str,
) -> dict[str, Any]:
    """Upgrade a schema-valid version-1 request or result to version 2 in memory.

    The host context is explicit (D1): absolute paths are made relative to
    ``managed_root`` / ``repo_root``; a path outside both is rejected.
    """
    if _version(document, "dispatch document") == 2:
        return copy.deepcopy(dict(document))
    if "roadmap_id" in document:
        validate_request(document, repo_root=repo_root)
        return _upgrade_request(document, repo_root, managed_root, host_id)
    validate_result(document, repo_root=repo_root)
    return _upgrade_result(document, repo_root, managed_root, host_id)


def _upgrade_request(
    document: Mapping[str, Any], repo_root: PathLike, managed_root: Optional[PathLike], host_id: str
) -> dict[str, Any]:
    upgraded = copy.deepcopy(dict(document))
    isolation = upgraded.pop("isolation")
    ref = portable_ref(
        isolation["worktree_path"], mode=isolation["mode"], repo_root=repo_root, managed_root=managed_root
    )
    if ref is None:
        raise DispatchContractError(
            "v1 request worktree_path is not repo-relative", pointer="/isolation/worktree_path"
        )
    upgraded.update(
        schema_version=2,
        isolation={
            "mode": isolation["mode"],
            "worktree_ref": ref,
            "branch": isolation["branch"],
            "host_id": host_id,
        },
        execution_profile={},
        review_requirements={},
        roadmap_approval_ref=None,
    )
    validate_request(upgraded, repo_root=repo_root)
    return upgraded


def _upgrade_result(
    document: Mapping[str, Any], repo_root: PathLike, managed_root: Optional[PathLike], host_id: str
) -> dict[str, Any]:
    upgraded = copy.deepcopy(dict(document))
    upgraded["schema_version"] = 2
    upgraded["degradations"] = []
    worktree_path = upgraded.pop("worktree_path", None)
    if worktree_path is not None:
        ref = portable_ref(worktree_path, mode=None, repo_root=repo_root, managed_root=managed_root)
        if ref is None:
            raise DispatchContractError(
                "v1 result worktree_path is not repo-relative", pointer="/worktree_path"
            )
        upgraded["worktree_ref"] = ref
        upgraded["host_id"] = host_id
    evidence = upgraded.get("evidence")
    if isinstance(evidence, dict):
        loop_path = str(evidence.get("loop_state_path", ""))
        if not is_portable_path(loop_path):
            relative = _relative_to(Path(loop_path), worktree_path) if worktree_path else None
            if relative is None:
                raise DispatchContractError(
                    "v1 result loop_state_path is not inside its worktree",
                    pointer="/evidence/loop_state_path",
                )
            evidence["loop_state_path"] = relative
    validate_result(upgraded, repo_root=repo_root)
    return upgraded


def ensure_v2_result(
    document: Mapping[str, Any],
    *,
    repo_root: PathLike,
    managed_root: Optional[PathLike],
    host_id: str,
) -> dict[str, Any]:
    """Validate a result of either version and return its version-2 form."""
    validated = validate_result(document, repo_root=repo_root)
    if validated["schema_version"] == 1:
        return upgrade_v1(validated, repo_root=repo_root, managed_root=managed_root, host_id=host_id)
    return validated


# --------------------------------------------------------------------------- #
# Launch digest (D6)
# --------------------------------------------------------------------------- #


def launch_digest(token: str) -> str:
    """``sha256:<hex>`` of a raw launch token — the only form ever persisted."""
    if not isinstance(token, str) or not token:
        raise DispatchContractError("launch token must be a non-empty string")
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_launch_token(token: Any, digest: Any) -> bool:
    """Constant-time comparison of ``sha256(token)`` with a stored digest."""
    if not isinstance(token, str) or not token or not isinstance(digest, str):
        return False
    if not _DIGEST.fullmatch(digest):
        return False
    return hmac.compare_digest(launch_digest(token), digest)


# --------------------------------------------------------------------------- #
# Loop state -> result (D4)
# --------------------------------------------------------------------------- #


def dispatch_slug(dispatch_id: str) -> str:
    """Replace every character outside ``[A-Za-z0-9._-]`` with ``-``."""
    if not isinstance(dispatch_id, str) or not dispatch_id:
        raise DispatchContractError("dispatch_id must be a non-empty string")
    return _SLUG_UNSAFE.sub("-", dispatch_id)


def result_relpath(change_id: str, dispatch_id: str, generation: int) -> str:
    """Repo-relative path of the committed result file for one generation."""
    return (
        f"openspec/changes/{change_id}/dispatch-results/"
        f"{dispatch_slug(dispatch_id)}-g{int(generation)}.json"
    )


def _bounded(text: Any, limit: int, fallback: str) -> str:
    value = str(text).strip() if text not in (None, "") else ""
    value = value or fallback
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _parked_from_park(park: Mapping[str, Any]) -> dict[str, Any]:
    kind = park.get("kind")
    common = {
        "reason": _bounded(park.get("reason"), 1024, f"child parked: {kind}"),
        "deadline": park.get("deadline"),
        "resume_hint": park.get("resume_hint"),
    }
    if kind == "permission_blocked":
        return {
            "kind": kind,
            "gate": None,
            "tool": park.get("tool"),
            "rule": park.get("rule"),
            "classifier_reason": park.get("classifier_reason"),
            "command": park.get("command"),
            **common,
        }
    if kind == "capability_unavailable":
        return {
            "kind": kind,
            "gate": None,
            "phase": park.get("phase"),
            "missing_lanes": list(park.get("missing_lanes") or []),
            **common,
        }
    raise DispatchContractError(f"unknown loop-state park kind {kind!r}", pointer="/park/kind")


def result_from_loop_state(
    state: Mapping[str, Any], attempt_ctx: Mapping[str, Any]
) -> Optional[dict[str, Any]]:
    """The normative mapping (D4), first match wins; ``None`` when not terminal.

    ``attempt_ctx`` supplies identity (``dispatch_id``, ``change_id``,
    ``attempt``, ``lease_generation``), host-portable location (``worktree_ref``,
    ``branch``, ``host_id``) and ``evidence``. The returned result is
    schema-valid version 2.
    """
    park = state.get("park")
    pending = state.get("pending_gate")
    phase = state.get("current_phase")
    goal_gate = state.get("goal_gate") or {}
    verdict = goal_gate.get("verdict") if isinstance(goal_gate, Mapping) else None

    parked: Optional[dict[str, Any]] = None
    handoff_id: Optional[str] = None
    if isinstance(park, Mapping) and park:
        outcome = "parked"
        parked = _parked_from_park(park)
    elif isinstance(pending, Mapping) and pending:
        outcome = "parked"
        gate = pending.get("gate")
        parked = {
            "kind": "pending_gate",
            "gate": gate,
            "reason": _bounded(
                pending.get("prompt"), 1024, f"gate {gate} is pending an answer"
            ),
            "deadline": None,
            "resume_hint": f"answer gate {gate} through the resume request's gate_answer",
        }
    elif phase == "ESCALATE":
        outcome = "parked"
        previous = state.get("previous_phase")
        parked = {
            "kind": "policy_pause",
            "gate": None,
            "reason": _bounded(state.get("escalation_reason"), 1024, "loop escalated"),
            "deadline": None,
            "resume_hint": _bounded(
                f"previous_phase={previous}; answer escalate_resume to resume", 512, ""
            ),
        }
    elif phase == "DONE" and verdict == "abandoned":
        outcome = "failed:abandoned"
    elif phase == "DONE" and verdict == "passed" and state.get("last_handoff_id"):
        outcome = "success"
        handoff_id = str(state["last_handoff_id"])
    elif phase == "DONE":
        outcome = "failed:goal_gate_unverified"
    else:
        return None

    result: dict[str, Any] = {
        "schema_version": 2,
        "dispatch_id": attempt_ctx["dispatch_id"],
        "change_id": attempt_ctx["change_id"],
        "attempt": int(attempt_ctx["attempt"]),
        "lease_generation": int(attempt_ctx["lease_generation"]),
        "outcome": outcome,
        "worktree_ref": attempt_ctx.get("worktree_ref"),
        "branch": attempt_ctx["branch"],
        "host_id": attempt_ctx["host_id"],
        "evidence": copy.deepcopy(dict(attempt_ctx["evidence"])),
        "degradations": copy.deepcopy(list(state.get("degradations") or [])),
    }
    if handoff_id is not None:
        result["handoff_id"] = handoff_id
    if parked is not None:
        result["parked"] = parked
    return validate_result(result)


# --------------------------------------------------------------------------- #
# Escalation dedupe (D9)
# --------------------------------------------------------------------------- #


def dedupe_fingerprint(parked: Mapping[str, Any]) -> Optional[str]:
    """The escalation subject for a capability park, or ``None`` for other kinds.

    ``permission_blocked``: ``sha256(tool, rule, classifier_reason)`` (never the
    command). ``capability_unavailable``: ``sha256(phase, sorted(missing_lanes))``.
    """
    kind = parked.get("kind")
    if kind == "permission_blocked":
        parts: list[Any] = [kind, parked.get("tool"), parked.get("rule"), parked.get("classifier_reason")]
    elif kind == "capability_unavailable":
        parts = [kind, parked.get("phase"), sorted(parked.get("missing_lanes") or [])]
    else:
        return None
    return hashlib.sha256(_canonical(parts)).hexdigest()


#: Credential-bearing HTTP auth schemes and headers. ``sanitize()``'s
#: ``bearer-token`` rule needs ``authorization:<value>`` with a 20+ character
#: value, so ``-H "Authorization: Bearer <short token>"`` passes it untouched;
#: these run first so a blocked command never persists such a value.
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic|token|digest)(\s+)[^\s\"'`]+")
_AUTH_HEADER = re.compile(
    r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|cookie)(\s*:\s*)(?!\[REDACTED:)[^\"'`\r\n]+"
)


def redact_command(command: Optional[str]) -> Optional[str]:
    """Redact a blocked command for persistence, truncated to 256 characters (D9).

    Auth-scheme / auth-header values are redacted first, then the command goes
    through ``sanitize_session_log.sanitize()`` (secret-pattern and high-entropy
    redaction) and the first element of its ``(content, redactions)`` result is
    kept.
    """
    if command is None:
        return None
    text = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:auth-scheme]", str(command))
    text = _AUTH_HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:auth-header]", text)
    redacted = _sanitizer()(text)[0]
    return redacted[:MAX_REDACTED_COMMAND]


@functools.lru_cache(maxsize=1)
def _sanitizer() -> Any:
    import importlib.util

    path = _SKILLS_ROOT / "session-log" / "scripts" / "sanitize_session_log.py"
    spec = importlib.util.spec_from_file_location("_dispatch_sanitize_session_log", path)
    if spec is None or spec.loader is None:  # pragma: no cover - installation guard
        raise DispatchContractError(f"session-log sanitizer not found at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sanitize


# --------------------------------------------------------------------------- #
# Launch marker (D10a)
# --------------------------------------------------------------------------- #

_MARKER_IDENTITY = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")


def marker_dir(change_id: str, *, repo_root: Optional[PathLike] = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / MARKER_DIRNAME / change_id


def _valid_marker(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    dispatch_id = record.get("dispatch_id")
    generation = record.get("generation")
    nonce = record.get("owner_nonce")
    return (
        isinstance(dispatch_id, str)
        and 1 <= len(dispatch_id) <= 256
        and isinstance(generation, int)
        and not isinstance(generation, bool)
        and generation >= 1
        and isinstance(nonce, str)
        and _MARKER_IDENTITY.fullmatch(nonce) is not None
    )


def read_launch_marker(
    change_id: str, *, repo_root: Optional[PathLike] = None
) -> Optional[dict[str, Any]]:
    """The highest-generation valid launch marker for ``change_id``, or ``None``.

    ``None`` means a standalone run; any returned marker means "dispatched child"
    in the dispatch-contract specs. Markers whose identity fields do not
    validate are ignored.
    """
    if not isinstance(change_id, str) or not change_id or "/" in change_id:
        return None
    folder = marker_dir(change_id, repo_root=repo_root)
    if not folder.is_dir():
        return None
    best: Optional[dict[str, Any]] = None
    for path in sorted(folder.glob("*.marker")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _valid_marker(record):
            continue
        if best is None or record["generation"] > best["generation"]:
            best = record
    return copy.deepcopy(best) if best is not None else None


# --------------------------------------------------------------------------- #
# Closure support (Dispatch Result Closure)
# --------------------------------------------------------------------------- #


def _resolve_local(schema: Mapping[str, Any], node: Mapping[str, Any]) -> Mapping[str, Any]:
    while isinstance(node, Mapping) and "$ref" in node and str(node["$ref"]).startswith("#/"):
        target: Any = schema
        for part in str(node["$ref"])[2:].split("/"):
            target = target[part]
        node = target
    return node


def _enum_values(schema: Mapping[str, Any], node: Any) -> list[Any]:
    node = _resolve_local(schema, node) if isinstance(node, Mapping) else node
    if not isinstance(node, Mapping):
        return [None]
    if "const" in node:
        return [node["const"]]
    if "enum" in node:
        return list(node["enum"])
    return [None]


def permitted_result_combinations(
    schema: Optional[Mapping[str, Any]] = None,
) -> set[tuple[str, Optional[str], Optional[str]]]:
    """Every ``(outcome class, parked.kind, parked.gate)`` the result schema permits.

    Derived from the schema itself: the ``outcome`` ``oneOf`` branches'
    ``x-outcome-class`` annotations, and the ``Parked`` ``oneOf`` branches'
    ``kind`` const and ``gate`` enum (an absent ``gate`` means ``null``).
    """
    document = schema if schema is not None else load_schema(RESULT_V2)
    combos: set[tuple[str, Optional[str], Optional[str]]] = set()
    classes = [
        branch.get("x-outcome-class")
        for branch in document["properties"]["outcome"]["oneOf"]
    ]
    parked_node = _resolve_local(document, document["properties"]["parked"])
    for outcome_class in classes:
        if outcome_class != "parked":
            combos.add((str(outcome_class), None, None))
            continue
        for branch in parked_node["oneOf"]:
            resolved = _resolve_local(document, branch)
            properties = resolved.get("properties", {})
            for kind in _enum_values(document, properties.get("kind")):
                for gate in _enum_values(document, properties.get("gate")):
                    combos.add(("parked", kind, gate))
    return combos
