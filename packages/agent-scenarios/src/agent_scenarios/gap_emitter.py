"""Capability-gap emission for deterministic scenario failures (design D3).

Every ``VendorRunVerdict`` with ``deterministic_status == "fail"`` becomes one
``source:scenario-parity`` episodic-memory entry (the body of the coordinator's
``POST /memory/store``). Entries the coordinator does not acknowledge are spooled to a local
JSONL file and replayed by :func:`flush_spool`. ``error``, ``skipped_budget`` and judge-only
results never emit gaps.

Standalone on purpose: stdlib ``urllib`` only, no dependency on ``skills/coordination-bridge``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import ParityMatrix
from .results_store import default_state_dir

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "agent-scenarios-nightly"
DEFAULT_URL_ENV = "COORDINATION_API_URL"
DEFAULT_KEY_ENV = "COORDINATION_API_KEY"
DETAIL_MAX_CHARS = 500
REQUEST_TIMEOUT_SECONDS = 10.0

GapEntry = dict[str, Any]


def default_spool_path() -> Path:
    return default_state_dir() / "gap-spool.jsonl"


# ---------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------


def build_gap_entries(
    run_id: str,
    matrices: Sequence[ParityMatrix],
    *,
    skill_of: Mapping[str, str],
    agent_id: str = DEFAULT_AGENT_ID,
    repo_sha: str | None = None,
    skills_sha: str | None = None,
) -> list[GapEntry]:
    """One capability-gap entry per ``fail`` verdict; nothing for anything else.

    The ``capability_gap:`` key uses the first failed gate in scenario declaration order
    (``failed_gates`` preserves the scorer's order), so it is stable across runs.
    """
    entries: list[GapEntry] = []
    for matrix in matrices:
        skill = skill_of[matrix.scenario_id]
        for verdict in matrix.results:
            if verdict.deterministic_status != "fail":
                continue
            failed = verdict.failed_gates
            if not failed:  # cannot happen for a scorer-produced fail; stay defensive
                continue
            gate_ids = [g.gate_id for g in failed]
            entries.append(
                {
                    "agent_id": agent_id,
                    "session_id": run_id,
                    "event_type": "capability_gap",
                    "summary": (
                        f"[{verdict.vendor}] scenario {matrix.scenario_id} "
                        f"failed gates: {', '.join(gate_ids)}"
                    ),
                    "details": {
                        "run_id": run_id,
                        "scenario_id": matrix.scenario_id,
                        "vendor": verdict.vendor,
                        "failed_gates": [
                            {"gate_id": g.gate_id, "detail": g.detail[:DETAIL_MAX_CHARS]}
                            for g in failed
                        ],
                        "skills_sha": skills_sha,
                        "repo_sha": repo_sha,
                    },
                    "tags": [
                        "capability_gap",
                        f"capability_gap:scenario-parity/{matrix.scenario_id}/{gate_ids[0]}",
                        "failure_type:verification_failed",
                        f"affected_skill:{skill}",
                        "severity:high",
                        "source:scenario-parity",
                        f"vendor:{verdict.vendor}",
                        f"scenario:{matrix.scenario_id}",
                    ],
                }
            )
    return entries


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------


class MemorySink(Protocol):
    """Destination for gap entries. ``send`` returns True only when delivery is acknowledged."""

    def send(self, entry: GapEntry) -> bool: ...


class CoordinatorMemorySink:
    """POST ``{base_url}/memory/store``. Acknowledged only by HTTP 2xx with ``success: true``."""

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None = None,
        *,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = (base_url or "").strip().rstrip("/")
        self._api_key = (api_key or "").strip()
        self._timeout = timeout

    @classmethod
    def from_env(
        cls,
        url_env: str = DEFAULT_URL_ENV,
        key_env: str = DEFAULT_KEY_ENV,
        *,
        environ: Mapping[str, str] | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> CoordinatorMemorySink:
        env = os.environ if environ is None else environ
        return cls(env.get(url_env), env.get(key_env), timeout=timeout)

    def send(self, entry: GapEntry) -> bool:
        if not self._base_url:
            return False  # unset URL => spool; never guess a localhost default
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/memory/store",
            data=json.dumps(entry).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                status = resp.status
                body = resp.read()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            logger.warning("gap delivery failed: %s", exc)
            return False
        if not 200 <= status < 300:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("gap delivery: coordinator answered with a non-JSON body")
            return False
        return isinstance(payload, dict) and payload.get("success") is True


class SpoolMemorySink:
    """Append entries (one JSON object per line) to a local spool under an exclusive lock."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @property
    def _flush_lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".flush.lock")

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    @contextmanager
    def _flushing(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._flush_lock_path, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def send(self, entry: GapEntry) -> bool:
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        with self.locked(), open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return True

    def _read_lines(self) -> list[str]:
        if not self.path.is_file():
            return []
        return self.path.read_text(encoding="utf-8").splitlines()

    def pending(self) -> list[GapEntry]:
        with self.locked():
            lines = self._read_lines()
        return [e for e in (_parse_line(ln) for ln in lines) if e is not None]


def _parse_line(line: str) -> GapEntry | None:
    if not line.strip():
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("gap spool: dropping unparsable line")
        return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------------------
# Emission and replay
# ---------------------------------------------------------------------------


@dataclass
class EmitResult:
    delivered: int
    spooled: int


def _try_send(sink: MemorySink, entry: GapEntry) -> bool:
    try:
        return sink.send(entry)
    except Exception as exc:  # a sink must never lose an entry by raising
        logger.warning("gap sink raised %s: %s", type(exc).__name__, exc)
        return False


def emit_gaps(
    entries: Sequence[GapEntry], coordinator: MemorySink, spool: SpoolMemorySink
) -> EmitResult:
    """Deliver each entry to the coordinator; spool every entry that is not acknowledged."""
    delivered = spooled = 0
    for entry in entries:
        if _try_send(coordinator, entry):
            delivered += 1
        else:
            spool.send(entry)
            spooled += 1
    return EmitResult(delivered=delivered, spooled=spooled)


@dataclass
class FlushResult:
    delivered: int
    remaining: int


def flush_spool(spool: SpoolMemorySink, coordinator: MemorySink) -> FlushResult:
    """Replay the spool; rewrite it with only the entries that still fail.

    Network calls happen outside the spool lock so a slow coordinator cannot stall emitters.
    The rewrite re-reads the file under the lock and keeps anything appended meanwhile, and a
    separate flush lock serializes concurrent flushers, so nothing is lost or duplicated.
    """
    with spool._flushing():
        with spool.locked():
            snapshot = spool._read_lines()
        failed: list[str] = []
        delivered = 0
        for line in snapshot:
            entry = _parse_line(line)
            if entry is None:
                continue
            if _try_send(coordinator, entry):
                delivered += 1
            else:
                failed.append(line)
        with spool.locked():
            current = spool._read_lines()
            remaining = failed + current[len(snapshot):]
            _atomic_write_lines(spool.path, remaining)
    return FlushResult(delivered=delivered, remaining=len(remaining))


def _atomic_write_lines(path: Path, lines: Sequence[str]) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(ln + "\n" for ln in lines))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# CLI: agent-scenarios gaps flush
# ---------------------------------------------------------------------------


