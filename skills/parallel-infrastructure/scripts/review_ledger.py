"""Gate-time review finding ledger.

Load, merge, compact, and blocking-set helpers for
``openspec/changes/<change-id>/.review-ledger/ledger.json``.

Fingerprint identity and synthesizer ``match_score`` are the two merge
paths (design D1). Compact is heuristic (D2). Blocking follows D3.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from consensus_synthesizer import (  # noqa: E402
    DEFAULT_AXIS,
    DETERMINISTIC,
    Finding,
    MATCH_THRESHOLD,
    _normalize_path,
    _tokenize,
    match_score,
)
from scope_checker import check_scope_compliance  # noqa: E402

logger = logging.getLogger(__name__)

LEDGER_DIRNAME = ".review-ledger"
LEDGER_FILENAME = "ledger.json"
PARKED_RELPATH = Path("reviews") / "parked-disagreements.json"
SCHEMA_VERSION = 1

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "are",
    "was", "were", "not", "but", "has", "have", "had", "its",
}

_LEDGER_ITEM_KEYS = (
    "id",
    "status",
    "axis",
    "type",
    "criticality",
    "evidence_class",
    "file_path",
    "line_start",
    "line_end",
    "fingerprint",
    "first_seen_round",
    "last_seen_round",
    "vendor_hits",
    "description",
    "resolution",
    "parked_reason",
    "consensus_status",
)


def ledger_dir(artifacts_dir: Path) -> Path:
    return Path(artifacts_dir) / LEDGER_DIRNAME


def ledger_path(artifacts_dir: Path) -> Path:
    return ledger_dir(artifacts_dir) / LEDGER_FILENAME


def parked_path(artifacts_dir: Path) -> Path:
    return Path(artifacts_dir) / PARKED_RELPATH


def empty_ledger(change_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "change_id": change_id,
        "items": [],
    }


def load_or_create(artifacts_dir: Path, change_id: str) -> dict[str, Any]:
    """Load the ledger, creating an empty document when absent (D8)."""
    path = ledger_path(artifacts_dir)
    if not path.exists():
        logger.warning(
            "Gate-time review ledger absent at %s; creating empty ledger",
            path,
        )
        ledger = empty_ledger(change_id)
        save(ledger, artifacts_dir)
        return ledger
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read review ledger %s: %s; recreating", path, exc)
        ledger = empty_ledger(change_id)
        save(ledger, artifacts_dir)
        return ledger
    if not isinstance(data, dict):
        ledger = empty_ledger(change_id)
        save(ledger, artifacts_dir)
        return ledger
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("change_id", change_id)
    data.setdefault("items", [])
    return data


def save(ledger: dict[str, Any], artifacts_dir: Path) -> Path:
    path = ledger_path(artifacts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        "schema_version": int(ledger.get("schema_version", SCHEMA_VERSION)),
        "change_id": str(ledger.get("change_id", "")),
        "items": [_strip_item(item) for item in ledger.get("items", [])],
    }
    if ledger.get("compacted_at"):
        serializable["compacted_at"] = ledger["compacted_at"]
    path.write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")
    return path


def _strip_item(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _LEDGER_ITEM_KEYS:
        if key in item and item[key] is not None:
            out[key] = item[key]
    return out


def fingerprint(
    axis: str | None,
    file_path: str | None,
    description: str,
) -> str:
    """Stable identity: hash(canonical_axis + normalized_path + token-set)."""
    axis_c = (axis or DEFAULT_AXIS).strip().lower()
    path_n = _normalize_path(file_path) if file_path else ""
    raw = (description or "").strip().lower()
    tokens = " ".join(sorted(_tokenize(raw)))
    payload = f"{axis_c}|{path_n}|{tokens}|{raw}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def significant_tokens(description: str) -> set[str]:
    return {t for t in _tokenize(description or "") if t not in _STOPWORDS}


def _next_id(ledger: dict[str, Any]) -> int:
    ids = [int(item.get("id", 0)) for item in ledger.get("items", [])]
    return max(ids, default=0) + 1


def _as_finding(data: dict[str, Any], vendor: str = "") -> Finding:
    return Finding(
        id=int(data.get("id") or data.get("primary_finding_id") or 0),
        type=str(data.get("type") or data.get("agreed_type") or "bug"),
        criticality=str(
            data.get("criticality") or data.get("agreed_criticality") or "low"
        ),
        description=str(data.get("description") or ""),
        disposition="fix",
        file_path=data.get("file_path"),
        line_start=data.get("line_start"),
        line_end=data.get("line_end"),
        vendor=vendor,
        axis=str(data.get("axis") or data.get("agreed_axis") or DEFAULT_AXIS),
        evidence_class=str(data.get("evidence_class") or DETERMINISTIC),
    )


def _finding_fields(cf: dict[str, Any]) -> dict[str, Any]:
    """Normalize a consensus-finding dict into ledger field names."""
    return {
        "axis": cf.get("axis") or cf.get("agreed_axis") or DEFAULT_AXIS,
        "type": cf.get("type") or cf.get("agreed_type") or "bug",
        "criticality": cf.get("criticality") or cf.get("agreed_criticality") or "low",
        "evidence_class": cf.get("evidence_class") or DETERMINISTIC,
        "file_path": cf.get("file_path"),
        "line_start": cf.get("line_start"),
        "line_end": cf.get("line_end"),
        "description": cf.get("description") or "",
        "consensus_status": cf.get("status") or cf.get("consensus_status") or "unconfirmed",
        "vendor_hits": list(cf.get("vendor_hits") or []),
    }


def _match_existing(
    ledger: dict[str, Any],
    incoming: dict[str, Any],
    fp: str,
) -> dict[str, Any] | None:
    new_finding = _as_finding(incoming)
    for item in ledger.get("items", []):
        if item.get("fingerprint") == fp:
            return item
        existing = _as_finding(item)
        score, _basis = match_score(existing, new_finding)
        if score < MATCH_THRESHOLD:
            continue
        # match_score on short generic descriptions (few tokens, no path)
        # over-merges distinct consensus items. Require a file or a
        # substantial token set before treating it as the same defect.
        if incoming.get("file_path") and item.get("file_path"):
            return item
        if len(significant_tokens(str(incoming.get("description") or ""))) >= 4:
            return item
    return None


def merge_findings(
    ledger: dict[str, Any],
    consensus_findings: list[dict[str, Any]],
    round_num: int,
) -> list[dict[str, Any]]:
    """Merge consensus findings into the ledger. Returns the merged items.

    New findings join an existing id when fingerprint matches or synthesizer
    ``match_score`` ≥ threshold. Retired and parked items are not reopened
    (delta review must not re-litigate them).
    """
    merged: list[dict[str, Any]] = []
    for cf in consensus_findings:
        fields = _finding_fields(cf)
        fp = fingerprint(fields["axis"], fields["file_path"], fields["description"])
        existing = _match_existing(ledger, {**fields, "id": cf.get("id", 0)}, fp)
        if existing is not None:
            if existing.get("status") in {"retired", "parked"}:
                merged.append(existing)
                continue
            if existing.get("status") == "addressed":
                existing["status"] = "open"
            existing["last_seen_round"] = round_num
            existing["fingerprint"] = fp
            existing["description"] = fields["description"] or existing.get("description", "")
            existing["criticality"] = fields["criticality"]
            existing["evidence_class"] = fields["evidence_class"]
            existing["consensus_status"] = fields["consensus_status"]
            existing["type"] = fields["type"]
            existing["axis"] = fields["axis"]
            if fields["file_path"]:
                existing["file_path"] = fields["file_path"]
            if fields["line_start"] is not None:
                existing["line_start"] = fields["line_start"]
            if fields["line_end"] is not None:
                existing["line_end"] = fields["line_end"]
            hits = list(existing.get("vendor_hits") or [])
            for vendor in fields["vendor_hits"]:
                if vendor not in hits:
                    hits.append(vendor)
            existing["vendor_hits"] = hits
            merged.append(existing)
            continue

        item = {
            "id": _next_id(ledger),
            "status": "open",
            "axis": fields["axis"],
            "type": fields["type"],
            "criticality": fields["criticality"],
            "evidence_class": fields["evidence_class"],
            "fingerprint": fp,
            "first_seen_round": round_num,
            "last_seen_round": round_num,
            "description": fields["description"],
            "consensus_status": fields["consensus_status"],
            "vendor_hits": fields["vendor_hits"],
        }
        if fields["file_path"]:
            item["file_path"] = fields["file_path"]
        if fields["line_start"] is not None:
            item["line_start"] = fields["line_start"]
        if fields["line_end"] is not None:
            item["line_end"] = fields["line_end"]
        ledger.setdefault("items", []).append(item)
        merged.append(item)
    return merged


def _tokens_present(
    repo_root: Path,
    item: dict[str, Any],
) -> bool | None:
    """Return True/False if file_path is set, None if the heuristic cannot run."""
    file_path = item.get("file_path")
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(repo_root) / file_path
    if not path.exists():
        # Parent missing means the path was never on disk (test fixtures,
        # findings that cite a file the repo does not have). Do not treat
        # that as "deleted".
        if not path.parent.exists():
            return None
        return False
    tokens = significant_tokens(str(item.get("description") or ""))
    if not tokens:
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    line_start = item.get("line_start")
    line_end = item.get("line_end")
    if isinstance(line_start, int):
        lines = text.splitlines()
        lo = max(0, line_start - 21)
        hi = min(len(lines), (line_end if isinstance(line_end, int) else line_start) + 20)
        text = "\n".join(lines[lo:hi])
    hay = text.lower()
    return any(tok in hay for tok in tokens)


def compact(ledger: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Heuristic compact against current files (D2). Mutates ``ledger``."""
    for item in ledger.get("items", []):
        status = item.get("status")
        if status in {"retired", "parked"}:
            continue
        present = _tokens_present(repo_root, item)
        if present is False:
            item["status"] = "retired"
            item["resolution"] = item.get("resolution") or "compact: tokens or file gone"
            continue
        if status == "addressed" and present is True:
            item["status"] = "open"
            item["resolution"] = "compact: claimed fix did not take"
    ledger["compacted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ledger


def is_blocking_item(
    item: dict[str, Any],
    *,
    blocking_criticalities: set[str] | None = None,
) -> bool:
    """D3 blocking: open + (deterministic OR confirmed high/critical)."""
    if item.get("status") not in {None, "open"}:
        # Consensus findings use confirmed/unconfirmed/disagreement here.
        if item.get("status") in {"addressed", "retired", "parked", "disagreement"}:
            return False
    ledger_status = item.get("status")
    if ledger_status in {"addressed", "retired", "parked"}:
        return False

    evidence = item.get("evidence_class") or DETERMINISTIC
    criticality = (
        item.get("criticality") or item.get("agreed_criticality") or "low"
    )
    consensus_status = (
        item.get("consensus_status") or item.get("status") or "unconfirmed"
    )
    if consensus_status == "disagreement":
        return False

    if evidence == DETERMINISTIC:
        if blocking_criticalities is None:
            return True
        return criticality in blocking_criticalities

    if consensus_status == "confirmed" and criticality in {"high", "critical"}:
        if blocking_criticalities is None:
            return True
        return criticality in blocking_criticalities
    return False


def blocking_items(
    ledger: dict[str, Any],
    *,
    blocking_criticalities: set[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in ledger.get("items", [])
        if is_blocking_item(item, blocking_criticalities=blocking_criticalities)
    ]


def mark_addressed(ledger: dict[str, Any], item_ids: list[int]) -> None:
    id_set = set(item_ids)
    for item in ledger.get("items", []):
        if item.get("id") in id_set and item.get("status") == "open":
            item["status"] = "addressed"


def park_item(
    ledger: dict[str, Any],
    item: dict[str, Any],
    *,
    reason: str = "disagreement",
) -> dict[str, Any]:
    item["status"] = "parked"
    item["parked_reason"] = reason
    item["consensus_status"] = "disagreement"
    return item


def append_parked_disagreement(
    artifacts_dir: Path,
    change_id: str,
    *,
    ledger_id: int,
    round_num: int,
    vendor_dispositions: dict[str, str],
    description: str,
) -> Path:
    path = parked_path(artifacts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {"schema_version": SCHEMA_VERSION, "change_id": change_id, "items": []}
    else:
        doc = {"schema_version": SCHEMA_VERSION, "change_id": change_id, "items": []}
    doc.setdefault("items", []).append({
        "ledger_id": ledger_id,
        "round": round_num,
        "vendor_dispositions": vendor_dispositions,
        "description": description,
        "parked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def parked_items(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in ledger.get("items", []) if item.get("status") == "parked"]


def allowed_paths(item: dict[str, Any]) -> list[str]:
    """Cited write paths for a scoped fix (D7)."""
    paths: list[str] = []
    file_path = item.get("file_path")
    if file_path:
        paths.append(str(file_path))
    finding_type = item.get("type") or item.get("agreed_type") or ""
    spec_file = item.get("spec_file")
    if finding_type == "spec_gap" and spec_file and spec_file not in paths:
        paths.append(str(spec_file))
    return paths


def scoped_fix_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    payload["allowed_paths"] = allowed_paths(item)
    if "agreed_criticality" not in payload and payload.get("criticality"):
        payload["agreed_criticality"] = payload["criticality"]
    if "agreed_type" not in payload and payload.get("type"):
        payload["agreed_type"] = payload["type"]
    return payload


def check_fix_scope(
    files_modified: list[str],
    allowed: list[str],
) -> dict[str, Any]:
    """Reject a fix whose edits leave the cited path set."""
    if not allowed:
        return {
            "compliant": False,
            "violations": [
                {
                    "file": f,
                    "reason": "not_in_write_allow",
                    "pattern": "",
                }
                for f in files_modified
            ],
            "summary": "Fix rejected: no cited file_path on blocking items",
        }
    return check_scope_compliance(
        files_modified=files_modified,
        write_allow=allowed,
        deny=[],
    )


def reject_out_of_scope_fix(
    files_modified: list[str],
    allowed: list[str],
) -> None:
    result = check_fix_scope(files_modified, allowed)
    if not result.get("compliant", False):
        raise ScopeViolation(result.get("summary") or "Fix is out of scope")


class ScopeViolation(ValueError):
    """Raised when a fix edits files outside the cited path set."""
