"""Durable append-only results store (design D2).

One JSONL file holds two record types, both carrying ``schema_version`` and
``record_type``: ``result`` (one per run x scenario x vendor) and ``run`` (one per nightly
invocation, written last). The :class:`ResultsStore` protocol leaves room for a
coordinator-backed implementation later.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from .models import ParityMatrix

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
ResultStatus = Literal["pass", "fail", "error", "skipped_budget"]
RunStatus = Literal[
    "completed", "disabled", "cap_exceeded", "budget_exhausted", "locked", "config_error"
]
SkillFamily = Literal["plan", "implement", "validate", "merge", "other"]
RunState = Literal["complete", "interrupted", "in_progress"]


def default_state_dir() -> Path:
    """``$XDG_STATE_HOME/agent-scenarios`` (``~/.local/state/agent-scenarios`` fallback)."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "agent-scenarios"


def default_results_path() -> Path:
    return default_state_dir() / "results.jsonl"


def lock_path_for(results_path: Path) -> Path:
    """The nightly run lock lives next to the results file."""
    return Path(results_path).parent / "nightly.lock"


def utc_now() -> datetime:
    return datetime.now(UTC)


class ResultRecord(BaseModel):
    """One scored (run, scenario, vendor) pair. Nullable fields are explicit nulls."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    record_type: Literal["result"] = "result"
    run_id: str
    recorded_at: str
    scenario_id: str
    skill_under_test: str
    skill_family: SkillFamily
    vendor: str
    deterministic_status: ResultStatus
    failed_gates: list[str]
    trajectory_status: Literal["pass", "fail", "skip"] | None
    duration_seconds: float | None
    repo_sha: str | None
    skills_sha: str | None
    error: str | None

    @model_validator(mode="after")
    def _consistent(self) -> ResultRecord:
        if not self.run_id or not self.scenario_id or not self.vendor:
            raise ValueError("run_id, scenario_id and vendor must be non-empty")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        if self.deterministic_status == "fail" and not self.failed_gates:
            raise ValueError("a 'fail' result must name at least one failed gate")
        if self.deterministic_status in ("pass", "skipped_budget") and self.failed_gates:
            raise ValueError(f"a '{self.deterministic_status}' result cannot have failed gates")
        if self.deterministic_status == "error" and not self.error:
            raise ValueError("an 'error' result requires an error message")
        parse_ts(self.recorded_at)
        return self


class RunRecord(BaseModel):
    """One nightly invocation summary, always appended last."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    record_type: Literal["run"] = "run"
    run_id: str
    started_at: str
    finished_at: str
    status: RunStatus
    planned_pairs: int
    executed_pairs: int
    vendors: list[str]
    config_digest: str | None
    repo_sha: str | None
    skills_sha: str | None
    reason: str | None

    @model_validator(mode="after")
    def _consistent(self) -> RunRecord:
        if not self.run_id:
            raise ValueError("run_id must be non-empty")
        if self.planned_pairs < 0 or self.executed_pairs < 0:
            raise ValueError("pair counts must be >= 0")
        parse_ts(self.started_at)
        parse_ts(self.finished_at)
        return self


Record = ResultRecord | RunRecord


