"""Tests for the plan-roadmap decomposer module."""

from __future__ import annotations

import pytest
from decomposer import (
    build_dependency_dag,
    decompose,
    validate_item_sizes,
    validate_proposal,
)
from models import Effort, ItemStatus, RoadmapItem

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
WELL_FORMED_PROPOSAL = """\
# Multi-Service Platform Proposal

## Phase 1: Foundation

### Database Infrastructure Setup

This component provides the foundational database infrastructure for all services.

- Must support PostgreSQL 15+
- Should handle connection pooling
- Database migrations must be automated
- Schema validation should pass on every deploy

### Authentication Service

This feature implements user authentication and authorization.

- OAuth2 provider integration
- JWT token management
- Role-based access control must be enforced
- Session management should handle concurrent logins

## Phase 2: Core Features

### API Gateway Component

The API gateway service routes requests to backend microservices.

- Rate limiting must be configurable per endpoint
- Request validation should reject malformed payloads
- Circuit breaker pattern for downstream failures
- Health check endpoints must respond within 100ms
- Load balancing across service instances
- Request/response logging for audit

### Notification System Feature

This feature delivers notifications across multiple channels.

- Email notification delivery
- Push notification support
- Notification preferences must be user-configurable
- Delivery status tracking should be real-time

## Constraints

- All services must pass security review before deployment
- Response latency must stay under 200ms p99
- System must handle 10k concurrent users
"""

MINIMAL_PROPOSAL = """\
# Simple Feature

## Component: User Dashboard

A basic user dashboard feature.

- Display user profile
- Show recent activity
"""

NO_CAPABILITIES_PROPOSAL = """\
# Meeting Notes

We discussed the timeline for the project.
The budget is approved.
Next meeting is on Friday.
"""

EMPTY_PROPOSAL = ""

# ---------------------------------------------------------------------------
# validate_proposal tests
# ---------------------------------------------------------------------------
class TestValidateProposal:
    def test_well_formed_proposal_passes(self):
        errors = validate_proposal(WELL_FORMED_PROPOSAL)
        assert errors == []

    def test_empty_proposal_fails(self):
        errors = validate_proposal(EMPTY_PROPOSAL)
        assert len(errors) >= 1
        assert any("empty" in e.lower() for e in errors)

    def test_no_capabilities_fails(self):
        errors = validate_proposal(NO_CAPABILITIES_PROPOSAL)
        assert len(errors) >= 1
        assert any("capabilit" in e.lower() or "no actionable" in e.lower() for e in errors)

    def test_minimal_proposal_passes(self):
        errors = validate_proposal(MINIMAL_PROPOSAL)
        assert errors == []

# ---------------------------------------------------------------------------
# decompose tests
# ---------------------------------------------------------------------------
class TestDecompose:
    def test_successful_decomposition(self):
        roadmap = decompose(WELL_FORMED_PROPOSAL, "proposals/platform.md")
        assert roadmap.roadmap_id == "roadmap-platform"
        assert roadmap.source_proposal == "proposals/platform.md"
        assert len(roadmap.items) >= 2  # At least some items extracted
        assert all(it.status == ItemStatus.CANDIDATE for it in roadmap.items)
        assert all(it.acceptance_outcomes for it in roadmap.items)
        assert roadmap.created_at is not None

    def test_items_have_priorities(self):
        roadmap = decompose(WELL_FORMED_PROPOSAL, "proposals/platform.md")
        priorities = [it.priority for it in roadmap.items]
        # Priorities should be sequential starting from 1
        assert priorities == list(range(1, len(priorities) + 1))

    def test_items_have_effort_estimates(self):
        roadmap = decompose(WELL_FORMED_PROPOSAL, "proposals/platform.md")
        for item in roadmap.items:
            assert item.effort in (Effort.XS, Effort.S, Effort.M, Effort.L, Effort.XL)

    def test_rejection_no_capabilities(self):
        with pytest.raises(ValueError, match="No actionable capabilities"):
            decompose(NO_CAPABILITIES_PROPOSAL, "proposals/notes.md")

    def test_rejection_empty(self):
        with pytest.raises(ValueError, match="empty"):
            decompose(EMPTY_PROPOSAL, "proposals/empty.md")

    def test_dag_is_acyclic(self):
        roadmap = decompose(WELL_FORMED_PROPOSAL, "proposals/platform.md")
        assert not roadmap.has_cycle()

    def test_minimal_proposal_produces_item(self):
        roadmap = decompose(MINIMAL_PROPOSAL, "proposals/simple.md")
        assert len(roadmap.items) >= 1

