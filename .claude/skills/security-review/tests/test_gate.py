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
