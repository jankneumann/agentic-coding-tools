"""Tests for TemplateGenerator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import (
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
)
from evaluation.gen_eval.generator import TemplateGenerator
from evaluation.gen_eval.models import EvalFeedback


@pytest.fixture
def descriptor(tmp_path: Path) -> InterfaceDescriptor:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    return InterfaceDescriptor(
        project="test-project",
        version="0.1.0",
        services=[
            ServiceDescriptor(
                name="api",
                type="http",
                base_url="http://localhost:8081",
                endpoints=[
                    EndpointDescriptor(path="/health", method="GET"),
                    EndpointDescriptor(path="/locks/acquire", method="POST"),
                ],
            ),
        ],
        startup=StartupConfig(
            command="echo start",
            health_check="http://localhost:8081/health",
            teardown="echo stop",
        ),
        scenario_dirs=[scenario_dir],
    )


@pytest.fixture
def config(tmp_path: Path) -> GenEvalConfig:
    dp = tmp_path / "descriptor.yaml"
    dp.write_text("project: test\nversion: '0.1'\n")
    return GenEvalConfig(descriptor_path=dp, max_expansions=100)


def _write_scenario_yaml(
    scenario_dir: Path,
    filename: str,
    data: dict[str, Any] | list[dict[str, Any]],
) -> Path:
    p = scenario_dir / filename
    p.write_text(yaml.dump(data, default_flow_style=False))
    return p


class TestTemplateGeneratorBasic:
    @pytest.mark.asyncio
    async def test_load_single_scenario(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "basic.yaml",
            {
                "id": "health-check",
                "name": "Health check",
                "description": "Check health endpoint",
                "category": "health",
                "interfaces": ["http"],
                "steps": [
                    {
                        "id": "s1",
                        "transport": "http",
                        "method": "GET",
                        "endpoint": "/health",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 1
        assert scenarios[0].id == "health-check"
        assert scenarios[0].category == "health"

    @pytest.mark.asyncio
    async def test_load_multiple_scenarios_from_list(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "multi.yaml",
            [
                {
                    "id": "s1",
                    "name": "Scenario 1",
                    "description": "First",
                    "category": "cat1",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "step1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
                {
                    "id": "s2",
                    "name": "Scenario 2",
                    "description": "Second",
                    "category": "cat2",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "step1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
            ],
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 2

    @pytest.mark.asyncio
    async def test_empty_scenario_dir(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate()
        assert scenarios == []

    @pytest.mark.asyncio
    async def test_missing_scenario_dir(
        self,
        config: GenEvalConfig,
    ) -> None:
        desc = InterfaceDescriptor(
            project="test",
            version="0.1",
            services=[],
            startup=StartupConfig(
                command="echo start",
                health_check="http://localhost/health",
                teardown="echo stop",
            ),
            scenario_dirs=[Path("/nonexistent/dir")],
        )
        gen = TemplateGenerator(desc, config)
        scenarios = await gen.generate()
        assert scenarios == []


class TestTemplateGeneratorParameterExpansion:
    @pytest.mark.asyncio
    async def test_jinja2_expansion(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "param.yaml",
            {
                "id": "lock-test",
                "name": "Lock {{ file_path }}",
                "description": "Lock test for {{ file_path }}",
                "category": "locks",
                "interfaces": ["http"],
                "parameters": {"file_path": ["main.py", "util.py"]},
                "steps": [
                    {
                        "id": "acquire",
                        "transport": "http",
                        "method": "POST",
                        "endpoint": "/locks/acquire",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 2
        assert scenarios[0].name == "Lock main.py"
        assert scenarios[1].name == "Lock util.py"
        # Each expansion gets unique ID
        assert scenarios[0].id != scenarios[1].id

    @pytest.mark.asyncio
    async def test_combinatorial_expansion(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "combo.yaml",
            {
                "id": "combo",
                "name": "{{ method }} {{ path }}",
                "description": "Test {{ method }} {{ path }}",
                "category": "api",
                "interfaces": ["http"],
                "parameters": {
                    "method": ["GET", "POST"],
                    "path": ["/a", "/b", "/c"],
                },
                "steps": [
                    {
                        "id": "s1",
                        "transport": "http",
                        "method": "GET",
                        "endpoint": "/health",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        # 2 methods x 3 paths = 6
        assert len(scenarios) == 6

    @pytest.mark.asyncio
    async def test_max_expansions_cap(
        self, descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        dp = tmp_path / "descriptor.yaml"
        dp.write_text("project: test\nversion: '0.1'\n")
        capped_config = GenEvalConfig(descriptor_path=dp, max_expansions=3)

        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "many.yaml",
            {
                "id": "many",
                "name": "Test {{ n }}",
                "description": "Test {{ n }}",
                "category": "test",
                "interfaces": ["http"],
                "parameters": {"n": list(range(20))},
                "steps": [
                    {
                        "id": "s1",
                        "transport": "http",
                        "method": "GET",
                        "endpoint": "/health",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, capped_config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 3

    @pytest.mark.asyncio
    async def test_scalar_parameter_coercion(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        """Scalar params should be wrapped in a list, not iterated char-by-char."""
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "scalar.yaml",
            {
                "id": "scalar-test",
                "name": "Test {{ mode }}",
                "description": "Scalar param test",
                "category": "test",
                "interfaces": ["http"],
                "parameters": {"mode": "single"},
                "steps": [
                    {
                        "id": "s1",
                        "transport": "http",
                        "method": "GET",
                        "endpoint": "/health",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        # Should produce exactly 1 scenario (the scalar string treated as a single value),
        # not 6 scenarios (one per character in "single")
        assert len(scenarios) == 1
        assert scenarios[0].name == "Test single"

    @pytest.mark.asyncio
    async def test_no_parameters_passthrough(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "noparam.yaml",
            {
                "id": "static",
                "name": "Static test",
                "description": "No parameters",
                "category": "test",
                "interfaces": ["http"],
                "steps": [
                    {
                        "id": "s1",
                        "transport": "http",
                        "method": "GET",
                        "endpoint": "/health",
                    }
                ],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 1
        assert scenarios[0].id == "static"


class TestTemplateGeneratorValidation:
    @pytest.mark.asyncio
    async def test_invalid_scenario_skipped(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        # Missing required 'interfaces' field
        _write_scenario_yaml(
            scenario_dir,
            "invalid.yaml",
            {
                "id": "bad",
                "name": "Bad scenario",
                "description": "Missing interfaces",
                "category": "test",
                "steps": [],
            },
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate()
        assert scenarios == []

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "mixed.yaml",
            [
                {
                    "id": "good",
                    "name": "Good",
                    "description": "Valid",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
                {
                    "id": "bad",
                    "name": "Bad",
                    # missing description, interfaces
                    "category": "test",
                    "steps": [],
                },
            ],
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert len(scenarios) == 1
        assert scenarios[0].id == "good"

    @pytest.mark.asyncio
    async def test_bad_yaml_skipped(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        (scenario_dir / "bad.yaml").write_text("{{invalid yaml: [}")
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate()
        assert scenarios == []


class TestTemplateGeneratorFiltering:
    @pytest.mark.asyncio
    async def test_filter_by_focus_areas(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "cats.yaml",
            [
                {
                    "id": "s1",
                    "name": "Lock test",
                    "description": "Lock",
                    "category": "locks",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
                {
                    "id": "s2",
                    "name": "Memory test",
                    "description": "Memory",
                    "category": "memory",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
            ],
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(focus_areas=["locks"], count=50)
        assert len(scenarios) == 1
        assert scenarios[0].category == "locks"

    @pytest.mark.asyncio
    async def test_priority_sorting(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "prio.yaml",
            [
                {
                    "id": "low",
                    "name": "Low prio",
                    "description": "Low",
                    "category": "test",
                    "priority": 3,
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
                {
                    "id": "high",
                    "name": "High prio",
                    "description": "High",
                    "category": "test",
                    "priority": 1,
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
            ],
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=50)
        assert scenarios[0].id == "high"
        assert scenarios[1].id == "low"

    @pytest.mark.asyncio
    async def test_feedback_prioritization(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "fb.yaml",
            [
                {
                    "id": "s1",
                    "name": "Locks",
                    "description": "Lock test",
                    "category": "locks",
                    "priority": 2,
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
                {
                    "id": "s2",
                    "name": "Memory",
                    "description": "Memory test",
                    "category": "memory",
                    "priority": 2,
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                },
            ],
        )
        feedback = EvalFeedback(
            iteration=1,
            under_tested_categories=["memory"],
        )
        gen = TemplateGenerator(descriptor, config, feedback=feedback)
        scenarios = await gen.generate(count=50)
        # Memory should come first due to feedback prioritization
        assert scenarios[0].category == "memory"

    @pytest.mark.asyncio
    async def test_count_cap(self, descriptor: InterfaceDescriptor, config: GenEvalConfig) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        _write_scenario_yaml(
            scenario_dir,
            "many.yaml",
            [
                {
                    "id": f"s{i}",
                    "name": f"Scenario {i}",
                    "description": f"Test {i}",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
                for i in range(20)
            ],
        )
        gen = TemplateGenerator(descriptor, config)
        scenarios = await gen.generate(count=5)
        assert len(scenarios) == 5
