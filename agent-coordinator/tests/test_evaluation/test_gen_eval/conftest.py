"""Shared fixtures for gen-eval tests.

This file is owned by wp-foundation and read-only for other packages.
It provides sample descriptors, scenarios, and mock backends used
across all gen-eval test modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from evaluation.gen_eval.config import BudgetTracker, GenEvalConfig, SDKBudget, TimeBudget
from evaluation.gen_eval.descriptor import (
    AuthConfig,
    CommandDescriptor,
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
    StateVerifier,
    ToolDescriptor,
)
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    ScenarioVerdict,
    StepVerdict,
)


@pytest.fixture
def sample_auth_config() -> AuthConfig:
    return AuthConfig(
        type="api_key",
        header="X-API-Key",
        env_var="COORDINATION_API_KEY",
    )


@pytest.fixture
def sample_endpoints() -> list[EndpointDescriptor]:
    return [
        EndpointDescriptor(
            path="/locks/acquire",
            method="POST",
            auth_required=True,
            description="Acquire a file lock",
            tags=["locks"],
        ),
        EndpointDescriptor(
            path="/locks/release",
            method="POST",
            auth_required=True,
            description="Release a file lock",
            tags=["locks"],
        ),
        EndpointDescriptor(
            path="/health",
            method="GET",
            auth_required=False,
            description="Health check",
            tags=["health"],
        ),
    ]


@pytest.fixture
def sample_tools() -> list[ToolDescriptor]:
    return [
        ToolDescriptor(name="acquire_lock", description="Acquire a file lock"),
        ToolDescriptor(name="release_lock", description="Release a file lock"),
    ]


@pytest.fixture
def sample_commands() -> list[CommandDescriptor]:
    return [
        CommandDescriptor(name="lock", subcommands=["acquire", "release", "status"]),
    ]


@pytest.fixture
def sample_http_service(
    sample_auth_config: AuthConfig,
    sample_endpoints: list[EndpointDescriptor],
) -> ServiceDescriptor:
    return ServiceDescriptor(
        name="coordination-api",
        type="http",
        base_url="http://localhost:8081",
        auth=sample_auth_config,
        endpoints=sample_endpoints,
    )


@pytest.fixture
def sample_mcp_service(sample_tools: list[ToolDescriptor]) -> ServiceDescriptor:
    return ServiceDescriptor(
        name="coordination-mcp",
        type="mcp",
        transport="sse",
        mcp_url="http://localhost:8082/sse",
        tools=sample_tools,
    )


@pytest.fixture
def sample_cli_service(sample_commands: list[CommandDescriptor]) -> ServiceDescriptor:
    return ServiceDescriptor(
        name="coordination-cli",
        type="cli",
        command="coordination-cli",
        json_flag="--output-format json",
        commands=sample_commands,
    )


@pytest.fixture
def sample_state_verifier() -> StateVerifier:
    return StateVerifier(
        name="postgres",
        type="postgres",
        dsn_env="DATABASE_URL",
        tables=["file_locks", "work_queue", "memory_episodic"],
    )


@pytest.fixture
def sample_startup_config() -> StartupConfig:
    return StartupConfig(
        command="docker-compose up -d",
        health_check="http://localhost:8081/health",
        health_timeout_seconds=60,
        teardown="docker-compose down -v",
        seed_command="python seed_data.py",
    )


@pytest.fixture
def sample_descriptor(
    sample_http_service: ServiceDescriptor,
    sample_mcp_service: ServiceDescriptor,
    sample_cli_service: ServiceDescriptor,
    sample_state_verifier: StateVerifier,
    sample_startup_config: StartupConfig,
) -> InterfaceDescriptor:
    return InterfaceDescriptor(
        project="agent-coordinator",
        version="0.1.0",
        services=[sample_http_service, sample_mcp_service, sample_cli_service],
        state_verifiers=[sample_state_verifier],
        startup=sample_startup_config,
    )


@pytest.fixture
def sample_action_step() -> ActionStep:
    return ActionStep(
        id="acquire_lock",
        transport="http",
        method="POST",
        endpoint="/locks/acquire",
        body={"file_path": "src/main.py", "agent_id": "agent-1"},
        expect=ExpectBlock(status=200, body={"success": True}),
        capture={"lock_id": "$.lock_id"},
    )


@pytest.fixture
def sample_scenario(sample_action_step: ActionStep) -> Scenario:
    return Scenario(
        id="lock-acquire-release",
        name="Lock acquire and release",
        description="Test basic lock acquisition and release",
        category="lock-lifecycle",
        priority=1,
        interfaces=["http"],
        steps=[
            sample_action_step,
            ActionStep(
                id="release_lock",
                transport="http",
                method="POST",
                endpoint="/locks/release",
                body={"file_path": "src/main.py", "agent_id": "agent-1"},
                expect=ExpectBlock(status=200, body={"success": True}),
            ),
        ],
        cleanup=[
            ActionStep(
                id="cleanup_release",
                transport="http",
                method="POST",
                endpoint="/locks/release",
                body={"file_path": "src/main.py", "agent_id": "agent-1"},
            ),
        ],
        tags=["locks", "basic"],
    )


@pytest.fixture
def sample_step_verdict() -> StepVerdict:
    return StepVerdict(
        step_id="acquire_lock",
        transport="http",
        status="pass",
        actual={"status": 200, "body": {"success": True, "lock_id": "abc123"}},
        expected={"status": 200, "body": {"success": True}},
        duration_ms=45.2,
    )


@pytest.fixture
def sample_scenario_verdict(sample_step_verdict: StepVerdict) -> ScenarioVerdict:
    return ScenarioVerdict(
        scenario_id="lock-acquire-release",
        scenario_name="Lock acquire and release",
        status="pass",
        steps=[sample_step_verdict],
        duration_seconds=0.12,
        interfaces_tested=["http"],
        category="lock-lifecycle",
    )


@pytest.fixture
def sample_config(tmp_path: Path) -> GenEvalConfig:
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text("project: test\nversion: '0.1'\n")
    return GenEvalConfig(descriptor_path=descriptor_path)


@pytest.fixture
def sample_time_budget() -> TimeBudget:
    return TimeBudget(total_minutes=10.0)


@pytest.fixture
def sample_sdk_budget() -> SDKBudget:
    return SDKBudget(budget_usd=5.0)


@pytest.fixture
def sample_budget_tracker() -> BudgetTracker:
    return BudgetTracker(
        mode="cli",
        time_budget=TimeBudget(total_minutes=10.0),
    )


def make_scenario(
    scenario_id: str = "test-scenario",
    category: str = "lock-lifecycle",
    priority: int = 1,
    steps: list[dict[str, Any]] | None = None,
) -> Scenario:
    """Factory function for creating test scenarios."""
    if steps is None:
        steps = [
            {
                "id": "step1",
                "transport": "http",
                "method": "GET",
                "endpoint": "/health",
                "expect": {"status": 200},
            }
        ]
    return Scenario(
        id=scenario_id,
        name=f"Test: {scenario_id}",
        description=f"Test scenario {scenario_id}",
        category=category,
        priority=priority,
        interfaces=["http"],
        steps=[ActionStep(**s) for s in steps],
    )


def make_verdict(
    scenario_id: str = "test-scenario",
    status: str = "pass",
    duration: float = 0.1,
) -> ScenarioVerdict:
    """Factory function for creating test verdicts."""
    return ScenarioVerdict(
        scenario_id=scenario_id,
        scenario_name=f"Test: {scenario_id}",
        status=status,  # type: ignore[arg-type]
        steps=[],
        duration_seconds=duration,
        interfaces_tested=["http"],
        category="lock-lifecycle",
    )
