"""Integration test: durable checkpoint supports string line_range replay.

Reproduces the original failure mode that motivated the parser fix: vendor
findings with ``line_range: "10-20"`` used to crash
``Finding.from_dict()`` because the synthesizer assumed every non-empty
``line_range`` was a dict. The parser now accepts that string shape, so the
in-process convergence path and manual checkpoint replay both succeed while
preserving the original vendor payload on disk.

Spec scenarios: skill-workflow.R2.S2, skill-workflow.R4.S1.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from convergence_loop import converge  # type: ignore[import-untyped]
from review_dispatcher import ReviewResult  # type: ignore[import-untyped]
from checkpoint_findings import read_manifest, read_vendor_findings  # type: ignore[import-untyped]


# Path to the parallel-infrastructure scripts dir, used for subprocess invocation.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SYNTHESIZER_PATH = (
    _REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts" / "consensus_synthesizer.py"
)


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
                        "type": "logic-error",
                        "criticality": "high",
                        "description": "Off-by-one in pagination",
                        "disposition": "fix",
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
                        "type": "logic-error",
                        "criticality": "high",
                        "description": "Off-by-one in pagination",
                        "disposition": "fix",
                        "file_path": "src/paginate.py",
                        "line_range": "10-20",  # Same malformed shape.
                    }],
                },
            ),
        ]


def test_string_line_range_replays_from_durable_checkpoint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """String line ranges no longer crash synthesis or checkpoint replay."""

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
    assert result.reason == "max_rounds"
    assert result.consensus is not None
    assert result.consensus["summary"]["confirmed_count"] == 1

    checkpoint_dir = tmp_path / ".review-cache" / "round-1"
    assert checkpoint_dir.exists()

    manifest = read_manifest(checkpoint_dir)
    assert manifest["change_id"] == "test-feature"
    assert manifest["review_type"] == "plan"
    assert manifest["schema_version"] == 1
    assert {v["name"] for v in manifest["vendors"]} == {"claude_code", "codex"}

    loaded = read_vendor_findings(checkpoint_dir)
    assert set(loaded) == {"claude_code", "codex"}
    # Findings array preserved verbatim, including the malformed line_range.
    assert loaded["claude_code"][0]["line_range"] == "10-20"
    assert loaded["codex"][0]["line_range"] == "10-20"

    findings_files = sorted(str(p) for p in checkpoint_dir.glob("findings-*-plan.json"))
    assert len(findings_files) == 2
    output_path = tmp_path / "consensus-replay.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(_SYNTHESIZER_PATH),
            "--review-type", "plan",
            "--target", "test-feature",
            "--findings", *findings_files,
            "--output", str(output_path),
            "--quorum", "2",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    replayed = json.loads(output_path.read_text())
    assert replayed["summary"]["confirmed_count"] == 1

    assert not [
        r for r in caplog.records
        if getattr(r, "event", None) == "convergence.synthesis_failed_with_checkpoint"
    ]


def test_checkpoint_findings_round_trip_against_real_synthesizer_input_format(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The on-disk format the helper writes is exactly what
    consensus_synthesizer.py's CLI consumes — no shape adaptation needed
    between the two paths. Any vendor that produces a wrapper-object the
    in-process path accepts can be replayed from the checkpoint."""
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
