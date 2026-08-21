from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from gate import evaluate_gate  # noqa: E402


def test_gate_fail_on_threshold() -> None:
    scanner_results = [{"scanner": "dependency-check", "status": "ok"}]
    findings = [{"severity": "high", "finding_id": "CVE-1"}]
    result = evaluate_gate(scanner_results, findings, fail_on="medium", allow_degraded_pass=False)
    assert result.decision == "FAIL"
    assert result.triggered_count == 1


def test_gate_inconclusive_when_scanner_unavailable() -> None:
    scanner_results = [{"scanner": "zap", "status": "unavailable"}]
    findings = []
    result = evaluate_gate(scanner_results, findings, fail_on="high", allow_degraded_pass=False)
    assert result.decision == "INCONCLUSIVE"


def test_gate_pass_when_degraded_allowed_and_no_findings() -> None:
    scanner_results = [{"scanner": "zap", "status": "unavailable"}]
    findings = []
    result = evaluate_gate(scanner_results, findings, fail_on="high", allow_degraded_pass=True)
    assert result.decision == "PASS"


# ---------------------------------------------------------------------------
# Degraded transparency (OpenSpec introduce-fitness-function-gates, D6)
#
# `--allow-degraded-pass` is a documented fail-open path: the gate returns PASS
# even though a scanner never ran. The decision stays PASS (callers depend on
# the exit code), but the reasons must say DEGRADED and name what was not
# checked, so a report can distinguish "clean" from "couldn't look".
# ---------------------------------------------------------------------------


def test_degraded_pass_reasons_are_marked_degraded() -> None:
    scanner_results = [{"scanner": "zap", "status": "unavailable"}]
    result = evaluate_gate(scanner_results, [], fail_on="high", allow_degraded_pass=True)

    joined = " ".join(result.reasons)
    assert "DEGRADED" in joined
    assert "NOT CHECKED" in joined


def test_degraded_pass_names_the_missing_scanner() -> None:
    scanner_results = [
        {"scanner": "zap", "status": "unavailable"},
        {"scanner": "dependency-check", "status": "error"},
        {"scanner": "semgrep", "status": "ok"},
    ]
    result = evaluate_gate(scanner_results, [], fail_on="high", allow_degraded_pass=True)

    joined = " ".join(result.reasons)
    assert "zap" in joined
    assert "dependency-check" in joined
    # A scanner that actually ran must not be reported as unchecked.
    assert "semgrep" not in joined


def test_clean_pass_is_not_marked_degraded() -> None:
    scanner_results = [{"scanner": "zap", "status": "ok"}]
    result = evaluate_gate(scanner_results, [], fail_on="high", allow_degraded_pass=True)

    assert result.decision == "PASS"
    assert "DEGRADED" not in " ".join(result.reasons)


def test_inconclusive_reasons_also_say_not_checked() -> None:
    scanner_results = [{"scanner": "zap", "status": "unavailable"}]
    result = evaluate_gate(scanner_results, [], fail_on="high", allow_degraded_pass=False)

    joined = " ".join(result.reasons)
    assert result.decision == "INCONCLUSIVE"
    assert "NOT CHECKED" in joined
