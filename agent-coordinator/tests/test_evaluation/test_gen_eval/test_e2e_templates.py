"""Tests validating E2E scenario template YAML structure and Pydantic model compliance (Phase 5).

Verifies that each template loads as valid YAML and parses into Scenario models.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evaluation.gen_eval.models import Scenario

# Path to scenarios relative to the gen_eval package
_SCENARIOS_DIR = Path(__file__).parent.parent.parent.parent / "evaluation" / "gen_eval" / "scenarios"

_E2E_TEMPLATES = [
    "memory-crud/memory-lifecycle-e2e.yaml",
    "work-queue/lock-task-workflow-e2e.yaml",
    "auth-boundary/policy-enforcement-e2e.yaml",
    "handoffs/handoff-integrity-e2e.yaml",
    "cross-interface/full-consistency-e2e.yaml",
]


class TestE2ETemplates:
    """Validate E2E scenario template YAML files."""

    @pytest.mark.parametrize("template_path", _E2E_TEMPLATES)
    def test_template_loads_as_valid_yaml(self, template_path: str) -> None:
        full_path = _SCENARIOS_DIR / template_path
        assert full_path.exists(), f"Template not found: {full_path}"

        with open(full_path) as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "id" in data
        assert "steps" in data

    @pytest.mark.parametrize("template_path", _E2E_TEMPLATES)
    def test_template_parses_as_scenario(self, template_path: str) -> None:
        full_path = _SCENARIOS_DIR / template_path

        with open(full_path) as f:
            data = yaml.safe_load(f)

        scenario = Scenario(**data)
        assert scenario.id
        assert len(scenario.steps) > 0
        assert scenario.category

    def test_memory_lifecycle_uses_extended_assertions(self) -> None:
        full_path = _SCENARIOS_DIR / "memory-crud/memory-lifecycle-e2e.yaml"
        with open(full_path) as f:
            data = yaml.safe_load(f)

        # Should use body_contains or side_effects
        steps = data.get("steps", [])
        has_extended = any(
            s.get("expect", {}).get("body_contains")
            or s.get("side_effects")
            for s in steps
        )
        assert has_extended, "Memory lifecycle template should use extended assertions"

    def test_lock_task_uses_side_effects(self) -> None:
        full_path = _SCENARIOS_DIR / "work-queue/lock-task-workflow-e2e.yaml"
        with open(full_path) as f:
            data = yaml.safe_load(f)

        steps = data.get("steps", [])
        has_side_effects = any(s.get("side_effects") for s in steps)
        assert has_side_effects, "Lock-task template should use side_effects"

    def test_policy_enforcement_uses_prohibit(self) -> None:
        full_path = _SCENARIOS_DIR / "auth-boundary/policy-enforcement-e2e.yaml"
        with open(full_path) as f:
            data = yaml.safe_load(f)

        steps = data.get("steps", [])
        has_prohibit = any(
            s.get("side_effects", {}).get("prohibit")
            for s in steps
            if isinstance(s.get("side_effects"), dict)
        )
        has_status_one_of = any(
            s.get("expect", {}).get("status_one_of")
            for s in steps
        )
        assert has_prohibit or has_status_one_of, (
            "Policy enforcement template should use prohibit or status_one_of"
        )


class TestManifestFiles:
    """Validate manifest YAML files load correctly."""

    _MANIFESTS_DIR = _SCENARIOS_DIR.parent / "manifests"
    _MANIFEST_FILES = [
        "memory-crud.manifest.yaml",
        "work-queue.manifest.yaml",
        "auth-boundary.manifest.yaml",
        "handoffs.manifest.yaml",
        "cross-interface.manifest.yaml",
        "lock-lifecycle.manifest.yaml",
    ]

    @pytest.mark.parametrize("manifest_file", _MANIFEST_FILES)
    def test_manifest_loads(self, manifest_file: str) -> None:
        from evaluation.gen_eval.manifest import ScenarioPackManifest

        full_path = self._MANIFESTS_DIR / manifest_file
        assert full_path.exists(), f"Manifest not found: {full_path}"

        with open(full_path) as f:
            data = yaml.safe_load(f)

        manifest = ScenarioPackManifest(**data)
        assert manifest.pack
        assert len(manifest.scenarios) > 0
