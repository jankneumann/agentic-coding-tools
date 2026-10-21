#!/usr/bin/env python3
"""Record metered review spend in the coordinator ledger, spooling on failure.

openrouter-review-lane, design D4. ``ReviewOrchestrator.dispatch_and_wait``
calls :func:`record` once per metered (``endpoint_kind: openrouter``) review
that sent a request. The row goes to ``POST /routing/spend``; when that write
fails (connection error, 403 from a partly forbidden coordinator, any non-2xx)
the row is appended to ``openspec/changes/<change-id>/reviews/spend-spool.jsonl``
and :class:`RecordOutcome.recorded` is ``False`` so the caller can record the
``metered_spend_unrecorded`` degradation. :func:`replay` (and the ``replay``
CLI, which the supervisor runs during ``apply``) posts spooled rows again;
``generation_id`` is the idempotency key, so replay is safe to repeat.

Credentials come only from the coordination bridge's resolution path
(``COORDINATION_API_URL`` / ``COORDINATION_API_KEY`` and their aliases, plus the
bridge's host allowlist and Cloudflare Access headers). No key value is ever
written to the spool, the outcome objects, or CLI output.

CLI::

    spend_recorder.py replay --change-id <id> [--repo-root <path>] [--json]
    spend_recorder.py total  --change-id <id> [--repo-root <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BRIDGE_SCRIPTS = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_SCRIPTS))

import coordination_bridge as _bridge  # noqa: E402

SPEND_PATH = "/routing/spend"
SPOOL_NAME = "spend-spool.jsonl"
DEFAULT_TIMEOUT_SECONDS = 5.0

# The coordinator's SpendRecordRequest fields. The route forbids anything else,
# so a row is filtered to exactly these before it is posted or spooled.
ROW_FIELDS: tuple[str, ...] = (
    "vendor",
    "model",
    "endpoint_kind",
    "generation_id",
    "prompt_tokens",
    "completion_tokens",
    "actual_usd",
    "tokens_estimated",
    "work_unit_ref",
    "occurred_at",
)

_CHANGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# transport(method=, path=, payload=, http_url=, api_key=, timeout=) ->
#   {"status_code": int | None, "data": Any, "error": str | None}
# Same keyword signature and shape as coordination_bridge._http_request.
Transport = Callable[..., Mapping[str, Any]]


def _default_transport(**kwargs: Any) -> Mapping[str, Any]:
    return _bridge._http_request(**kwargs)


@dataclass(frozen=True)
class RecordOutcome:
    """Result of one :func:`record` call.

    ``recorded`` is what ``ReviewResult.spend_recorded`` takes. It is ``True``
    when the coordinator inserted the row (201) or already held its
    ``generation_id`` (200). Otherwise the row was spooled (``spooled``), and
    ``reason`` is a fixed code such as ``connection_error`` or ``http_403``.
    """

    recorded: bool
    spooled: bool
    status_code: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReplayOutcome:
    replayed: int = 0
    already_recorded: int = 0
    remaining: int = 0
    malformed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "replayed": self.replayed,
            "already_recorded": self.already_recorded,
            "remaining": self.remaining,
            "malformed": self.malformed,
        }


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def _default_repo_root() -> Path:
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        if top:
            return Path(top)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def _change_dir(change_id: str, repo_root: Path) -> Path:
    changes = repo_root / "openspec" / "changes"
    live = changes / change_id
    if live.is_dir():
        return live
    archived = sorted((changes / "archive").glob(f"*-{change_id}"))
    archived = [path for path in archived if path.is_dir()]
    return archived[-1] if archived else live


def spool_path(change_id: str, *, repo_root: Path | str | None = None) -> Path:
    """``<repo>/openspec/changes/<change-id>/reviews/spend-spool.jsonl``.

    Falls back to the archived change directory when the change has been
    archived. ``repo_root`` defaults to the git top level of the current
    directory (the worker's worktree). Raises ``ValueError`` for a change id
    that is not a single safe path segment.
    """
    if not change_id or not _CHANGE_ID_RE.match(change_id) or change_id in {".", ".."}:
        raise ValueError(f"unsafe change id: {change_id!r}")
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    return _change_dir(change_id, root) / "reviews" / SPOOL_NAME


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #


def _clean_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ROW_FIELDS if row.get(key) is not None}


def row_from_review_result(
    result: Any,
    *,
    lane_id: str,
    work_unit_ref: str | None,
    endpoint_kind: str = "openrouter",
) -> dict[str, Any]:
    """Build a spend row from an OpenAI-compatible ``ReviewResult``.

    ``vendor`` is the lane id; ``tokens_estimated`` is true unless the
    response reported its cost (``cost_source == "reported"``).
    """
    row = {
        "vendor": lane_id,
        "model": getattr(result, "model_used", None),
        "endpoint_kind": endpoint_kind,
        "generation_id": getattr(result, "generation_id", None),
        "prompt_tokens": getattr(result, "prompt_tokens", None),
        "completion_tokens": getattr(result, "completion_tokens", None),
        "actual_usd": getattr(result, "cost_usd", None),
        "tokens_estimated": getattr(result, "cost_source", None) != "reported",
        "work_unit_ref": work_unit_ref,
    }
    return _clean_row(row)


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #


def _failure_reason(response: Mapping[str, Any]) -> str:
    status = response.get("status_code")
    if isinstance(status, int):
        return f"http_{status}"
    error = response.get("error")
    if error in {"missing_http_url", "url_not_allowed"}:
        return str(error)
    return "connection_error"


def _post(
    row: dict[str, Any],
    *,
    transport: Transport | None,
    http_url: str | None,
    api_key: str | None,
    timeout: float,
) -> tuple[bool, int | None, str | None]:
    send = transport or _default_transport
    try:
        response = send(
            method="POST",
            path=SPEND_PATH,
            payload=row,
            http_url=_bridge._resolve_http_url(http_url),
            api_key=_bridge._resolve_api_key(api_key),
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - a recorder failure must never fail a review
        return False, None, "connection_error"
    status = response.get("status_code")
    if status in (200, 201):
        return True, int(status), None
    return False, status if isinstance(status, int) else None, _failure_reason(response)


def _append_spool(path: Path, row: dict[str, Any], reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "row": row,
        "reason": reason,
        "spooled_at": datetime.now(UTC).isoformat(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def record(
    row: Mapping[str, Any],
    *,
    change_id: str,
    repo_root: Path | str | None = None,
    transport: Transport | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RecordOutcome:
    """Post one spend row; on any failure append it to the change's spool.

    Never raises for a coordinator failure. ``http_url`` / ``api_key`` default
    to the coordination bridge's resolution (``COORDINATION_API_URL`` /
    ``COORDINATION_API_KEY``). ``transport`` is injectable for tests.
    """
    clean = _clean_row(row)
    path = spool_path(change_id, repo_root=repo_root)
    ok, status, reason = _post(
        clean, transport=transport, http_url=http_url, api_key=api_key, timeout=timeout
    )
    if ok:
        return RecordOutcome(recorded=True, spooled=False, status_code=status)
    failure = reason or "connection_error"
    _append_spool(path, clean, failure)
    return RecordOutcome(recorded=False, spooled=True, status_code=status, reason=failure)


# --------------------------------------------------------------------------- #
# Spool reads and replay
# --------------------------------------------------------------------------- #


def _read_spool(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    entries: list[dict[str, Any]] = []
    malformed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(entry, dict) and isinstance(entry.get("row"), dict):
            entries.append(entry)
        else:
            malformed += 1
    return entries, malformed


def spooled_total_usd(change_id: str, *, repo_root: Path | str | None = None) -> float:
    """Sum of ``actual_usd`` over the change's unreplayed spool rows.

    The per-round budget re-check (design D4) counts this as used against the
    coordinator ceiling.
    """
    entries, _ = _read_spool(spool_path(change_id, repo_root=repo_root))
    total = 0.0
    for entry in entries:
        try:
            total += max(float(entry["row"].get("actual_usd") or 0.0), 0.0)
        except (TypeError, ValueError):
            continue
    return total


def _write_spool(path: Path, entries: list[dict[str, Any]]) -> None:
    if not entries:
        path.unlink(missing_ok=True)
        return
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".spend-spool.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def replay(
    change_id: str,
    *,
    repo_root: Path | str | None = None,
    transport: Transport | None = None,
    http_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ReplayOutcome:
    """Post every spooled row again and drop each one the ledger now holds.

    A 201 counts as ``replayed``, a 200 (``generation_id`` already recorded) as
    ``already_recorded``; both are removed. Rows that still fail stay in the
    spool. Run it serially (the supervisor's ``apply``): rows appended while a
    replay is in flight can be lost from the spool rewrite.
    """
    path = spool_path(change_id, repo_root=repo_root)
    entries, malformed = _read_spool(path)
    if not entries:
        return ReplayOutcome(malformed=malformed)
    replayed = already = 0
    keep: list[dict[str, Any]] = []
    for entry in entries:
        ok, status, reason = _post(
            _clean_row(entry["row"]),
            transport=transport,
            http_url=http_url,
            api_key=api_key,
            timeout=timeout,
        )
        if ok and status == 201:
            replayed += 1
        elif ok:
            already += 1
        else:
            keep.append({**entry, "reason": reason or "connection_error"})
    _write_spool(path, keep)
    return ReplayOutcome(
        replayed=replayed, already_recorded=already, remaining=len(keep), malformed=malformed
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("replay", "post spooled spend rows to the coordinator (idempotent)"),
        ("total", "print the unreplayed spooled actual_usd total"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--change-id", required=True)
        cmd.add_argument("--repo-root", default=None)
        cmd.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        if args.command == "total":
            total = spooled_total_usd(args.change_id, repo_root=args.repo_root)
            print(json.dumps({"spooled_usd": total}) if args.as_json else f"{total:.6f}")
            return 0
        outcome = replay(args.change_id, repo_root=args.repo_root)
    except ValueError as exc:
        print(f"spend_recorder: {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(outcome.as_dict(), sort_keys=True))
    else:
        print(
            "spend_recorder replay: "
            + " ".join(f"{key}={value}" for key, value in outcome.as_dict().items())
        )
    return 0 if outcome.remaining == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