def parse_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are taken as UTC."""
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def parse_bound(value: str, *, end: bool = False) -> datetime:
    """Parse a ``--since``/``--until`` bound. A bare date is midnight UTC; as an upper
    bound (``end=True``) it covers the whole day."""
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return parse_ts(value)
    start = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return start + timedelta(days=1) - timedelta(microseconds=1) if end else start


@dataclass
class RecordFilter:
    """Filters over ``result`` records (``run`` records only match ``record_type='run'``)."""

    vendor: str | None = None
    skill: str | None = None
    family: str | None = None
    scenario: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    status: Sequence[str] = field(default_factory=tuple)
    run_id: str | None = None

    def matches(self, rec: ResultRecord) -> bool:
        if self.vendor and rec.vendor != self.vendor:
            return False
        if self.skill and rec.skill_under_test != self.skill:
            return False
        if self.family and rec.skill_family != self.family:
            return False
        if self.scenario and rec.scenario_id != self.scenario:
            return False
        if self.run_id and rec.run_id != self.run_id:
            return False
        if self.status and rec.deterministic_status not in self.status:
            return False
        if self.since or self.until:
            ts = parse_ts(rec.recorded_at)
            if self.since and ts < self.since:
                return False
            if self.until and ts > self.until:
                return False
        return True


class ResultsStore(Protocol):
    def append(self, records: Sequence[Record]) -> None: ...

    def iter_records(self, flt: RecordFilter | None = None) -> Iterator[Record]: ...


class JsonlResultsStore:
    """Append-only JSONL store: flock-protected whole-line appends, tolerant reader."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # -- write ------------------------------------------------------------------
    def append(self, records: Sequence[Record]) -> None:
        if not records:
            return
        payload = "".join(
            json.dumps(r.model_dump(mode="json"), separators=(",", ":")) + "\n" for r in records
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "ab+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                prefix = b""
                fh.seek(0, os.SEEK_END)
                if fh.tell() > 0:
                    fh.seek(-1, os.SEEK_END)
                    if fh.read(1) != b"\n":
                        prefix = b"\n"  # a crash tore the last line; do not glue onto it
                fh.write(prefix + payload.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # -- read -------------------------------------------------------------------
    def _parse(self) -> Iterator[Record]:
        if not self.path.is_file():
            return
        with open(self.path, "rb") as fh:
            data = fh.read()
        lines = data.split(b"\n")
        last_index = len(lines) - 1
        for i, raw in enumerate(lines):
            if not raw.strip():
                continue
            torn_tail = i == last_index  # no trailing newline => possibly partial
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(
                    "results store %s: skipping %s line %d",
                    self.path, "torn final" if torn_tail else "unparsable", i + 1,
                )
                continue
            rec = self._to_record(obj, i + 1)
            if rec is not None:
                yield rec

    def _to_record(self, obj: Any, lineno: int) -> Record | None:
        if not isinstance(obj, dict):
            logger.warning("results store %s: line %d is not an object", self.path, lineno)
            return None
        if obj.get("schema_version") != SCHEMA_VERSION:
            logger.warning(
                "results store %s: skipping line %d with unknown schema_version %r",
                self.path, lineno, obj.get("schema_version"),
            )
            return None
        try:
            if obj.get("record_type") == "result":
                return ResultRecord.model_validate(obj)
            if obj.get("record_type") == "run":
                return RunRecord.model_validate(obj)
        except ValueError as exc:
            logger.warning("results store %s: invalid record on line %d: %s",
                           self.path, lineno, str(exc).splitlines()[0])
            return None
        logger.warning("results store %s: unknown record_type on line %d", self.path, lineno)
        return None

    def iter_records(self, flt: RecordFilter | None = None) -> Iterator[Record]:
        for rec in self._parse():
            if flt is None or not isinstance(rec, ResultRecord) or flt.matches(rec):
                yield rec

    def iter_results(self, flt: RecordFilter | None = None) -> Iterator[ResultRecord]:
        for rec in self.iter_records(flt):
            if isinstance(rec, ResultRecord):
                yield rec


# ---------------------------------------------------------------------------
# Run-state annotation (interrupted vs in progress)
# ---------------------------------------------------------------------------


def lock_is_held(lock_path: Path) -> bool:
    """Non-blocking ``flock`` probe; a missing lock file means not held."""
    if not lock_path.exists():
        return False
    try:
        fd = os.open(lock_path, os.O_RDONLY)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def run_states(store: JsonlResultsStore, lock_path: Path | None = None) -> dict[str, RunState]:
    """Classify every run id: ``complete`` (has a run record); else ``in_progress`` for the
    newest unfinished run while the nightly lock is held; else ``interrupted``.

    The lock admits one nightly at a time, so at most one unfinished run can be live: the
    most recently appended one. Older unfinished runs were killed before writing their run
    record and stay ``interrupted`` even while a later nightly holds the lock.
    """
    lock = lock_path or lock_path_for(store.path)
    held = lock_is_held(lock)
    have_run: set[str] = set()
    seen: list[str] = []
    for rec in store.iter_records():
        if isinstance(rec, RunRecord):
            have_run.add(rec.run_id)
        elif rec.run_id not in seen:
            seen.append(rec.run_id)
    states: dict[str, RunState] = dict.fromkeys(have_run, "complete")
    unfinished = [run_id for run_id in seen if run_id not in have_run]
    for run_id in unfinished:
        states[run_id] = "interrupted"
    if held and unfinished:
        states[unfinished[-1]] = "in_progress"
    return states


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

GROUP_BY_CHOICES: dict[str, tuple[str, ...]] = {
    "vendor,skill": ("vendor", "skill"),
    "vendor,family": ("vendor", "family"),
    "scenario,vendor": ("scenario", "vendor"),
}


def _key_value(rec: ResultRecord, key: str) -> str:
    return {
        "vendor": rec.vendor,
        "skill": rec.skill_under_test,
        "family": rec.skill_family,
        "scenario": rec.scenario_id,
    }[key]


def bucket_label(ts: datetime, bucket: Literal["day", "week"]) -> str:
    d = ts.astimezone(UTC).date()
    if bucket == "week":
        d -= timedelta(days=d.weekday())  # Monday of the ISO week
    return d.isoformat()


def compute_trend(
    results: Sequence[ResultRecord],
    group_by: Sequence[str],
    bucket: Literal["day", "week"] = "day",
) -> list[dict[str, Any]]:
    """Pass-rate rows per (bucket, group keys). ``error`` and ``skipped_budget`` are counted
    separately and excluded from the pass-rate denominator (``pass / (pass + fail)``)."""
    counts: dict[tuple[str, ...], dict[str, int]] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "error": 0, "skipped_budget": 0}
    )
    for rec in results:
        key = (bucket_label(parse_ts(rec.recorded_at), bucket),
               *(_key_value(rec, k) for k in group_by))
        counts[key][rec.deterministic_status] += 1
    rows: list[dict[str, Any]] = []
    for key in sorted(counts):
        c = counts[key]
        decided = c["pass"] + c["fail"]
        row: dict[str, Any] = {"bucket": key[0], **dict(zip(group_by, key[1:], strict=True))}
        row.update(c)
        row["pass_rate"] = round(c["pass"] / decided, 4) if decided else None
        rows.append(row)
    return rows


