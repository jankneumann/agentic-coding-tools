"""Handoff payload (de)serialization round-trip tests.

The handoff payload is a strict subset of PhaseRecord (no alternatives /
trade_offs / open_questions). Round-trip must preserve all fields the
schema captures; subset fields are passed via the from_handoff_payload
side channel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/session-log/scripts"))

from phase_record import (  # noqa: E402
    Alternative,
    Decision,
    FileRef,
    PhaseRecord,
    TradeOff,
)


class TestToHandoffPayloadShape:
    def test_payload_keys_match_handoff_service_arguments(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        payload = rec.to_handoff_payload()
        # Keys match HandoffService.write parameters in agent-coordinator/src/handoffs.py:105
        expected_keys = {
            "agent_name",
            "session_id",
            "summary",
            "completed_work",
            "in_progress",
            "decisions",
            "next_steps",
            "relevant_files",
        }
        assert set(payload.keys()) == expected_keys

    def test_agent_name_is_agent_type(self) -> None:
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="codex", summary="s")
        assert rec.to_handoff_payload()["agent_name"] == "codex"

    def test_decisions_serialize_with_capability_and_supersedes(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[
                Decision(
                    title="T", rationale="R",
                    capability="cap", supersedes="old#D1",
                )
            ],
        )
        payload = rec.to_handoff_payload()
        assert payload["decisions"] == [
            {"title": "T", "rationale": "R", "capability": "cap", "supersedes": "old#D1"}
        ]

    def test_payload_is_json_serializable(self) -> None:
        rec = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            decisions=[Decision(title="t", rationale="r")],
            relevant_files=[FileRef(path="p", description="d")],
        )
        json.dumps(rec.to_handoff_payload())  # must not raise

    def test_empty_lists_preserved_not_omitted(self) -> None:
        """Empty lists are valid in the schema and preserve "explicitly empty"
        intent — the API distinguishes them from missing fields."""
        rec = PhaseRecord(change_id="c", phase_name="P", agent_type="x", summary="s")
        payload = rec.to_handoff_payload()
        assert payload["decisions"] == []
        assert payload["completed_work"] == []
        assert payload["relevant_files"] == []


class TestFromHandoffPayload:
    def test_minimal_payload(self) -> None:
        payload = {"agent_name": "x", "summary": "s"}
        rec = PhaseRecord.from_handoff_payload(
            payload, change_id="c", phase_name="P"
        )
        assert rec.change_id == "c"
        assert rec.phase_name == "P"
        assert rec.agent_type == "x"
        assert rec.summary == "s"
        assert rec.session_id is None
        assert rec.decisions == []

    def test_full_payload_round_trips(self) -> None:
        original = PhaseRecord(
            change_id="my-change",
            phase_name="Implementation",
            agent_type="autopilot",
            session_id="sess-1",
            summary="Did the work.",
            decisions=[
                Decision(
                    title="D1", rationale="Because.",
                    capability="skill-workflow", supersedes=None,
                ),
                Decision(title="D2", rationale="Other.", capability=None, supersedes=None),
            ],
            completed_work=["a", "b"],
            in_progress=["c"],
            next_steps=["d"],
            relevant_files=[
                FileRef(path="src/x.py", description="entrypoint"),
                FileRef(path="src/y.py"),
            ],
        )
        payload = original.to_handoff_payload()
        restored = PhaseRecord.from_handoff_payload(
            payload, change_id=original.change_id, phase_name=original.phase_name
        )
        assert restored == original

    def test_alternatives_passed_via_side_channel(self) -> None:
        """Subset fields (alternatives/trade_offs/open_questions) are not in
        the handoff payload but can be restored by passing them explicitly."""
        original = PhaseRecord(
            change_id="c", phase_name="P", agent_type="x", summary="s",
            alternatives=[Alternative(alternative="A", reason="R")],
            trade_offs=[TradeOff(accepted="X", over="Y", reason="Z")],
            open_questions=["q?"],
        )
        payload = original.to_handoff_payload()
        # Payload doesn't carry these
        assert "alternatives" not in payload
        # ...but from_handoff_payload accepts them as side-channel args
        restored = PhaseRecord.from_handoff_payload(
            payload,
            change_id="c",
            phase_name="P",
            alternatives=original.alternatives,
            trade_offs=original.trade_offs,
            open_questions=original.open_questions,
        )
        assert restored == original

    def test_payload_with_only_required_fields_loads(self) -> None:
        """Resilience: a payload missing optional fields entirely should still load."""
        payload = {"agent_name": "a", "summary": "s"}
        rec = PhaseRecord.from_handoff_payload(
            payload, change_id="c", phase_name="P"
        )
        assert rec.completed_work == []
        assert rec.relevant_files == []
        assert rec.decisions == []


class TestRoundTripPureData:
    """Round-trip a record through to_handoff_payload + from_handoff_payload
    plus the side-channel for subset fields. Spec scenario:
    `Round-trip equality through handoff payload`."""

    def test_full_round_trip(self) -> None:
        original = PhaseRecord(
            change_id="c",
            phase_name="P",
            agent_type="x",
            session_id="sess-1",
            summary="s",
            decisions=[Decision(title="t", rationale="r", capability="cap")],
            completed_work=["item"],
            in_progress=["wip"],
            next_steps=["next"],
            relevant_files=[FileRef(path="p", description="d")],
        )
        payload = original.to_handoff_payload()
        # Round-trip via JSON to catch any non-JSON-safe types
        payload_via_json = json.loads(json.dumps(payload))
        restored = PhaseRecord.from_handoff_payload(
            payload_via_json, change_id=original.change_id, phase_name=original.phase_name
        )
        assert restored == original
