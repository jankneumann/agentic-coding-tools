"""Tests for per-capability decision-index extraction + emitter.

Covers spec scenarios:
- skill-workflow.1: Single tagged decision in a phase entry
- skill-workflow.2: Multiple decisions in one phase targeting different capabilities
- skill-workflow.3: Untagged decision remains valid (excluded from index)
- skill-workflow.4: Tag with invalid capability is reported
- skill-workflow.5: Sanitizer preserves tagged decisions
- software-factory-tooling.1: Tagged decisions aggregated by capability
- software-factory-tooling.2: Supersession chain preserved
- software-factory-tooling.3: Untagged decisions excluded
- software-factory-tooling.4: New capability directory auto-created
- software-factory-tooling.5: Incremental regeneration on re-run (byte-identical)
- software-factory-tooling.6: Malformed tag reported in strict mode

Design decisions: D1 (inline backtick tags), D2 (per-bullet tags),
D3 (explicit supersession), D4 (emitter pass), D6 (capability files),
D7 (generated README).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

# Add explore-feature scripts dir and session-log scripts dir
_SKILLS_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR / "explore-feature" / "scripts"))
sys.path.insert(0, str(_SKILLS_DIR / "session-log" / "scripts"))

from decision_index import (  # noqa: E402
    TaggedDecision,
    emit_decision_index,
    emit_readme,
    extract_decisions,
)

# ── Fixtures ────────────────────────────────────────────────────────


def _write_session_log(dir_path: Path, content: str) -> Path:
    """Write a session-log.md in a synthesized change directory.

    Returns the session-log path.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    log = dir_path / "session-log.md"
    log.write_text(dedent(content).lstrip("\n"))
    return log


SINGLE_TAGGED_PHASE = """
# Session Log: 2026-02-06-add-worktree-isolation

---

## Phase: Plan (2026-02-06)

**Agent**: claude-opus | **Session**: session-abc

### Decisions
1. **Pin worktrees during overnight pauses** `architectural: software-factory-tooling` — prevents GC during idle

### Context
Small phase.
"""


MULTI_CAPABILITY_PHASE = """
# Session Log: 2026-03-01-add-coordinator-profiles

---

## Phase: Implementation (2026-03-01)

**Agent**: claude-opus | **Session**: session-xyz

### Decisions
1. **Use `--` separator for parallel agent branches** `architectural: software-factory-tooling` — `/` would collide with parent feature branch ref
2. **Extend Phase Entry with archetype hints** `architectural: skill-workflow` — needed for archetype routing

### Context
Two decisions across two capabilities.
"""


MIXED_TAGGED_UNTAGGED = """
# Session Log: 2026-02-22-add-bug-scrub-skill

---

## Phase: Plan (2026-02-22)

### Decisions
1. **Run hooks before collecting signals** `architectural: skill-workflow` — ensures fresh data
2. **Use pydantic for report models** — internal choice, not a cross-change pattern
3. **Cache signal output to disk** — routine engineering, not architectural
"""


MULTI_PHASE_LOG = """
# Session Log: 2026-02-06-add-worktree-isolation

---

## Phase: Plan (2026-02-06)

### Decisions
1. **Worktree at `.git-worktrees/<change-id>/`** `architectural: software-factory-tooling` — stable relative path

---

## Phase: Implementation (2026-02-08)

### Decisions
1. **Registry JSON for advisory tracking** `architectural: software-factory-tooling` — JSON is simpler than sqlite for a metadata-only file
2. **Use `--` separator for agent branches** `architectural: software-factory-tooling` — git ref storage limitation
"""


SUPERSEDES_LOG = """
# Session Log: 2026-03-25-expose-coordinator-apis

---

## Phase: Implementation (2026-03-25)

### Decisions
1. **Replace Beads with built-in tracker** `architectural: agent-coordinator` `supersedes: 2026-02-xx-add-beads-integration#D1` — built-in tracker reduces vendor surface
"""


FIRST_OCCURRENCE_LOG = """
# Session Log: 2026-04-01-demo

---

## Phase: Plan (2026-04-01)

### Decisions
1. **Double-tagged decision (pathological)** `architectural: skill-workflow` `architectural: agent-coordinator` — should only count first tag per deterministic extraction rule
"""


MALFORMED_CAPABILITY_LOG = """
# Session Log: 2026-04-15-malformed

---

## Phase: Plan (2026-04-15)

### Decisions
1. **Bad tag with underscore** `architectural: has_underscore` — underscore is not valid kebab
2. **Bad tag with uppercase** `architectural: HasUppercase` — uppercase is not valid kebab
3. **Valid tag afterward** `architectural: skill-workflow` — this one should still extract
"""


