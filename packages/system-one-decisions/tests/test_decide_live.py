"""Tests for decide()'s live path: the four ordered unavailability branches.

Spec: specs/system-one-decisions/spec.md
  "decide() returns None, never raises, on any of four unavailability branches"
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
        },
    )


def test_extra_not_installed_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the ImportError branch deterministically, regardless of whether
    typesafe_sdk happens to be importable in this dev/test environment (it
    is, via the `dev` extra) -- a fallback-only consumer never has it."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site")
    assert result is None


def test_key_absent_returns_none_without_a_network_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site")
    assert result is None


def test_token_budget_exceeded_returns_none_without_a_network_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")

    def _client_should_not_be_constructed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("client constructed despite exceeding the token budget")

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", _client_should_not_be_constructed
    )
    huge_state = {"doc": "x" * 200_000}  # ~50K estimated tokens at 4 chars/token
    result = decide(huge_state, {"category": "..."}, site="test-site")
    assert result is None


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: typesafe_sdk.TypeSafeAPIConnectionError("connection failed"),
        lambda: typesafe_sdk.TypeSafeAuthenticationError(
            401, body=None, headers={}, message="bad key"
        ),
    ],
)
def test_network_or_api_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch, error_factory: object
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")

    class _FailingClient:
        def system_one(self, **_kwargs: object) -> typesafe_sdk.SystemOneResponse:
            raise error_factory()

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", lambda: _FailingClient()
    )
    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site")
    assert result is None


def test_successful_call_returns_the_real_answers_dict(
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
    assert result["category"].choice == "billing"
