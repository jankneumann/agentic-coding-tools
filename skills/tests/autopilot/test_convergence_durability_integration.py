"""Integration test: durable checkpoint survives the line_range parser bug.

Reproduces the original failure mode that motivated this proposal — vendor
findings with ``line_range: "10-20"`` (the malformed string shape) cause
the in-process synthesizer to raise (because consensus_synthesizer.py:59's
``Finding.from_dict()`` does ``line_range.get("start")`` on what may be a
str). Asserts:

  (a) the original exception propagates to the caller
  (b) the checkpoint files exist on disk and contain the original findings
  (c) running ``consensus_synthesizer.py`` manually against the checkpoint
      via subprocess STILL fails (the parser bug is intentionally unfixed
      here — its fix is a separate Post-Merge Action proposal)
  (d) the structured ``convergence.synthesis_failed_with_checkpoint`` log
      entry was emitted with the correct fields

This verifies durability and observability — NOT recovery. The proposal
explicitly does not introduce automatic recovery.

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


class _BuggyVendorOrchestrator:
    """Returns vendor results whose findings include the malformed
    ``line_range: "10-20"`` shape — the exact bug this proposal makes
    survivable."""

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


def test_line_range_bug_propagates_with_durable_checkpoint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Full durability + observability contract under the real parser bug."""

    # Use REAL ConsensusSynthesizer (no monkeypatch) so we hit the actual bug.
    orch = _BuggyVendorOrchestrator()

    with caplog.at_level(logging.ERROR, logger="checkpoint_findings"):
        # (a) Original exception propagates. The bug raises AttributeError
        # because str.get() doesn't exist.
        with pytest.raises(AttributeError, match="'str' object has no attribute"):
            converge(
                change_id="test-feature",
                review_type="plan",
                artifacts_dir=tmp_path,
                worktree_path=tmp_path,
                orchestrator=orch,  # type: ignore[arg-type]
                max_rounds=1,
                min_quorum=2,
            )

    # (b) Checkpoint files exist on disk and contain the original findings.
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

    # (c) Manual subprocess invocation of consensus_synthesizer.py against
    # the checkpoint STILL fails — this verifies the parser bug is unfixed
    # (out of scope; separate Post-Merge proposal). The point is durability:
    # the data is on disk and re-runnable; recovery awaits the parser fix.
    findings_files = sorted(str(p) for p in checkpoint_dir.glob("findings-*-plan.json"))
    assert len(findings_files) == 2
    output_path = tmp_path / "consensus-attempt.json"
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
    assert proc.returncode != 0, (
        f"Expected synthesizer subprocess to fail (parser bug unfixed). "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # The same AttributeError surface is what we expect in stderr.
    assert "AttributeError" in proc.stderr or "'str' object has no attribute" in proc.stderr, (
        f"Subprocess should fail with the line_range AttributeError. "
        f"stderr={proc.stderr!r}"
    )

    # (d) Structured log entry was emitted with the correct fields.
    events = [
        r for r in caplog.records
        if getattr(r, "event", None) == "convergence.synthesis_failed_with_checkpoint"
    ]
    assert len(events) == 1
    rec = events[0]
    assert rec.change_id == "test-feature"  # type: ignore[attr-defined]
    assert rec.review_type == "plan"  # type: ignore[attr-defined]
    assert rec.original_exception_class == "AttributeError"  # type: ignore[attr-defined]
    # The checkpoint_dir field in the log payload points at the actual checkpoint.
    assert "round-1" in str(rec.checkpoint_dir)  # type: ignore[attr-defined]


def test_checkpoint_findings_round_trip_against_real_synthesizer_input_format(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The on-disk format the helper writes is exactly what
    consensus_synthesizer.py's CLI consumes — no shape adaptation needed
    between the two paths. Any vendor that produces a wrapper-object the
    in-process path accepts can be replayed from the checkpoint."""
    orch = _BuggyVendorOrchestrator()

    with pytest.raises(AttributeError):
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
