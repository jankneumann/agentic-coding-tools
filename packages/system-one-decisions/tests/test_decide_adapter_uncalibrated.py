"""Behavioural tests of decide()'s wiring against a real LLM-backed adapter.

Spec: specs/system-one-decisions/spec.md
  "Adapter-backed behavioural tests are double-gated and named uncalibrated"

Skipped unless BOTH `ANTHROPIC_API_KEY` and `SYSTEM_ONE_ADAPTER_TESTS=1` are
set (design D3) -- a key merely being present in the environment is not
enough to start spending money on a normally-skipped suite. Every test
function here has "uncalibrated" in its name: `SystemOneAdapterClient`'s
probabilities are an LLM's self-report, never `ri-01`'s calibrated-judgment
contract, and a passing test must never be mistaken for one.
"""

from __future__ import annotations

import os

import pytest

from system_one_decisions import decide

_ADAPTER_ENV_PRESENT = bool(
    os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("SYSTEM_ONE_ADAPTER_TESTS") == "1"
)

pytestmark = pytest.mark.skipif(
    not _ADAPTER_ENV_PRESENT,
    reason="requires ANTHROPIC_API_KEY and SYSTEM_ONE_ADAPTER_TESTS=1 (double opt-in, design D3)",
)


def test_decide_wiring_against_the_uncalibrated_anthropic_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import system_one_adapter

    adapter_client = system_one_adapter.SystemOneAdapterClient(
        structured_outputs=True,
        llm_answer_mode="probabilities",
        provider="anthropic",
    )
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-used-by-the-adapter-but-required-by-decide")
    monkeypatch.setattr(
        "system_one_decisions._core._get_client", lambda: adapter_client
    )

    result = decide(
        {"ticket": "I was charged twice, please refund the duplicate."},
        {
            "category": system_one_adapter.Choice(
                instructions="What is this support ticket about?",
                criteria={"billing": None, "technical": None, "other": None},
            ),
        },
        site="test-adapter-behavioural",
    )

    assert result is not None
    assert "category" in result
    assert result["category"].choice in {"billing", "technical", "other"}
