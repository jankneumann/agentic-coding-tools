"""Tests for ConvergenceResult.checkpoint_dir field shape and defaults.

Verifies existing converge() callers continue to construct ConvergenceResult
without modification (default checkpoint_dir=None), and that recovery-aware
callers can read the checkpoint_dir to locate persisted findings.

Spec scenarios: skill-workflow.R3.S1, skill-workflow.R3.S2.
"""

from __future__ import annotations

from pathlib import Path

from convergence_loop import ConvergenceResult  # type: ignore[import-untyped]


def test_default_checkpoint_dir_is_none() -> None:
    """An existing caller constructing ConvergenceResult without naming
    checkpoint_dir gets None — no migration burden on legacy code."""
    result = ConvergenceResult(converged=True, rounds=1)
    assert result.checkpoint_dir is None


def test_checkpoint_dir_accepts_path() -> None:
    """A recovery-aware caller can populate checkpoint_dir with a Path."""
    p = Path("/tmp/checkpoint")
    result = ConvergenceResult(converged=True, rounds=2, checkpoint_dir=p)
    assert result.checkpoint_dir == p


def test_existing_caller_pattern_with_full_kwargs() -> None:
    """The legacy construction pattern (every other field set) still works."""
    result = ConvergenceResult(
        converged=False,
        rounds=3,
        reason="max_rounds",
        consensus={"summary": {}, "consensus_findings": []},
        escalate_findings=[{"id": 1}],
        validation_errors=["test failure"],
    )
    # All legacy fields preserved
    assert result.converged is False
    assert result.rounds == 3
    assert result.reason == "max_rounds"
    assert result.consensus is not None
    assert result.escalate_findings == [{"id": 1}]
    assert result.validation_errors == ["test failure"]
    # Default for new field
    assert result.checkpoint_dir is None


def test_no_synthesis_failed_field() -> None:
    """Round 2 review caught that synthesis_failed: bool would be unreachable
    from converge() — the synthesis exception propagates without a result
    being constructed. Verify the field was NOT added to the dataclass."""
    fields = ConvergenceResult.__dataclass_fields__
    assert "synthesis_failed" not in fields
    # checkpoint_dir is the only new observability field
    assert "checkpoint_dir" in fields


def test_checkpoint_dir_field_type_annotation() -> None:
    """The annotation is Path | None (or compatible) — not a forced Path."""
    fields = ConvergenceResult.__dataclass_fields__
    cd_field = fields["checkpoint_dir"]
    # Annotation is a string or runtime type; accept either since dataclass
    # may render it textually depending on `from __future__ import annotations`.
    annotation = str(cd_field.type)
    assert "Path" in annotation
    assert "None" in annotation
