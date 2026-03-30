"""Tests for CLIGenerator and CLIBackend (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from evaluation.gen_eval.cli_generator import CLIBackend, CLIBackendError, CLIGenerator
from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import (
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
)
from evaluation.gen_eval.models import EvalFeedback


@pytest.fixture
def descriptor() -> InterfaceDescriptor:
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
    )


@pytest.fixture
def config(tmp_path: Path) -> GenEvalConfig:
    dp = tmp_path / "descriptor.yaml"
    dp.write_text("project: test\nversion: '0.1'\n")
    return GenEvalConfig(descriptor_path=dp)


def _make_yaml_response(scenarios: list[dict]) -> str:
    return yaml.dump(scenarios, default_flow_style=False)


class TestCLIBackend:
    @pytest.mark.asyncio
    async def test_run_success(self) -> None:
        backend = CLIBackend(command="echo", args=["hello"])
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await backend.run("test prompt")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_nonzero_exit(self) -> None:
        backend = CLIBackend(command="false")
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(CLIBackendError) as exc_info:
                await backend.run("test")
        assert exc_info.value.exit_code == 1
        assert "error msg" in exc_info.value.stderr

    @pytest.mark.asyncio
    async def test_run_timeout(self) -> None:
        backend = CLIBackend(command="sleep", args=["100"], timeout_seconds=1)
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(CLIBackendError) as exc_info:
                await backend.run("test")
        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_file_not_found(self) -> None:
        backend = CLIBackend(command="nonexistent_tool_xyz")

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("not found"),
        ):
            with pytest.raises(CLIBackendError):
                await backend.run("test")

    @pytest.mark.asyncio
    async def test_is_available_true(self) -> None:
        backend = CLIBackend(command="echo")
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_false(self) -> None:
        backend = CLIBackend(command="nonexistent_xyz")
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            assert await backend.is_available() is False

    def test_name(self) -> None:
        backend = CLIBackend(command="claude")
        assert backend.name == "cli:claude"

    def test_is_subscription_covered(self) -> None:
        backend = CLIBackend()
        assert backend.is_subscription_covered is True

    @pytest.mark.asyncio
    async def test_run_with_system_prompt(self) -> None:
        backend = CLIBackend(command="echo", args=[])
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await backend.run("user prompt", system="system instruction")
        # Verify the prompt is passed as a positional argument (not stdin)
        exec_args = mock_exec.call_args[0]
        full_prompt = exec_args[-1]  # last positional arg is the prompt
        assert "system instruction" in full_prompt
        assert "user prompt" in full_prompt


class TestCLIGenerator:
    @pytest.mark.asyncio
    async def test_generate_parses_yaml(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        yaml_output = _make_yaml_response(
            [
                {
                    "id": "gen-1",
                    "name": "Generated scenario",
                    "description": "LLM generated",
                    "category": "locks",
                    "interfaces": ["http"],
                    "steps": [
                        {
                            "id": "s1",
                            "transport": "http",
                            "method": "POST",
                            "endpoint": "/locks/acquire",
                        }
                    ],
                }
            ]
        )
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value=yaml_output)

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate(count=5)
        assert len(scenarios) == 1
        assert scenarios[0].id == "gen-1"
        assert scenarios[0].generated_by == "llm"

    @pytest.mark.asyncio
    async def test_generate_strips_markdown_fences(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        yaml_content = _make_yaml_response(
            [
                {
                    "id": "fenced",
                    "name": "Fenced",
                    "description": "With fences",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            ]
        )
        fenced = f"```yaml\n{yaml_content}\n```"
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value=fenced)

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert len(scenarios) == 1

    @pytest.mark.asyncio
    async def test_generate_invalid_yaml_returns_empty(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value="this is not valid yaml: [}")

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert scenarios == []

    @pytest.mark.asyncio
    async def test_generate_invalid_scenario_skipped(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        yaml_output = _make_yaml_response(
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
                    # missing required fields
                },
            ]
        )
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value=yaml_output)

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert len(scenarios) == 1
        assert scenarios[0].id == "good"

    @pytest.mark.asyncio
    async def test_generate_propagates_cli_error(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(
            side_effect=CLIBackendError("failed", exit_code=1, stderr="error")
        )

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        with pytest.raises(CLIBackendError):
            await gen.generate()

    @pytest.mark.asyncio
    async def test_prompt_includes_interfaces(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value="[]")

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        await gen.generate(focus_areas=["locks"], count=5)

        call_args = mock_backend.run.call_args
        prompt = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "/locks/acquire" in prompt
        assert "locks" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_feedback(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        feedback = EvalFeedback(
            iteration=1,
            failing_interfaces=["POST /locks/acquire"],
            under_tested_categories=["audit-trail"],
        )
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value="[]")

        gen = CLIGenerator(descriptor, config, backend=mock_backend, feedback=feedback)
        await gen.generate()

        call_args = mock_backend.run.call_args
        prompt = call_args[0][0]
        assert "audit-trail" in prompt
        assert "POST /locks/acquire" in prompt

    @pytest.mark.asyncio
    async def test_generate_empty_output(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=CLIBackend)
        mock_backend.run = AsyncMock(return_value="")

        gen = CLIGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert scenarios == []
