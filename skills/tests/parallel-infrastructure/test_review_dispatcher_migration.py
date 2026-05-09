"""Tests for review_dispatcher.py's migration to checkpoint_findings.

Verifies the migration preserves the existing per-vendor file path layout
and manifest legacy fields while adding the superset fields needed by the
in-process converge() caller. These tests guard against regressions in
existing-consumer behavior (consensus_synthesizer.py readers, scripts that
glob the output dir, fixtures that parse legacy manifest fields).
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# review_dispatcher and checkpoint_findings live in skills/parallel-infrastructure/scripts/;
# conftest.py adds that directory to sys.path.
from review_dispatcher import (  # type: ignore[import-untyped]
    ErrorClass,
    ReviewOrchestrator,
    ReviewResult,
)
from checkpoint_findings import read_manifest, read_vendor_findings  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _vendor_finding(idx: int) -> dict[str, Any]:
    return {
        "id": idx,
        "type": "logic-error",
        "criticality": "medium",
        "description": f"Finding {idx}",
        "disposition": "fix",
    }


@pytest.fixture
def vendor_results() -> list[ReviewResult]:
    """Two successful vendors + one failed, mimicking a typical CLI dispatch."""
    return [
        ReviewResult(
            vendor="claude_code",
            success=True,
            model_used="opus",
            models_attempted=["opus"],
            elapsed_seconds=12.0,
            findings={
                "review_type": "plan",
                "target": "vendor-supplied",
                "findings": [_vendor_finding(1), _vendor_finding(2)],
            },
        ),
        ReviewResult(
            vendor="codex",
            success=True,
            model_used="gpt-5.4",
            models_attempted=["gpt-5.4"],
            elapsed_seconds=8.5,
            findings={
                "findings": [_vendor_finding(10)],
            },
        ),
        ReviewResult(
            vendor="gemini",
            success=False,
            error="429 rate_limit",
            error_class=ErrorClass.CAPACITY,
            models_attempted=["gemini-2.5-pro"],
        ),
    ]


# ---------------------------------------------------------------------------
# Manifest superset fields
# ---------------------------------------------------------------------------


def test_orchestrator_write_manifest_has_legacy_fields(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """Existing CLI callers that read legacy fields continue to work."""
    orch = ReviewOrchestrator({})
    output_path = tmp_path / "review-manifest.json"
    orch.write_manifest(vendor_results, output_path, "plan", "cli-dispatch")

    manifest = json.loads(output_path.read_text())
    # Legacy fields preserved
    assert manifest["review_type"] == "plan"
    assert manifest["target"] == "cli-dispatch"
    assert len(manifest["dispatches"]) == 3
    assert manifest["dispatches"][0]["vendor"] == "claude_code"
    assert manifest["dispatches"][0]["success"] is True
    assert manifest["dispatches"][2]["error_class"] == "capacity_exhausted"
    assert manifest["quorum_requested"] == 3
    assert manifest["quorum_received"] == 2


def test_orchestrator_write_manifest_has_superset_fields(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """New superset fields populated via the helper."""
    orch = ReviewOrchestrator({})
    output_path = tmp_path / "review-manifest.json"
    orch.write_manifest(vendor_results, output_path, "plan", "cli-dispatch")

    manifest = json.loads(output_path.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["change_id"] is None  # CLI dispatcher omits change_id
    assert "created_at" in manifest
    assert "vendors" in manifest


def test_orchestrator_write_manifest_accepts_vendors_index(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """When the orchestrator method is given a vendors index, the manifest carries it."""
    orch = ReviewOrchestrator({})
    output_path = tmp_path / "review-manifest.json"
    vendors_index = [
        {"name": "claude_code", "findings_path": "findings-claude_code-plan.json", "finding_count": 2},
        {"name": "codex", "findings_path": "findings-codex-plan.json", "finding_count": 1},
    ]
    orch.write_manifest(vendor_results, output_path, "plan", "cli-dispatch", vendors=vendors_index)
    manifest = json.loads(output_path.read_text())
    assert manifest["vendors"] == vendors_index


def test_orchestrator_write_manifest_default_vendors_is_empty(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """Backward-compat: callers that don't pass vendors get an empty index, not an error."""
    orch = ReviewOrchestrator({})
    output_path = tmp_path / "review-manifest.json"
    orch.write_manifest(vendor_results, output_path, "plan", "cli-dispatch")
    manifest = json.loads(output_path.read_text())
    assert manifest["vendors"] == []


# ---------------------------------------------------------------------------
# CLI main() — integrated write flow
# ---------------------------------------------------------------------------


