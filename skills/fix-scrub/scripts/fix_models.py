#!/usr/bin/env python3
"""Fix-scrub data models.

Imports Finding and FindingOrigin from bug-scrub's models module using
importlib to avoid circular import (both skills have a models.py).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

# Load bug-scrub models via importlib under a unique name to avoid collision
# __file__ is at skills/fix-scrub/scripts/models.py
# bug-scrub is at skills/bug-scrub/scripts/models.py (sibling skill)
_bug_scrub_models_path = str(
    Path(__file__).resolve().parents[2] / "bug-scrub" / "scripts" / "models.py"
)

if "bug_scrub_models" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("bug_scrub_models", _bug_scrub_models_path)
    assert _spec is not None and _spec.loader is not None
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["bug_scrub_models"] = _mod
    _spec.loader.exec_module(_mod)

import bug_scrub_models as _bsm  # noqa: E402

Finding = _bsm.Finding
FindingOrigin = _bsm.FindingOrigin
severity_rank = _bsm.severity_rank

FixTier = Literal["auto", "agent", "manual"]


@dataclass(slots=True)
class ClassifiedFinding:
    """A finding with its fixability classification."""

    finding: Finding
    tier: FixTier
    fix_strategy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.to_dict(),
            "tier": self.tier,
            "fix_strategy": self.fix_strategy,
        }


@dataclass(slots=True)
class FixGroup:
    """Group of classified findings sharing a file path."""

    file_path: str
    classified_findings: list[ClassifiedFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "classified_findings": [cf.to_dict() for cf in self.classified_findings],
        }


@dataclass(slots=True)
class FixPlan:
    """Complete fix execution plan."""

    auto_groups: list[FixGroup] = field(default_factory=list)
    agent_groups: list[FixGroup] = field(default_factory=list)
    manual_findings: list[ClassifiedFinding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_groups": [g.to_dict() for g in self.auto_groups],
            "agent_groups": [g.to_dict() for g in self.agent_groups],
            "manual_findings": [cf.to_dict() for cf in self.manual_findings],
            "summary": self.summary,
        }
