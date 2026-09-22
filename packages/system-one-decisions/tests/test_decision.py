"""Tests for the Decision dataclass.

Spec: specs/system-one-decisions/spec.md
  "Decision is a frozen dataclass with a fixed field set"
"""

from __future__ import annotations

import dataclasses

import pytest
from system_one_decisions import Decision


def test_decision_is_immutable() -> None:
    d = Decision(intent="a", p=0.9, distribution={"a": 0.9}, degraded=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.intent = "b"  # type: ignore[misc]


def test_evidence_class_defaults_to_judgment() -> None:
    d = Decision(intent="a", p=0.9, distribution={"a": 0.9}, degraded=False)
    assert d.evidence_class == "judgment"


def test_evidence_class_can_be_overridden() -> None:
    d = Decision(
        intent="a", p=0.9, distribution={"a": 0.9}, degraded=False,
        evidence_class="deterministic",
    )
    assert d.evidence_class == "deterministic"


def test_all_fields_present() -> None:
    d = Decision(intent="a", p=0.9, distribution={"a": 0.9}, degraded=True)
    assert d.intent == "a"
    assert d.p == 0.9
    assert d.distribution == {"a": 0.9}
    assert d.degraded is True
