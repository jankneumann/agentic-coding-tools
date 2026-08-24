"""Tests for the config-ratcheted Architecture gate in gate_logic.py.

TDD tests written before implementation (task 2.3, OpenSpec change
introduce-fitness-function-gates). Covers design decision D4 and
contracts/architecture-gates-config.md:

- advisory mode (the shipped default): architecture findings never block
- blocking mode: a new dependency cycle blocks the hard / pre-merge gate
- architecture.config.yaml carries gates.architecture.mode and non-empty
  health.severity_thresholds
- the config file stays OPTIONAL: absent, empty, or unparseable falls back to
  advisory built-in defaults, and unknown keys warn rather than error
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gate_logic import (  # noqa: E402
    REQUIRED_PHASES,
    architecture_mode,
    architecture_status,
    load_gate_config,
    pre_merge_gate,
    resolve_required_phases,
    severity_for_category,
)


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "architecture.config.yaml").is_file():
            return parent
    raise AssertionError("architecture.config.yaml not found above this test file")


def _write_config(tmp_path: Path, mode: str) -> Path:
    config = tmp_path / "architecture.config.yaml"
    config.write_text(
        "gates:\n"
        "  architecture:\n"
        f"    mode: {mode}\n"
        "    block_on:\n"
        "      new_dependency_cycles: true\n"
        "    clean_runs_before_flip: 3\n"
        "health:\n"
        "  severity_thresholds:\n"
        "    new_cycle: critical\n"
        "    cross_layer_violation: major\n"
        "    file_size: minor\n"
    )
    return config


_NEW_CYCLE_FINDING = {
    "category": "new_cycle",
    "description": "New dependency cycle: skills.a -> skills.b -> skills.a",
}
_FILE_SIZE_FINDING = {
    "category": "file_size",
    "description": "runner.py has 812 lines, exceeding the 500 line limit",
}

_PASSING_REQUIRED_PHASES = (
    "## Smoke Tests\n\n- **Status**: pass\n\n"
    "## Security\n\n- **Status**: pass\n\n"
    "## E2E Tests\n\n- **Status**: pass\n"
)


def test_validate_feature_produces_and_consumes_architecture_diff() -> None:
    skill = (_repo_root() / "skills" / "validate-feature" / "SKILL.md").read_text()

    assert "make architecture-diff BASE_SHA=\"$ARCH_BASE_SHA\"" in skill
    assert "architecture.diff.json" in skill
    assert "new_cycles" in skill
    assert "architecture_status" in skill


class TestConfigLoader:
    """The loader must keep architecture.config.yaml optional (Rule 4)."""

    def test_absent_file_defaults_to_advisory(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.yaml"
        assert architecture_mode(missing) == "advisory"

    def test_empty_file_defaults_to_advisory(self, tmp_path: Path) -> None:
        empty = tmp_path / "architecture.config.yaml"
        empty.write_text("")
        assert architecture_mode(empty) == "advisory"

    def test_unparseable_file_defaults_to_advisory(self, tmp_path: Path) -> None:
        broken = tmp_path / "architecture.config.yaml"
        broken.write_text("gates: [unclosed\n  : :\n")
        assert architecture_mode(broken) == "advisory"

    def test_unknown_mode_falls_back_to_advisory(self, tmp_path: Path) -> None:
        weird = tmp_path / "architecture.config.yaml"
        weird.write_text("gates:\n  architecture:\n    mode: banana\n")
        assert architecture_mode(weird) == "advisory"

    def test_unknown_keys_warn_but_do_not_error(self, tmp_path: Path) -> None:
        config = tmp_path / "architecture.config.yaml"
        config.write_text(
            "gates:\n"
            "  architecture:\n"
            "    mode: blocking\n"
            "    unheard_of_key: 42\n"
        )
        with pytest.warns(UserWarning, match="unheard_of_key"):
            loaded = load_gate_config(config)
        # The recognised keys still take effect.
        assert loaded["architecture"]["mode"] == "blocking"

    def test_defaults_include_block_on_and_thresholds(self, tmp_path: Path) -> None:
        loaded = load_gate_config(tmp_path / "absent.yaml")
        assert loaded["architecture"]["mode"] == "advisory"
        assert loaded["architecture"]["block_on"]["new_dependency_cycles"] is True
        assert loaded["severity_thresholds"]["new_cycle"] == "critical"

    def test_blocking_mode_is_read_from_config(self, tmp_path: Path) -> None:
        assert architecture_mode(_write_config(tmp_path, "blocking")) == "blocking"


class TestShippedConfig:
    """architecture.config.yaml itself must satisfy the contract (task 2.4)."""

    def test_repo_config_declares_architecture_gate_mode(self) -> None:
        raw = yaml.safe_load((_repo_root() / "architecture.config.yaml").read_text())
        mode = raw["gates"]["architecture"]["mode"]
        assert mode in ("advisory", "blocking")

    def test_repo_config_ships_advisory_default(self) -> None:
        """Phase 1 ships advisory; flipping to blocking is a separate one-line PR."""
        raw = yaml.safe_load((_repo_root() / "architecture.config.yaml").read_text())
        assert raw["gates"]["architecture"]["mode"] == "advisory"
        assert raw["gates"]["architecture"]["block_on"]["new_dependency_cycles"] is True
        assert raw["gates"]["architecture"]["clean_runs_before_flip"] == 3

    def test_repo_config_severity_thresholds_are_populated(self) -> None:
        raw = yaml.safe_load((_repo_root() / "architecture.config.yaml").read_text())
        thresholds = raw["gates"]["architecture"]["severity_thresholds"]
        assert thresholds, "severity_thresholds must no longer be empty"
        assert thresholds["new_cycle"] == "critical"
        assert thresholds["cross_layer_violation"] == "major"
        assert thresholds["file_size"] == "minor"

    def test_gate_thresholds_do_not_leak_into_report_namespace(self) -> None:
        """The gate grades {critical, major, minor}; the architecture report grades
        {error, warning, info}. They must not share `health.severity_thresholds` --
        a category graded in the wrong vocabulary resolves to no filtering at all,
        which is a threshold that silently does nothing."""
        raw = yaml.safe_load((_repo_root() / "architecture.config.yaml").read_text())
        report_thresholds = raw["health"]["severity_thresholds"] or {}
        gate_vocabulary = {"critical", "major", "minor"}
        offenders = {
            cat: sev
            for cat, sev in report_thresholds.items()
            if str(sev) in gate_vocabulary
        }
        assert not offenders, (
            f"gate-vocabulary severities found under health.severity_thresholds: "
            f"{offenders}. Put gate thresholds under gates.architecture."
        )


class TestSeverityMapping:
    """A new dependency cycle is the first critical fitness-function finding."""

    def test_new_cycle_maps_to_critical(self, tmp_path: Path) -> None:
        assert severity_for_category("new_cycle", _write_config(tmp_path, "advisory")) == "critical"

    def test_thresholds_are_config_driven(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, "advisory")
        assert severity_for_category("cross_layer_violation", config) == "major"
        assert severity_for_category("file_size", config) == "minor"

    def test_unknown_category_is_not_critical(self, tmp_path: Path) -> None:
        assert severity_for_category("who_knows", _write_config(tmp_path, "advisory")) != "critical"


class TestAdvisoryMode:
    """Advisory mode reports loudly but never changes a run's outcome."""

    def test_architecture_not_in_required_phases(self, tmp_path: Path) -> None:
        phases = resolve_required_phases(_write_config(tmp_path, "advisory"))
        assert "Architecture" not in phases
        assert set(phases) == set(REQUIRED_PHASES)

    def test_new_cycle_does_not_fail_the_gate(self, tmp_path: Path) -> None:
        status = architecture_status(
            [_NEW_CYCLE_FINDING], config_path=_write_config(tmp_path, "advisory"),
        )
        assert status == "pass"

    def test_failing_architecture_section_does_not_block_pre_merge(
        self, tmp_path: Path
    ) -> None:
        """Advisory: even an explicit Architecture failure leaves the merge open."""
        report = tmp_path / "validation-report.md"
        report.write_text(
            _PASSING_REQUIRED_PHASES + "\n## Architecture\n\n- **Status**: fail\n"
        )

        action, reason, statuses = pre_merge_gate(
            str(report), config_path=_write_config(tmp_path, "advisory"),
        )
        assert action == "continue"
        assert "Architecture" not in statuses

    def test_default_config_preserves_existing_outcomes(self, tmp_path: Path) -> None:
        """No config argument at all must behave exactly as before this change."""
        report = tmp_path / "validation-report.md"
        report.write_text(_PASSING_REQUIRED_PHASES)

        action, _reason, statuses = pre_merge_gate(str(report))
        assert action == "continue"
        assert set(statuses) == {"Smoke Tests", "Security", "E2E Tests"}


