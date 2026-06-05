"""Tests for session-log Capability Gaps section in PhaseRecord.

Validates:
- PhaseRecord round-trip (markdown -> dataclass) for CapabilityGap field
- Section appears between Trade-offs and Relevant Files in rendered markdown
- Empty capability_gaps list parses to empty list (no section rendered)
- CapabilityGap dataclass has the expected fields
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))

from phase_record import (  # noqa: E402
    FileRef,
    PhaseRecord,
    TradeOff,
    parse_markdown,
)


class TestCapabilityGapDataclass:
    """CapabilityGap dataclass must exist with the expected fields."""

    def test_capability_gap_importable(self) -> None:
        from phase_record import CapabilityGap

        gap = CapabilityGap(
            failure_type="scope_violation",
            capability_gap="missing file lock detection",
            affected_skill="implement-feature",
            severity="high",
        )
        assert gap.failure_type == "scope_violation"
        assert gap.capability_gap == "missing file lock detection"
        assert gap.affected_skill == "implement-feature"
        assert gap.severity == "high"

    def test_capability_gap_in_all_exports(self) -> None:
        from phase_record import __all__

        assert "CapabilityGap" in __all__


class TestRenderCapabilityGaps:
    """Capability Gaps section renders between Trade-offs and Relevant Files."""

    def test_section_not_rendered_when_empty(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
        )
        md = rec.render_markdown(date="2026-06-01")
        assert "### Capability Gaps Observed" not in md

    def test_section_rendered_when_populated(self) -> None:
        from phase_record import CapabilityGap

        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            capability_gaps=[
                CapabilityGap(
                    failure_type="timeout",
                    capability_gap="slow lock acquisition",
                    affected_skill="implement-feature",
                    severity="medium",
                ),
            ],
        )
        md = rec.render_markdown(date="2026-06-01")
        assert "### Capability Gaps Observed" in md
        assert "timeout" in md
        assert "slow lock acquisition" in md

    def test_section_between_trade_offs_and_relevant_files(self) -> None:
        """Section must appear after Trade-offs and before Relevant Files."""
        from phase_record import CapabilityGap

        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            trade_offs=[
                TradeOff(accepted="A", over="B", reason="C"),
            ],
            capability_gaps=[
                CapabilityGap(
                    failure_type="scope_violation",
                    capability_gap="missing detection",
                    affected_skill="plan-feature",
                    severity="low",
                ),
            ],
            relevant_files=[
                FileRef(path="src/foo.py", description="test"),
            ],
        )
        md = rec.render_markdown(date="2026-06-01")
        trade_offs_pos = md.index("### Trade-offs")
        gaps_pos = md.index("### Capability Gaps Observed")
        files_pos = md.index("### Relevant Files")
        assert trade_offs_pos < gaps_pos < files_pos

    def test_section_before_relevant_files_no_trade_offs(self) -> None:
        """When no trade-offs, gaps section still before relevant files."""
        from phase_record import CapabilityGap

        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            capability_gaps=[
                CapabilityGap(
                    failure_type="timeout",
                    capability_gap="slow",
                    affected_skill="x",
                    severity="low",
                ),
            ],
            relevant_files=[
                FileRef(path="src/foo.py"),
            ],
        )
        md = rec.render_markdown(date="2026-06-01")
        gaps_pos = md.index("### Capability Gaps Observed")
        files_pos = md.index("### Relevant Files")
        assert gaps_pos < files_pos


class TestParseCapabilityGaps:
    """parse_markdown extracts CapabilityGap entries from markdown."""

    def test_empty_section_parses_to_empty_list(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
        )
        md = rec.render_markdown(date="2026-06-01")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.capability_gaps == []

    def test_populated_section_parses_correctly(self) -> None:
        from phase_record import CapabilityGap

        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            capability_gaps=[
                CapabilityGap(
                    failure_type="scope_violation",
                    capability_gap="missing file lock",
                    affected_skill="implement-feature",
                    severity="high",
                ),
            ],
        )
        md = original.render_markdown(date="2026-06-01")
        parsed = parse_markdown(md, change_id="c")
        assert len(parsed.capability_gaps) == 1
        gap = parsed.capability_gaps[0]
        assert gap.failure_type == "scope_violation"
        assert gap.capability_gap == "missing file lock"
        assert gap.affected_skill == "implement-feature"
        assert gap.severity == "high"

    def test_multiple_gaps_round_trip(self) -> None:
        from phase_record import CapabilityGap

        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            capability_gaps=[
                CapabilityGap(
                    failure_type="timeout",
                    capability_gap="slow lock",
                    affected_skill="plan-feature",
                    severity="medium",
                ),
                CapabilityGap(
                    failure_type="context_exhaustion",
                    capability_gap="CLAUDE.md too large",
                    affected_skill="implement-feature",
                    severity="high",
                ),
            ],
        )
        md = original.render_markdown(date="2026-06-01")
        parsed = parse_markdown(md, change_id="c")
        assert len(parsed.capability_gaps) == 2
        assert parsed.capability_gaps[0].failure_type == "timeout"
        assert parsed.capability_gaps[1].failure_type == "context_exhaustion"


class TestRoundTripWithCapabilityGaps:
    """Full round-trip: PhaseRecord with capability_gaps survives render + parse."""

    def test_full_round_trip(self) -> None:
        from phase_record import CapabilityGap, Decision

        original = PhaseRecord(
            change_id="my-change",
            phase_name="Implementation",
            agent_type="claude_code",
            session_id="sess-42",
            summary="Implemented feature with gaps observed.",
            decisions=[Decision(title="Use approach A", rationale="simpler")],
            trade_offs=[TradeOff(accepted="Speed", over="Flexibility", reason="deadline")],
            capability_gaps=[
                CapabilityGap(
                    failure_type="verification_failed",
                    capability_gap="missing pytest fixture for coordinator",
                    affected_skill="validate-feature",
                    severity="medium",
                ),
            ],
            relevant_files=[FileRef(path="src/main.py", description="entrypoint")],
        )
        md = original.render_markdown(date="2026-06-01")
        parsed = parse_markdown(md, change_id="my-change")
        assert parsed == original
