"""Integration test: invalid vendor output remains durably recoverable.

Reproduces the original failure mode that motivated the parser fix: vendor
Findings with ``line_range: "10-20"`` violate the canonical schema. The
checkpoint writer must persist them before validation, exclude them from
quorum, and retain the exact payload for diagnosis or repair.

Spec scenarios: skill-workflow.R2.S2, skill-workflow.R4.S1.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from convergence_loop import converge  # type: ignore[import-untyped]
from review_dispatcher import ReviewResult  # type: ignore[import-untyped]
from checkpoint_findings import read_manifest  # type: ignore[import-untyped]


class _StringLineRangeVendorOrchestrator:
    """Returns vendor results whose findings include ``line_range: "10-20"``."""

    def dispatch_and_wait(self, **_kwargs: Any) -> list[ReviewResult]:
        # Two vendors, both with a finding using the malformed string shape.
        # Quorum=2 will be met for the dispatch step; the synthesis step
        # is what crashes.
        return [
            ReviewResult(
                vendor="claude_code",
                success=True,
                model_used="opus",
                models_attempted=["opus"],
                elapsed_seconds=1.0,
                findings={
                    "review_type": "plan",
                    "target": "test-feature",
                    "findings": [{
                        "id": 1,
                        "type": "correctness",
                        "criticality": "high",
                        "description": "Off-by-one in pagination",
                        "disposition": "fix",
                        "axis": "correctness",
                        "severity": "critical",
                        "file_path": "src/paginate.py",
                        # NOTE: the malformed string shape — this is the bug.
                        "line_range": "10-20",
                    }],
                },
            ),
            ReviewResult(
                vendor="codex",
                success=True,
                model_used="gpt-5.4",
                models_attempted=["gpt-5.4"],
                elapsed_seconds=1.0,
                findings={
                    "review_type": "plan",
                    "target": "test-feature",
                    "findings": [{
                        "id": 100,
                        "type": "correctness",
                        "criticality": "high",
                        "description": "Off-by-one in pagination",
                        "disposition": "fix",
                        "axis": "correctness",
                        "severity": "critical",
                        "file_path": "src/paginate.py",
                        "line_range": "10-20",  # Same malformed shape.
                    }],
                },
            ),
        ]


def test_invalid_string_line_range_is_persisted_then_rejected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Schema-invalid findings survive on disk but do not count for quorum."""

    orch = _StringLineRangeVendorOrchestrator()

    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        result = converge(
            change_id="test-feature",
            review_type="plan",
            artifacts_dir=tmp_path,
            worktree_path=tmp_path,
            orchestrator=orch,  # type: ignore[arg-type]
            max_rounds=1,
            min_quorum=2,
        )

    assert result.converged is False
    assert result.reason == "quorum_lost"
    assert result.consensus is None

    checkpoint_dir = tmp_path / ".review-cache" / "round-1"
    assert checkpoint_dir.exists()

    manifest = read_manifest(checkpoint_dir)
    assert manifest["change_id"] == "test-feature"
    assert manifest["review_type"] == "plan"
    assert manifest["schema_version"] == 1
    assert manifest["vendors"] == []
    assert manifest["quorum_received"] == 0

    for vendor in ("claude_code", "codex"):
        data = json.loads(
            (checkpoint_dir / f"findings-{vendor}-plan.json").read_text()
        )
        assert data["findings"][0]["line_range"] == "10-20"

    invalid_events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "convergence.vendor_findings_invalid"
    ]
    assert len(invalid_events) == 2


def test_invalid_checkpoint_keeps_wrapper_shape_for_manual_recovery(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A rejected checkpoint still preserves the standard wrapper shape."""
    orch = _StringLineRangeVendorOrchestrator()

    converge(
        change_id="test-feature",
        review_type="plan",
        artifacts_dir=tmp_path,
        worktree_path=tmp_path,
        orchestrator=orch,  # type: ignore[arg-type]
        max_rounds=1,
        min_quorum=2,
    )

    # Verify the per-vendor file shape matches what consensus_synthesizer.py
    # main() reads at line ~467: ``data = json.loads(p.read_text())`` then
    # ``data.get("reviewer_vendor", ...)`` and ``data.get("findings", [])``.
    checkpoint_dir = tmp_path / ".review-cache" / "round-1"
    for vendor in ("claude_code", "codex"):
        fpath = checkpoint_dir / f"findings-{vendor}-plan.json"
        assert fpath.exists()
        data = json.loads(fpath.read_text())
        # consensus_synthesizer's CLI reads these specific keys:
        assert "reviewer_vendor" in data
        assert data["reviewer_vendor"] == vendor
        assert "findings" in data
        assert isinstance(data["findings"], list)
