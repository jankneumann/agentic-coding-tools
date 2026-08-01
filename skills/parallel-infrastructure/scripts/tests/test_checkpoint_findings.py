"""Review-hardening checkpoint characterization tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checkpoint_findings import read_vendor_findings, write_manifest  # noqa: E402


def test_empty_eligible_vendor_stays_indexed_without_a_findings_file(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        review_type="plan",
        target="change",
        vendors=[{
            "name": "alpha",
            "findings_path": None,
            "finding_count": 0,
            "quorum_eligible": True,
        }],
    )

    assert read_vendor_findings(tmp_path) == {"alpha": []}
