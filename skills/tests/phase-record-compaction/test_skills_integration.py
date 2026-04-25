"""Cross-skill integration test for PhaseRecord retrofit.

Asserts that:
1. All six phase-boundary SKILL.md files reference `PhaseRecord` and `write_both`.
2. For each documented phase name, a `PhaseRecord(...).write_both()` call
   produces matching content in `session-log.md` (via render_markdown) and
   the coordinator handoff payload (via to_handoff_payload). "Matching" means
   the same structured fields appear in both representations and that the
   markdown round-trips back to an equal PhaseRecord via parse_markdown.

Spec reference: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption —
"A skill produces matching session-log and coordinator content".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

SKILL_FILES = [
    "skills/plan-feature/SKILL.md",
    "skills/iterate-on-plan/SKILL.md",
    "skills/implement-feature/SKILL.md",
    "skills/iterate-on-implementation/SKILL.md",
    "skills/validate-feature/SKILL.md",
    "skills/cleanup-feature/SKILL.md",
]

PHASE_NAMES = [
    ("plan-feature", "Plan"),
    ("iterate-on-plan", "Plan Iteration 1"),
    ("implement-feature", "Implementation"),
    ("iterate-on-implementation", "Implementation Iteration 1"),
    ("validate-feature", "Validation"),
    ("cleanup-feature", "Cleanup"),
]


class _StubWriter:
    """Captures calls to a stand-in coordinator writer."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"handoff_id": f"h-{len(self.calls)}"}


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestSkillFilesReferenceAPI:
    """Each phase-boundary SKILL.md must reference PhaseRecord.write_both()."""

    @pytest.mark.parametrize("skill_path", SKILL_FILES)
    def test_skill_file_references_phase_record(self, skill_path: str) -> None:
        path = REPO_ROOT / skill_path
        assert path.exists(), f"SKILL.md missing: {skill_path}"
        body = path.read_text(encoding="utf-8")
        assert "PhaseRecord" in body, (
            f"{skill_path} does not reference PhaseRecord — retrofit incomplete"
        )
        assert "write_both" in body, (
            f"{skill_path} does not call write_both — retrofit incomplete"
        )

    @pytest.mark.parametrize("skill_path", SKILL_FILES)
    def test_skill_file_does_not_use_legacy_pattern(self, skill_path: str) -> None:
        """Sanity check: a retrofit must not still describe the manual
        sanitize_session_log.py shell call as the primary persistence path."""
        path = REPO_ROOT / skill_path
        body = path.read_text(encoding="utf-8")
        # Allow `sanitize_session_log.py` to be mentioned as historical context
        # or in a different role (e.g., docstring), but the active "Append
        # Session Log" section must use PhaseRecord(...).write_both().
        # We assert the new pattern appears alongside any legacy reference.
        if "sanitize_session_log.py" in body:
            assert "write_both()" in body, (
                f"{skill_path} mentions sanitize_session_log.py but does not "
                f"document write_both() — retrofit may be incomplete"
            )


class TestPerPhaseRoundTrip:
    """For each retrofitted phase, write_both produces matching markdown
    and handoff payload, and the markdown round-trips back to an equal
    PhaseRecord via parse_markdown.
    """

    @pytest.mark.parametrize("skill_id,phase_name", PHASE_NAMES)
    def test_session_log_and_handoff_match(
        self,
        skill_id: str,
        phase_name: str,
        workdir: Path,
    ) -> None:
        record = PhaseRecord(
            change_id=f"test-{skill_id}",
            phase_name=phase_name,
            agent_type="claude_code",
            summary=f"Phase entry for {skill_id} integration test.",
            decisions=[
                Decision(
                    title="Use approach A",
                    rationale="simpler than B",
                    capability="skill-workflow",
                ),
            ],
            alternatives=[
                Alternative(alternative="approach B", reason="more complex"),
            ],
            trade_offs=[
                TradeOff(accepted="X", over="Y", reason="performance"),
            ],
            open_questions=["Is Z stable?"],
            completed_work=[f"{skill_id} retrofit applied"],
            next_steps=["Proceed to next phase"],
            relevant_files=[
                FileRef(path=f"skills/{skill_id}/SKILL.md", description="retrofit target"),
            ],
        )

        stub = _StubWriter()
        result = record.write_both(coordinator_writer=stub)

        # 1. Session-log markdown produced
        assert result.markdown_path is not None
        body = result.markdown_path.read_text(encoding="utf-8")
        assert f"## Phase: {phase_name}" in body
        assert "**Agent**: claude_code" in body
        assert "`architectural: skill-workflow`" in body
        assert "Use approach A" in body
        assert f"{skill_id} retrofit applied" in body

        # 2. Coordinator received the structured payload
        assert len(stub.calls) == 1
        call = stub.calls[0]
        assert call["agent_id"] == "claude_code"
        assert call["summary"].startswith("Phase entry for ")
        payload = call["content"]
        assert payload["completed_work"] == [f"{skill_id} retrofit applied"]
        assert payload["next_steps"] == ["Proceed to next phase"]
        assert len(payload["decisions"]) == 1
        assert payload["decisions"][0]["title"] == "Use approach A"
        assert payload["decisions"][0]["capability"] == "skill-workflow"
        assert payload["relevant_files"] == [
            {"path": f"skills/{skill_id}/SKILL.md", "description": "retrofit target"},
        ]

        # 3. Session-log markdown round-trips back to an equal record
        # (modulo date/session-id, which the markdown does not store).
        parsed = parse_markdown(body, change_id=record.change_id)
        assert parsed.phase_name == record.phase_name
        assert parsed.agent_type == record.agent_type
        assert parsed.summary == record.summary
        assert parsed.decisions == record.decisions
        assert parsed.alternatives == record.alternatives
        assert parsed.trade_offs == record.trade_offs
        assert parsed.open_questions == record.open_questions
        assert parsed.completed_work == record.completed_work
        assert parsed.next_steps == record.next_steps
        assert parsed.relevant_files == record.relevant_files

        # 4. handoff_id surfaced from the stub writer
        assert result.handoff_id == "h-1"
        assert result.handoff_local_path is None
