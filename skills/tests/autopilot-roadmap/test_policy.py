"""Tests for the vendor scheduling policy engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from models import Policy, PolicyAction
from policy import PolicyDecision, VendorLimit, evaluate_policy


class TestWaitPolicy:
    """Tests for wait_if_budget_exceeded policy."""

    def test_wait_returns_wait_action(self):
        policy = Policy(default_action=PolicyAction.WAIT)
        limit = VendorLimit(vendor="claude", reason="rate limit exceeded")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex", "gemini"],
            switch_attempts=0,
        )

        assert decision.action == "wait"
        assert decision.from_vendor == "claude"
        assert decision.to_vendor is None
        assert "rate limit" in decision.reason

    def test_wait_includes_expected_resume_time(self):
        reset_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        policy = Policy(default_action=PolicyAction.WAIT)
        limit = VendorLimit(vendor="claude", reason="budget exceeded", reset_at=reset_time)

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex"],
            switch_attempts=0,
        )

        assert decision.action == "wait"
        assert decision.expected_wait_seconds is not None
        assert decision.expected_wait_seconds > 0
        assert decision.expected_wait_seconds <= 300 + 5  # ~5 minutes with tolerance

    def test_wait_with_no_reset_time(self):
        policy = Policy(default_action=PolicyAction.WAIT)
        limit = VendorLimit(vendor="codex", reason="unknown limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["claude"],
            switch_attempts=0,
        )

        assert decision.action == "wait"
        assert decision.expected_wait_seconds is None

class TestSwitchPolicy:
    """Tests for switch_if_time_saved policy."""

    def test_switch_returns_switch_when_alternate_available(self):
        policy = Policy(default_action=PolicyAction.SWITCH)
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex", "gemini"],
            switch_attempts=0,
        )

        assert decision.action == "switch"
        assert decision.from_vendor == "claude"
        assert decision.to_vendor in ("codex", "gemini")
        assert "claude" not in [decision.to_vendor]

    def test_switch_returns_fail_closed_when_no_alternates(self):
        policy = Policy(default_action=PolicyAction.SWITCH)
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=[],
            switch_attempts=0,
        )

        assert decision.action == "fail_closed"
        assert "No alternate vendors" in decision.reason

    def test_switch_returns_fail_closed_when_only_limited_vendor(self):
        """Available vendors list contains only the limited vendor."""
        policy = Policy(default_action=PolicyAction.SWITCH)
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["claude"],
            switch_attempts=0,
        )

        assert decision.action == "fail_closed"

    def test_switch_prefers_preferred_vendor(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            preferred_vendor="gemini",
        )
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex", "gemini"],
            switch_attempts=0,
        )

        assert decision.action == "switch"
        assert decision.to_vendor == "gemini"

    def test_switch_includes_cost_delta(self):
        policy = Policy(default_action=PolicyAction.SWITCH)
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex"],
            switch_attempts=0,
        )

        assert decision.action == "switch"
        assert decision.expected_cost_delta_usd is not None

class TestCascadingFailover:
    """Tests for cascading switch limit enforcement."""

    def test_switch_exceeds_max_attempts_returns_fail_closed(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            max_switch_attempts_per_item=2,
        )
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex", "gemini"],
            switch_attempts=2,  # Already at max
        )

        assert decision.action == "fail_closed"
        assert "max switch attempts" in decision.reason.lower() or "Exceeded" in decision.reason

    def test_switch_within_max_attempts_succeeds(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            max_switch_attempts_per_item=3,
        )
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex"],
            switch_attempts=2,  # Under max of 3
        )

        assert decision.action == "switch"

    def test_wait_policy_also_respects_max_switch_attempts(self):
        """Even with wait policy, if switch_attempts >= max, fail closed."""
        policy = Policy(
            default_action=PolicyAction.WAIT,
            max_switch_attempts_per_item=1,
        )
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex"],
            switch_attempts=1,
        )

        assert decision.action == "fail_closed"

class TestCostCeiling:
    """Tests for cost ceiling enforcement on switch decisions."""

    def test_switch_under_ceiling_succeeds(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            cost_ceiling_usd=5.0,
        )
        limit = VendorLimit(vendor="claude", reason="rate limit")

        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["gemini"],  # gemini is cheaper, delta negative
            switch_attempts=0,
        )

        assert decision.action == "switch"

    def test_switch_exceeds_ceiling_returns_fail_closed(self):
        policy = Policy(
            default_action=PolicyAction.SWITCH,
            cost_ceiling_usd=0.01,  # Very tight ceiling
        )
        limit = VendorLimit(vendor="gemini", reason="rate limit")

        # Switch from gemini (0.6) to codex (0.8) = delta 0.2, exceeds 0.01
        decision = evaluate_policy(
            policy=policy,
            vendor_limit=limit,
            available_vendors=["codex"],
            switch_attempts=0,
        )

        assert decision.action == "fail_closed"
        assert "ceiling" in decision.reason.lower()
        assert decision.expected_cost_delta_usd is not None
        assert decision.expected_cost_delta_usd > policy.cost_ceiling_usd
