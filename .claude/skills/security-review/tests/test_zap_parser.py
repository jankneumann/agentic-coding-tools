from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from parse_zap_results import parse_report  # noqa: E402


def test_parse_zap_report() -> None:
    payload = {
        "site": [
            {
                "name": "http://localhost:3000",
                "alerts": [
                    {
                        "pluginid": "10021",
                        "name": "X-Content-Type-Options Header Missing",
                        "riskcode": "1",
                        "desc": "Header missing",
                        "instances": [{"uri": "http://localhost:3000/"}],
                    },
                    {
                        "pluginid": "40001",
                        "name": "SQL Injection",
                        "riskcode": "3",
                        "desc": "Potential SQL injection",
                        "instances": [{"uri": "http://localhost:3000/api"}],
                    },
                ],
            }
        ]
    }

    result = parse_report(payload)
    assert result.status == "ok"
    assert len(result.findings) == 2
    severities = {f.finding_id: f.severity for f in result.findings}
    assert severities["10021"] == "low"
    assert severities["40001"] == "high"
