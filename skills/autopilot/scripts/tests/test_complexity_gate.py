"""Tests for the entry gate module.

The gate no longer blocks on size. It applies one deterministic hard block —
the scope-safety floor (broad write scope) — and otherwise gathers a risk +
verifiability signal profile for the GATEKEEPER judge, demoting former blockers
(LOC, package count, db-migration) to advisory signals / validation review.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))
from complexity_gate import (
    assess_complexity,
    default_gate_verdict,
    gather_signals,
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
        """200 LOC, 2 packages -> allowed=True, no warnings, no force."""
        packages = _make_packages(2, loc_each=100)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.warnings == []
        assert result.force_required is False
        assert result.val_review_enabled is False
        assert result.signals["package_count"] == 2
        assert result.signals["total_loc_estimate"] == 200


class TestNoSizeBlocking:
    """LOC and package count are signals now, never hard blocks."""

    def test_high_loc_does_not_force(self, tmp_path: Path) -> None:
        """800 LOC -> reported as a signal, but never blocks."""
        packages = _make_packages(2, loc_each=400)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert result.signals["total_loc_estimate"] == 800

    def test_extreme_package_count_does_not_force(self, tmp_path: Path) -> None:
        """13 packages -> scheduling warnings + checkpoints, but no force."""
        packages = _make_packages(13, loc_each=20)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert result.signals["package_count"] == 13
        # Still emits scheduling signals so the DAG paces itself.
        assert "wave-validation" in result.checkpoints
        assert "limit-concurrency" in result.checkpoints

    def test_package_count_scheduling_warning(self, tmp_path: Path) -> None:
        """6 packages -> wave checkpoint + warning, not a block."""
        packages = _make_packages(6, loc_each=50)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert any("Package count" in w and "6" in w for w in result.warnings)
        assert "wave-validation" in result.checkpoints
        assert "limit-concurrency" not in result.checkpoints

    def test_integration_package_excluded_from_count(self, tmp_path: Path) -> None:
        """wp-integration not counted in package_count signal."""
        packages = _make_packages(
            6,
            loc_each=50,
            ids=["wp-a", "wp-b", "wp-c", "wp-d", "wp-e", "wp-integration"],
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.signals["package_count"] == 5


class TestScopeSafetyFloor:
    """Broad write scope is the ONLY remaining deterministic hard block."""

    def test_broad_write_scope_requires_force(self, tmp_path: Path) -> None:
        packages = _make_packages(1, loc_each=50)
        packages[0]["scope"] = {"write_allow": ["**"]}
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is False
        assert result.force_required is True
        assert result.signals["has_broad_write_scope"] is True
        assert any("Broad write scope" in w for w in result.warnings)

    def test_force_bypasses_scope_floor(self, tmp_path: Path) -> None:
        """--force lets broad write scope through (still flagged)."""
        packages = _make_packages(1, loc_each=50)
        packages[0]["scope"] = {"write_allow": ["**"]}
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path, force=True)

        assert result.allowed is True
        assert result.force_required is True
        assert len(result.warnings) > 0


class TestRiskSignalsEnableReview:
    """Risk signals enable validation review but never force."""

    def test_db_migration_enables_val_review_without_force(self, tmp_path: Path) -> None:
        packages = _make_packages(
            2, loc_each=100, descriptions=["Add database migration", "Update API"]
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert result.val_review_enabled is True
        assert result.signals["has_db_migration"] is True
        assert "db-migration-review" in result.checkpoints

    def test_security_signal_enables_val_review(self, tmp_path: Path) -> None:
        packages = _make_packages(
            2, loc_each=100, descriptions=["Implement auth flow", "Update UI"]
        )
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert result.val_review_enabled is True
        assert result.signals["has_security_signal"] is True
        assert "security-review" in result.checkpoints

    def test_external_deps_emit_dependency_review(self, tmp_path: Path) -> None:
        packages = _make_packages(2, loc_each=100)
        packages[0]["metadata"]["external_deps"] = ["a", "b", "c"]
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert result.force_required is False
        assert result.signals["external_dep_count"] == 3
        assert "dependency-review" in result.checkpoints


class TestGatherSignals:
    def test_verifiability_facts_from_change_dir(self, tmp_path: Path) -> None:
        """has_specs/has_tasks/has_proposal reflect the change directory."""
        packages = _make_packages(2, loc_each=50)
        wp_path = _write_yaml(tmp_path, {"packages": packages})
        (tmp_path / "specs").mkdir()
        (tmp_path / "tasks.md").write_text("- [ ] task")
        (tmp_path / "proposal.md").write_text("# proposal")

        signals = gather_signals(wp_path)

        assert signals["has_specs"] is True
        assert signals["has_tasks"] is True
        assert signals["has_proposal"] is True
        assert signals["has_work_packages"] is True

    def test_missing_artifacts_report_false(self, tmp_path: Path) -> None:
        packages = _make_packages(1, loc_each=50)
        wp_path = _write_yaml(tmp_path, {"packages": packages})

        signals = gather_signals(wp_path)

        assert signals["has_specs"] is False
        assert signals["has_tasks"] is False
        assert signals["has_proposal"] is False

    def test_missing_work_packages_tolerated(self, tmp_path: Path) -> None:
        """A bare description (no work-packages.yaml yet) must not raise."""
        signals = gather_signals(tmp_path / "work-packages.yaml")

        assert signals["package_count"] == 0
        assert signals["has_work_packages"] is False


class TestDefaultVerdict:
    def test_clean_change_proceeds(self) -> None:
        signals = {"has_db_migration": False, "has_security_signal": False,
                   "has_broad_write_scope": False}
        assert default_gate_verdict(signals) == "proceed"

    def test_risk_signal_triggers_review(self) -> None:
        signals = {"has_db_migration": True}
        assert default_gate_verdict(signals) == "proceed_with_review"

    def test_empty_signals_proceed(self) -> None:
        assert default_gate_verdict({}) == "proceed"


class TestCustomThresholds:
    def test_custom_scheduling_threshold_from_yaml(self, tmp_path: Path) -> None:
        """defaults.auto_loop.max_packages widens the wave-checkpoint threshold."""
        packages = _make_packages(6, loc_each=50)
        data = {
            "defaults": {"auto_loop": {"max_packages": 10}},
            "packages": packages,
        }
        wp_path = _write_yaml(tmp_path, data)

        result = assess_complexity(wp_path)

        assert result.allowed is True
        assert "wave-validation" not in result.checkpoints
        assert not any("Package count" in w for w in result.warnings)
