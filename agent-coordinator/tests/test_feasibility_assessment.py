"""Tests for conflict analysis and feasibility assessment (Task 7.2)."""

from __future__ import annotations

import pytest
from httpx import Response

from src.feature_registry import (
    ConflictReport,
    Feasibility,
    FeatureRegistryService,
)


def _active_feature_response(
    feature_id: str,
    resource_claims: list[str],
    merge_priority: int = 5,
) -> dict:
    """Build a mock feature_registry row."""
    return {
        "feature_id": feature_id,
        "title": f"Feature {feature_id}",
        "status": "active",
        "registered_by": "agent-1",
        "registered_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "completed_at": None,
        "resource_claims": resource_claims,
        "branch_name": f"openspec/{feature_id}",
        "merge_priority": merge_priority,
        "metadata": {},
    }


class TestFeasibilityFull:
    """Tests for FULL feasibility (no overlaps)."""

    @pytest.mark.asyncio
    async def test_no_active_features(self, mock_supabase, db_client):
        """No active features → FULL feasibility."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(return_value=Response(200, json=[]))

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "new-feature", ["src/new.py", "api:/new"]
        )

        assert report.feasibility == Feasibility.FULL
        assert report.conflicts == []
        assert report.total_conflicting_claims == 0

    @pytest.mark.asyncio
    async def test_no_overlap(self, mock_supabase, db_client):
        """Active features with disjoint claims → FULL feasibility."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response("f-existing", ["src/old.py", "api:/old"]),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "f-new", ["src/new.py", "api:/new"]
        )

        assert report.feasibility == Feasibility.FULL
        assert report.conflicts == []

    @pytest.mark.asyncio
    async def test_self_exclusion(self, mock_supabase, db_client):
        """Candidate feature should not conflict with itself."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response("f-self", ["src/main.py"]),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts("f-self", ["src/main.py"])

        assert report.feasibility == Feasibility.FULL
        assert report.conflicts == []


class TestFeasibilityPartial:
    """Tests for PARTIAL feasibility (some overlaps, below threshold)."""

    @pytest.mark.asyncio
    async def test_minor_overlap(self, mock_supabase, db_client):
        """One overlapping key out of many → PARTIAL."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing", ["src/shared.py", "api:/old"]
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 1 overlap out of 4 claims = 25% < 50% threshold
        report = await service.analyze_conflicts(
            "f-new",
            ["src/shared.py", "src/new.py", "api:/new", "db:new_table"],
        )

        assert report.feasibility == Feasibility.PARTIAL
        assert len(report.conflicts) == 1
        assert report.conflicts[0]["feature_id"] == "f-existing"
        assert report.conflicts[0]["overlapping_keys"] == ["src/shared.py"]
        assert report.total_conflicting_claims == 1
        assert report.total_candidate_claims == 4

    @pytest.mark.asyncio
    async def test_overlap_with_multiple_features(self, mock_supabase, db_client):
        """Overlaps with multiple features, still below threshold → PARTIAL."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response("f1", ["src/shared1.py"]),
                    _active_feature_response("f2", ["src/shared2.py"]),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 2 overlaps out of 5 claims = 40% < 50% threshold
        report = await service.analyze_conflicts(
            "f-new",
            [
                "src/shared1.py",
                "src/shared2.py",
                "src/new1.py",
                "src/new2.py",
                "src/new3.py",
            ],
        )

        assert report.feasibility == Feasibility.PARTIAL
        assert len(report.conflicts) == 2
        assert report.total_conflicting_claims == 2


class TestFeasibilitySequential:
    """Tests for SEQUENTIAL feasibility (too many overlaps)."""

    @pytest.mark.asyncio
    async def test_majority_overlap(self, mock_supabase, db_client):
        """More than 50% overlap → SEQUENTIAL."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing",
                        ["src/a.py", "src/b.py", "src/c.py"],
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 3 overlaps out of 4 claims = 75% > 50% threshold
        report = await service.analyze_conflicts(
            "f-new",
            ["src/a.py", "src/b.py", "src/c.py", "src/d.py"],
        )

        assert report.feasibility == Feasibility.SEQUENTIAL
        assert len(report.conflicts) == 1
        assert report.total_conflicting_claims == 3

    @pytest.mark.asyncio
    async def test_full_overlap(self, mock_supabase, db_client):
        """100% overlap → SEQUENTIAL."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing", ["src/main.py", "src/utils.py"]
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "f-new", ["src/main.py", "src/utils.py"]
        )

        assert report.feasibility == Feasibility.SEQUENTIAL
        assert report.total_conflicting_claims == 2

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, mock_supabase, db_client):
        """Exactly at 50% threshold → PARTIAL (threshold is exclusive)."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response("f-existing", ["src/a.py", "src/b.py"]),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 2 overlaps out of 4 claims = 50% = threshold (not > threshold)
        report = await service.analyze_conflicts(
            "f-new",
            ["src/a.py", "src/b.py", "src/c.py", "src/d.py"],
        )

        assert report.feasibility == Feasibility.PARTIAL

    @pytest.mark.asyncio
    async def test_just_above_threshold(self, mock_supabase, db_client):
        """Just above 50% → SEQUENTIAL."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing", ["src/a.py", "src/b.py", "src/c.py"]
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 3 overlaps out of 5 claims = 60% > 50% threshold
        report = await service.analyze_conflicts(
            "f-new",
            ["src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"],
        )

        assert report.feasibility == Feasibility.SEQUENTIAL


class TestConflictReportStructure:
    """Tests for ConflictReport data structure."""

    @pytest.mark.asyncio
    async def test_report_includes_candidate_info(self, mock_supabase, db_client):
        """Report should include candidate feature info."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(return_value=Response(200, json=[]))

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "my-feature", ["src/a.py", "api:/test"]
        )

        assert report.candidate_feature_id == "my-feature"
        assert report.candidate_claims == ["src/a.py", "api:/test"]
        assert report.total_candidate_claims == 2

    @pytest.mark.asyncio
    async def test_overlapping_keys_are_sorted(self, mock_supabase, db_client):
        """Overlapping keys in conflict entries should be sorted."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing", ["src/z.py", "src/a.py", "src/m.py"]
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "f-new",
            [
                "src/z.py",
                "src/a.py",
                "src/m.py",
                "src/new1.py",
                "src/new2.py",
                "src/new3.py",
                "src/new4.py",
            ],
        )

        assert report.conflicts[0]["overlapping_keys"] == [
            "src/a.py",
            "src/m.py",
            "src/z.py",
        ]

    @pytest.mark.asyncio
    async def test_logical_key_conflicts(self, mock_supabase, db_client):
        """Logical lock keys (api:, db:, etc.) are also detected."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[
                    _active_feature_response(
                        "f-existing",
                        ["api:/users", "db:sessions", "event:user.created"],
                    ),
                ],
            )
        )

        service = FeatureRegistryService(db_client)
        # 1 overlap out of 4 = 25% → PARTIAL
        report = await service.analyze_conflicts(
            "f-new",
            ["api:/users", "db:orders", "event:order.placed", "src/new.py"],
        )

        assert report.feasibility == Feasibility.PARTIAL
        assert report.conflicts[0]["overlapping_keys"] == ["api:/users"]


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_empty_candidate_claims(self, mock_supabase, db_client):
        """Candidate with no claims → FULL (vacuously)."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[_active_feature_response("f1", ["src/a.py"])],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts("f-new", [])

        assert report.feasibility == Feasibility.FULL
        assert report.conflicts == []
        assert report.total_candidate_claims == 0

    @pytest.mark.asyncio
    async def test_duplicate_claims_in_candidate(self, mock_supabase, db_client):
        """Duplicate claims in candidate should be handled (set semantics)."""
        mock_supabase.get(
            "https://test.supabase.co/rest/v1/feature_registry"
        ).mock(
            return_value=Response(
                200,
                json=[_active_feature_response("f1", ["src/a.py"])],
            )
        )

        service = FeatureRegistryService(db_client)
        report = await service.analyze_conflicts(
            "f-new",
            ["src/a.py", "src/a.py", "src/b.py", "src/c.py"],
        )

        # "src/a.py" overlap, total_candidate_claims=4 (list length),
        # total_conflicting_claims=1 (set overlap)
        assert report.total_candidate_claims == 4
        assert report.total_conflicting_claims == 1
