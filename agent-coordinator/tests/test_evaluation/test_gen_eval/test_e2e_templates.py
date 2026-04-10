"""Tests validating E2E scenario template YAML structure and Pydantic compliance.

Covers spec scenarios:
- gen-eval-framework (End-to-End User Scenario Templates): all scenarios

Design decisions: D2 (side-effect blocks), D5 (extended assertions)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evaluation.gen_eval.models import ActionStep, ExpectBlock, Scenario, SideEffectsBlock

# Path to scenarios directory
SCENARIOS_DIR = Path(__file__).parents[3] / "evaluation" / "gen_eval" / "scenarios"

# E2E template files
E2E_TEMPLATES = [
    SCENARIOS_DIR / "memory-crud" / "memory-lifecycle-e2e.yaml",
    SCENARIOS_DIR / "work-queue" / "lock-task-workflow-e2e.yaml",
    SCENARIOS_DIR / "auth-boundary" / "policy-enforcement-e2e.yaml",
    SCENARIOS_DIR / "handoffs" / "handoff-integrity-e2e.yaml",
    SCENARIOS_DIR / "cross-interface" / "full-consistency-e2e.yaml",
]


class TestE2ETemplateStructure:
    """Test that all E2E templates are valid YAML and parse into Scenario models."""

    @pytest.mark.parametrize("template_path", E2E_TEMPLATES, ids=lambda p: p.stem)
    def test_template_is_valid_yaml(self, template_path: Path) -> None:
        assert template_path.exists(), f"Template not found: {template_path}"
        with open(template_path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "id" in data
        assert "steps" in data

    @pytest.mark.parametrize("template_path", E2E_TEMPLATES, ids=lambda p: p.stem)
    def test_template_parses_as_scenario(self, template_path: Path) -> None:
        with open(template_path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        assert scenario.id.endswith("-e2e") or scenario.id.endswith("-e2e")
        assert len(scenario.steps) >= 2
        assert "e2e" in scenario.tags

    @pytest.mark.parametrize("template_path", E2E_TEMPLATES, ids=lambda p: p.stem)
    def test_template_uses_extended_features(self, template_path: Path) -> None:
        """Each E2E template must use at least one extended assertion or side-effect block."""
        with open(template_path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)

        has_extended_assertion = False
        has_side_effect = False

        for step in scenario.steps:
            if step.expect:
                if any([
                    step.expect.body_contains,
                    step.expect.body_excludes,
                    step.expect.status_one_of,
                    step.expect.rows_gte,
                    step.expect.rows_lte,
                    step.expect.array_contains,
                ]):
                    has_extended_assertion = True
            if step.side_effects:
                has_side_effect = True

        assert has_extended_assertion or has_side_effect, (
            f"Template {scenario.id} must use at least one extended assertion "
            f"or side-effect block"
        )


class TestMemoryLifecycleE2E:
    """Specific tests for memory lifecycle template."""

    def test_uses_body_contains(self) -> None:
        path = SCENARIOS_DIR / "memory-crud" / "memory-lifecycle-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        # First step should use body_contains
        assert scenario.steps[0].expect is not None
        assert scenario.steps[0].expect.body_contains is not None

    def test_has_verify_and_prohibit(self) -> None:
        path = SCENARIOS_DIR / "memory-crud" / "memory-lifecycle-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        store_step = scenario.steps[0]
        assert store_step.side_effects is not None
        assert len(store_step.side_effects.verify) >= 1
        assert len(store_step.side_effects.prohibit) >= 1


class TestLockTaskWorkflowE2E:
    """Specific tests for lock-task workflow template."""

    def test_uses_status_one_of(self) -> None:
        path = SCENARIOS_DIR / "work-queue" / "lock-task-workflow-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        # Acquire step should accept multiple status codes
        assert scenario.steps[0].expect is not None
        assert scenario.steps[0].expect.status_one_of is not None

    def test_verifies_state_transitions(self) -> None:
        """Multiple steps should have side-effect verify blocks."""
        path = SCENARIOS_DIR / "work-queue" / "lock-task-workflow-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        se_steps = [s for s in scenario.steps if s.side_effects]
        assert len(se_steps) >= 2, "Should verify state after multiple steps"


class TestPolicyEnforcementE2E:
    """Specific tests for policy enforcement template."""

    def test_denied_step_has_prohibit(self) -> None:
        path = SCENARIOS_DIR / "auth-boundary" / "policy-enforcement-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        denied_step = scenario.steps[0]
        assert denied_step.side_effects is not None
        assert len(denied_step.side_effects.prohibit) >= 1


class TestCrossInterfaceE2E:
    """Specific tests for cross-interface consistency template."""

    def test_multiple_transports(self) -> None:
        path = SCENARIOS_DIR / "cross-interface" / "full-consistency-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        transports = {s.transport for s in scenario.steps}
        assert len(transports) >= 2, "Should use multiple transport types"

    def test_uses_rows_gte(self) -> None:
        path = SCENARIOS_DIR / "cross-interface" / "full-consistency-e2e.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        scenario = Scenario(**data)
        has_rows_gte = any(
            s.expect and s.expect.rows_gte is not None
            for s in scenario.steps
        )
        assert has_rows_gte
