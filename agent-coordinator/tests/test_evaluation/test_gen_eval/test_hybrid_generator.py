"""Tests for HybridGenerator and AdaptiveBackend."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from evaluation.gen_eval.cli_generator import CLIBackend, CLIBackendError
from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import (
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
)
from evaluation.gen_eval.hybrid_generator import AdaptiveBackend, HybridGenerator
from evaluation.gen_eval.models import EvalFeedback
from evaluation.gen_eval.sdk_generator import SDKBackend


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
    return GenEvalConfig(descriptor_path=dp, mode="cli-augmented")


@pytest.fixture
def mock_cli_backend() -> AsyncMock:
    backend = AsyncMock(spec=CLIBackend)
    backend.name = "cli:claude"
    backend.is_subscription_covered = True
    backend.command = "claude"
    backend.args = ["--print"]
    return backend


@pytest.fixture
def mock_sdk_backend() -> AsyncMock:
    backend = AsyncMock(spec=SDKBackend)
    backend.name = "sdk:anthropic/claude-sonnet-4-6"
    backend.is_subscription_covered = False
    return backend


class TestAdaptiveBackend:
    @pytest.mark.asyncio
    async def test_uses_cli_first(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.return_value = "cli output"
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)

        result = await adaptive.run("test prompt")
        assert result == "cli output"
        mock_cli_backend.run.assert_called_once()
        mock_sdk_backend.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "rate limited", exit_code=1, stderr="Error: rate limit exceeded"
        )
        mock_sdk_backend.run.return_value = "sdk output"

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        result = await adaptive.run("test prompt")
        assert result == "sdk output"

    @pytest.mark.asyncio
    async def test_fallback_on_429(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "http error", exit_code=1, stderr="HTTP 429 Too Many Requests"
        )
        mock_sdk_backend.run.return_value = "sdk fallback"

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        result = await adaptive.run("test")
        assert result == "sdk fallback"

    @pytest.mark.asyncio
    async def test_fallback_on_quota_exceeded(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "quota", exit_code=1, stderr="Error: quota exceeded for this account"
        )
        mock_sdk_backend.run.return_value = "sdk quota fallback"

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        result = await adaptive.run("test")
        assert result == "sdk quota fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_on_non_rate_limit_error(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "syntax error", exit_code=2, stderr="SyntaxError: invalid syntax"
        )

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        with pytest.raises(CLIBackendError):
            await adaptive.run("test")
        mock_sdk_backend.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sdk_configured_raises(self, mock_cli_backend: AsyncMock) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "rate limited", exit_code=1, stderr="rate limit"
        )

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=None)
        with pytest.raises(CLIBackendError, match="no SDK backend"):
            await adaptive.run("test")

    @pytest.mark.asyncio
    async def test_subsequent_calls_use_sdk_after_fallback(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "rate limited", exit_code=1, stderr="rate limit"
        )
        mock_sdk_backend.run.return_value = "sdk output"

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        await adaptive.run("first")
        await adaptive.run("second")

        # CLI called once (first attempt), SDK called twice (fallback + second)
        assert mock_cli_backend.run.call_count == 1
        assert mock_sdk_backend.run.call_count == 2

    @pytest.mark.asyncio
    async def test_reset_restores_cli(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "rate limited", exit_code=1, stderr="rate limit"
        )
        mock_sdk_backend.run.return_value = "sdk"

        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        await adaptive.run("test")

        # Reset and make CLI work again
        adaptive.reset()
        mock_cli_backend.run.side_effect = None
        mock_cli_backend.run.return_value = "cli again"

        result = await adaptive.run("test2")
        assert result == "cli again"

    def test_name_reflects_active_backend(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        assert "cli" in adaptive.name

        adaptive._cli_available = False
        assert "sdk" in adaptive.name

    def test_is_subscription_covered(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        assert adaptive.is_subscription_covered is True

        adaptive._cli_available = False
        assert adaptive.is_subscription_covered is False

    @pytest.mark.asyncio
    async def test_is_available_cli(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.is_available.return_value = True
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        assert await adaptive.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_sdk_fallback(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.is_available.return_value = False
        mock_sdk_backend.is_available.return_value = True
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        assert await adaptive.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_neither(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.is_available.return_value = False
        mock_sdk_backend.is_available.return_value = False
        adaptive = AdaptiveBackend(cli=mock_cli_backend, sdk=mock_sdk_backend)
        assert await adaptive.is_available() is False

    @pytest.mark.asyncio
    async def test_custom_rate_limit_patterns(
        self, mock_cli_backend: AsyncMock, mock_sdk_backend: AsyncMock
    ) -> None:
        mock_cli_backend.run.side_effect = CLIBackendError(
            "custom error", exit_code=1, stderr="CUSTOM_THROTTLE_ERROR"
        )
        mock_sdk_backend.run.return_value = "sdk"

        adaptive = AdaptiveBackend(
            cli=mock_cli_backend,
            sdk=mock_sdk_backend,
            rate_limit_patterns=["CUSTOM_THROTTLE_ERROR"],
        )
        result = await adaptive.run("test")
        assert result == "sdk"


class TestHybridGenerator:
    @pytest.mark.asyncio
    async def test_template_only_mode(
        self, descriptor: InterfaceDescriptor, tmp_path: Path
    ) -> None:
        dp = tmp_path / "descriptor.yaml"
        dp.write_text("project: test\nversion: '0.1'\n")
        template_config = GenEvalConfig(descriptor_path=dp, mode="template-only")

        # Write a template
        scenario_dir = descriptor.scenario_dirs[0]
        (scenario_dir / "basic.yaml").write_text(
            yaml.dump(
                {
                    "id": "tmpl-1",
                    "name": "Template scenario",
                    "description": "From template",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            )
        )

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=template_config,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=10)
        assert len(scenarios) == 1
        assert scenarios[0].id == "tmpl-1"
        # In template-only mode, no LLM calls
        mock_adaptive.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_augments_with_llm(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        # Write one template scenario
        scenario_dir = descriptor.scenario_dirs[0]
        (scenario_dir / "basic.yaml").write_text(
            yaml.dump(
                {
                    "id": "tmpl-1",
                    "name": "Template",
                    "description": "From template",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            )
        )

        llm_yaml = yaml.dump(
            [
                {
                    "id": "llm-1",
                    "name": "LLM scenario",
                    "description": "Generated",
                    "category": "test",
                    "interfaces": ["http"],
                    "generated_by": "llm",
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

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.run.return_value = llm_yaml
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=config,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=5)
        assert len(scenarios) == 2
        ids = {s.id for s in scenarios}
        assert "tmpl-1" in ids
        assert "llm-1" in ids

    @pytest.mark.asyncio
    async def test_deduplicates_by_id(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        (scenario_dir / "basic.yaml").write_text(
            yaml.dump(
                {
                    "id": "dup-id",
                    "name": "Template",
                    "description": "From template",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            )
        )

        # LLM returns scenario with same ID
        llm_yaml = yaml.dump(
            [
                {
                    "id": "dup-id",
                    "name": "LLM duplicate",
                    "description": "Duplicate",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            ]
        )

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.run.return_value = llm_yaml
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=config,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=10)
        # Only one scenario with the duplicate ID
        assert sum(1 for s in scenarios if s.id == "dup-id") == 1

    @pytest.mark.asyncio
    async def test_llm_failure_returns_templates_only(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        (scenario_dir / "basic.yaml").write_text(
            yaml.dump(
                {
                    "id": "tmpl-safe",
                    "name": "Safe template",
                    "description": "Always works",
                    "category": "test",
                    "interfaces": ["http"],
                    "steps": [
                        {"id": "s1", "transport": "http", "method": "GET", "endpoint": "/health"}
                    ],
                }
            )
        )

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.run.side_effect = CLIBackendError(
            "failed", exit_code=1, stderr="connection refused"
        )
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=config,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=10)
        assert len(scenarios) == 1
        assert scenarios[0].id == "tmpl-safe"

    @pytest.mark.asyncio
    async def test_templates_sufficient_no_llm_call(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        scenario_dir = descriptor.scenario_dirs[0]
        # Write enough templates to satisfy count
        (scenario_dir / "many.yaml").write_text(
            yaml.dump(
                [
                    {
                        "id": f"tmpl-{i}",
                        "name": f"Template {i}",
                        "description": f"Test {i}",
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
                    }
                    for i in range(5)
                ]
            )
        )

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=config,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=3)
        assert len(scenarios) == 3
        mock_adaptive.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_feedback(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        feedback = EvalFeedback(
            iteration=1,
            under_tested_categories=["auth"],
        )

        mock_adaptive = AsyncMock(spec=AdaptiveBackend)
        mock_adaptive.run.return_value = "[]"
        mock_adaptive.cli = AsyncMock(spec=CLIBackend)
        mock_adaptive.cli.command = "claude"
        mock_adaptive.cli.args = ["--print"]
        mock_adaptive.sdk = AsyncMock(spec=SDKBackend)

        gen = HybridGenerator(
            descriptor=descriptor,
            config=config,
            feedback=feedback,
            adaptive_backend=mock_adaptive,
        )
        scenarios = await gen.generate(count=5)
        # Should not crash; feedback is passed through
        assert isinstance(scenarios, list)
