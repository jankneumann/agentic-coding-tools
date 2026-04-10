"""Tests for the complexity gate module."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))
from complexity_gate import (
    assess_complexity,
)


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    """Write a work-packages.yaml file and return its path."""
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(yaml.dump(data, default_flow_style=False))
    return wp_path


def _make_packages(
    count: int,
    loc_each: int | None = None,
    descriptions: list[str] | None = None,
    task_types: list[str] | None = None,
    ids: list[str] | None = None,
    locks: list[dict] | None = None,
) -> list[dict]:
    """Helper to generate package entries using real schema field names."""
    packages = []
    for i in range(count):
        pkg: dict = {"package_id": f"wp-pkg-{i}", "description": f"Package {i}"}
        if ids and i < len(ids):
            pkg["package_id"] = ids[i]
        if descriptions and i < len(descriptions):
            pkg["description"] = descriptions[i]
        if task_types and i < len(task_types):
            pkg["task_type"] = task_types[i]
        if loc_each is not None:
            pkg["metadata"] = {"loc_estimate": loc_each}
        if locks and i < len(locks):
            pkg["locks"] = locks[i]
        packages.append(pkg)
    return packages


class TestSimpleFeature:
    def test_simple_feature_passes(self, tmp_path: Path) -> None:
        """200 LOC, 2 packages -> allowed=True, no warnings."""
        packages = _make_packages(2, loc_each=100)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.warnings == []
        assert result.force_required is False
        assert result.val_review_enabled is False


class TestLOCThreshold:
    def test_loc_exceeds_threshold(self, tmp_path: Path) -> None:
        """800 LOC -> force_required=True, warning."""
        packages = _make_packages(2, loc_each=400)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.force_required is True
        assert any("LOC estimate" in w and "800" in w for w in result.warnings)

    def test_no_metadata_loc_check_passes(self, tmp_path: Path) -> None:
        """Packages without metadata -> LOC threshold not triggered."""
        packages = _make_packages(2)  # No loc_each
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert not any("LOC" in w for w in result.warnings)
        assert result.force_required is False


class TestPackageThreshold:
    def test_packages_exceed_threshold(self, tmp_path: Path) -> None:
        """6 packages -> force_required=True, warning."""
        packages = _make_packages(6, loc_each=50)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.force_required is True
        assert any("Package count" in w and "6" in w for w in result.warnings)

    def test_integration_package_excluded_from_count(self, tmp_path: Path) -> None:
        """wp-integration not counted in package count."""
        # 5 regular packages + 1 integration = 5 impl (exceeds default 4)
        packages = _make_packages(
            6,
            loc_each=50,
            ids=["wp-a", "wp-b", "wp-c", "wp-d", "wp-e", "wp-integration"],
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.force_required is True
        assert any("Package count (5)" in w for w in result.warnings)

        # Now with 4 regular + 1 integration = 4 impl (within threshold)
        packages2 = _make_packages(
            5,
            loc_each=50,
            ids=["wp-a", "wp-b", "wp-c", "wp-d", "wp-integration"],
        )
        wp_path2 = _write_yaml(tmp_path, {"packages": packages2})

        result2 = assess_complexity(wp_path2)

        assert not any("Package count" in w for w in result2.warnings)


class TestForceFlag:
    def test_force_bypasses_threshold(self, tmp_path: Path) -> None:
        """800 LOC + force=True -> allowed=True (still has warnings)."""
        packages = _make_packages(2, loc_each=400)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path, force=True)

        assert result.allowed is True
        assert result.force_required is True
        assert len(result.warnings) > 0

    def test_force_not_provided_blocks(self, tmp_path: Path) -> None:
        """800 LOC + force=False -> allowed=False."""
        packages = _make_packages(2, loc_each=400)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path, force=False)

        assert result.allowed is False
        assert result.force_required is True


class TestSignalDetection:
    def test_db_migration_enables_val_review(self, tmp_path: Path) -> None:
        """Package with 'migration' in description -> val_review_enabled=True."""
        packages = _make_packages(
            2, loc_each=100, descriptions=["Add database migration", "Update API"]
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.val_review_enabled is True
        assert "db-migration-review" in result.checkpoints

    def test_security_path_enables_val_review(self, tmp_path: Path) -> None:
        """Package with 'auth' in description -> val_review_enabled=True."""
        packages = _make_packages(
            2, loc_each=100, descriptions=["Implement auth flow", "Update UI"]
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.val_review_enabled is True
        assert "security-review" in result.checkpoints


class TestCustomThresholds:
    def test_custom_thresholds_from_yaml(self, tmp_path: Path) -> None:
        """defaults.auto_loop.max_loc=1000 -> 700 LOC passes."""
        packages = _make_packages(2, loc_each=350)
        data = {
            "defaults": {"auto_loop": {"max_loc": 1000}},
            "packages": packages,
        }
        wp_path = _write_yaml(tmp_path, data)

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert not any("LOC" in w for w in result.warnings)


class TestCombined:
    def test_combined_thresholds(self, tmp_path: Path) -> None:
        """LOC + packages + db migration -> all warnings present."""
        packages = _make_packages(
            6,
            loc_each=200,
            descriptions=[
                "Schema migration for users",
                "API handler",
                "CLI tool",
                "Worker",
                "Tests",
                "Docs",
            ],
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.force_required is True
        assert result.val_review_enabled is True
        assert any("LOC" in w for w in result.warnings)
        assert any("Package count" in w for w in result.warnings)
        assert "db-migration-review" in result.checkpoints