def test_cli_main_writes_per_vendor_files_at_legacy_paths(
    tmp_path: Path, vendor_results: list[ReviewResult], capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI main() writes per-vendor files at the same paths existing globs depend on."""
    from review_dispatcher import main as cli_main

    # Mock dispatch to return our vendor_results without launching subprocesses.
    output_dir = tmp_path / "reviews"
    with (
        patch.object(ReviewOrchestrator, "from_coordinator", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "from_agents_yaml", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "discover_reviewers") as mock_discover,
        patch.object(ReviewOrchestrator, "dispatch_and_wait", return_value=vendor_results),
        patch("sys.argv", [
            "review_dispatcher.py",
            "--review-type", "plan",
            "--prompt", "test prompt",
            "--cwd", str(tmp_path),
            "--output-dir", str(output_dir),
        ]),
    ):
        # discover_reviewers returns a list of mock reviewers marked available
        from unittest.mock import MagicMock
        mock_reviewer = MagicMock(agent_id="claude", dispatch_tier="cli", available=True, vendor="claude_code")
        mock_discover.return_value = [mock_reviewer]
        cli_main()

    # Existing-glob caller continues to find files
    found = sorted(glob.glob(str(output_dir / "findings-*-plan.json")))
    assert len(found) == 2  # claude_code + codex; gemini failed
    paths = {Path(p).name for p in found}
    assert paths == {"findings-claude_code-plan.json", "findings-codex-plan.json"}


def test_cli_main_per_vendor_file_is_wrapper_object(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """Per-vendor file shape is {review_type, target, reviewer_vendor, findings: [...]}."""
    from review_dispatcher import main as cli_main

    output_dir = tmp_path / "reviews"
    with (
        patch.object(ReviewOrchestrator, "from_coordinator", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "from_agents_yaml", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "discover_reviewers") as mock_discover,
        patch.object(ReviewOrchestrator, "dispatch_and_wait", return_value=vendor_results),
        patch("sys.argv", [
            "review_dispatcher.py",
            "--review-type", "plan",
            "--prompt", "x",
            "--cwd", str(tmp_path),
            "--output-dir", str(output_dir),
        ]),
    ):
        from unittest.mock import MagicMock
        mock_discover.return_value = [MagicMock(agent_id="claude", dispatch_tier="cli", available=True, vendor="claude_code")]
        cli_main()

    payload = json.loads((output_dir / "findings-claude_code-plan.json").read_text())
    # Canonical wrapper fields populated by the helper
    assert payload["review_type"] == "plan"
    assert payload["target"] == "cli-dispatch"
    assert payload["reviewer_vendor"] == "claude_code"
    # Findings array passed through from vendor output
    assert len(payload["findings"]) == 2
    assert payload["findings"][0]["id"] == 1


def test_cli_main_manifest_has_vendor_index_pointing_at_files(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """Manifest's vendors[] contains exactly the vendors that produced files, with correct counts."""
    from review_dispatcher import main as cli_main

    output_dir = tmp_path / "reviews"
    with (
        patch.object(ReviewOrchestrator, "from_coordinator", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "from_agents_yaml", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "discover_reviewers") as mock_discover,
        patch.object(ReviewOrchestrator, "dispatch_and_wait", return_value=vendor_results),
        patch("sys.argv", [
            "review_dispatcher.py",
            "--review-type", "plan",
            "--prompt", "x",
            "--cwd", str(tmp_path),
            "--output-dir", str(output_dir),
        ]),
    ):
        from unittest.mock import MagicMock
        mock_discover.return_value = [MagicMock(agent_id="claude", dispatch_tier="cli", available=True, vendor="claude_code")]
        cli_main()

    manifest = read_manifest(output_dir)
    vendors = {v["name"]: v for v in manifest["vendors"]}
    assert set(vendors) == {"claude_code", "codex"}  # gemini failed
    assert vendors["claude_code"]["finding_count"] == 2
    assert vendors["codex"]["finding_count"] == 1
    assert vendors["claude_code"]["findings_path"] == "findings-claude_code-plan.json"


def test_cli_round_trip_via_helper(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """A cache written by the CLI is fully readable via read_vendor_findings."""
    from review_dispatcher import main as cli_main

    output_dir = tmp_path / "reviews"
    with (
        patch.object(ReviewOrchestrator, "from_coordinator", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "from_agents_yaml", return_value=ReviewOrchestrator({})),
        patch.object(ReviewOrchestrator, "discover_reviewers") as mock_discover,
        patch.object(ReviewOrchestrator, "dispatch_and_wait", return_value=vendor_results),
        patch("sys.argv", [
            "review_dispatcher.py",
            "--review-type", "plan",
            "--prompt", "x",
            "--cwd", str(tmp_path),
            "--output-dir", str(output_dir),
        ]),
    ):
        from unittest.mock import MagicMock
        mock_discover.return_value = [MagicMock(agent_id="claude", dispatch_tier="cli", available=True, vendor="claude_code")]
        cli_main()

    loaded = read_vendor_findings(output_dir)
    assert set(loaded) == {"claude_code", "codex"}
    assert len(loaded["claude_code"]) == 2
    assert loaded["codex"][0]["id"] == 10


# ---------------------------------------------------------------------------
# Backward-compat shim filename validation
# (IMPL_REVIEW round-1 finding C3 — codex)
# ---------------------------------------------------------------------------


def test_write_manifest_rejects_non_canonical_filename(
    tmp_path: Path, vendor_results: list[ReviewResult]
) -> None:
    """Passing a custom filename to the shim raises rather than silently
    losing it. Old behavior was to ignore output_path.name entirely."""
    import pytest

    orch = ReviewOrchestrator({})
    output_path = tmp_path / "my-custom-manifest.json"
    with pytest.raises(ValueError, match="review-manifest.json"):
        orch.write_manifest(vendor_results, output_path, "plan", "cli-dispatch")
    # And the file with the requested name is NOT created — fail-fast,
    # not write-then-mismatch.
    assert not output_path.exists()
