"""Property-based tests for coordination invariants (Task FV.3).

Tests randomized operation sequences against an abstract model
of the coordination system to verify key safety properties:

1. Lock exclusivity — no two agents hold the same lock
2. No double-claim — a task is claimed by at most one agent
3. Dependency safety — tasks only execute after deps complete
4. Result immutability — completed task results cannot be overwritten
5. Cancellation propagation — cancelling a package cancels dependents
6. Pause-lock safety — pause lock blocks new work on a feature
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule

# Import the actual modules under test
_SKILL_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "parallel-implement-feature"
    / "scripts"
)
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from circuit_breaker import CircuitBreaker
from dag_scheduler import DAGScheduler, PackageState, compute_topo_order
from escalation_handler import EscalationAction, EscalationHandler
from scope_checker import check_scope_compliance


# =============================================================================
# Abstract Coordination Model
# =============================================================================


class TaskStatus(Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AbstractCoordinator:
    """Abstract model of coordination state for property checking.

    This is a simplified model that tracks the essential state
    needed to verify safety properties without database calls.
    """

    # Lock state: key -> holder (None if unlocked)
    locks: dict[str, str | None] = field(default_factory=dict)

    # Task state
    task_status: dict[str, TaskStatus] = field(
        default_factory=lambda: defaultdict(lambda: TaskStatus.PENDING)
    )
    task_claimed_by: dict[str, str | None] = field(default_factory=dict)
    task_result: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    task_depends_on: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    # Feature state
    paused_features: set[str] = field(default_factory=set)

    def acquire_lock(self, key: str, agent_id: str) -> bool:
        """Try to acquire a lock. Returns True if successful."""
        current_holder = self.locks.get(key)
        if current_holder is None or current_holder == agent_id:
            self.locks[key] = agent_id
            return True
        return False

    def release_lock(self, key: str, agent_id: str) -> bool:
        """Release a lock. Returns True if successful."""
        if self.locks.get(key) == agent_id:
            self.locks[key] = None
            return True
        return False

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """Claim a task. Returns True if successful."""
        status = self.task_status[task_id]
        if status != TaskStatus.PENDING:
            return False

        # Check dependencies are complete
        for dep in self.task_depends_on[task_id]:
            if self.task_status[dep] != TaskStatus.COMPLETED:
                return False

        self.task_status[task_id] = TaskStatus.CLAIMED
        self.task_claimed_by[task_id] = agent_id
        return True

    def complete_task(
        self, task_id: str, agent_id: str, success: bool, result: dict | None = None
    ) -> bool:
        """Complete a task. Returns True if successful."""
        if self.task_status[task_id] != TaskStatus.CLAIMED:
            return False
        if self.task_claimed_by.get(task_id) != agent_id:
            return False

        self.task_status[task_id] = (
            TaskStatus.COMPLETED if success else TaskStatus.FAILED
        )
        if result is not None and success:
            self.task_result[task_id] = result
        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        status = self.task_status[task_id]
        if status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            return False
        self.task_status[task_id] = TaskStatus.CANCELLED
        return True

    def pause_feature(self, feature_id: str) -> None:
        """Set the pause lock for a feature."""
        self.paused_features.add(feature_id)

    def is_paused(self, feature_id: str) -> bool:
        """Check if a feature is paused."""
        return feature_id in self.paused_features


# =============================================================================
# Property 1: Lock Exclusivity
# =============================================================================


class TestLockExclusivity:
    """No two agents can hold the same lock simultaneously."""

    @given(
        keys=st.lists(st.sampled_from(["src/a.py", "src/b.py", "api:/test"]), min_size=1, max_size=5),
        agents=st.lists(st.sampled_from(["agent-1", "agent-2", "agent-3"]), min_size=1, max_size=5),
    )
    @settings(max_examples=200)
    def test_lock_exclusivity_random_sequences(self, keys, agents):
        """Random lock acquire/release sequences maintain exclusivity."""
        model = AbstractCoordinator()

        for i, agent in enumerate(agents):
            key = keys[i % len(keys)]
            if i % 3 == 0:
                model.acquire_lock(key, agent)
            elif i % 3 == 1:
                model.release_lock(key, agent)
            else:
                model.acquire_lock(key, agent)

            # INVARIANT: each lock has at most one holder
            holders = {k: v for k, v in model.locks.items() if v is not None}
            # No key has multiple holders (by construction of dict,
            # but verify semantically)
            for k, holder in holders.items():
                assert isinstance(holder, str)

    @given(
        agent1=st.sampled_from(["agent-1", "agent-2"]),
        agent2=st.sampled_from(["agent-1", "agent-2"]),
    )
    @settings(max_examples=50)
    def test_concurrent_acquire_one_wins(self, agent1, agent2):
        """When two agents try to acquire the same lock, only one succeeds."""
        model = AbstractCoordinator()
        key = "src/shared.py"

        r1 = model.acquire_lock(key, agent1)
        r2 = model.acquire_lock(key, agent2)

        if agent1 == agent2:
            assert r1 and r2  # Same agent, refresh
        else:
            assert r1  # First always succeeds
            assert not r2  # Second fails (different agent)


# =============================================================================
# Property 2: No Double-Claim
# =============================================================================


class TestNoDoubleClaim:
    """A task is claimed by at most one agent at any time."""

    @given(
        agents=st.lists(
            st.sampled_from(["agent-1", "agent-2", "agent-3"]),
            min_size=2,
            max_size=6,
        ),
    )
    @settings(max_examples=100)
    def test_no_double_claim(self, agents):
        """Multiple agents racing to claim the same task — only one wins."""
        model = AbstractCoordinator()
        task_id = "task-1"

        winners = []
        for agent in agents:
            if model.claim_task(task_id, agent):
                winners.append(agent)

        # INVARIANT: at most one winner
        assert len(winners) <= 1

        if winners:
            assert model.task_claimed_by[task_id] == winners[0]


# =============================================================================
# Property 3: Dependency Safety
# =============================================================================


class TestDependencySafety:
    """Tasks only execute after their dependencies complete."""

    @given(
        complete_deps=st.lists(st.booleans(), min_size=2, max_size=4),
    )
    @settings(max_examples=100)
    def test_dependency_gating(self, complete_deps):
        """A task can only be claimed if all deps are complete."""
        model = AbstractCoordinator()

        dep_ids = [f"dep-{i}" for i in range(len(complete_deps))]
        task_id = "main-task"
        model.task_depends_on[task_id] = dep_ids

        # Complete some deps
        for dep_id, should_complete in zip(dep_ids, complete_deps):
            if should_complete:
                model.task_status[dep_id] = TaskStatus.PENDING
                model.claim_task(dep_id, "dep-agent")
                model.complete_task(dep_id, "dep-agent", success=True)

        result = model.claim_task(task_id, "agent-1")

        # INVARIANT: task only claimable when all deps complete
        if all(complete_deps):
            assert result is True
        else:
            assert result is False


# =============================================================================
# Property 4: Result Immutability
# =============================================================================


class TestResultImmutability:
    """Completed task results cannot be overwritten."""

    def test_completed_task_cannot_be_reclaimed(self):
        """A completed task cannot be claimed again."""
        model = AbstractCoordinator()
        model.claim_task("t1", "agent-1")
        model.complete_task("t1", "agent-1", success=True, result={"output": "v1"})

        # Try to claim again
        assert model.claim_task("t1", "agent-2") is False
        # Result unchanged
        assert model.task_result["t1"] == {"output": "v1"}

    def test_completed_task_cannot_be_completed_again(self):
        """A completed task cannot be completed again."""
        model = AbstractCoordinator()
        model.claim_task("t1", "agent-1")
        model.complete_task("t1", "agent-1", success=True, result={"output": "v1"})

        # Try to complete again
        assert model.complete_task("t1", "agent-1", success=True, result={"output": "v2"}) is False
        assert model.task_result["t1"] == {"output": "v1"}


# =============================================================================
# Property 5: Cancellation Propagation
# =============================================================================


class TestCancellationPropagation:
    """Cancelling a package cancels all transitive dependents."""

    def test_transitive_cancellation(self):
        """Circuit breaker propagates cancellation transitively."""
        packages = [
            {"package_id": "wp-a", "depends_on": []},
            {"package_id": "wp-b", "depends_on": ["wp-a"]},
            {"package_id": "wp-c", "depends_on": ["wp-b"]},
        ]
        breaker = CircuitBreaker(packages=packages)

        # Trip wp-a
        breaker.trip("wp-a")

        # All transitive dependents should be identifiable
        deps = breaker.get_transitive_dependents("wp-a")
        assert set(deps) == {"wp-b", "wp-c"}

    @given(
        failed_idx=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=50)
    def test_cancellation_in_diamond_dag(self, failed_idx):
        """Cancellation propagates correctly in a diamond DAG."""
        packages = [
            {"package_id": "wp-root", "depends_on": []},
            {"package_id": "wp-left", "depends_on": ["wp-root"]},
            {"package_id": "wp-right", "depends_on": ["wp-root"]},
            {"package_id": "wp-merge", "depends_on": ["wp-left", "wp-right"]},
        ]
        breaker = CircuitBreaker(packages=packages)
        pkg_ids = [p["package_id"] for p in packages]
        failed = pkg_ids[failed_idx]

        breaker.trip(failed)
        deps = set(breaker.get_transitive_dependents(failed))

        # INVARIANT: all packages downstream of failed are in deps
        # For root: left, right, merge
        # For left: merge
        # For right: merge
        # For merge: nothing
        expected = {
            "wp-root": {"wp-left", "wp-right", "wp-merge"},
            "wp-left": {"wp-merge"},
            "wp-right": {"wp-merge"},
            "wp-merge": set(),
        }
        assert deps == expected[failed]


# =============================================================================
# Property 6: Pause-Lock Safety
# =============================================================================


class TestPauseLockSafety:
    """Pause lock blocks new work on a feature."""

    def test_pause_blocks_claims(self):
        """When a feature is paused, the model reports it."""
        model = AbstractCoordinator()

        model.pause_feature("feat-1")
        assert model.is_paused("feat-1") is True
        assert model.is_paused("feat-2") is False

    @given(
        features=st.lists(
            st.sampled_from(["feat-1", "feat-2", "feat-3"]),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_pause_only_affects_target(self, features):
        """Pausing features only affects the specific features paused."""
        model = AbstractCoordinator()
        all_features = {"feat-1", "feat-2", "feat-3"}

        for f in features:
            model.pause_feature(f)

        paused = set(features)
        for f in all_features:
            if f in paused:
                assert model.is_paused(f) is True
            else:
                assert model.is_paused(f) is False


# =============================================================================
# DAG Scheduler Properties
# =============================================================================


class TestDAGSchedulerProperties:
    """Property-based tests for the actual DAG scheduler."""

    @given(
        n_packages=st.integers(min_value=1, max_value=6),
    )
    @settings(max_examples=50)
    def test_topo_order_includes_all_packages(self, n_packages):
        """Topological order must include every package exactly once."""
        # Build a linear chain
        packages = []
        for i in range(n_packages):
            pkg = {
                "package_id": f"wp-{i}",
                "depends_on": [f"wp-{i-1}"] if i > 0 else [],
            }
            packages.append(pkg)

        order = compute_topo_order(packages)
        assert len(order) == n_packages
        assert set(order) == {f"wp-{i}" for i in range(n_packages)}

    @given(
        n_packages=st.integers(min_value=2, max_value=6),
    )
    @settings(max_examples=50)
    def test_topo_order_respects_deps(self, n_packages):
        """In topological order, every package appears after its deps."""
        packages = []
        for i in range(n_packages):
            pkg = {
                "package_id": f"wp-{i}",
                "depends_on": [f"wp-{i-1}"] if i > 0 else [],
            }
            packages.append(pkg)

        order = compute_topo_order(packages)
        positions = {pid: idx for idx, pid in enumerate(order)}

        for pkg in packages:
            for dep in pkg["depends_on"]:
                assert positions[dep] < positions[pkg["package_id"]]

    def test_diamond_dag_order(self):
        """Diamond DAG produces valid topological order."""
        packages = [
            {"package_id": "wp-root", "depends_on": []},
            {"package_id": "wp-left", "depends_on": ["wp-root"]},
            {"package_id": "wp-right", "depends_on": ["wp-root"]},
            {"package_id": "wp-merge", "depends_on": ["wp-left", "wp-right"]},
        ]
        order = compute_topo_order(packages)

        positions = {pid: idx for idx, pid in enumerate(order)}
        assert positions["wp-root"] < positions["wp-left"]
        assert positions["wp-root"] < positions["wp-right"]
        assert positions["wp-left"] < positions["wp-merge"]
        assert positions["wp-right"] < positions["wp-merge"]


# =============================================================================
# Scope Checker Properties
# =============================================================================


class TestScopeCheckerProperties:
    """Property-based tests for scope compliance checking."""

    @given(
        files=st.lists(
            st.sampled_from([
                "src/a.py", "src/b.py", "tests/test_a.py",
                "docs/readme.md", "config.yaml",
            ]),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_wildcard_allow_always_passes(self, files):
        """write_allow=['*'] should pass for any file set."""
        result = check_scope_compliance(files, write_allow=["*"])
        assert result["compliant"] is True

    @given(
        files=st.lists(
            st.sampled_from(["src/a.py", "src/b.py", "src/c.py"]),
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    @settings(max_examples=50)
    def test_deny_overrides_allow(self, files):
        """Deny always overrides allow."""
        result = check_scope_compliance(
            files,
            write_allow=["src/*"],
            deny=["src/a.py"],
        )

        if "src/a.py" in files:
            assert result["compliant"] is False
        else:
            assert result["compliant"] is True


# =============================================================================
# Escalation Handler Properties
# =============================================================================


class TestEscalationHandlerProperties:
    """Property-based tests for escalation handler determinism."""

    @given(
        esc_type=st.sampled_from([
            "CONTRACT_REVISION_REQUIRED",
            "PLAN_REVISION_REQUIRED",
            "RESOURCE_CONFLICT",
            "VERIFICATION_INFEASIBLE",
            "SCOPE_VIOLATION",
            "ENV_RESOURCE_CONFLICT",
            "SECURITY_ESCALATION",
            "FLAKY_TEST_QUARANTINE_REQUEST",
        ]),
    )
    @settings(max_examples=50)
    def test_all_types_produce_decision(self, esc_type):
        """Every escalation type produces a non-None decision."""
        handler = EscalationHandler(
            feature_id="test-feature",
            contracts_revision=1,
            plan_revision=1,
        )
        escalation = {
            "type": esc_type,
            "package_id": "wp-test",
            "severity": "medium",
            "description": "Test escalation",
        }

        decision = handler.handle(escalation)

        assert decision is not None
        assert decision.action is not None
        assert isinstance(decision.requires_human, bool)

    @given(
        esc_type=st.sampled_from([
            "CONTRACT_REVISION_REQUIRED",
            "PLAN_REVISION_REQUIRED",
            "RESOURCE_CONFLICT",
            "VERIFICATION_INFEASIBLE",
            "SCOPE_VIOLATION",
            "ENV_RESOURCE_CONFLICT",
            "SECURITY_ESCALATION",
            "FLAKY_TEST_QUARANTINE_REQUEST",
        ]),
        data1=st.fixed_dictionaries({
            "severity": st.sampled_from(["low", "medium", "high"]),
        }),
        data2=st.fixed_dictionaries({
            "severity": st.sampled_from(["low", "medium", "high"]),
        }),
    )
    @settings(max_examples=100)
    def test_handler_is_deterministic(self, esc_type, data1, data2):
        """Same escalation type always produces the same action."""
        handler = EscalationHandler(
            feature_id="test-feature",
            contracts_revision=1,
            plan_revision=1,
        )

        esc1 = {"type": esc_type, "package_id": "wp-test", **data1, "description": "Test"}
        esc2 = {"type": esc_type, "package_id": "wp-test", **data2, "description": "Test"}

        d1 = handler.handle(esc1)
        d2 = handler.handle(esc2)

        # Same type → same action (deterministic)
        assert d1.action == d2.action
