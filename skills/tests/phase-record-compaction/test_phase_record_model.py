"""Unit tests for the PhaseRecord dataclass family.

Covers construction, defaults, equality, and asdict round-trip — the basic
shape of the data model. Markdown and handoff serialization round-trips
live in sibling test modules.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))

from phase_record import (  # noqa: E402
    Alternative,
    Decision,
    FileRef,
    PhaseRecord,
    PhaseWriteResult,
    TradeOff,
)


class TestRequiredFields:
    def test_minimal_construction(self) -> None:
        rec = PhaseRecord(
            change_id="my-change",
            phase_name="Plan",
            agent_type="claude_code",
            summary="Did the planning.",
        )
        assert rec.change_id == "my-change"
        assert rec.phase_name == "Plan"
        assert rec.agent_type == "claude_code"
        assert rec.summary == "Did the planning."

    def test_collection_fields_default_empty(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="a", summary="s"
        )
        assert rec.decisions == []
        assert rec.alternatives == []
        assert rec.trade_offs == []
        assert rec.open_questions == []
        assert rec.completed_work == []
        assert rec.in_progress == []
        assert rec.next_steps == []
        assert rec.relevant_files == []
        assert rec.session_id is None

    def test_default_lists_are_independent_per_instance(self) -> None:
        """Catches the classic mutable-default bug — different PhaseRecord
        instances must not share the same list object."""
        a = PhaseRecord(change_id="a", phase_name="P", agent_type="x", summary="s")
        b = PhaseRecord(change_id="b", phase_name="P", agent_type="x", summary="s")
        a.completed_work.append("did a thing")
        assert b.completed_work == []


class TestEquality:
    def test_equal_records_compare_equal(self) -> None:
        a = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="t", rationale="r")],
        )
        b = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="t", rationale="r")],
        )
        assert a == b

    def test_different_decisions_not_equal(self) -> None:
        a = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="t1", rationale="r")],
        )
        b = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="t2", rationale="r")],
        )
        assert a != b


class TestDecisionSubType:
    def test_decision_minimal(self) -> None:
        d = Decision(title="Title", rationale="Why")
        assert d.title == "Title"
        assert d.rationale == "Why"
        assert d.capability is None
        assert d.supersedes is None

    def test_decision_with_capability_and_supersedes(self) -> None:
        d = Decision(
            title="Pin worktrees",
            rationale="Survives GC",
            capability="software-factory-tooling",
            supersedes="2026-01-15-old#D2",
        )
        assert d.capability == "software-factory-tooling"
        assert d.supersedes == "2026-01-15-old#D2"


class TestAlternativeAndTradeOff:
    def test_alternative_construction(self) -> None:
        a = Alternative(alternative="Use X", reason="too slow")
        assert a.alternative == "Use X"
        assert a.reason == "too slow"

    def test_trade_off_construction(self) -> None:
        t = TradeOff(accepted="simplicity", over="flexibility", reason="YAGNI")
        assert t.accepted == "simplicity"
        assert t.over == "flexibility"
        assert t.reason == "YAGNI"


class TestFileRef:
    def test_file_ref_minimal(self) -> None:
        fr = FileRef(path="src/foo.py")
        assert fr.path == "src/foo.py"
        assert fr.description == ""

    def test_file_ref_with_description(self) -> None:
        fr = FileRef(path="src/foo.py", description="entrypoint")
        assert fr.description == "entrypoint"


class TestPhaseWriteResult:
    def test_default_warnings_empty_list(self) -> None:
        r = PhaseWriteResult(
            markdown_path=None, sanitized=False,
            handoff_id=None, handoff_local_path=None,
        )
        assert r.warnings == []


class TestAsdictRoundTrip:
    """asdict must produce a JSON-serializable dict that captures all fields."""

    def test_asdict_includes_all_fields(self) -> None:
        rec = PhaseRecord(
            change_id="c",
            phase_name="P",
            agent_type="a",
            summary="s",
            session_id="sess-1",
            decisions=[Decision(title="t", rationale="r", capability="cap")],
            alternatives=[Alternative(alternative="A", reason="R")],
            trade_offs=[TradeOff(accepted="X", over="Y", reason="Z")],
            open_questions=["q?"],
            completed_work=["did"],
            in_progress=["wip"],
            next_steps=["next"],
            relevant_files=[FileRef(path="p", description="d")],
        )
        d = asdict(rec)
        assert d["change_id"] == "c"
        assert d["decisions"][0]["capability"] == "cap"
        assert d["alternatives"][0]["alternative"] == "A"
        assert d["trade_offs"][0]["over"] == "Y"
        assert d["relevant_files"][0]["path"] == "p"

    def test_asdict_is_json_serializable(self) -> None:
        import json
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="a", summary="s",
            decisions=[Decision(title="t", rationale="r")],
        )
        json.dumps(asdict(rec))  # must not raise


@pytest.mark.parametrize(
    "missing_field",
    ["change_id", "phase_name", "agent_type", "summary"],
)
def test_required_fields_must_be_provided(missing_field: str) -> None:
    """Constructing a PhaseRecord without a required field must fail at TypeError."""
    kwargs = {
        "change_id": "c", "phase_name": "P", "agent_type": "a", "summary": "s",
    }
    del kwargs[missing_field]
    with pytest.raises(TypeError):
        PhaseRecord(**kwargs)  # type: ignore[arg-type]
