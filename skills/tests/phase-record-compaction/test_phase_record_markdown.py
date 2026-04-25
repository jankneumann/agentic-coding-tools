"""Markdown render + parse round-trip tests.

Verifies that PhaseRecord → render_markdown → parse_markdown round-trips
losslessly, and that the inline `architectural:` and `supersedes:` spans
that feed `make decisions` are preserved exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))

from phase_record import (  # noqa: E402
    Alternative,
    Decision,
    FileRef,
    PhaseRecord,
    TradeOff,
    parse_markdown,
)


def _full_record() -> PhaseRecord:
    return PhaseRecord(
        change_id="phase-record-compaction",
        phase_name="Implementation Iteration 2",
        agent_type="autopilot",
        session_id="sess-2026-04-25-9P9o1",
        summary=(
            "Wired PhaseRecord through autopilot Layer 1 boundaries. "
            "Six handoff sites now populated."
        ),
        decisions=[
            Decision(
                title="Bump LoopState schema_version to 2",
                rationale="Adding last_handoff_id requires version increment.",
                capability="skill-workflow",
            ),
            Decision(
                title="Use append_phase_entry shim",
                rationale="Out-of-tree callers still invoke the legacy API.",
                capability="skill-workflow",
                supersedes="2026-01-15-old-handoff-design#D2",
            ),
        ],
        alternatives=[
            Alternative(alternative="Migrate snapshots eagerly", reason="lazy is simpler"),
        ],
        trade_offs=[
            TradeOff(
                accepted="Two API surfaces during transition",
                over="Single canonical API immediately",
                reason="Shim is shallow",
            ),
        ],
        open_questions=["Should shim removal be time-based?"],
        completed_work=[
            "Added LoopState.last_handoff_id field",
            "Bumped schema_version to 2",
        ],
        in_progress=["Token instrumentation wiring"],
        next_steps=["Hand off to wp-autopilot-layer-2"],
        relevant_files=[
            FileRef(
                path="skills/autopilot/scripts/autopilot.py",
                description="_maybe_handoff modified at line 712",
            ),
            FileRef(path="skills/autopilot/scripts/handoff_builder.py"),
        ],
    )


class TestRenderMarkdownStructure:
    def test_render_starts_with_phase_header(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="Plan", agent_type="x", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert md.startswith("## Phase: Plan (2026-04-25)")

    def test_agent_line_uses_NA_when_no_session(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="claude_code", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert "**Agent**: claude_code | **Session**: N/A" in md

    def test_agent_line_includes_session_id(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s", session_id="sess-1"
        )
        md = rec.render_markdown(date="2026-04-25")
        assert "**Agent**: x | **Session**: sess-1" in md

    def test_decision_with_capability_uses_inline_span(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="T", rationale="R", capability="my-cap")],
        )
        md = rec.render_markdown(date="2026-04-25")
        assert "1. **T** `architectural: my-cap` — R" in md

    def test_decision_with_supersedes_uses_inline_span(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[
                Decision(
                    title="T", rationale="R",
                    capability="cap", supersedes="2026-01-01-old#D1",
                )
            ],
        )
        md = rec.render_markdown(date="2026-04-25")
        assert "`architectural: cap`" in md
        assert "`supersedes: 2026-01-01-old#D1`" in md

    def test_summary_in_context_section(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x",
            summary="The summary goes here.",
        )
        md = rec.render_markdown(date="2026-04-25")
        assert "### Context\nThe summary goes here." in md


class TestEmptyOptionalSections:
    """Empty optional sections must be omitted from the rendered markdown.
    This is spec scenario `Empty optional sections render compactly`."""

    def test_no_empty_decisions_section(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert "### Decisions" not in md

    def test_no_empty_alternatives_section(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert "### Alternatives Considered" not in md

    def test_no_empty_relevant_files_section(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert "### Relevant Files" not in md

    def test_context_section_always_present(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        md = rec.render_markdown(date="2026-04-25")
        assert "### Context" in md


class TestRoundTrip:
    """PhaseRecord → render_markdown → parse_markdown produces equal record.

    Spec scenario: `Round-trip equality through markdown`.
    """

    def test_minimal_round_trip(self) -> None:
        original = PhaseRecord(
            change_id="my-change",
            phase_name="Plan",
            agent_type="claude_code",
            summary="A minimal phase summary.",
        )
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="my-change")
        assert parsed == original

    def test_full_round_trip(self) -> None:
        original = _full_record()
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id=original.change_id)
        assert parsed == original

    def test_capability_tag_round_trip(self) -> None:
        """Spec scenario: Capability tag survives round-trip."""
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[
                Decision(
                    title="My decision",
                    rationale="Because.",
                    capability="software-factory-tooling",
                )
            ],
        )
        md = original.render_markdown(date="2026-04-25")
        assert "`architectural: software-factory-tooling`" in md
        parsed = parse_markdown(md, change_id="c")
        assert parsed.decisions[0].capability == "software-factory-tooling"

    def test_supersedes_tag_round_trip(self) -> None:
        """Spec scenario: Supersedes tag survives round-trip."""
        ref = "2026-01-15-old-change#D2"
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[
                Decision(
                    title="Replacement",
                    rationale="Better.",
                    capability="cap",
                    supersedes=ref,
                )
            ],
        )
        md = original.render_markdown(date="2026-04-25")
        assert f"`supersedes: {ref}`" in md
        parsed = parse_markdown(md, change_id="c")
        assert parsed.decisions[0].supersedes == ref

    def test_phased_supersedes_format_round_trip(self) -> None:
        ref = "2026-01-15-old#plan/D1"
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="T", rationale="R", supersedes=ref)],
        )
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.decisions[0].supersedes == ref

    def test_round_trip_preserves_session_id(self) -> None:
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            session_id="sess-abc",
        )
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.session_id == "sess-abc"

    def test_round_trip_preserves_no_session_id_as_none(self) -> None:
        original = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.session_id is None

    def test_round_trip_preserves_file_ref_without_description(self) -> None:
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            relevant_files=[FileRef(path="src/foo.py")],
        )
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.relevant_files == [FileRef(path="src/foo.py")]

    def test_round_trip_preserves_file_ref_with_description(self) -> None:
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            relevant_files=[FileRef(path="src/foo.py", description="entrypoint")],
        )
        md = original.render_markdown(date="2026-04-25")
        parsed = parse_markdown(md, change_id="c")
        assert parsed.relevant_files == [FileRef(path="src/foo.py", description="entrypoint")]


class TestParseErrors:
    def test_missing_phase_header_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Phase header"):
            parse_markdown("just some text", change_id="c")
