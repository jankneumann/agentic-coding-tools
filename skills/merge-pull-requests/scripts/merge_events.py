"""Merge event emission and loading for merge throughput metrics.

Emits structured JSON events to a local JSONL file and optionally to the
coordinator audit service. Each event follows the D6 schema from design.md.
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

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


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
