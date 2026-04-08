"""Tests for scenario pack manifest model and loader (Phase 4).

Covers: manifest model validation, visibility filtering, provenance
tracking, and invalid enum rejection.

Design decisions: D6 (manifest format), D7 (filter integration point).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.gen_eval.manifest import (
    Determinism,
    PromotionStatus,
    ScenarioManifestEntry,
    ScenarioPackManifest,
    Source,
    Visibility,
    filter_by_visibility,
    get_scenario_visibility,
    load_manifests,
)


class TestScenarioManifestEntry:
    """Manifest entry validation."""

    def test_valid_entry(self) -> None:
        entry = ScenarioManifestEntry(
            id="acquire-release",
            visibility=Visibility.public,
            source=Source.spec,
            determinism=Determinism.deterministic,
            owner="gen-eval-testing",
            promotion_status=PromotionStatus.approved,
        )
        assert entry.visibility == Visibility.public
        assert entry.source == Source.spec

    def test_invalid_visibility_rejected(self) -> None:
        """Spec scenario: Invalid visibility is rejected."""
        with pytest.raises(ValidationError):
            ScenarioManifestEntry(
                id="bad",
                visibility="private",  # type: ignore[arg-type]
                source=Source.manual,
            )

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioManifestEntry(
                id="bad",
                visibility=Visibility.public,
                source="unknown",  # type: ignore[arg-type]
            )

    def test_preserves_provenance(self) -> None:
        """Spec scenario: Manifest preserves provenance metadata."""
        entry = ScenarioManifestEntry(
            id="incident-recovery-1",
            visibility=Visibility.public,
            source=Source.incident,
            owner="incident-2024-001",
        )
        assert entry.source == Source.incident
        assert entry.owner == "incident-2024-001"

    def test_defaults(self) -> None:
        entry = ScenarioManifestEntry(
            id="test",
            visibility=Visibility.public,
            source=Source.manual,
        )
        assert entry.determinism == Determinism.deterministic
        assert entry.promotion_status == PromotionStatus.draft
        assert entry.owner == ""


class TestScenarioPackManifest:
    """Pack manifest model."""

    def test_valid_manifest(self) -> None:
        """Spec scenario: Manifest validates public vs holdout classification."""
        manifest = ScenarioPackManifest(
            pack="lock-lifecycle",
            scenarios=[
                ScenarioManifestEntry(
                    id="acquire-release",
                    visibility=Visibility.public,
                    source=Source.spec,
                ),
                ScenarioManifestEntry(
                    id="contention-holdout-1",
                    visibility=Visibility.holdout,
                    source=Source.manual,
                ),
            ],
        )
        assert len(manifest.scenarios) == 2
        assert manifest.scenarios[0].visibility == Visibility.public
        assert manifest.scenarios[1].visibility == Visibility.holdout

    def test_empty_scenarios(self) -> None:
        manifest = ScenarioPackManifest(pack="empty")
        assert manifest.scenarios == []


class TestLoadManifests:
    """Loading manifests from disk."""

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "lock-lifecycle.manifest.yaml"
        manifest_file.write_text(
            "pack: lock-lifecycle\n"
            "scenarios:\n"
            "  - id: acquire-release\n"
            "    visibility: public\n"
            "    source: spec\n"
        )
        manifests = load_manifests(tmp_path)
        assert "lock-lifecycle" in manifests
        assert len(manifests["lock-lifecycle"].scenarios) == 1

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        manifests = load_manifests(tmp_path / "missing")
        assert manifests == {}

    def test_load_invalid_yaml_skipped(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.manifest.yaml"
        bad_file.write_text("pack: bad\nscenarios:\n  - id: x\n    visibility: invalid\n")
        manifests = load_manifests(tmp_path)
        assert "bad" not in manifests

    def test_load_empty_file_skipped(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.manifest.yaml"
        empty_file.write_text("")
        manifests = load_manifests(tmp_path)
        assert manifests == {}


class TestVisibilityFiltering:
    """Visibility-aware scenario filtering (D7)."""

    def _sample_manifests(self) -> dict[str, ScenarioPackManifest]:
        return {
            "lock-lifecycle": ScenarioPackManifest(
                pack="lock-lifecycle",
                scenarios=[
                    ScenarioManifestEntry(
                        id="acquire-release",
                        visibility=Visibility.public,
                        source=Source.spec,
                    ),
                    ScenarioManifestEntry(
                        id="contention-holdout",
                        visibility=Visibility.holdout,
                        source=Source.manual,
                    ),
                ],
            ),
            "memory-crud": ScenarioPackManifest(
                pack="memory-crud",
                scenarios=[
                    ScenarioManifestEntry(
                        id="store-recall",
                        visibility=Visibility.public,
                        source=Source.spec,
                    ),
                ],
            ),
        }

    def test_filter_public_excludes_holdout(self) -> None:
        """Spec scenario: Implementation run excludes holdout scenarios."""
        manifests = self._sample_manifests()
        ids = ["acquire-release", "contention-holdout", "store-recall"]
        filtered = filter_by_visibility(manifests, ids, "public")
        assert "acquire-release" in filtered
        assert "store-recall" in filtered
        assert "contention-holdout" not in filtered

    def test_filter_all_includes_everything(self) -> None:
        """Spec scenario: Cleanup gate includes holdout scenarios."""
        manifests = self._sample_manifests()
        ids = ["acquire-release", "contention-holdout", "store-recall"]
        filtered = filter_by_visibility(manifests, ids, "all")
        assert len(filtered) == 3

    def test_unknown_scenarios_treated_as_public(self) -> None:
        manifests = self._sample_manifests()
        ids = ["unknown-scenario"]
        filtered = filter_by_visibility(manifests, ids, "public")
        assert "unknown-scenario" in filtered

    def test_get_scenario_visibility(self) -> None:
        manifests = self._sample_manifests()
        assert get_scenario_visibility(manifests, "acquire-release") == Visibility.public
        assert get_scenario_visibility(manifests, "contention-holdout") == Visibility.holdout
        assert get_scenario_visibility(manifests, "unknown") is None