class TestBlockingMode:
    """Blocking mode (the Phase-2 flip) makes new cycles fail the merge gate."""

    def test_architecture_joins_required_phases(self, tmp_path: Path) -> None:
        phases = resolve_required_phases(_write_config(tmp_path, "blocking"))
        assert "Architecture" in phases

    def test_new_cycle_fails_the_gate(self, tmp_path: Path) -> None:
        status = architecture_status(
            [_NEW_CYCLE_FINDING], config_path=_write_config(tmp_path, "blocking"),
        )
        assert status == "fail"

    def test_non_blocking_category_still_passes(self, tmp_path: Path) -> None:
        status = architecture_status(
            [_FILE_SIZE_FINDING], config_path=_write_config(tmp_path, "blocking"),
        )
        assert status == "pass"

    def test_cycle_described_without_category_is_detected(self, tmp_path: Path) -> None:
        status = architecture_status(
            [{"description": "New dependency cycle introduced between A and B"}],
            config_path=_write_config(tmp_path, "blocking"),
        )
        assert status == "fail"

    def test_pre_merge_gate_blocks_on_failed_architecture(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(
            _PASSING_REQUIRED_PHASES + "\n## Architecture\n\n- **Status**: fail\n"
        )

        action, reason, statuses = pre_merge_gate(
            str(report), config_path=_write_config(tmp_path, "blocking"),
        )
        assert action == "halt"
        assert statuses["Architecture"] == "fail"
        assert "Architecture" in reason

    def test_pre_merge_gate_blocks_when_architecture_missing(
        self, tmp_path: Path
    ) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_PASSING_REQUIRED_PHASES)

        action, _reason, statuses = pre_merge_gate(
            str(report), config_path=_write_config(tmp_path, "blocking"),
        )
        assert action == "halt"
        assert statuses["Architecture"] == "missing"

    def test_pre_merge_gate_passes_with_clean_architecture(
        self, tmp_path: Path
    ) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(
            _PASSING_REQUIRED_PHASES + "\n## Architecture\n\n- **Status**: pass\n"
        )

        action, _reason, statuses = pre_merge_gate(
            str(report), config_path=_write_config(tmp_path, "blocking"),
        )
        assert action == "continue"
        assert statuses["Architecture"] == "pass"

    def test_block_on_disabled_lets_cycles_through(self, tmp_path: Path) -> None:
        config = tmp_path / "architecture.config.yaml"
        config.write_text(
            "gates:\n"
            "  architecture:\n"
            "    mode: blocking\n"
            "    block_on:\n"
            "      new_dependency_cycles: false\n"
        )
        assert architecture_status([_NEW_CYCLE_FINDING], config_path=config) == "pass"
