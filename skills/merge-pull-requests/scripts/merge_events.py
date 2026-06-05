"""Merge event emission and loading for merge throughput metrics.

Emits structured JSON events to a local JSONL file and optionally to the
coordinator audit service. Each event follows the D6 schema from design.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


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
    log_path: Path = DEFAULT_LOG_PATH,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(event.to_json() + "\n")


def load_events(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    event_type: str | None = None,
) -> list[dict]:
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
