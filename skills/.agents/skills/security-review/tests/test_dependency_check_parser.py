from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from parse_dependency_check import parse_report  # noqa: E402


def test_parse_dependency_check_report() -> None:
    payload = {
        "dependencies": [
            {
                "fileName": "package.json",
                "vulnerabilities": [
                    {
                        "name": "CVE-2025-0001",
                        "severity": "HIGH",
                        "description": "Critical auth bypass",
                    }
                ],
            }
        ]
    }

    result = parse_report(payload)
    assert result.status == "ok"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.finding_id == "CVE-2025-0001"
    assert finding.severity == "high"
    assert finding.location == "package.json"
