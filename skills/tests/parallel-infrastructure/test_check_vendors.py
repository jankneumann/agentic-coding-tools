"""Tests for ``review_dispatcher.py --check-vendors``.

The flag exists so an orchestrator can detect CLI review availability from an
exit status. The contract that matters is **fail closed**: anything other than
a confirmed quorum must be non-zero, because a false "vendors available" enables
multi-vendor review with nothing behind it (issue 853e8242).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import review_dispatcher as rd

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "parallel-infrastructure"
    / "scripts"
    / "review_dispatcher.py"
)


class _Reviewer:
    def __init__(self, vendor: str) -> None:
        self.vendor = vendor


class _Orch:
    """Stand-in orchestrator yielding a fixed reviewer set."""

    def __init__(self, vendors: list[str]) -> None:
        self._vendors = vendors
        self.adapters = {v: object() for v in vendors}

    def discover_reviewers(self, exclude_vendor=None, dispatch_mode="review"):
        return [_Reviewer(v) for v in self._vendors if v != exclude_vendor]


@pytest.fixture()
def _patch_orch(monkeypatch):
    def _install(vendors: list[str] | Exception):
        def _from_agents_yaml(*_args, **_kwargs):
            if isinstance(vendors, Exception):
                raise vendors
            return _Orch(vendors)

        monkeypatch.setattr(
            rd.ReviewOrchestrator, "from_agents_yaml",
            staticmethod(_from_agents_yaml),
        )
        monkeypatch.setattr(
            rd.ReviewOrchestrator, "from_coordinator",
            staticmethod(lambda *a, **k: _Orch([])),
        )

    return _install


def test_quorum_met_exits_zero(_patch_orch) -> None:
    _patch_orch(["claude_code", "codex"])

    assert rd._check_vendors(min_vendors=2) == 0


def test_below_quorum_exits_nonzero(_patch_orch) -> None:
    _patch_orch(["claude_code"])

    assert rd._check_vendors(min_vendors=2) == rd.CHECK_VENDORS_BELOW_QUORUM


def test_no_vendors_exits_nonzero(_patch_orch) -> None:
    _patch_orch([])

    assert rd._check_vendors(min_vendors=2) != 0


def test_exclude_vendor_counts_against_quorum(_patch_orch) -> None:
    """Excluding the vendor under retirement can drop the roster below quorum."""
    _patch_orch(["claude_code", "grok"])

    assert rd._check_vendors(min_vendors=2, exclude_vendor="grok") != 0
    assert rd._check_vendors(min_vendors=2) == 0


def test_roster_resolution_error_fails_closed(_patch_orch) -> None:
    """A broken roster must report below-quorum, never pass silently."""
    _patch_orch(RuntimeError("agents.yaml unreadable"))

    assert rd._check_vendors(min_vendors=2) == rd.CHECK_VENDORS_BELOW_QUORUM


def test_min_vendors_is_configurable(_patch_orch) -> None:
    _patch_orch(["claude_code", "codex"])

    assert rd._check_vendors(min_vendors=3) != 0
    assert rd._check_vendors(min_vendors=1) == 0


def test_flag_is_accepted_by_the_cli() -> None:
    """The documented invocation must parse — the original defect was that
    ``--check-vendors`` did not exist and exited 2 on an argparse error."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-vendors", "--min-vendors", "2"],
        capture_output=True, text=True, timeout=120,
    )

    combined = proc.stdout + proc.stderr
    assert "unrecognized arguments" not in combined
    assert "check-vendors:" in combined
    assert proc.returncode in (0, rd.CHECK_VENDORS_BELOW_QUORUM)


def test_check_vendors_needs_no_review_type() -> None:
    """The probe must not require --review-type; it is a pre-dispatch check."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-vendors"],
        capture_output=True, text=True, timeout=120,
    )

    assert "--review-type required" not in (proc.stdout + proc.stderr)
