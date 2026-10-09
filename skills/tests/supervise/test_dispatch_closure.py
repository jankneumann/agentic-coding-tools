"""Dispatch result closure (dispatch-contract SV "Dispatch Result Closure", D3).

Every ``(outcome class, parked.kind, parked.gate)`` combination the published
result schema permits has exactly one supervisor answer or resume path in
``gate_router.ANSWER_PATHS``. The permitted set is derived from the schema
itself, never from a hand-written list.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

_SKILLS = Path(__file__).resolve().parents[2]
for path in (_SKILLS, _SKILLS / "supervise" / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import gate_router  # noqa: E402
from shared import dispatch_contract  # noqa: E402

Combo = tuple[str, Optional[str], Optional[str]]


def closure_gaps(schema: dict[str, Any], answer_paths: dict[Combo, str]) -> tuple[list[Combo], list[Combo]]:
    """``(missing, forbidden)``: permitted combinations without a path, and
    paths for combinations the schema forbids."""
    permitted = dispatch_contract.permitted_result_combinations(schema)
    missing = sorted(permitted - answer_paths.keys(), key=str)
    forbidden = sorted(answer_paths.keys() - permitted, key=str)
    return missing, forbidden


def test_every_permitted_combination_has_exactly_one_path() -> None:
    schema = dispatch_contract.load_schema(dispatch_contract.RESULT_V2)
    missing, forbidden = closure_gaps(schema, gate_router.ANSWER_PATHS)
    assert missing == [], f"combinations without an answer path: {missing}"
    assert forbidden == [], f"answer paths for combinations the schema forbids: {forbidden}"


def test_the_enumeration_covers_every_outcome_class_and_parked_kind() -> None:
    combos = dispatch_contract.permitted_result_combinations(
        dispatch_contract.load_schema(dispatch_contract.RESULT_V2)
    )
    assert {c[0] for c in combos} == {"success", "failed", "vendor_limit", "parked"}
    assert {c[1] for c in combos if c[0] == "parked"} == {
        "pending_gate", "policy_pause", "permission_blocked", "capability_unavailable",
    }


def test_adding_a_kind_without_a_path_fails_naming_it() -> None:
    schema = copy.deepcopy(dispatch_contract.load_schema(dispatch_contract.RESULT_V2))
    schema["$defs"]["ParkedExampleKind"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "reason"],
        "properties": {"kind": {"const": "example_kind"}, "gate": {"enum": [None]}, "reason": {"type": "string"}},
    }
    schema["$defs"]["Parked"]["oneOf"].append({"$ref": "#/$defs/ParkedExampleKind"})

    missing, _forbidden = closure_gaps(schema, gate_router.ANSWER_PATHS)

    assert missing == [("parked", "example_kind", None)]


def test_a_path_for_a_forbidden_combination_fails() -> None:
    paths = dict(gate_router.ANSWER_PATHS)
    paths[("parked", "pending_gate", "roadmap_approval")] = "never: a child does not evaluate it"
    schema = dispatch_contract.load_schema(dispatch_contract.RESULT_V2)
    _missing, forbidden = closure_gaps(schema, paths)
    assert forbidden == [("parked", "pending_gate", "roadmap_approval")]


def test_pending_gate_with_escalate_resume_is_answerable() -> None:
    """The narrow fix merged as bdb0048 (openspec/supervise-pending-escalate-answer)."""
    assert gate_router.has_answer_path("pending_gate", "escalate_resume")
    assert gate_router._is_escalate_park({"kind": "pending_gate", "gate": "escalate_resume"})


@pytest.mark.parametrize(
    ("kind", "gate", "routable"),
    [
        ("pending_gate", "merge", True),
        ("pending_gate", "roadmap_approval", False),
        ("policy_pause", None, True),
        ("permission_blocked", None, True),
        ("permission_blocked", "merge", False),
        ("example_kind", None, False),
    ],
)
def test_the_apply_time_predicate_follows_the_table(kind: str, gate: Optional[str], routable: bool) -> None:
    assert gate_router.has_answer_path(kind, gate) is routable
