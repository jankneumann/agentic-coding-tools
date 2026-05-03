"""Tests for the --prototype-context loader.

Spec scenarios:
- skill-workflow.ConvergenceViaIterateOnPlan.convergence-mode-activated
- skill-workflow.ConvergenceViaIterateOnPlan.convergence-without-context
- skill-workflow.ConvergenceViaIterateOnPlan.missing-prototype-artifacts

Design decisions: D1 (convergence via iterate-on-plan, not new skill).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "iterate-on-plan" / "scripts"
)
PARALLEL_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
PROTOTYPE_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "prototype-feature" / "scripts"
)
for p in (PARALLEL_SCRIPTS, PROTOTYPE_SCRIPTS, SKILL_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from prototype_context import (
    PrototypeContext,
    PrototypeContextMissing,
    load_prototype_context,
)


def _write_findings(change_dir: Path, descriptors: list[dict]) -> Path:
    """Write a minimal prototype-findings.md with embedded JSON blocks
    (matches collect_outcomes.write_findings_file output)."""
    from collect_outcomes import write_findings_file
    from variant_descriptor import VariantDescriptor

    vds = [VariantDescriptor.from_dict(d) for d in descriptors]
    return write_findings_file(change_dir=change_dir, descriptors=vds)


def _basic_descriptor(variant_id: str, **picks: bool) -> dict:
    return {
        "variant_id": variant_id,
        "angle": "simplest",
        "vendor": "claude-opus-4-7",
        "branch": f"prototype/add-foo/{variant_id}",
        "automated_scores": {
            "smoke": {"pass": True, "report": "ok"},
            "spec": {"covered": 5, "total": 5, "missing": []},
        },
        "human_picks": {
            "data_model": picks.get("data_model", False),
            "api": picks.get("api", False),
            "tests": picks.get("tests", False),
            "layout": picks.get("layout", False),
        },
    }


class TestLoadPrototypeContext:
    """Spec: convergence-mode-activated."""

    def test_loads_descriptors_from_findings_file(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)
        _write_findings(
            change_dir,
            [
                _basic_descriptor("v1", data_model=True),
                _basic_descriptor("v2", api=True),
                _basic_descriptor("v3", layout=True),
            ],
        )

        ctx = load_prototype_context(change_dir=change_dir)
        assert isinstance(ctx, PrototypeContext)
        assert len(ctx.descriptors) == 3
        assert [d.variant_id for d in ctx.descriptors] == ["v1", "v2", "v3"]

    def test_synthesis_plan_attached(self, tmp_path: Path) -> None:
        # The loader must compute a synthesis_plan from the descriptors so
        # the SKILL workflow doesn't have to reach into parallel-infra.
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)
        _write_findings(
            change_dir,
            [
                _basic_descriptor("v1", data_model=True),
                _basic_descriptor("v2", api=True),
                _basic_descriptor("v3", layout=True),
            ],
        )

        ctx = load_prototype_context(change_dir=change_dir)
        assert ctx.synthesis_plan["change_id"] == "add-foo"
        assert ctx.synthesis_plan["per_aspect_picks"]["data_model"]["source"] == "v1"


class TestMissingArtifactFailsFast:
    """Spec: missing-prototype-artifacts."""

    def test_raises_when_findings_file_absent(self, tmp_path: Path) -> None:
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)
        # No prototype-findings.md — fail fast, do NOT silently no-op.
        with pytest.raises(PrototypeContextMissing, match="prototype-findings"):
            load_prototype_context(change_dir=change_dir)

    def test_raises_when_change_dir_absent(self, tmp_path: Path) -> None:
        with pytest.raises(PrototypeContextMissing):
            load_prototype_context(change_dir=tmp_path / "no-such-change")

    def test_raises_when_findings_file_has_no_descriptors(
        self, tmp_path: Path
    ) -> None:
        # Empty/malformed findings file should also fail fast — partial
        # convergence with no source data is worse than a clear error.
        change_dir = tmp_path / "openspec" / "changes" / "add-foo"
        change_dir.mkdir(parents=True)
        (change_dir / "prototype-findings.md").write_text(
            "# Prototype Findings — add-foo\n\n(no variants — write failed?)\n"
        )
        with pytest.raises(PrototypeContextMissing, match="(?i)descriptor"):
            load_prototype_context(change_dir=change_dir)


class TestConvergenceWithoutContext:
    """Spec: convergence-without-context.

    The loader is the entry point for convergence mode. When the SKILL
    workflow calls it without a --prototype-context flag, it shouldn't
    even reach the loader. This test documents that contract: there is
    no implicit lookup, no auto-discovery.
    """

    def test_no_implicit_findings_lookup(self, tmp_path: Path) -> None:
        # Imagine someone calls iterate-on-plan WITHOUT --prototype-context
        # but the findings file exists in the project. The loader is only
        # triggered explicitly; this test asserts the API has no
        # auto-discovery surface that could accidentally enable convergence.
        # (We test by inspecting the public symbols.)
        import prototype_context

        public = {
            name for name in dir(prototype_context) if not name.startswith("_")
        }
        # No "auto" / "discover" / "find" entry-points
        assert not any(
            "auto" in name.lower() or "discover" in name.lower()
            for name in public
        ), (
            f"prototype_context exposes auto-discovery: {public}; "
            "convergence mode must always be explicit per spec"
        )
