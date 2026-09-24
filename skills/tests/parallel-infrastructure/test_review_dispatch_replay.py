"""Replay archived failure blobs through coerce + ingest."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_dispatcher import CliConfig, CliVendorAdapter, ModeConfig
from review_findings_schema import coerce_findings_payload, timeout_for_vendor


def _adapter() -> CliVendorAdapter:
    return CliVendorAdapter(
        agent_id="codex-local",
        vendor="codex",
        cli_config=CliConfig(
            command="codex",
            dispatch_modes={"review": ModeConfig(args=["exec"])},
            model_flag="-m",
        ),
    )


def test_completeness_blob_coerces_to_valid_type() -> None:
    blob = {
        "findings": [
            {
                "id": 1,
                "type": "completeness",
                "criticality": "high",
                "description": "Critical: missing SHALL",
                "disposition": "fix",
            }
        ]
    }
    coerced, notes = coerce_findings_payload(blob)
    assert coerced["findings"][0]["type"] == "architecture"
    assert notes


@patch("review_dispatcher.subprocess.run")
def test_timeout_does_not_count_as_successful_empty(
    mock_run: MagicMock, tmp_path: Path,
) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=10)
    result = _adapter().dispatch("review", "prompt", cwd=tmp_path, timeout_seconds=10)
    assert result.success is False
    assert "Timeout" in (result.error or "")


def test_one_timeout_does_not_imply_quorum_lost_when_two_succeed() -> None:
    """Synthesis proceeds from survivors; timeout is not an empty vote."""
    from consensus_synthesizer import ConsensusSynthesizer, VendorResult, Finding

    timed_out = VendorResult(
        vendor="grok", findings=[], success=False, error="Timeout after 180s",
    )
    ok_a = VendorResult(
        vendor="codex",
        findings=[
            Finding(
                id=1, type="correctness", criticality="low",
                description="ok", disposition="accept", vendor="codex",
            )
        ],
        success=True,
    )
    ok_b = VendorResult(
        vendor="claude_code",
        findings=[
            Finding(
                id=1, type="correctness", criticality="low",
                description="ok", disposition="accept", vendor="claude_code",
            )
        ],
        success=True,
    )
    report = ConsensusSynthesizer(quorum=2).synthesize(
        "plan", "t", [timed_out, ok_a, ok_b],
    )
    assert report.quorum_met is True
    assert report.quorum_received == 2


def test_claude_budget_is_above_archive_median() -> None:
    assert timeout_for_vendor("claude_code") >= 720