def add_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the ``gaps`` command group (``gaps flush``)."""
    gaps: argparse.ArgumentParser = subparsers.add_parser(
        "gaps", help="capability-gap spool maintenance"
    )
    sub = gaps.add_subparsers(dest="gaps_cmd", required=True)
    flush = sub.add_parser("flush", help="replay spooled capability-gap entries")
    flush.add_argument("--spool", type=Path, default=None, help="spool JSONL (default: XDG state)")
    flush.add_argument("--url-env", default=DEFAULT_URL_ENV,
                       help="env var holding the coordinator base URL")
    flush.add_argument("--key-env", default=DEFAULT_KEY_ENV,
                       help="env var holding the coordinator API key")
    flush.set_defaults(func=_cmd_flush)
    return gaps


def _cmd_flush(args: argparse.Namespace) -> int:
    spool = SpoolMemorySink(args.spool or default_spool_path())
    sink = CoordinatorMemorySink.from_env(args.url_env, args.key_env)
    result = flush_spool(spool, sink)
    print(json.dumps({"delivered": result.delivered, "remaining": result.remaining}))
    return 0


__all__ = [
    "CoordinatorMemorySink",
    "EmitResult",
    "FlushResult",
    "GapEntry",
    "MemorySink",
    "SpoolMemorySink",
    "add_parser",
    "build_gap_entries",
    "default_spool_path",
    "emit_gaps",
    "flush_spool",
]
