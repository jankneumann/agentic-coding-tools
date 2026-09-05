"""Characterization: test_quality findings never block convergence alone.

Pins existing `_is_blocking` behavior in `convergence_loop.py` that the
`skill-workflow` spec's "Implementation Review Test-Quality Findings"
requirement now depends on: a round whose only consensus findings are
`type: test_quality` at `criticality: low` converges, because `_is_blocking`
keys on `agreed_criticality` alone (never on `type`) and `low` is not in
`_BLOCKING_CRITICALITIES`.

This test is a CHARACTERIZATION, not a RED-phase test — `_is_blocking`
already behaves this way before any change in this work package, and it
passes unmodified against the current `convergence_loop.py`. It exists so
the guarantee the spec scenario makes ("the round SHALL converge") is pinned
by an executable test rather than left implicit in the criticality gate.

Spec scenario: skill-workflow "Implementation Review Test-Quality Findings" —
Scenario: Test-quality findings do not block convergence alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parents[2]
_AUTOPILOT_SCRIPTS = _SKILLS_DIR / "autopilot" / "scripts"
if str(_AUTOPILOT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AUTOPILOT_SCRIPTS))

from convergence_loop import _is_blocking  # type: ignore[import-untyped]  # noqa: E402


def _test_quality_finding(**overrides) -> dict:
    """Build a consensus-finding dict shaped as convergence_loop expects
    (see synthesize_consensus / consensus_findings entries: `agreed_criticality`,
    `status`), for a read-only test_quality finding at criticality: low."""
    finding = {
        "id": 1,
        "type": "test_quality",
        "axis": "readability",
        "agreed_criticality": "low",
        "status": "confirmed",
        "description": "Nit: tests/foo_test.py:12 mirrors the source constant instead of behavior.",
        "disposition": "fix",
        "package_id": "wp-example",
        "file_path": "tests/foo_test.py",
    }
    finding.update(overrides)
    return finding


def test_confirmed_test_quality_low_criticality_is_not_blocking() -> None:
    cf = _test_quality_finding(status="confirmed")
    assert _is_blocking(cf) is False


def test_unconfirmed_test_quality_low_criticality_is_not_blocking() -> None:
    cf = _test_quality_finding(status="unconfirmed")
    assert _is_blocking(cf) is False


def test_unconfirmed_test_quality_low_criticality_is_not_blocking_final_round() -> None:
    cf = _test_quality_finding(status="unconfirmed")
    assert _is_blocking(cf, relax_unconfirmed=True) is False


def test_round_of_only_test_quality_findings_yields_no_blocking() -> None:
    """Mirrors the filter expression convergence_loop uses to build `blocking`
    (see convergence_loop.py ~line 536-546: a list comprehension over
    consensus_findings filtered by _is_blocking)."""
    consensus_findings = [
        _test_quality_finding(id=1, status="confirmed"),
        _test_quality_finding(id=2, status="unconfirmed"),
        _test_quality_finding(id=3, status="confirmed", axis="correctness"),
    ]

    blocking = [
        cf for cf in consensus_findings
        if _is_blocking(cf, relax_unconfirmed=False, blocking_criticalities=None)
    ]

    assert blocking == []


def test_medium_criticality_control_is_blocking() -> None:
    """Control: a medium-criticality finding of any type IS blocking, proving
    the low-criticality test_quality cases above are not vacuously true."""
    cf = _test_quality_finding(agreed_criticality="medium", status="confirmed")
    assert _is_blocking(cf) is True
