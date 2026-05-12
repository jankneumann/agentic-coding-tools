"""Durable checkpoint helper for vendor-findings cache.

Both the CLI dispatcher (review_dispatcher.py) and the in-process
convergence loop (skills/autopilot/scripts/convergence_loop.py) write
per-vendor finding files and a manifest through this module so the on-disk
format is identical regardless of caller. After dispatch returns, every
vendor's findings are durably persisted; a synthesis crash leaves the data
intact for manual or postmortem analysis.

Schema reference (in this proposal's contracts/ dir):
- ``finding.schema.json`` — per-vendor file shape (wrapper object + findings[])
- ``review-cache-layout.schema.json`` — manifest superset shape

Caller contract:
- ``write_vendor_findings(out_dir, *, vendor, review_type, target, findings, ...)``
- ``write_manifest(out_dir, *, review_type, target, vendors, ...)``
- ``read_vendor_findings(out_dir) -> dict[vendor, list[finding_dict]]``
- ``read_manifest(out_dir) -> dict``

Path-safety constants are enforced BEFORE any disk operation so a malformed
input never reaches the filesystem.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Manifest schema version. Bump if the manifest layout changes; readers
# must refuse unknown versions.
MANIFEST_SCHEMA_VERSION = 1

# Path-safety constants.
_VENDOR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REVIEW_TYPES = frozenset({"plan", "implementation"})
# Schema pattern for vendors[].findings_path (matches contract spec).
_FINDINGS_PATH_RE = re.compile(
    r"^findings-[A-Za-z0-9_-]+-(plan|implementation)\.json$"
)

# Per-finding required fields and enum values. The full JSON Schema lives in
# contracts/finding.schema.json (documentation); this module enforces the
# load-bearing subset at write time without pulling jsonschema at runtime.
_FINDING_REQUIRED_FIELDS = ("id", "type", "criticality", "description", "disposition")
_CRITICALITY_VALUES = frozenset({"low", "medium", "high", "critical"})
_DISPOSITION_VALUES = frozenset({"fix", "regenerate", "accept", "escalate"})


# ---------------------------------------------------------------------------
# Atomic JSON write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Atomically write ``payload`` as JSON to ``path``.

    Sequence: write to ``<path>.tmp``, ``f.flush()`` then ``os.fsync(file)``,
    ``os.replace(tmp, path)``, then open the parent directory and
    ``os.fsync(dirfd)`` to persist the directory entry. The per-file fsync
    is the load-bearing durability call — it guarantees the data hits
    stable storage. The parent-dir fsync is best-effort durability for
    the rename itself.

    Best-effort hygiene: any failure between tmp creation and successful
    rename removes the partial ``.tmp`` so chronic failures don't leak
    temp files into the artifacts directory. Three failure surfaces are
    handled:

    - ``json.dump`` / ``f.flush`` / ``os.fsync(file)`` raising
      ``(OSError, TypeError, ValueError)`` — TypeError is what
      ``json.dump`` raises for non-serializable payloads (sets, custom
      classes, datetime); ValueError is reachable for NaN/Infinity
      floats with ``allow_nan=False``; OSError covers disk-full /
      permission / signal interrupts.
    - ``os.replace`` raising ``OSError`` — narrow window (replace is
      atomic on POSIX), but possible on read-only network filesystems
      or with concurrent renames.

    All three branches unlink ``tmp`` before re-raising the original
    exception to the caller.

    Cross-platform note: parent-dir fsync via ``os.O_RDONLY`` is POSIX-only
    and may raise ``OSError`` on Windows or older filesystems. The wrapping
    try/except OSError downgrades that to a no-op.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except (OSError, TypeError, ValueError):
        # TypeError covers json.dump on non-serializable payloads
        # (sets, datetime, custom classes — the realistic encoder
        # failure mode). ValueError covers NaN/Infinity with
        # allow_nan=False. OSError covers disk-full, permission-denied,
        # signal interrupts.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    parent = path.parent
    try:
        fd = os.open(parent, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _validate_path_safety(
    artifacts_dir: Path, vendor: str, review_type: str
) -> Path:
    """Validate vendor / review_type and resolve ``artifacts_dir``.

    Returns the resolved (absolute) artifacts_dir, suitable for use as a
    write root. Raises ``ValueError`` on any safety violation. Called
    BEFORE any disk operation.
    """
    if not _VENDOR_NAME_RE.match(vendor):
        raise ValueError(
            f"Unsafe vendor name {vendor!r}; must match "
            f"{_VENDOR_NAME_RE.pattern}"
        )
    if review_type not in _REVIEW_TYPES:
        raise ValueError(
            f"Unknown review_type {review_type!r}; expected one of "
            f"{sorted(_REVIEW_TYPES)}"
        )
    return Path(artifacts_dir).resolve(strict=False)


def _validate_finding(finding: dict[str, Any]) -> None:
    """Validate one finding has the required fields and enum values.

    Lightweight runtime guard — full JSON Schema is in
    ``contracts/finding.schema.json``.
    """
    missing = [k for k in _FINDING_REQUIRED_FIELDS if k not in finding]
    if missing:
        raise ValueError(
            f"Finding missing required fields: {missing}"
        )
    if finding["criticality"] not in _CRITICALITY_VALUES:
        raise ValueError(
            f"Finding criticality {finding['criticality']!r} not in "
            f"{sorted(_CRITICALITY_VALUES)}"
        )
    if finding["disposition"] not in _DISPOSITION_VALUES:
        raise ValueError(
            f"Finding disposition {finding['disposition']!r} not in "
            f"{sorted(_DISPOSITION_VALUES)}"
        )


# ---------------------------------------------------------------------------
# Per-vendor findings file
# ---------------------------------------------------------------------------


def write_vendor_findings(
    out_dir: Path,
    *,
    vendor: str,
    review_type: str,
    target: str,
    findings: list[dict[str, Any]],
    reviewer_vendor: str | None = None,
) -> Path:
    """Write a per-vendor findings file as a wrapper object.

    Wrapper shape: ``{review_type, target, reviewer_vendor, findings: [...]}``.
    Path: ``out_dir / "findings-{vendor}-{review_type}.json"``.

    Keyword-only after ``out_dir`` to prevent positional confusion. Validates
    vendor name, review_type, and each finding BEFORE any disk operation —
    a malformed input never produces a partial file.
    """
    safe_dir = _validate_path_safety(out_dir, vendor, review_type)
    for finding in findings:
        _validate_finding(finding)
    safe_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "review_type": review_type,
        "target": target,
        "reviewer_vendor": reviewer_vendor or vendor,
        "findings": findings,
    }
    fpath = safe_dir / f"findings-{vendor}-{review_type}.json"
    _atomic_write_json(fpath, payload)
    return fpath


def read_vendor_findings(out_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Read all per-vendor findings via the manifest's ``vendors[]`` index.

    Returns a dict mapping vendor name to a list of raw finding dicts (NOT
    constructed Finding objects — callers that need them invoke
    ``Finding.from_dict()`` themselves).

    Path safety: each ``findings_path`` is checked for separators and ``..``,
    then resolved and verified to stay within ``out_dir``. Raises ValueError
    on path-safety violation or FileNotFoundError if a referenced file is
    missing.
    """
    safe_dir = Path(out_dir).resolve(strict=False)
    manifest = read_manifest(out_dir)
    out: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest.get("vendors", []):
        name = entry["name"]
        if not _VENDOR_NAME_RE.match(name):
            raise ValueError(
                f"Manifest vendors[].name {name!r} fails path-safety regex"
            )
        relpath = entry["findings_path"]
        if "/" in relpath or "\\" in relpath or ".." in relpath:
            raise ValueError(
                f"Manifest findings_path {relpath!r} contains path "
                f"separator or '..'"
            )
        fpath = (safe_dir / relpath).resolve(strict=False)
        try:
            fpath.relative_to(safe_dir)
        except ValueError as exc:
            raise ValueError(
                f"Resolved findings_path {fpath} escapes out_dir {safe_dir}"
            ) from exc
        if not fpath.exists():
            raise FileNotFoundError(
                f"Manifest references {relpath} but file is missing from "
                f"{safe_dir}"
            )
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError(
                f"Per-vendor file {fpath} is not a JSON object "
                f"(got {type(data).__name__}); expected the wrapper-object "
                f"shape {{review_type, target, reviewer_vendor, findings: [...]}}"
            )
        findings_field = data.get("findings", [])
        if not isinstance(findings_field, list):
            raise TypeError(
                f"Per-vendor file {fpath} has 'findings' field of type "
                f"{type(findings_field).__name__}; expected list"
            )
        out[name] = list(findings_field)
    return out


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def write_manifest(
    out_dir: Path,
    *,
    review_type: str,
    target: str,
    vendors: list[dict[str, Any]],
    change_id: str | None = None,
    dispatches: list[dict[str, Any]] | None = None,
    quorum_requested: int | None = None,
    quorum_received: int | None = None,
) -> Path:
    """Write the review-cache manifest with the superset schema.

    Keyword-only after ``out_dir``. ``change_id`` defaults to None for CLI
    callers; in-process callers populate it. ``dispatches`` defaults to ``[]``
    when not supplied. ``quorum_requested`` defaults to ``len(vendors)``;
    ``quorum_received`` defaults to count of ``dispatches[].success=True``,
    or ``len(vendors)`` when ``dispatches`` is empty (in-process callers
    have no per-dispatch metadata, so all listed vendors count as received).
    """
    if review_type not in _REVIEW_TYPES:
        raise ValueError(
            f"Unknown review_type {review_type!r}; expected one of "
            f"{sorted(_REVIEW_TYPES)}"
        )
    for v in vendors:
        name = v.get("name", "")
        if not _VENDOR_NAME_RE.match(name):
            raise ValueError(
                f"vendors[].name {name!r} fails path-safety regex"
            )
        # The contract schema (review-cache-layout.schema.json line 81)
        # requires every vendors[] entry to include name, findings_path,
        # AND finding_count. Enforcing those at write time ensures the
        # writer can never produce a manifest its own reader cannot
        # process. Round-2 review caught that earlier "validate when
        # present" semantics let through schema-invalid manifests.
        if "findings_path" not in v:
            raise ValueError(
                f"vendors[] entry for {name!r} missing required "
                f"'findings_path' field"
            )
        findings_path = v["findings_path"]
        if not isinstance(findings_path, str):
            raise ValueError(
                f"vendors[].findings_path for {name!r} must be a string, "
                f"got {type(findings_path).__name__}"
            )
        if "/" in findings_path or "\\" in findings_path or ".." in findings_path:
            raise ValueError(
                f"vendors[].findings_path {findings_path!r} for {name!r} "
                f"contains path separator or '..'"
            )
        # Mirror the schema's pattern: findings-{vendor}-{plan|implementation}.json
        if not _FINDINGS_PATH_RE.match(findings_path):
            raise ValueError(
                f"vendors[].findings_path {findings_path!r} for {name!r} "
                f"does not match required pattern "
                f"{_FINDINGS_PATH_RE.pattern}"
            )
        if "finding_count" not in v:
            raise ValueError(
                f"vendors[] entry for {name!r} missing required "
                f"'finding_count' field"
            )
        finding_count = v["finding_count"]
        if not isinstance(finding_count, int):
            raise ValueError(
                f"vendors[].finding_count for {name!r} must be an integer, "
                f"got {type(finding_count).__name__}"
            )
        if finding_count < 0:
            raise ValueError(
                f"vendors[].finding_count for {name!r} must be >= 0, "
                f"got {finding_count}"
            )

    safe_dir = Path(out_dir).resolve(strict=False)
    safe_dir.mkdir(parents=True, exist_ok=True)

    dispatches_list = list(dispatches) if dispatches is not None else []

    if quorum_requested is None:
        quorum_requested = len(vendors)
    if quorum_received is None:
        if dispatches_list:
            quorum_received = sum(
                1 for d in dispatches_list if d.get("success")
            )
        else:
            quorum_received = len(vendors)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "change_id": change_id,
        "review_type": review_type,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": target,
        "dispatches": dispatches_list,
        "quorum_requested": quorum_requested,
        "quorum_received": quorum_received,
        "vendors": list(vendors),
    }
    mpath = safe_dir / "review-manifest.json"
    _atomic_write_json(mpath, manifest)
    return mpath