# ---------------------------------------------------------------------------
# validate_item_sizes tests
# ---------------------------------------------------------------------------
class TestValidateItemSizes:
    def _make_item(
        self, item_id: str, effort: Effort, title: str = "Test"
    ) -> RoadmapItem:
        return RoadmapItem(
            item_id=item_id,
            title=title,
            status=ItemStatus.CANDIDATE,
            priority=1,
            effort=effort,
        )

    def test_items_within_range_unchanged(self):
        items = [
            self._make_item("ri-01", Effort.S, "Small item"),
            self._make_item("ri-02", Effort.M, "Medium item"),
            self._make_item("ri-03", Effort.L, "Large item"),
        ]
        result = validate_item_sizes(items, min_effort=Effort.S, max_effort=Effort.L)
        assert len(result) == 3
        assert [it.item_id for it in result] == ["ri-01", "ri-02", "ri-03"]

    def test_merge_undersized_items(self):
        """Two XS items should be merged into one S item."""
        items = [
            self._make_item("ri-01", Effort.XS, "Tiny feature A"),
            self._make_item("ri-02", Effort.XS, "Tiny feature B"),
        ]
        result = validate_item_sizes(items, min_effort=Effort.S, max_effort=Effort.L)
        assert len(result) == 1
        merged = result[0]
        # Merged item should have bumped effort
        assert merged.effort == Effort.S
        assert "Tiny feature A" in merged.title
        assert "Tiny feature B" in merged.title

    def test_merge_preserves_acceptance_outcomes(self):
        item_a = self._make_item("ri-01", Effort.XS, "Feature A")
        item_a.acceptance_outcomes = ["A works"]
        item_b = self._make_item("ri-02", Effort.XS, "Feature B")
        item_b.acceptance_outcomes = ["B works"]
        result = validate_item_sizes([item_a, item_b], min_effort=Effort.S, max_effort=Effort.L)
        assert len(result) == 1
        assert "A works" in result[0].acceptance_outcomes
        assert "B works" in result[0].acceptance_outcomes

    def test_split_oversized_item(self):
        """An XL item with multiple bullets should be split."""
        item = self._make_item("ri-01", Effort.XL, "Mega feature")
        item.description = (
            "- Implement user auth system\n"
            "- Build notification pipeline\n"
            "- Create analytics dashboard\n"
            "- Deploy monitoring infrastructure\n"
        )
        result = validate_item_sizes([item], min_effort=Effort.S, max_effort=Effort.L)
        assert len(result) == 2
        # Split items should have reduced effort
        assert all(it.effort == Effort.L for it in result)
        # Part 2 should depend on part 1
        assert result[1].depends_on == [result[0].item_id]

    def test_no_split_single_bullet(self):
        """XL item with only one bullet cannot be split meaningfully."""
        item = self._make_item("ri-01", Effort.XL, "Single thing")
        item.description = "- Just one big task"
        result = validate_item_sizes([item], min_effort=Effort.S, max_effort=Effort.L)
        # Cannot split — returned as-is
        assert len(result) == 1

    def test_mixed_sizes(self):
        """Mix of undersized, normal, and oversized items."""
        items = [
            self._make_item("ri-01", Effort.XS, "Tiny A"),
            self._make_item("ri-02", Effort.XS, "Tiny B"),
            self._make_item("ri-03", Effort.M, "Normal"),
        ]
        result = validate_item_sizes(items, min_effort=Effort.S, max_effort=Effort.L)
        # Two XS merged into one, plus the M — should be 2 items
        assert len(result) == 2

    def test_priorities_reassigned(self):
        items = [
            self._make_item("ri-01", Effort.S, "First"),
            self._make_item("ri-02", Effort.M, "Second"),
            self._make_item("ri-03", Effort.L, "Third"),
        ]
        result = validate_item_sizes(items)
        priorities = [it.priority for it in result]
        assert priorities == list(range(1, len(result) + 1))

# ---------------------------------------------------------------------------
# build_dependency_dag tests
# ---------------------------------------------------------------------------
class TestBuildDependencyDag:
    def _make_item(
        self,
        item_id: str,
        title: str,
        priority: int,
        description: str | None = None,
    ) -> RoadmapItem:
        return RoadmapItem(
            item_id=item_id,
            title=title,
            status=ItemStatus.CANDIDATE,
            priority=priority,
            effort=Effort.M,
            description=description,
        )

    def test_infra_items_become_dependencies(self):
        """Infrastructure items should be depended upon by feature items."""
        infra = self._make_item("ri-01", "Database Infrastructure Setup", 1)
        feature = self._make_item("ri-02", "User Dashboard Feature", 2)
        items = build_dependency_dag([infra, feature])
        assert "ri-01" in items[1].depends_on

    def test_no_self_dependency(self):
        items = [
            self._make_item("ri-01", "Infrastructure Setup", 1),
        ]
        items = build_dependency_dag(items)
        assert "ri-01" not in items[0].depends_on

    def test_preserves_existing_deps(self):
        item_a = self._make_item("ri-01", "Foundation Setup", 1)
        item_b = self._make_item("ri-02", "Feature Build", 2)
        item_b.depends_on = ["ri-01"]
        items = build_dependency_dag([item_a, item_b])
        assert "ri-01" in items[1].depends_on

    def test_no_cycles_produced(self):
        """DAG builder must never produce cycles."""
        items = [
            self._make_item("ri-01", "Service Alpha Component", 1, "Uses bravo integration"),
            self._make_item("ri-02", "Service Bravo Component", 2, "Uses alpha integration"),
            self._make_item("ri-03", "Service Charlie Component", 3, "Independent module"),
        ]
        items = build_dependency_dag(items)

        # Verify no cycles using the Roadmap.has_cycle method
        from models import Roadmap, RoadmapStatus

        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="test",
            source_proposal="test.md",
            items=items,
            status=RoadmapStatus.PLANNING,
        )
        assert not roadmap.has_cycle()

    def test_keyword_overlap_creates_dependency(self):
        """Items sharing significant unique keywords should have dependency edges."""
        infra = self._make_item(
            "ri-01",
            "Authentication Provider Setup",
            1,
            "Configure OAuth2 authentication provider with token management",
        )
        consumer = self._make_item(
            "ri-02",
            "Protected API Authentication Integration",
            2,
            "Integrate OAuth2 authentication tokens for protected endpoints",
        )
        items = build_dependency_dag([infra, consumer])
        # consumer should depend on infra due to keyword overlap
        assert "ri-01" in items[1].depends_on

    def test_empty_items(self):
        result = build_dependency_dag([])
        assert result == []

    def test_single_item(self):
        item = self._make_item("ri-01", "Solo Feature", 1)
        result = build_dependency_dag([item])
        assert len(result) == 1
        assert result[0].depends_on == []
