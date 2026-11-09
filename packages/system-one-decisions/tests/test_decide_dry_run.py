"""Tests for decide()'s dry_run flag.

Spec: specs/system-one-decisions/spec.md
  "decide() accepts a dry_run flag that guarantees zero client construction"
"""

from __future__ import annotations

import pytest

from system_one_decisions import decide


def test_dry_run_true_returns_none_and_never_constructs_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")

    def _client_should_not_be_constructed(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("client constructed despite dry_run=True")

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", _client_should_not_be_constructed
    )

    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site", dry_run=True)
    assert result is None


def test_dry_run_true_short_circuits_before_the_key_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with no TYPESAFE_API_KEY at all, dry_run=True must not raise or
    behave any differently -- it returns before that check runs."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site", dry_run=True)
    assert result is None


def test_dry_run_false_is_indistinguishable_from_omitting_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert decide({"doc": "hi"}, {}, site="test-site", dry_run=False) is None
    assert decide({"doc": "hi"}, {}, site="test-site") is None


def test_dry_run_default_false_preserves_ri02_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed call with dry_run omitted proceeds exactly as ri-02's
    own success-path test proves -- dry_run introduces no new branch in
    the already-tested live path."""
    import typesafe_sdk

    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test-key")
    response = typesafe_sdk.SystemOneResponse(
        model="typesafe-1",
        usage=typesafe_sdk.Usage(input_tokens=1, output_tokens=1),
        answers={
            "category": typesafe_sdk.ChoiceAnswer(
                type="choice", choice="billing", confidence=0.9,
                probabilities={"billing": 0.9},
            ),
        },
    )

    class _SucceedingClient:
        def system_one(self, **_kwargs: object) -> typesafe_sdk.SystemOneResponse:
            return response

    monkeypatch.setattr(
        "system_one_decisions._core._get_client", lambda: _SucceedingClient()
    )
    result = decide({"doc": "hi"}, {"category": "..."}, site="test-site")
    assert result is response.answers
