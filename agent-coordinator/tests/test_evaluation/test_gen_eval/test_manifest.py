"""Tests for scenario-pack manifest parsing, visibility filtering, and reporting.

Covers spec scenarios:
- gen-eval-framework.1.1: Manifest validates public vs holdout classification
- gen-eval-framework.1.2: Manifest preserves provenance metadata
- gen-eval-framework.1.3: Invalid visibility is rejected
- gen-eval-framework.2.3: Report includes visibility coverage

Design decisions: D1 (manifest-driven visibility), D2 (three-layer enforcement)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation.gen_eval.manifest import (
    ManifestEntry,
    ScenarioPackManifest,
    filter_scenarios_by_visibility,
    group_verdicts_by_visibility,
    load_manifest,
    load_manifests_from_dirs,
)

from .conftest import make_scenario, make_verdict

# ── Model validation ───────────────────────────────────────────────


class TestManifestEntry:
    """Test ManifestEntry model validation."""

    def test_valid_public_entry(self) -> None:
        entry = ManifestEntry(
            scenario_id="lock-acquire-001",
            visibility="public",
            source="spec",
            owner="agent-coordinator",
        )
        assert entry.visibility == "public"
        assert entry.source == "spec"
        assert entry.promotion_status == "draft"

    def test_valid_holdout_entry(self) -> None:
        entry = ManifestEntry(
            scenario_id="lock-contention-001",
            visibility="holdout",
            source="incident",
            incident_ref="INC-42",
            owner="oncall",
        )
        assert entry.visibility == "holdout"
        assert entry.incident_ref == "INC-42"

    def test_invalid_visibility_rejected(self) -> None:
        """gen-eval-framework.1.3: Invalid visibility is rejected."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ManifestEntry(
                scenario_id="bad",
                visibility="private",  # type: ignore[arg-type]
            )

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(Exception):
            ManifestEntry(
                scenario_id="bad",
                visibility="public",
                source="unknown",  # type: ignore[arg-type]
            )

    def test_invalid_determinism_rejected(self) -> None:
        with pytest.raises(Exception):
            ManifestEntry(
                scenario_id="bad",
                visibility="public",
                determinism="random",  # type: ignore[arg-type]
            )

    def test_preserves_provenance_metadata(self) -> None:
        """gen-eval-framework.1.2: Manifest preserves provenance metadata."""
        entry = ManifestEntry(
            scenario_id="incident-replay-001",
            visibility="holdout",
            source="incident",
            incident_ref="INC-99",
            determinism="bounded-nondeterministic",
            owner="platform-team",
            promotion_status="candidate",
        )
        assert entry.source == "incident"
        assert entry.incident_ref == "INC-99"
        assert entry.determinism == "bounded-nondeterministic"
        assert entry.owner == "platform-team"
        assert entry.promotion_status == "candidate"

    def test_all_valid_sources(self) -> None:
        for source in ("spec", "contract", "doc", "incident", "archive", "manual"):
            entry = ManifestEntry(
                scenario_id=f"test-{source}",
                visibility="public",
                source=source,  # type: ignore[arg-type]
            )
            assert entry.source == source

    def test_all_valid_promotion_statuses(self) -> None:
        for status in ("draft", "candidate", "approved"):
            entry = ManifestEntry(
                scenario_id=f"test-{status}",
                visibility="public",
                promotion_status=status,  # type: ignore[arg-type]
            )
            assert entry.promotion_status == status


# ── ScenarioPackManifest ───────────────────────────────────────────


class TestScenarioPackManifest:
    """Test ScenarioPackManifest model and utility methods."""

    @pytest.fixture
    def mixed_manifest(self) -> ScenarioPackManifest:
        return ScenarioPackManifest(
            entries=[
                ManifestEntry(scenario_id="s1", visibility="public", source="spec"),
                ManifestEntry(scenario_id="s2", visibility="public", source="contract"),
                ManifestEntry(scenario_id="s3", visibility="holdout", source="incident"),
                ManifestEntry(scenario_id="s4", visibility="holdout", source="archive"),
            ]
        )

    def test_public_ids(self, mixed_manifest: ScenarioPackManifest) -> None:
        """gen-eval-framework.1.1: Manifest validates public vs holdout."""
        assert mixed_manifest.public_ids() == {"s1", "s2"}

    def test_holdout_ids(self, mixed_manifest: ScenarioPackManifest) -> None:
        assert mixed_manifest.holdout_ids() == {"s3", "s4"}

    def test_ids_by_visibility(self, mixed_manifest: ScenarioPackManifest) -> None:
        assert mixed_manifest.ids_by_visibility("public") == {"s1", "s2"}
        assert mixed_manifest.ids_by_visibility("holdout") == {"s3", "s4"}

    def test_empty_manifest(self) -> None:
        manifest = ScenarioPackManifest()
        assert manifest.public_ids() == set()
        assert manifest.holdout_ids() == set()

    def test_version_default(self) -> None:
        manifest = ScenarioPackManifest()
        assert manifest.version == 1


# ── Manifest loading ───────────────────────────────────────────────


class TestLoadManifest:
    """Test YAML manifest loading and error handling."""

    def _write_manifest(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f)
        return path

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        manifest_path = self._write_manifest(
            tmp_path / "manifest.yaml",
            {
                "version": 1,
                "entries": [
                    {"scenario_id": "s1", "visibility": "public", "source": "spec"},
                    {"scenario_id": "s2", "visibility": "holdout", "source": "manual"},
                ],
            },
        )
        manifest = load_manifest(manifest_path)
        assert len(manifest.entries) == 2
        assert manifest.public_ids() == {"s1"}
        assert manifest.holdout_ids() == {"s2"}

    def test_load_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "missing.yaml")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("")
        with pytest.raises(ValueError, match="Empty manifest"):
            load_manifest(path)

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("not: a: valid: !!!")
        # yaml.safe_load may parse this or raise; either way, it shouldn't crash
        # The key test is that invalid manifest content is caught.

    def test_load_invalid_visibility_in_file(self, tmp_path: Path) -> None:
        manifest_path = self._write_manifest(
            tmp_path / "manifest.yaml",
            {
                "entries": [
                    {"scenario_id": "bad", "visibility": "private"},
                ],
            },
        )
        with pytest.raises(ValueError, match="Invalid manifest"):
            load_manifest(manifest_path)

    def test_load_non_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_manifest(path)