def latest_per_pair(results: Sequence[ResultRecord]) -> list[ResultRecord]:
    """Most recent result per (scenario, vendor); later file position wins ties."""
    best: dict[tuple[str, str], ResultRecord] = {}
    for rec in results:
        key = (rec.scenario_id, rec.vendor)
        cur = best.get(key)
        if cur is None or parse_ts(rec.recorded_at) >= parse_ts(cur.recorded_at):
            best[key] = rec
    return [best[k] for k in sorted(best)]


# ---------------------------------------------------------------------------
# Building records from runner output
# ---------------------------------------------------------------------------


def records_from_matrices(
    run_id: str,
    matrices: Sequence[ParityMatrix],
    *,
    skill_of: Mapping[str, str],
    family_of: Callable[[str], str],
    durations: Mapping[tuple[str, str], float | None] | None = None,
    repo_sha: str | None = None,
    skills_sha: str | None = None,
    recorded_at: datetime | None = None,
) -> list[ResultRecord]:
    """Map ri-15 parity matrices to ``result`` records (design D2 field mapping).

    ``family_of`` is injected (the nightly runner passes ``suite.skill_family``) so this
    module does not depend on the seed-suite taxonomy.
    """
    stamp = (recorded_at or utc_now()).isoformat()
    out: list[ResultRecord] = []
    for matrix in matrices:
        skill = skill_of[matrix.scenario_id]
        for v in matrix.results:
            status: ResultStatus = v.deterministic_status
            error = v.error
            if status == "error" and not error:
                error = "unknown executor error"
            out.append(
                ResultRecord(
                    run_id=run_id,
                    recorded_at=stamp,
                    scenario_id=matrix.scenario_id,
                    skill_under_test=skill,
                    skill_family=family_of(skill),  # type: ignore[arg-type]
                    vendor=v.vendor,
                    deterministic_status=status,
                    failed_gates=[g.gate_id for g in v.failed_gates],
                    trajectory_status=v.trajectory.status,
                    duration_seconds=(durations or {}).get((matrix.scenario_id, v.vendor)),
                    repo_sha=repo_sha,
                    skills_sha=skills_sha,
                    error=error if status == "error" else None,
                )
            )
    return out


def skipped_budget_record(
    run_id: str,
    scenario_id: str,
    skill: str,
    vendor: str,
    *,
    family_of: Callable[[str], str],
    repo_sha: str | None = None,
    skills_sha: str | None = None,
    recorded_at: datetime | None = None,
) -> ResultRecord:
    return ResultRecord(
        run_id=run_id,
        recorded_at=(recorded_at or utc_now()).isoformat(),
        scenario_id=scenario_id,
        skill_under_test=skill,
        skill_family=family_of(skill),  # type: ignore[arg-type]
        vendor=vendor,
        deterministic_status="skipped_budget",
        failed_gates=[],
        trajectory_status=None,
        duration_seconds=None,
        repo_sha=repo_sha,
        skills_sha=skills_sha,
        error=None,
    )


__all__ = [
    "GROUP_BY_CHOICES",
    "JsonlResultsStore",
    "Record",
    "RecordFilter",
    "ResultRecord",
    "ResultsStore",
    "RunRecord",
    "bucket_label",
    "compute_trend",
    "default_results_path",
    "default_state_dir",
    "latest_per_pair",
    "lock_is_held",
    "lock_path_for",
    "parse_bound",
    "parse_ts",
    "records_from_matrices",
    "run_states",
    "skipped_budget_record",
    "utc_now",
]
