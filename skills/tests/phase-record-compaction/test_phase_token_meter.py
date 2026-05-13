"""Tests for phase_token_meter.measure_context — three paths.

D9 (design.md): token instrumentation has three execution paths:
1. SDK path — anthropic.messages.count_tokens (authoritative).
2. Proxy fallback — char-length / 4 estimate when SDK is unavailable.
3. Disabled path — AUTOPILOT_TOKEN_PROBE=disabled returns 0 (skip).

Spec reference: skill-workflow / Context Window Token Instrumentation —
all three scenarios.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills/autopilot/scripts"))

from phase_token_meter import measure_context  # noqa: E402


@pytest.fixture
def messages() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "Hello world"},
        {"role": "assistant", "content": "Hi there, how can I help?"},
        {"role": "user", "content": "Count tokens please."},
    ]


class TestSDKPath:
    """When the Anthropic SDK is available, use messages.count_tokens."""

    def test_sdk_call_returns_authoritative_count(
        self,
        messages: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Inject a fake SDK client whose count_tokens returns a known value.
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.input_tokens = 42
        fake_client.messages.count_tokens.return_value = fake_response

        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        result = measure_context(messages, sdk_client=fake_client)
        assert result == 42
        fake_client.messages.count_tokens.assert_called_once()

    def test_sdk_failure_falls_through_to_proxy(
        self,
        messages: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # When the SDK call raises, the meter should fall back to proxy.
        fake_client = MagicMock()
        fake_client.messages.count_tokens.side_effect = RuntimeError("network down")

        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        result = measure_context(messages, sdk_client=fake_client)
        # Proxy path: sum of content lengths / 4
        char_len = sum(len(m["content"]) for m in messages)
        assert result == char_len // 4


class TestProxyFallback:
    """When no SDK client is provided, use the char-length proxy."""

    def test_proxy_estimate_is_chars_div_four(
        self,
        messages: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        result = measure_context(messages, sdk_client=None)
        char_len = sum(len(m["content"]) for m in messages)
        assert result == char_len // 4

    def test_proxy_handles_empty_messages(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        assert measure_context([], sdk_client=None) == 0

    def test_proxy_handles_list_content(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Anthropic messages can have list-of-blocks content; the proxy must
        # not crash and should give a sensible estimate.
        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ]
        result = measure_context(msgs, sdk_client=None)
        assert result >= 0
        # We expect the proxy to extract text content somehow — at minimum
        # it should not return a negative.

    def test_proxy_handles_non_string_content(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Defensive: if content is unexpectedly non-string, the meter should
        # not raise — return 0 for that message.
        monkeypatch.delenv("AUTOPILOT_TOKEN_PROBE", raising=False)
        msgs = [{"role": "user", "content": None}]
        result = measure_context(msgs, sdk_client=None)
        assert result == 0


class TestDisabledPath:
    """When AUTOPILOT_TOKEN_PROBE=disabled, measure_context returns 0."""

    def test_env_var_disabled_returns_zero(
        self,
        messages: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTOPILOT_TOKEN_PROBE", "disabled")
        # Even with an SDK client, disabled wins.
        fake_client = MagicMock()
        result = measure_context(messages, sdk_client=fake_client)
        assert result == 0
        # SDK should NOT be called when disabled.
        fake_client.messages.count_tokens.assert_not_called()

    def test_env_var_other_values_do_not_disable(
        self,
        messages: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Only the explicit "disabled" value disables. Other values like
        # "true", "1", "off" do not disable.
        monkeypatch.setenv("AUTOPILOT_TOKEN_PROBE", "off")
        result = measure_context(messages, sdk_client=None)
        assert result > 0
