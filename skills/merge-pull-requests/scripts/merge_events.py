"""Merge event emission and loading for merge throughput metrics.

Emits structured JSON events to a local JSONL file and optionally to the
coordinator audit service. Each event follows the D6 schema from design.md.

``event_type`` is an open ``str`` and :meth:`MergeEvent.to_dict` drops ``None``
fields, which is what lets a new kind of record land here without touching a
single reader: ``merge_metrics`` switches on the event types it knows and ignores
the rest, and every field a record does not set is simply absent from its JSON.
``context_gate`` (D7 of rescope-context-drift-enforcement) is the first record to
use that seam -- see :func:`context_gate_event`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


#: Relative on purpose -- the skill runs from a worktree root and writes the
#: log into that worktree's docs/. Because it is relative it resolves against
#: the CWD, so anything invoked from elsewhere writes wherever it happens to
#: be standing. The functions below read this at CALL time rather than binding
#: it as a default argument at import time, which makes it a single
#: monkeypatchable seam; the suite's conftest.py redirects it to tmp_path so a
#: test exercising auto_rebase / auto_rollback / merge_watcher cannot append to
#: the repo's own tracked metrics.jsonl (it did, until 2026-08-25).
DEFAULT_LOG_PATH = Path("docs/merge-logs/metrics.jsonl")


@dataclass
class MergeEvent:
    event_type: str
    pr_number: int
    backend: str
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    origin: str | None = None
    strategy: str | None = None
    duration_seconds: float | None = None
    queue_depth: int | None = None
    partition_count: int | None = None
    train_id: str | None = None
    error: str | None = None

    # ----------------------------------------------------------------- #
    # ``context_gate`` fields (D7). Every one of them is optional and every
    # one is ``gate_``-prefixed, so a merge record serialises to exactly the
    # keys it serialised to before this block existed, and a reader can
    # select the whole namespace by prefix instead of by an enumeration it
    # would have to keep in step. Set as a group by
    # :func:`context_gate_event`; never set on a merge record.
    # ----------------------------------------------------------------- #
    gate_outcome: str | None = None
    gate_exit_code: int | None = None
    gate_event: str | None = None
    gate_source_revision: str | None = None
    gate_base_revision: str | None = None
    gate_base_resolved_from: str | None = None
    gate_blocking_inherited: int | None = None
    gate_blocking_introduced: int | None = None
    gate_blocking_indeterminate: int | None = None
    gate_informational_inherited: int | None = None
    gate_informational_introduced: int | None = None
    gate_informational_indeterminate: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


#: Event type for one deterministic context drift gate run (D7).
CONTEXT_GATE_EVENT_TYPE = "context_gate"

#: ``backend`` for a gate record. The field names the mechanism that produced the
#: row; for a merge that is the merge backend, and for a gate run it is the gate.
#: No reader aggregates it outside ``event_type == "merge"``, so this is a label,
#: not a discriminator.
CONTEXT_GATE_BACKEND = "context-drift-gate"

#: ``pr_number`` for a gate run that is not answering for a pull request -- a
#: ``merge_group``, a ``push``, or a developer at a shell. Zero rather than a
#: dropped field, because ``pr_number`` is required on every record and an
#: invented number would join against a real pull request.
NO_PULL_REQUEST = 0


def context_gate_event(
    *,
    outcome: str,
    exit_code: int,
    gate_event: str | None = None,
    source_revision: str | None = None,
    base_revision: str | None = None,
    base_resolved_from: str | None = None,
    blocking_inherited: int = 0,
    blocking_introduced: int = 0,
    blocking_indeterminate: int = 0,
    informational_inherited: int = 0,
    informational_introduced: int = 0,
    informational_indeterminate: int = 0,
    pr_number: int = NO_PULL_REQUEST,
) -> MergeEvent:
    """Build the record for one context drift gate run (D7).

    The record exists to make the advisory->blocking flip an evidence decision
    rather than an intuition, in the vocabulary ``architecture.config.yaml``
    already uses for the architecture gate (``clean_runs_before_flip: 3``).
    Answering "is introduced drift trending down, and have the last three runs
    been clean" needs four things per run, and the field set is exactly those:

    *outcome* describes the **tree** and *exit_code* answers for the **event**.
    They disagree on precisely the case this change created -- a pull request
    carrying inherited drift reports ``drift (exit 0)`` -- so a record keeping
    only one of them could not tell that run apart from a clean tree.

    *gate_event* is the trigger, because a clean run means different things at
    ``pull_request`` (introduced drift only) and at ``merge_group`` (everything).
    ``None`` means no event was supplied, which selects the strict rule; it is
    recorded as an absent key rather than a placeholder, because "no event" is a
    real state and inventing a name for it would make it unqueryable.

    *base_revision* and *base_resolved_from* record the base the verdict was
    taken against, so a trend line cannot silently be two trend lines measured
    against two different bases.

    The six counters are the attribution axis, split by drift group. Blocking
    counts drive the flip; informational counts are the control group -- the
    projection producer never blocks, so a shift there is evidence about the
    attribution machinery rather than about the tree. Counters are plain ints
    including zero: ``to_dict`` drops ``None``, so a zero must be a genuine zero
    or a clean run would serialise as a run that never measured.

    *success* is derived, not passed: for a gate record it means this run's
    verdict was green, which is the same question ``merge_success_rate`` asks of
    a merge and keeps the field's meaning stable across event types.
    """
    return MergeEvent(
        event_type=CONTEXT_GATE_EVENT_TYPE,
        pr_number=pr_number,
        backend=CONTEXT_GATE_BACKEND,
        success=exit_code == 0,
        gate_outcome=outcome,
        gate_exit_code=exit_code,
        gate_event=gate_event,
        gate_source_revision=source_revision,
        gate_base_revision=base_revision,
        gate_base_resolved_from=base_resolved_from,
        gate_blocking_inherited=blocking_inherited,
        gate_blocking_introduced=blocking_introduced,
        gate_blocking_indeterminate=blocking_indeterminate,
        gate_informational_inherited=informational_inherited,
        gate_informational_introduced=informational_introduced,
        gate_informational_indeterminate=informational_indeterminate,
    )


def emit_event(
    event: MergeEvent,
    *,
    log_path: Path | None = None,
) -> None:
    log_path = DEFAULT_LOG_PATH if log_path is None else log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(event.to_json() + "\n")


def load_events(
    *,
    log_path: Path | None = None,
    event_type: str | None = None,
) -> list[dict]:
    log_path = DEFAULT_LOG_PATH if log_path is None else log_path
    if not log_path.exists():
        return []
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if event_type and parsed.get("event_type") != event_type:
                continue
            events.append(parsed)
    return events
