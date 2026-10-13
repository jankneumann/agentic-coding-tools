"""Human oracle-source label ledger (design D2, D9).

A sidecar JSON file keyed by pytest node id plus a normalized content hash,
so a label goes stale when its test's logic changes. Test files are never
edited. Reusable by ri-08 through ``entry_type``.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .records import validate
from .vocabulary import ORACLE_SOURCES, validate_label

LEDGER_SCHEMA_VERSION = 1


class LabelState(str, enum.Enum):
    CURRENT = "current"
    STALE = "stale"


@dataclass(frozen=True)
class LabelEntry:
    node_id: str
    content_hash: str
    label: str
    labeller: str
    labelled_at: str
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "node_id": self.node_id,
            "content_hash": self.content_hash,
            "label": self.label,
            "labeller": self.labeller,
            "labelled_at": self.labelled_at,
        }
        if self.note is not None:
            out["note"] = self.note
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> LabelEntry:
        return cls(
            node_id=data["node_id"],
            content_hash=data["content_hash"],
            label=data["label"],
            labeller=data["labeller"],
            labelled_at=data["labelled_at"],
            note=data.get("note"),
        )


class LabelLedger:
    """In-memory view of a label ledger file."""

    def __init__(
        self,
        entries: list[LabelEntry] | None = None,
        *,
        path: Path | None = None,
        entry_type: str = "pytest_test",
        sample: dict[str, Any] | None = None,
    ) -> None:
        self.entries: list[LabelEntry] = list(entries or [])
        self.path = Path(path) if path is not None else None
        self.entry_type = entry_type
        self.sample = sample

    @classmethod
    def load(cls, path: Path) -> LabelLedger:
        """Load ``path``; a missing file is an empty ledger."""
        path = Path(path)
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text("utf-8"))
        validate(data, "label-ledger")
        return cls(
            [LabelEntry.from_json(e) for e in data.get("entries", [])],
            path=path,
            entry_type=data.get("entry_type", "pytest_test"),
            sample=data.get("sample"),
        )

    def add(
        self,
        node_id: str,
        content_hash: str,
        label: str,
        labeller: str,
        *,
        note: str | None = None,
        labelled_at: str | None = None,
    ) -> LabelEntry:
        """Append one label; raise ``ValueError`` for a label outside the vocabulary."""
        validate_label(label)
        entry = LabelEntry(
            node_id=node_id,
            content_hash=content_hash,
            label=label,
            labeller=labeller,
            labelled_at=labelled_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            note=note,
        )
        self.entries.append(entry)
        return entry

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "entry_type": self.entry_type,
            "vocabulary": list(ORACLE_SOURCES),
            "entries": [e.to_json() for e in self.entries],
        }
        if self.sample is not None:
            data["sample"] = self.sample
        return data

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("no path given and the ledger was not loaded from one")
        data = self.to_json()
        validate(data, "label-ledger")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self.path = target
        return target

    @staticmethod
    def state(entry: LabelEntry, current_hash: str | None) -> LabelState:
        """``CURRENT`` when the test still hashes the same, else ``STALE``."""
        return LabelState.CURRENT if current_hash == entry.content_hash else LabelState.STALE

    def states(self, current_hashes: Mapping[str, str]) -> list[tuple[LabelEntry, LabelState]]:
        return [(e, self.state(e, current_hashes.get(e.node_id))) for e in self.entries]

    def current_labels(self, current_hashes: Mapping[str, str]) -> dict[str, LabelEntry]:
        """First current (non-stale) entry per node id; stale entries are excluded."""
        out: dict[str, LabelEntry] = {}
        for entry, state in self.states(current_hashes):
            if state is LabelState.CURRENT and entry.node_id not in out:
                out[entry.node_id] = entry
        return out

    def labelled_node_ids(self) -> set[str]:
        return {e.node_id for e in self.entries}
