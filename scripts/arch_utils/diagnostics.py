"""Structured diagnostics for architecture analysis scripts.

Provides a collector that accumulates errors, warnings, and info findings
and can report them consistently to stderr or serialise them to JSON.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    """A single diagnostic finding."""

    severity: str  # "error", "warning", "info"
    code: str  # e.g. "ORPHAN_NODE", "MISSING_TEST"
    message: str
    node_id: str | None = None
    file: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.node_id is not None:
            d["node_id"] = self.node_id
        if self.file is not None:
            d["file"] = self.file
        if self.details:
            d["details"] = self.details
        return d


class DiagnosticCollector:
    """Accumulates diagnostics and provides summary counts.

    Usage::

        dc = DiagnosticCollector()
        dc.error("SCHEMA_MISMATCH", "Expected 'functions' key", file="python_analysis.json")
        dc.warning("LOW_EDGE_COUNT", "Only 6 edges for 518 nodes")
        dc.info("ORPHAN_NODE", "Node has no edges", node_id="py:utils.helper")

        # At the end:
        dc.print_summary()
        sys.exit(dc.exit_code)
    """

    def __init__(self) -> None:
        self.items: list[Diagnostic] = []

    # -- convenience methods --

    def error(self, code: str, message: str, **kwargs: Any) -> None:
        self.items.append(Diagnostic(severity="error", code=code, message=message, **kwargs))

    def warning(self, code: str, message: str, **kwargs: Any) -> None:
        self.items.append(Diagnostic(severity="warning", code=code, message=message, **kwargs))

    def info(self, code: str, message: str, **kwargs: Any) -> None:
        self.items.append(Diagnostic(severity="info", code=code, message=message, **kwargs))

    # -- queries --

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "warning"]

    @property
    def exit_code(self) -> int:
        """0 if no errors, 1 otherwise."""
        return 1 if self.errors else 0

    def count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
        for d in self.items:
            counts[d.severity] = counts.get(d.severity, 0) + 1
        return counts

    def to_list(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self.items]

    # -- output --

    def print_summary(self, *, file: Any = None) -> None:
        """Print a one-line summary of diagnostic counts."""
        out = file or sys.stderr
        c = self.count_by_severity()
        print(
            f"Diagnostics: {c['error']} error(s), {c['warning']} warning(s), {c['info']} info(s)",
            file=out,
        )
