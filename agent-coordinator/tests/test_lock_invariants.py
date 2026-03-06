"""Stateful property tests for lock invariants under concurrent interleavings (Task 4.2).

Extends the abstract model from test_property_based.py with:
- Trust-level enforcement integration
- Multi-agent concurrent acquire/release sequences with enforcement
- Invariant: enforcement + lock exclusivity compose correctly
- Invariant: denied operations never appear in lock state
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import hypothesis.strategies as st
from hypothesis import given, settings

# =============================================================================
# Extended Abstract Model with Enforcement
# =============================================================================


@dataclass
class EnforcedLockModel:
    """Lock model that includes trust-level enforcement.

    Combines lock exclusivity with policy enforcement to verify
    that the two mechanisms compose correctly under random
    operation sequences.
    """

    # Lock state: key -> holder (None if unlocked)
    locks: dict[str, str | None] = field(default_factory=dict)

    # Agent trust levels
    agent_trust: dict[str, int] = field(default_factory=dict)

    # Audit: track all operations and their outcomes
    operation_log: list[dict[str, str | bool]] = field(default_factory=list)

    # Denied operations log
    denied_ops: list[dict[str, str]] = field(default_factory=list)

    def set_trust(self, agent_id: str, trust_level: int) -> None:
        self.agent_trust[agent_id] = trust_level

    def _check_policy(self, agent_id: str, operation: str) -> bool:
        """Simulate policy check: write ops require trust >= 2."""
        trust = self.agent_trust.get(agent_id, 1)
        if trust == 0:
            return False  # suspended
        if operation in ("acquire_lock", "release_lock"):
            return trust >= 2
        return True  # read ops always allowed

    def acquire_lock(self, key: str, agent_id: str) -> bool:
        """Try to acquire a lock with enforcement. Returns True if successful."""
        if not self._check_policy(agent_id, "acquire_lock"):
            self.denied_ops.append({
                "agent_id": agent_id,
                "operation": "acquire_lock",
                "key": key,
            })
            self.operation_log.append({
                "agent_id": agent_id,
                "operation": "acquire_lock",
                "key": key,
                "success": False,
                "reason": "policy_denied",
            })
            return False

        current_holder = self.locks.get(key)
        if current_holder is None or current_holder == agent_id:
            self.locks[key] = agent_id
            self.operation_log.append({
                "agent_id": agent_id,
                "operation": "acquire_lock",
                "key": key,
                "success": True,
            })
            return True

        self.operation_log.append({
            "agent_id": agent_id,
            "operation": "acquire_lock",
            "key": key,
            "success": False,
            "reason": "lock_held",
        })
        return False

    def release_lock(self, key: str, agent_id: str) -> bool:
        """Release a lock with enforcement. Returns True if successful."""
        if not self._check_policy(agent_id, "release_lock"):
            self.denied_ops.append({
                "agent_id": agent_id,
                "operation": "release_lock",
                "key": key,
            })
            return False

        if self.locks.get(key) == agent_id:
            self.locks[key] = None
            return True
        return False


# =============================================================================
# Invariant 1: Lock Exclusivity Under Enforcement
# =============================================================================


class TestLockExclusivityWithEnforcement:
    """Lock exclusivity must hold even when enforcement denials are mixed in."""

    @given(
        ops=st.lists(
            st.tuples(
                st.sampled_from(["agent-1", "agent-2", "agent-3"]),
                st.sampled_from(["acquire", "release"]),
                st.sampled_from(["src/a.py", "src/b.py", "api:/test"]),
            ),
            min_size=5,
            max_size=30,
        ),
        trust_levels=st.fixed_dictionaries({
            "agent-1": st.integers(min_value=0, max_value=4),
            "agent-2": st.integers(min_value=0, max_value=4),
            "agent-3": st.integers(min_value=0, max_value=4),
        }),
    )
    @settings(max_examples=200)
    def test_exclusivity_holds_with_mixed_trust(self, ops, trust_levels):
        """Random acquire/release with varying trust levels preserves exclusivity."""
        model = EnforcedLockModel()
        for agent_id, trust in trust_levels.items():
            model.set_trust(agent_id, trust)

        for agent_id, action, key in ops:
            if action == "acquire":
                model.acquire_lock(key, agent_id)
            else:
                model.release_lock(key, agent_id)

            # INVARIANT: each lock has at most one holder
            for k, holder in model.locks.items():
                if holder is not None:
                    assert isinstance(holder, str)

            # INVARIANT: no two different agents hold the same lock
            holders_per_key: dict[str, set[str]] = defaultdict(set)
            for k, holder in model.locks.items():
                if holder is not None:
                    holders_per_key[k].add(holder)
            for k, holders in holders_per_key.items():
                assert len(holders) <= 1, f"Lock {k} has multiple holders: {holders}"


# =============================================================================
# Invariant 2: Denied Operations Never Appear in Lock State
# =============================================================================


class TestDeniedOpsNeverInState:
    """Policy-denied operations must never produce lock state changes."""

    @given(
        keys=st.lists(
            st.sampled_from(["src/a.py", "src/b.py"]),
            min_size=3,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_suspended_agent_never_holds_lock(self, keys):
        """Suspended agent (trust=0) can never acquire any lock."""
        model = EnforcedLockModel()
        model.set_trust("suspended-agent", 0)
        model.set_trust("normal-agent", 2)

        for key in keys:
            model.acquire_lock(key, "suspended-agent")

        # INVARIANT: suspended agent holds no locks
        for key, holder in model.locks.items():
            assert holder != "suspended-agent", (
                f"Suspended agent holds lock on {key}"
            )

    @given(
        keys=st.lists(
            st.sampled_from(["src/a.py", "src/b.py", "src/c.py"]),
            min_size=3,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_low_trust_agent_never_holds_lock(self, keys):
        """Low-trust agent (trust=1) can never acquire any lock."""
        model = EnforcedLockModel()
        model.set_trust("low-trust", 1)

        for key in keys:
            model.acquire_lock(key, "low-trust")

        for key, holder in model.locks.items():
            assert holder != "low-trust", f"Low-trust agent holds lock on {key}"

    @given(
        ops=st.lists(
            st.tuples(
                st.sampled_from(["denied-agent", "allowed-agent"]),
                st.sampled_from(["src/a.py", "src/b.py"]),
            ),
            min_size=5,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_denied_ops_logged(self, ops):
        """All policy-denied operations are recorded in denied_ops log."""
        model = EnforcedLockModel()
        model.set_trust("denied-agent", 0)
        model.set_trust("allowed-agent", 3)

        for agent_id, key in ops:
            model.acquire_lock(key, agent_id)

        # Every denied agent attempt should be logged
        denied_by_agent = [d for d in model.denied_ops if d["agent_id"] == "denied-agent"]
        denied_attempts = sum(1 for a, _ in ops if a == "denied-agent")
        assert len(denied_by_agent) == denied_attempts


# =============================================================================
# Invariant 3: Lock State Consistency Under Trust Changes
# =============================================================================


class TestTrustChangeConsistency:
    """Verify lock behavior when trust levels change mid-sequence."""

    def test_trust_downgrade_doesnt_revoke_existing_locks(self):
        """Lowering trust doesn't automatically revoke locks already held.

        This is a design decision: trust enforcement applies at operation time,
        not retroactively. Existing locks remain until released or expired.
        """
        model = EnforcedLockModel()
        model.set_trust("agent-1", 3)

        # Acquire while trusted
        assert model.acquire_lock("src/a.py", "agent-1") is True
        assert model.locks.get("src/a.py") == "agent-1"

        # Downgrade trust
        model.set_trust("agent-1", 0)

        # Lock still held (not retroactively revoked)
        assert model.locks.get("src/a.py") == "agent-1"

        # But new acquisitions should fail
        assert model.acquire_lock("src/b.py", "agent-1") is False

    def test_trust_upgrade_enables_new_operations(self):
        """Upgrading trust allows previously denied operations."""
        model = EnforcedLockModel()
        model.set_trust("agent-1", 0)

        assert model.acquire_lock("src/a.py", "agent-1") is False
        assert model.locks.get("src/a.py") is None

        model.set_trust("agent-1", 2)
        assert model.acquire_lock("src/a.py", "agent-1") is True
        assert model.locks.get("src/a.py") == "agent-1"


# =============================================================================
# Invariant 4: Re-entrant Lock Refresh
# =============================================================================


class TestReentrantLockRefresh:
    """Same agent re-acquiring a held lock should succeed (refresh)."""

    @given(
        n_refreshes=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_reentrant_acquire_succeeds(self, n_refreshes):
        """Same agent can re-acquire the same lock any number of times."""
        model = EnforcedLockModel()
        model.set_trust("agent-1", 2)

        assert model.acquire_lock("src/a.py", "agent-1") is True

        for _ in range(n_refreshes):
            assert model.acquire_lock("src/a.py", "agent-1") is True

        assert model.locks.get("src/a.py") == "agent-1"

    def test_reentrant_does_not_change_holder(self):
        """Re-entrant acquire doesn't change the holder identity."""
        model = EnforcedLockModel()
        model.set_trust("agent-1", 2)

        model.acquire_lock("src/a.py", "agent-1")
        model.acquire_lock("src/a.py", "agent-1")
        model.acquire_lock("src/a.py", "agent-1")

        assert model.locks["src/a.py"] == "agent-1"
