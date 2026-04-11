"""Tests for archetype-aware work queue routing and schema validation.

Spec scenarios:
- agent-archetypes.5 (fallback chain integration)
- agent-archetypes.6 (work queue archetype routing)
- agent-archetypes.7 (work package archetype field)

Design decisions: D4 (extend existing fallback), D7 (merge train coexistence)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents_config import AgentEntry
from src.work_queue import Task

# ---------------------------------------------------------------------------
# Task 3.0.1: Work queue agent_requirements filtering
# ---------------------------------------------------------------------------

class TestAgentRequirementsOnTask:
    """Verify agent_requirements field on Task dataclass."""

    def test_task_has_agent_requirements_field(self) -> None:
        """Task dataclass should support agent_requirements."""
        task = Task(
            id="00000000-0000-0000-0000-000000000001",
            task_type="implement",
            description="Test task",
            status="pending",
            priority=5,
            agent_requirements={"archetype": "implementer"},
        )
        assert task.agent_requirements == {"archetype": "implementer"}

    def test_task_without_agent_requirements(self) -> None:
        """Task without agent_requirements defaults to None (backward compat)."""
        task = Task(
            id="00000000-0000-0000-0000-000000000001",
            task_type="implement",
            description="Test task",
            status="pending",
            priority=5,
        )
        assert task.agent_requirements is None

    def test_task_from_dict_with_agent_requirements(self) -> None:
        """from_dict should parse agent_requirements from JSONB result."""
        data = {
            "id": "00000000-0000-0000-0000-000000000001",
            "task_type": "implement",
            "description": "Test",
            "status": "pending",
            "priority": 5,
            "agent_requirements": {"archetype": "reviewer", "min_trust_level": 3},
        }
        task = Task.from_dict(data)
        assert task.agent_requirements is not None
        assert task.agent_requirements["archetype"] == "reviewer"
        assert task.agent_requirements["min_trust_level"] == 3

    def test_task_from_dict_without_agent_requirements(self) -> None:
        """from_dict should handle missing agent_requirements gracefully."""
        data = {
            "id": "00000000-0000-0000-0000-000000000001",
            "task_type": "implement",
            "description": "Test",
            "status": "pending",
            "priority": 5,
        }
        task = Task.from_dict(data)
        assert task.agent_requirements is None


class TestAgentEntryArchetypes:
    """Verify archetypes field on AgentEntry."""

    def test_agent_entry_has_archetypes_field(self) -> None:
        """AgentEntry should support archetypes list."""
        agent = AgentEntry(
            name="claude-local",
            type="claude_code",
            profile="operator",
            trust_level=4,
            transport="mcp",
            capabilities=["lock", "queue"],
            description="Test agent",
            archetypes=["implementer", "reviewer"],
        )
        assert agent.archetypes == ["implementer", "reviewer"]

    def test_agent_entry_default_empty_archetypes(self) -> None:
        """AgentEntry without archetypes defaults to empty list."""
        agent = AgentEntry(
            name="claude-local",
            type="claude_code",
            profile="operator",
            trust_level=4,
            transport="mcp",
            capabilities=["lock", "queue"],
            description="Test agent",
        )
        assert agent.archetypes == []


# ---------------------------------------------------------------------------
# Task 3.0.2: Work-packages archetype field validation
# ---------------------------------------------------------------------------

class TestWorkPackagesArchetypeField:
    """Spec: agent-archetypes.7 — work package archetype field."""

    @pytest.fixture
    def schema_path(self) -> Path:
        """Path to the work-packages schema."""
        p = Path(__file__).resolve().parent.parent.parent / "openspec" / "schemas" / "work-packages.schema.json"
        if not p.exists():
            pytest.skip("work-packages.schema.json not found")
        return p

    def test_schema_accepts_archetype_field(self, schema_path: Path) -> None:
        """Package with valid archetype field should validate."""
        schema = json.loads(schema_path.read_text())
        # Schema uses $ref to #/$defs/WorkPackage
        pkg_props = schema["$defs"]["WorkPackage"]["properties"]
        assert "archetype" in pkg_props
        assert pkg_props["archetype"]["type"] == "string"

    def test_schema_accepts_complexity_in_metadata(self, schema_path: Path) -> None:
        """Package metadata should accept complexity field."""
        schema = json.loads(schema_path.read_text())
        pkg_props = schema["$defs"]["WorkPackage"]["properties"]
        metadata_props = pkg_props["metadata"]["properties"]
        assert "complexity" in metadata_props
        assert metadata_props["complexity"]["enum"] == ["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Task 3.4.0: Fallback chain integration tests
# ---------------------------------------------------------------------------

class TestFallbackChainIntegration:
    """Spec: agent-archetypes.5 — fallback chain integration.
    Design: D4 — extend existing fallback."""

    def _import_dispatcher(self) -> Any:
        """Import review_dispatcher from skills directory."""
        import importlib
        import sys
        repo_root = Path(__file__).resolve().parent.parent.parent
        scripts_dir = repo_root / "skills" / "parallel-infrastructure" / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        return importlib.import_module("review_dispatcher")

    def test_archetype_model_overrides_primary(self) -> None:
        """archetype_model should replace the agent's default primary model."""
        mod = self._import_dispatcher()
        import inspect
        sig = inspect.signature(mod.CliVendorAdapter.dispatch)
        assert "archetype_model" in sig.parameters

    def test_dispatch_builds_correct_model_chain_with_archetype(self) -> None:
        """When archetype_model is provided, it should be first in models_to_try."""
        mod = self._import_dispatcher()
        config = mod.CliConfig(
            command="claude",
            dispatch_modes={"review": MagicMock(args=["-p"])},
            model_flag="--model",
            model="opus",
            model_fallbacks=["sonnet"],
        )
        adapter = mod.CliVendorAdapter(vendor="test", cli_config=config, agent_id="test-agent")

        # Verify build_command uses the archetype model override
        cmd = adapter.build_command("review", "test prompt", model="sonnet")
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "sonnet"
