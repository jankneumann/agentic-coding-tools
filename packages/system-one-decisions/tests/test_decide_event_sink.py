"""Tests for decide()'s optional event_sink telemetry.

Spec: specs/system-one-decisions/spec.md
  "decide() accepts an optional event_sink, invoked once per completed call"
"""

from __future__ import annotations

import sys

import pytest
import typesafe_sdk
from system_one_decisions import decide


def _real_response() -> typesafe_sdk.SystemOneResponse:
    return typesafe_sdk.SystemOneResponse(
        model="typesafe-1",
        usage=typesafe_sdk.Usage(input_tokens=42, output_tokens=8),
        answers={
            "category": typesafe_sdk.ChoiceAnswer(
                type="choice",
                choice="billing",
                confidence=0.87,
                probabilities={"billing": 0.87, "technical": 0.1, "other": 0.03},
            ),
            "urgent": typesafe_sdk.NoulAnswer(type="noul", noul=0.92),
        },
    )


def test_event_sink_receives_one_record_on_a_completed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
    response = _real_response()

    class _SucceedingClient:
        def system_one(self, **_kwargs: object) -> typesafe_sdk.SystemOneResponse:
            return response

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", lambda: _SucceedingClient()
    )

    records: list[dict[str, object]] = []
    decide(
        {"doc": "hi"},
        {"category": "...", "urgent": "..."},
        site="test-site",
        event_sink=records.append,
    )

    assert len(records) == 1
    record = records[0]
    assert record["site"] == "test-site"
    assert isinstance(record["latency_ms"], float)
    assert record["usage_input_tokens"] == 42
    assert record["probabilities"] == {
        "category": {"billing": 0.87, "technical": 0.1, "other": 0.03},
        "urgent": {"noul": 0.92},
    }


@pytest.mark.parametrize(
    "setup",
    [
        "extra_not_installed",
        "key_absent",
        "budget_exceeded",
        "network_failure",
    ],
)
def test_event_sink_not_invoked_on_any_unavailability_branch(
    monkeypatch: pytest.MonkeyPatch, setup: str
) -> None:
    records: list[dict[str, object]] = []

    if setup == "extra_not_installed":
        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
        monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
        state, questions = {"doc": "hi"}, {"category": "..."}
    elif setup == "key_absent":
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        state, questions = {"doc": "hi"}, {"category": "..."}
    elif setup == "budget_exceeded":
        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
        state, questions = {"doc": "x" * 200_000}, {"category": "..."}
    else:  # network_failure
        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")

        class _FailingClient:
            def system_one(self, **_kwargs: object) -> typesafe_sdk.SystemOneResponse:
                raise typesafe_sdk.TypeSafeAPIConnectionError("connection failed")

        monkeypatch.setattr(
            "system_one_decisions._core._get_client", lambda: _FailingClient()
        )
        state, questions = {"doc": "hi"}, {"category": "..."}

    result = decide(state, questions, site="test-site", event_sink=records.append)
    assert result is None
    assert records == []


def test_omitting_event_sink_on_a_completed_call_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
    response = _real_response()

    class _SucceedingClient:
        def system_one(self, **_kwargs: object) -> typesafe_sdk.SystemOneResponse:
            return response

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", lambda: _SucceedingClient()
    )

    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site")
    assert result is response.answers