# ── Phase 1 tests — TaggedDecision extraction (tasks 1.1, 1.3) ────────


class TestExtractDecisions:
    """Extraction of TaggedDecision records from session-log markdown."""

    def test_extract_single_tagged_decision(self, tmp_path: Path) -> None:
        """skill-workflow.1: Single tagged decision → one TaggedDecision."""
        change_dir = tmp_path / "2026-02-06-add-worktree-isolation"
        log = _write_session_log(change_dir, SINGLE_TAGGED_PHASE)

        decisions = extract_decisions(log)

        assert len(decisions) == 1
        d = decisions[0]
        assert isinstance(d, TaggedDecision)
        assert d.capability == "software-factory-tooling"
        assert d.change_id == "2026-02-06-add-worktree-isolation"
        assert d.phase_name == "Plan"
        assert d.phase_date == date(2026, 2, 6)
        assert d.title == "Pin worktrees during overnight pauses"
        assert d.rationale == "prevents GC during idle"
        assert d.supersedes is None
        assert d.source_offset >= 0

    def test_extract_multiple_capabilities_in_phase(self, tmp_path: Path) -> None:
        """skill-workflow.2: Two decisions, different capabilities → both extracted."""
        change_dir = tmp_path / "2026-03-01-add-coordinator-profiles"
        log = _write_session_log(change_dir, MULTI_CAPABILITY_PHASE)

        decisions = extract_decisions(log)

        assert len(decisions) == 2
        capabilities = {d.capability for d in decisions}
        assert capabilities == {"software-factory-tooling", "skill-workflow"}
        titles = {d.title for d in decisions}
        assert titles == {
            "Use `--` separator for parallel agent branches",
            "Extend Phase Entry with archetype hints",
        }
        # Both point to the same phase
        phase_dates = {d.phase_date for d in decisions}
        assert phase_dates == {date(2026, 3, 1)}

    def test_untagged_decision_excluded(self, tmp_path: Path) -> None:
        """skill-workflow.3: Untagged decisions excluded from extraction."""
        change_dir = tmp_path / "2026-02-22-add-bug-scrub-skill"
        log = _write_session_log(change_dir, MIXED_TAGGED_UNTAGGED)

        decisions = extract_decisions(log)

        # Only the `skill-workflow` one should come through
        assert len(decisions) == 1
        assert decisions[0].capability == "skill-workflow"
        assert decisions[0].title == "Run hooks before collecting signals"

    def test_extract_from_multi_phase_session_log(self, tmp_path: Path) -> None:
        """Multiple phases → all tagged decisions extracted with correct phase metadata."""
        change_dir = tmp_path / "2026-02-06-add-worktree-isolation"
        log = _write_session_log(change_dir, MULTI_PHASE_LOG)

        decisions = extract_decisions(log)

        assert len(decisions) == 3
        plan_decisions = [d for d in decisions if d.phase_name == "Plan"]
        impl_decisions = [d for d in decisions if d.phase_name == "Implementation"]
        assert len(plan_decisions) == 1
        assert len(impl_decisions) == 2
        assert plan_decisions[0].phase_date == date(2026, 2, 6)
        assert impl_decisions[0].phase_date == date(2026, 2, 8)
        # All share the same change_id
        assert {d.change_id for d in decisions} == {"2026-02-06-add-worktree-isolation"}

    def test_first_occurrence_only_per_bullet(self, tmp_path: Path) -> None:
        """Bullet with multiple `architectural:` tags → only first is counted."""
        change_dir = tmp_path / "2026-04-01-demo"
        log = _write_session_log(change_dir, FIRST_OCCURRENCE_LOG)

        decisions = extract_decisions(log)

        assert len(decisions) == 1
        assert decisions[0].capability == "skill-workflow"  # first tag wins

    def test_extract_decision_with_supersedes_marker(self, tmp_path: Path) -> None:
        """Decision with both `architectural:` and `supersedes:` → supersedes captured."""
        change_dir = tmp_path / "2026-03-25-expose-coordinator-apis"
        log = _write_session_log(change_dir, SUPERSEDES_LOG)

        decisions = extract_decisions(log)

        assert len(decisions) == 1
        d = decisions[0]
        assert d.capability == "agent-coordinator"
        assert d.supersedes == "2026-02-xx-add-beads-integration#D1"
        assert d.title == "Replace Beads with built-in tracker"

    def test_malformed_capability_tag_skipped(self, tmp_path: Path) -> None:
        """Tag values that don't match kebab-case are skipped silently at extraction.

        Capability existence (i.e., whether `openspec/specs/<cap>/` exists) is validated
        later by the emitter — but format violations (uppercase, underscore) are caught
        by the extraction regex and result in no TaggedDecision.
        """
        change_dir = tmp_path / "2026-04-15-malformed"
        log = _write_session_log(change_dir, MALFORMED_CAPABILITY_LOG)

        decisions = extract_decisions(log)

        # Only the `skill-workflow` decision should extract; the underscore + uppercase
        # variants fail the kebab-case regex.
        assert len(decisions) == 1
        assert decisions[0].capability == "skill-workflow"

    def test_missing_session_log_returns_empty(self, tmp_path: Path) -> None:
        """Design open question #3: non-existent session-log → [] (no warning)."""
        missing = tmp_path / "nowhere" / "session-log.md"

        decisions = extract_decisions(missing)

        assert decisions == []

    def test_empty_session_log_returns_empty(self, tmp_path: Path) -> None:
        """Session-log with no Decisions section → []."""
        change_dir = tmp_path / "2026-01-01-empty"
        log = _write_session_log(change_dir, "# Session Log\n\n## Phase: Plan (2026-01-01)\n\nNothing here.\n")

        decisions = extract_decisions(log)

        assert decisions == []

    def test_decision_index_in_phase_is_bullet_position_not_tag_order(
        self, tmp_path: Path
    ) -> None:
        """Regression: `decision_index_in_phase` must be the 1-indexed bullet
        position as written in the session-log, not the match-order among
        tagged decisions. Otherwise `supersedes: <id>#D<n>` references
        written by a human reading the natural bullet numbers fail to resolve.
        """
        change_dir = tmp_path / "2026-02-06-mixed"
        log = _write_session_log(
            change_dir,
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Untagged routine choice** — internal detail, not architectural
            2. **Tagged architectural call** `architectural: software-factory-tooling` — shapes future work
            3. **Another tagged call** `architectural: skill-workflow` — different capability
            """,
        )

        decisions = extract_decisions(log)

        assert len(decisions) == 2
        tagged_sft = next(d for d in decisions if d.capability == "software-factory-tooling")
        tagged_sw = next(d for d in decisions if d.capability == "skill-workflow")
        # Must match the natural-read "2." and "3." bullet numbers, not "1, 2"
        # from the tagged-only counter.
        assert tagged_sft.decision_index_in_phase == 2
        assert tagged_sw.decision_index_in_phase == 3

    def test_source_relpath_is_captured_from_path_argument(
        self, tmp_path: Path
    ) -> None:
        """`TaggedDecision.source_relpath` carries the path passed to
        `extract_decisions`, enabling the emitter to render real back-ref links
        instead of the glob placeholder.
        """
        change_dir = tmp_path / "2026-02-06-demo"
        log = _write_session_log(change_dir, SINGLE_TAGGED_PHASE)

        decisions = extract_decisions(log)

        assert len(decisions) == 1
        assert decisions[0].source_relpath == str(log)

    def test_source_offsets_are_distinct(self, tmp_path: Path) -> None:
        """Multiple decisions in same session-log must have distinct source_offset values."""
        change_dir = tmp_path / "2026-02-06-add-worktree-isolation"
        log = _write_session_log(change_dir, MULTI_PHASE_LOG)

        decisions = extract_decisions(log)
        offsets = [d.source_offset for d in decisions]

        assert len(offsets) == len(set(offsets))
        assert all(o >= 0 for o in offsets)


# ── Phase 1 tests — Sanitizer compatibility (task 1.3) ────────────────


class TestSanitizerPreservesTags:
    """Verify `sanitize_session_log.py` leaves tagged Decisions unredacted (task 1.3)."""

    def test_sanitizer_preserves_tagged_decisions(self) -> None:
        """skill-workflow.5: Tags survive sanitization; secrets still redacted."""
        import sanitize_session_log

        content = dedent(
            """
            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** `architectural: software-factory-tooling` — prevents GC
            2. **Use `--` separator** `architectural: software-factory-tooling` — git ref storage constraint
            3. **Adopt archetype routing** `architectural: skill-workflow` — reduces routing ambiguity

            ### Context
            API key was AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE during testing.
            """
        ).lstrip("\n")

        sanitized, redactions = sanitize_session_log.sanitize(content)

        # Tagged decision strings survive verbatim
        assert "`architectural: software-factory-tooling`" in sanitized
        assert "`architectural: skill-workflow`" in sanitized
        assert "[REDACTED:" not in sanitized.split("### Context")[0]

        # But secrets in the Context section are still redacted
        assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
        assert any(r["type"] for r in redactions)

    def test_sanitizer_preserves_supersedes_marker(self) -> None:
        """Supersedes marker (second backtick span) also survives sanitization."""
        import sanitize_session_log

        content = (
            "1. **Replace Beads with built-in tracker** "
            "`architectural: agent-coordinator` "
            "`supersedes: 2026-02-xx-add-beads-integration#D1` "
            "— built-in tracker reduces vendor surface\n"
        )

        sanitized, _ = sanitize_session_log.sanitize(content)

        assert "`architectural: agent-coordinator`" in sanitized
        assert "`supersedes: 2026-02-xx-add-beads-integration#D1`" in sanitized


# ── Phase 2 tests — Per-capability emitter (tasks 2.1-2.6) ────────────


class TestEmitDecisionIndex:
    """Per-capability emitter: aggregation, supersession, untagged exclusion, idempotency."""

    @pytest.fixture
    def capabilities_root(self, tmp_path: Path) -> Path:
        """Create `openspec/specs/<cap>/spec.md` skeletons for a known capability set."""
        specs_root = tmp_path / "openspec" / "specs"
        for cap in ("skill-workflow", "software-factory-tooling", "agent-coordinator"):
            (specs_root / cap).mkdir(parents=True, exist_ok=True)
            (specs_root / cap / "spec.md").write_text(f"# {cap}\n")
        return specs_root

    def test_aggregates_by_capability_reverse_chronological(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.1: Three decisions tagged skill-workflow across
        three changes → 3 entries in skill-workflow.md, newest first."""
        decisions = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-add-worktree-isolation",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="Old decision",
                rationale="first in time",
                supersedes=None,
                source_offset=10,
            ),
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-03-01-add-coordinator-profiles",
                phase_name="Plan",
                phase_date=date(2026, 3, 1),
                title="Middle decision",
                rationale="second in time",
                supersedes=None,
                source_offset=20,
            ),
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-04-15-latest",
                phase_name="Implementation",
                phase_date=date(2026, 4, 15),
                title="Recent decision",
                rationale="newest",
                supersedes=None,
                source_offset=30,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        index_file = out / "skill-workflow.md"
        assert index_file.exists()
        content = index_file.read_text()

        # Newest-first: "Recent decision" appears before "Middle decision" before "Old"
        recent_pos = content.index("Recent decision")
        middle_pos = content.index("Middle decision")
        old_pos = content.index("Old decision")
        assert recent_pos < middle_pos < old_pos

    def test_decision_record_fields_complete(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Each emitted record contains title, rationale, change-id, phase, date, back-ref."""
        decisions = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-add-worktree-isolation",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="Pin worktrees overnight",
                rationale="prevents GC during idle",
                supersedes=None,
                source_offset=42,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        content = (out / "skill-workflow.md").read_text()

        assert "Pin worktrees overnight" in content
        assert "prevents GC during idle" in content
        assert "2026-02-06-add-worktree-isolation" in content
        assert "Plan" in content
        assert "2026-02-06" in content
        # Back-reference to session-log
        assert "session-log" in content.lower()

    def test_supersession_chain_preserved(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.2: Supersession marks earlier as superseded,
        emits bidirectional links, preserves earlier entry."""
        decisions = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-add-beads-integration",
                phase_name="Plan",
                phase_date=date(2026, 2, 10),
                title="Use Beads for issue tracking",
                rationale="external tool",
                supersedes=None,
                source_offset=100,
            ),
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-03-25-replace-beads-with-builtin-tracker",
                phase_name="Plan",
                phase_date=date(2026, 3, 25),
                title="Replace Beads with built-in tracker",
                rationale="reduces vendor surface",
                supersedes="2026-02-10-add-beads-integration#D1",
                source_offset=200,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        content = (out / "agent-coordinator.md").read_text()

        # Earlier decision is preserved (not deleted) and marked superseded
        assert "Use Beads for issue tracking" in content
        assert "superseded" in content.lower()
        # Bidirectional links
        assert "Superseded by" in content
        assert "2026-03-25-replace-beads-with-builtin-tracker" in content
        assert "Supersedes" in content
        assert "2026-02-10-add-beads-integration" in content

    def test_untagged_decisions_excluded(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.3: Emitter only writes decisions that come in
        as TaggedDecision (by construction, untagged are already filtered at extraction)."""
        # Simulate only tagged decisions making it to the emitter
        decisions = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-x",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="Only this one",
                rationale="tagged",
                supersedes=None,
                source_offset=0,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        # Only skill-workflow.md should have non-README content; other capability
        # files should not be created (they have zero tagged decisions).
        assert (out / "skill-workflow.md").exists()
        assert not (out / "software-factory-tooling.md").exists()
        assert not (out / "agent-coordinator.md").exists()

    def test_unknown_capability_warns_non_strict(
        self, tmp_path: Path, capabilities_root: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """skill-workflow.4 / software-factory-tooling.6: Unknown capability → warning;
        non-strict mode skips and continues."""
        decisions = [
            TaggedDecision(
                capability="no-such-capability",
                change_id="2026-04-01-x",
                phase_name="Plan",
                phase_date=date(2026, 4, 1),
                title="Mystery decision",
                rationale="tag without matching spec dir",
                supersedes=None,
                source_offset=0,
            ),
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-04-01-x",
                phase_name="Plan",
                phase_date=date(2026, 4, 1),
                title="Valid decision",
                rationale="capability exists",
                supersedes=None,
                source_offset=100,
            ),
        ]
        out = tmp_path / "docs" / "decisions"

        import logging
        with caplog.at_level(logging.WARNING):
            emit_decision_index(
                decisions,
                output_dir=out,
                capabilities_root=capabilities_root,
                strict=False,
            )

        # Non-strict: skips unknown, continues with valid one
        assert (out / "skill-workflow.md").exists()
        assert not (out / "no-such-capability.md").exists()
        # Warning identifies change-id and invalid capability
        assert any(
            "no-such-capability" in rec.getMessage() and "2026-04-01-x" in rec.getMessage()
            for rec in caplog.records
        )

    def test_unknown_capability_strict_raises(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.6: Strict mode exits non-zero on unknown capability."""
        decisions = [
            TaggedDecision(
                capability="no-such-capability",
                change_id="2026-04-01-x",
                phase_name="Plan",
                phase_date=date(2026, 4, 1),
                title="Mystery decision",
                rationale="tag without matching spec dir",
                supersedes=None,
                source_offset=0,
            ),
        ]
        out = tmp_path / "docs" / "decisions"

        with pytest.raises(SystemExit) as exc_info:
            emit_decision_index(
                decisions,
                output_dir=out,
                capabilities_root=capabilities_root,
                strict=True,
            )
        assert exc_info.value.code != 0

    def test_byte_identical_on_rerun(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.5: Running emitter twice produces byte-identical output."""
        decisions = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-x",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="D1",
                rationale="r1",
                supersedes=None,
                source_offset=0,
            ),
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-03-01-y",
                phase_name="Implementation",
                phase_date=date(2026, 3, 1),
                title="D2",
                rationale="r2",
                supersedes=None,
                source_offset=0,
            ),
        ]
        out = tmp_path / "docs" / "decisions"

        emit_decision_index(decisions, output_dir=out, capabilities_root=capabilities_root, strict=False)
        first = (out / "skill-workflow.md").read_bytes()
        first_readme = (out / "README.md").read_bytes() if (out / "README.md").exists() else b""

        emit_decision_index(decisions, output_dir=out, capabilities_root=capabilities_root, strict=False)
        second = (out / "skill-workflow.md").read_bytes()
        second_readme = (out / "README.md").read_bytes() if (out / "README.md").exists() else b""

        assert first == second
        assert first_readme == second_readme

    def test_new_capability_file_auto_created(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """software-factory-tooling.4: Decision tagged with capability where file doesn't
        yet exist → file is created."""
        decisions = [
            TaggedDecision(
                capability="software-factory-tooling",
                change_id="2026-04-01-x",
                phase_name="Plan",
                phase_date=date(2026, 4, 1),
                title="Brand new decision",
                rationale="capability exists but file doesn't",
                supersedes=None,
                source_offset=0,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        assert not (out / "software-factory-tooling.md").exists()

        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        assert (out / "software-factory-tooling.md").exists()

    def test_stale_capability_file_removed_on_rerun(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Regression: re-running with fewer tagged capabilities should delete
        the previously-emitted files whose capability no longer has decisions.
        Without this, removing a tag leaves an orphan `<cap>.md` that CI's
        `git diff --exit-code` cannot detect (the stale file is unchanged)
        while README regenerates to list only current caps — so README and
        capability files drift apart.
        """
        initial = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-x",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="D1",
                rationale="r",
                supersedes=None,
                source_offset=0,
            ),
            TaggedDecision(
                capability="software-factory-tooling",
                change_id="2026-02-06-x",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="D2",
                rationale="r",
                supersedes=None,
                source_offset=10,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            initial,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )
        assert (out / "skill-workflow.md").exists()
        assert (out / "software-factory-tooling.md").exists()

        # Re-emit with only skill-workflow decisions
        emit_decision_index(
            [initial[0]],
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        assert (out / "skill-workflow.md").exists()
        assert not (out / "software-factory-tooling.md").exists()
        # README still present and regenerated
        assert (out / "README.md").exists()

    def test_back_reference_uses_source_relpath(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Regression: when `source_relpath` is set, the back-reference
        rendered in the capability file should be a real navigable path, not
        a glob placeholder."""
        decisions = [
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-02-06-demo",
                phase_name="Plan",
                phase_date=date(2026, 2, 6),
                title="Demo",
                rationale="r",
                supersedes=None,
                source_offset=0,
                source_relpath="openspec/changes/archive/2026-02-06-demo/session-log.md",
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )
        content = (out / "skill-workflow.md").read_text()

        assert "openspec/changes/archive/2026-02-06-demo/session-log.md" in content
        # No glob characters anywhere in the rendered body
        assert "**/" not in content

    def test_cross_capability_supersession(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Regression: a decision in capability X may explicitly supersede an
        earlier decision in capability Y. Both files must render the correct
        bidirectional Supersedes / Superseded-by links."""
        decisions = [
            # Earlier decision tagged `agent-coordinator`
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-legacy",
                phase_name="Plan",
                phase_date=date(2026, 2, 10),
                title="Legacy coordinator decision",
                rationale="original approach",
                supersedes=None,
                source_offset=0,
                decision_index_in_phase=1,
            ),
            # Later decision tagged different capability, explicitly supersedes the earlier
            TaggedDecision(
                capability="skill-workflow",
                change_id="2026-03-01-refactor",
                phase_name="Plan",
                phase_date=date(2026, 3, 1),
                title="Cross-capability supersession",
                rationale="refines workflow pattern",
                supersedes="2026-02-10-legacy#D1",
                source_offset=100,
                decision_index_in_phase=1,
            ),
        ]
        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            decisions,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        # Both capability files exist
        ac_content = (out / "agent-coordinator.md").read_text()
        sw_content = (out / "skill-workflow.md").read_text()
        # Earlier decision marked superseded with Superseded-by link to later change
        assert "superseded" in ac_content.lower()
        assert "2026-03-01-refactor" in ac_content
        # Later decision shows the Supersedes link
        assert "Supersedes" in sw_content
        assert "2026-02-10-legacy" in sw_content

    def test_bullet_position_supersedes_resolves_with_untagged_prefix(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Regression: when the superseded target decision was bullet N in a
        phase that also had untagged decisions preceding it, a `supersedes:
        <id>#D<N>` reference must still resolve. This was broken when
        `decision_index_in_phase` counted only tagged bullets.
        """
        earlier_log = """
            # Session Log

            ## Phase: Plan (2026-02-10)

            ### Decisions
            1. **Untagged routine choice** — internal detail
            2. **Legacy architectural call** `architectural: agent-coordinator` — original approach
        """
        earlier_dir = tmp_path / "2026-02-10-legacy"
        earlier_path = _write_session_log(earlier_dir, earlier_log)
        earlier = extract_decisions(earlier_path)
        assert len(earlier) == 1
        # Critical invariant: the tagged bullet retains its natural position.
        assert earlier[0].decision_index_in_phase == 2

        # Later change explicitly supersedes #D2 — must resolve
        later = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-03-01-replace",
                phase_name="Plan",
                phase_date=date(2026, 3, 1),
                title="New approach",
                rationale="replaces the legacy path",
                supersedes="2026-02-10-legacy#D2",
                source_offset=0,
                decision_index_in_phase=1,
            )
        ]

        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            earlier + later,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )
        content = (out / "agent-coordinator.md").read_text()
        # Earlier decision rendered with Superseded-by backlink → lookup resolved
        assert "superseded" in content.lower()
        assert "2026-03-01-replace" in content

    def test_phased_supersedes_disambiguates_multi_phase_target(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Regression: when a target change has Plan D1 AND Implementation D1,
        a `supersedes: <id>#<phase-slug>/D<n>` marker must mark ONLY the named
        phase as superseded. The legacy bare `#D1` form would collide."""
        targets = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-multi-phase",
                phase_name="Plan",
                phase_date=date(2026, 2, 10),
                title="Plan-phase decision",
                rationale="early thinking",
                supersedes=None,
                source_offset=0,
                decision_index_in_phase=1,
            ),
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-multi-phase",
                phase_name="Implementation",
                phase_date=date(2026, 2, 12),
                title="Implementation-phase decision",
                rationale="final shape after coding",
                supersedes=None,
                source_offset=100,
                decision_index_in_phase=1,
            ),
        ]
        # Later change targets ONLY the Plan-phase D1 via the phased form.
        later = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-03-01-refactor",
                phase_name="Plan",
                phase_date=date(2026, 3, 1),
                title="Supersede just the plan call",
                rationale="scope change",
                supersedes="2026-02-10-multi-phase#plan/D1",
                source_offset=0,
                decision_index_in_phase=1,
            )
        ]

        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            targets + later,
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )
        content = (out / "agent-coordinator.md").read_text()

        # Count status markers — exactly one `superseded` (the Plan-phase D1)
        # and the Implementation-phase D1 must stay `active`.
        superseded_count = content.count("Status: `superseded`")
        active_count = content.count("Status: `active`")
        assert superseded_count == 1, (
            f"Expected exactly 1 superseded entry (Plan-phase D1), "
            f"got {superseded_count}. Full content:\n{content}"
        )
        assert active_count == 2, (
            f"Expected exactly 2 active entries (Implementation D1 + "
            f"later decision), got {active_count}. Full content:\n{content}"
        )

    def test_ambiguous_bare_supersedes_warns_and_skips(
        self,
        tmp_path: Path,
        capabilities_root: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Regression: a bare `#D<n>` ref targeting a change with multiple
        phases carrying that bullet index must emit a WARNING and skip the
        link rather than silently marking every matching phase as superseded.
        """
        targets = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-multi-phase",
                phase_name="Plan",
                phase_date=date(2026, 2, 10),
                title="Plan-phase decision",
                rationale="plan call",
                supersedes=None,
                source_offset=0,
                decision_index_in_phase=1,
            ),
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-02-10-multi-phase",
                phase_name="Implementation",
                phase_date=date(2026, 2, 12),
                title="Implementation-phase decision",
                rationale="impl call",
                supersedes=None,
                source_offset=100,
                decision_index_in_phase=1,
            ),
        ]
        later = [
            TaggedDecision(
                capability="agent-coordinator",
                change_id="2026-03-01-refactor",
                phase_name="Plan",
                phase_date=date(2026, 3, 1),
                title="Ambiguous supersession",
                rationale="which phase did I mean?",
                supersedes="2026-02-10-multi-phase#D1",  # bare form — ambiguous!
                source_offset=0,
                decision_index_in_phase=1,
            )
        ]

        out = tmp_path / "docs" / "decisions"
        import logging
        with caplog.at_level(logging.WARNING):
            emit_decision_index(
                targets + later,
                output_dir=out,
                capabilities_root=capabilities_root,
                strict=False,
            )

        content = (out / "agent-coordinator.md").read_text()

        # Warning names the ambiguous ref, the target change, and both phases
        warning_msgs = [r.getMessage() for r in caplog.records]
        assert any(
            "2026-02-10-multi-phase#D1" in m and "2 phases" in m
            for m in warning_msgs
        ), f"Expected ambiguity warning; got {warning_msgs!r}"

        # Neither Plan nor Implementation D1 is marked superseded
        assert content.count("Status: `superseded`") == 0

    def test_bare_supersedes_still_works_when_target_has_single_phase(
        self, tmp_path: Path, capabilities_root: Path
    ) -> None:
        """Backward-compat: legacy bare `#D<n>` remains valid when the target
        change has exactly one phase carrying that bullet index. No warning."""
        target = TaggedDecision(
            capability="agent-coordinator",
            change_id="2026-02-10-single-phase",
            phase_name="Plan",
            phase_date=date(2026, 2, 10),
            title="Only-phase decision",
            rationale="nothing to disambiguate",
            supersedes=None,
            source_offset=0,
            decision_index_in_phase=1,
        )
        later = TaggedDecision(
            capability="agent-coordinator",
            change_id="2026-03-01-refactor",
            phase_name="Plan",
            phase_date=date(2026, 3, 1),
            title="Clean supersession",
            rationale="unambiguous",
            supersedes="2026-02-10-single-phase#D1",
            source_offset=0,
            decision_index_in_phase=1,
        )

        out = tmp_path / "docs" / "decisions"
        emit_decision_index(
            [target, later],
            output_dir=out,
            capabilities_root=capabilities_root,
            strict=False,
        )

        content = (out / "agent-coordinator.md").read_text()
        assert content.count("Status: `superseded`") == 1


class TestEmitReadme:
    """Generated README covers purpose, generation, tagging conventions."""

    def test_generated_readme_listing_capabilities(self, tmp_path: Path) -> None:
        """README is generated (not hand-maintained) and lists active capabilities."""
        out = tmp_path / "docs" / "decisions"
        out.mkdir(parents=True)
        capabilities = ["skill-workflow", "software-factory-tooling", "agent-coordinator"]

        emit_readme(out, capabilities)

        readme = (out / "README.md").read_text()
        for cap in capabilities:
            assert cap in readme
        # Explains what "architectural" means for tagging
        assert "architectural" in readme.lower()
        # Explains generation
        assert "generated" in readme.lower() or "make decisions" in readme.lower()


# ── Phase 3 E2E — archive walk -> per-capability files (task 3.5) ────


class TestEndToEndArchiveWalk:
    """End-to-end: synthesized multi-change archive -> emitted capability files.

    Covers the integration between:
    - archive walk in `archive_index.emit_decisions_from_archive`
    - extract_decisions() per session-log
    - emit_decision_index() + emit_readme() for markdown output
    """

    def test_walks_archive_emits_capability_files_with_readme(
        self, tmp_path: Path
    ) -> None:
        """task 3.5: multi-change archive -> one file per tagged capability,
        reverse-chronologically ordered, with README listing all capabilities."""
        # Import archive_index here to avoid circular import at module load
        sys.path.insert(
            0, str(Path(__file__).parent.parent / "scripts")
        )
        from archive_index import emit_decisions_from_archive  # noqa: E402

        archive = tmp_path / "openspec" / "changes"
        specs = tmp_path / "openspec" / "specs"

        for cap in (
            "skill-workflow",
            "software-factory-tooling",
            "agent-coordinator",
            "configuration",
        ):
            (specs / cap).mkdir(parents=True)
            (specs / cap / "spec.md").write_text(f"# {cap}\n")

        # Synthesize 3 archived changes with tagged decisions spanning 3 capabilities
        _write_session_log(
            archive / "archive" / "2026-02-06-add-worktree-isolation",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Pin worktrees during overnight pauses** `architectural: software-factory-tooling` — prevents GC during idle
            2. **Use `--` separator for parallel agent branches** `architectural: software-factory-tooling` — git ref collision

            ## Phase: Implementation (2026-02-08)

            ### Decisions
            1. **Registry JSON** `architectural: software-factory-tooling` — simple metadata-only tracking
            """,
        )
        _write_session_log(
            archive / "archive" / "2026-03-15-coordinator-profiles",
            """
            # Session Log

            ## Phase: Plan (2026-03-15)

            ### Decisions
            1. **Profile inheritance** `architectural: configuration` — base + override pattern
            2. **Register extension as MCP server** `architectural: agent-coordinator` — unifies access
            """,
        )
        _write_session_log(
            archive / "archive" / "2026-04-01-add-decision-tagging",
            """
            # Session Log

            ## Phase: Plan (2026-04-01)

            ### Decisions
            1. **Inline backtick tag on decisions** `architectural: skill-workflow` — sanitizer-compatible
            """,
        )

        output = tmp_path / "docs" / "decisions"
        count = emit_decisions_from_archive(
            archive_root=archive,
            output_dir=output,
            capabilities_root=specs,
            strict=False,
        )

        assert count == 6
        # One file per capability with tagged decisions
        assert (output / "software-factory-tooling.md").exists()
        assert (output / "configuration.md").exists()
        assert (output / "agent-coordinator.md").exists()
        assert (output / "skill-workflow.md").exists()
        assert (output / "README.md").exists()

        # Reverse-chronological: within software-factory-tooling, the 2026-02-08
        # decision appears BEFORE the two 2026-02-06 ones.
        sft_content = (output / "software-factory-tooling.md").read_text()
        feb_08_pos = sft_content.index("2026-02-08")
        feb_06_pos = sft_content.index("2026-02-06")
        assert feb_08_pos < feb_06_pos

        # README lists every generated capability
        readme = (output / "README.md").read_text()
        for cap in (
            "skill-workflow",
            "software-factory-tooling",
            "agent-coordinator",
            "configuration",
        ):
            assert cap in readme

    def test_strict_mode_fails_on_unknown_capability(
        self, tmp_path: Path
    ) -> None:
        """Strict mode (CI) rejects any tag pointing at an unknown capability."""
        sys.path.insert(
            0, str(Path(__file__).parent.parent / "scripts")
        )
        from archive_index import emit_decisions_from_archive  # noqa: E402

        archive = tmp_path / "openspec" / "changes"
        specs = tmp_path / "openspec" / "specs"
        (specs / "known-capability").mkdir(parents=True)
        (specs / "known-capability" / "spec.md").write_text("# known\n")

        _write_session_log(
            archive / "archive" / "2026-02-06-demo",
            """
            # Session Log

            ## Phase: Plan (2026-02-06)

            ### Decisions
            1. **Bad tag** `architectural: unknown-capability` — oops
            """,
        )

        with pytest.raises(SystemExit):
            emit_decisions_from_archive(
                archive_root=archive,
                output_dir=tmp_path / "docs" / "decisions",
                capabilities_root=specs,
                strict=True,
            )