def read_manifest(out_dir: Path) -> dict[str, Any]:
    """Read and parse ``review-manifest.json`` from ``out_dir``.

    Raises ``TypeError`` if the file does not parse to a JSON object — guards
    against a corrupt or hand-edited manifest making it past write-time
    validation. Raises ``ValueError`` if the manifest has a missing or unknown
    ``schema_version`` — the contract (``review-cache-layout.schema.json``)
    explicitly requires readers to refuse unknown versions so a future v2
    manifest is never silently misinterpreted as v1.
    """
    mpath = Path(out_dir) / "review-manifest.json"
    with open(mpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(
            f"Manifest at {mpath} is not a JSON object (got {type(data).__name__})"
        )
    version = data.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"Manifest at {mpath} has schema_version={version!r}; "
            f"this reader only accepts schema_version={MANIFEST_SCHEMA_VERSION}. "
            f"Upgrade the reader or regenerate the manifest."
        )
    return data


# ---------------------------------------------------------------------------
# Best-effort structured logging
# ---------------------------------------------------------------------------


def _safe_log_error(event: str, **payload: Any) -> None:
    """Best-effort structured ERROR log.

    Emits with ``msg=event`` and ``extra={"event": event, **payload}``, so
    test fixtures can assert on ``LogRecord.event`` rather than rendered
    message text. Wraps ``logger.error()`` in a bare try/except: a custom
    handler raising in ``emit()`` (or the logging machinery surfacing it
    via ``raiseExceptions=True``) MUST NOT propagate to the caller, because
    that would mask the original exception that prompted the log.
    """
    try:
        logger.error(event, extra={"event": event, **payload})
    except Exception:  # pragma: no cover — best-effort by design
        pass