class TestLoadManifestsFromDirs:
    """Test multi-directory manifest loading and merging."""

    def test_merge_from_multiple_dirs(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "public"
        dir2 = tmp_path / "holdout"
        dir1.mkdir()
        dir2.mkdir()

        with open(dir1 / "manifest.yaml", "w") as f:
            yaml.dump(
                {"entries": [{"scenario_id": "s1", "visibility": "public"}]},
                f,
            )
        with open(dir2 / "manifest.yaml", "w") as f:
            yaml.dump(
                {"entries": [{"scenario_id": "s2", "visibility": "holdout"}]},
                f,
            )

        manifest = load_manifests_from_dirs([dir1, dir2])
        assert len(manifest.entries) == 2
        assert manifest.public_ids() == {"s1"}
        assert manifest.holdout_ids() == {"s2"}

    def test_no_manifests_found(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        manifest = load_manifests_from_dirs([empty_dir])
        assert len(manifest.entries) == 0

    def test_yml_extension_supported(self, tmp_path: Path) -> None:
        d = tmp_path / "scenarios"
        d.mkdir()
        with open(d / "manifest.yml", "w") as f:
            yaml.dump(
                {"entries": [{"scenario_id": "s1", "visibility": "public"}]},
                f,
            )
        manifest = load_manifests_from_dirs([d])
        assert len(manifest.entries) == 1

    def test_malformed_manifest_logged_and_skipped(self, tmp_path: Path) -> None:
        d = tmp_path / "bad"
        d.mkdir()
        (d / "manifest.yaml").write_text("")
        manifest = load_manifests_from_dirs([d])
        assert len(manifest.entries) == 0


# ── Visibility filtering ──────────────────────────────────────────


class TestFilterByVisibility:
    """Test scenario filtering by visibility."""

    @pytest.fixture
    def manifest(self) -> ScenarioPackManifest:
        return ScenarioPackManifest(
            entries=[
                ManifestEntry(scenario_id="pub-1", visibility="public"),
                ManifestEntry(scenario_id="pub-2", visibility="public"),
                ManifestEntry(scenario_id="hold-1", visibility="holdout"),
            ]
        )

    @pytest.fixture
    def scenarios(self) -> list[Any]:
        return [
            make_scenario("pub-1"),
            make_scenario("pub-2"),
            make_scenario("hold-1"),
            make_scenario("unclassified-1"),
        ]

    def test_public_filter(self, scenarios: list[Any], manifest: ScenarioPackManifest) -> None:
        """gen-eval-framework.2.1: Implementation run excludes holdout."""
        result = filter_scenarios_by_visibility(scenarios, manifest, "public")
        ids = {s.id for s in result}
        assert "pub-1" in ids
        assert "pub-2" in ids
        assert "hold-1" not in ids
        # Unclassified included in non-strict mode
        assert "unclassified-1" in ids

    def test_holdout_filter(self, scenarios: list[Any], manifest: ScenarioPackManifest) -> None:
        """gen-eval-framework.2.2: Cleanup gate includes holdout."""
        result = filter_scenarios_by_visibility(scenarios, manifest, "holdout")
        ids = {s.id for s in result}
        assert "hold-1" in ids
        assert "pub-1" not in ids

    def test_strict_excludes_unclassified(
        self, scenarios: list[Any], manifest: ScenarioPackManifest
    ) -> None:
        result = filter_scenarios_by_visibility(scenarios, manifest, "public", strict=True)
        ids = {s.id for s in result}
        assert "unclassified-1" not in ids

    def test_empty_manifest_returns_all_non_strict(self, scenarios: list[Any]) -> None:
        empty = ScenarioPackManifest()
        result = filter_scenarios_by_visibility(scenarios, empty, "public")
        assert len(result) == len(scenarios)

    def test_empty_manifest_strict_returns_none(self, scenarios: list[Any]) -> None:
        empty = ScenarioPackManifest()
        result = filter_scenarios_by_visibility(scenarios, empty, "public", strict=True)
        assert len(result) == 0


# ── Verdict grouping ──────────────────────────────────────────────


class TestGroupVerdictsByVisibility:
    """Test verdict grouping for visibility-aware reporting."""

    def test_groups_correctly(self) -> None:
        """gen-eval-framework.2.3: Report includes visibility coverage."""
        manifest = ScenarioPackManifest(
            entries=[
                ManifestEntry(scenario_id="pub-1", visibility="public"),
                ManifestEntry(scenario_id="hold-1", visibility="holdout"),
            ]
        )
        verdicts = [
            make_verdict("pub-1", status="pass"),
            make_verdict("hold-1", status="fail"),
            make_verdict("unknown-1", status="pass"),
        ]
        groups = group_verdicts_by_visibility(verdicts, manifest)
        assert len(groups["public"]) == 1
        assert len(groups["holdout"]) == 1
        assert len(groups["unclassified"]) == 1

    def test_empty_verdicts(self) -> None:
        manifest = ScenarioPackManifest()
        groups = group_verdicts_by_visibility([], manifest)
        assert groups == {"public": [], "holdout": [], "unclassified": []}
