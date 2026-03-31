"""Tests for SDKGenerator and SDKBackend (mocked API)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import (
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
)
from evaluation.gen_eval.models import EvalFeedback
from evaluation.gen_eval.sdk_generator import SDKBackend, SDKBackendError, SDKGenerator


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
    return GenEvalConfig(descriptor_path=dp, mode="sdk-only")


def _make_yaml_response(scenarios: list[dict]) -> str:
    return yaml.dump(scenarios, default_flow_style=False)


class TestSDKBackend:
    def test_name(self) -> None:
        backend = SDKBackend(provider="anthropic", model="claude-sonnet-4-6")
        assert "anthropic" in backend.name
        assert "claude-sonnet-4-6" in backend.name

    def test_not_subscription_covered(self) -> None:
        backend = SDKBackend()
        assert backend.is_subscription_covered is False

    def test_default_api_key_env_anthropic(self) -> None:
        """L5: Default api_key_env should be ANTHROPIC_API_KEY for anthropic provider."""
        backend = SDKBackend(provider="anthropic")
        assert backend.api_key_env == "ANTHROPIC_API_KEY"

    def test_default_api_key_env_openai(self) -> None:
        """L5: Default api_key_env should be OPENAI_API_KEY for openai provider."""
        backend = SDKBackend(provider="openai")
        assert backend.api_key_env == "OPENAI_API_KEY"

    def test_explicit_api_key_env_overrides_default(self) -> None:
        """L5: Explicit api_key_env should override the provider-based default."""
        backend = SDKBackend(provider="openai", api_key_env="MY_CUSTOM_KEY")
        assert backend.api_key_env == "MY_CUSTOM_KEY"

    @pytest.mark.asyncio
    async def test_is_available_with_key(self) -> None:
        backend = SDKBackend(api_key_env="TEST_KEY_FOR_SDK")
        with patch.dict(os.environ, {"TEST_KEY_FOR_SDK": "sk-test"}):
            assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_without_key(self) -> None:
        backend = SDKBackend(api_key_env="NONEXISTENT_KEY_XYZ_123")
        # Ensure the env var doesn't exist
        env = os.environ.copy()
        env.pop("NONEXISTENT_KEY_XYZ_123", None)
        with patch.dict(os.environ, env, clear=True):
            assert await backend.is_available() is False

    @pytest.mark.asyncio
    async def test_run_anthropic_success(self) -> None:
        backend = SDKBackend(provider="anthropic", api_key_env="TEST_API_KEY")

        mock_content = MagicMock()
        mock_content.text = "- id: test\n  name: Test"
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            with patch("evaluation.gen_eval.sdk_generator.anthropic", create=True):
                # Mock the import
                import sys

                mock_anthropic_module = MagicMock()
                mock_anthropic_module.AsyncAnthropic.return_value = mock_client
                with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}):
                    result = await backend.run("generate scenarios", system="system")
        assert "test" in result

    @pytest.mark.asyncio
    async def test_run_missing_api_key(self) -> None:
        backend = SDKBackend(provider="anthropic", api_key_env="MISSING_KEY_XYZ")
        env = os.environ.copy()
        env.pop("MISSING_KEY_XYZ", None)

        import sys

        mock_anthropic = MagicMock()
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
                with pytest.raises(SDKBackendError, match="API key not found"):
                    await backend.run("test")

    @pytest.mark.asyncio
    async def test_run_unsupported_provider(self) -> None:
        backend = SDKBackend(provider="unsupported")  # type: ignore[arg-type]
        with pytest.raises(SDKBackendError, match="Unsupported provider"):
            await backend.run("test")

    @pytest.mark.asyncio
    async def test_run_anthropic_empty_response(self) -> None:
        """Empty response.content should raise SDKBackendError, not crash."""
        backend = SDKBackend(provider="anthropic", api_key_env="TEST_API_KEY")

        mock_response = MagicMock()
        mock_response.content = []  # empty content

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        import sys

        mock_anthropic_module = MagicMock()
        mock_anthropic_module.AsyncAnthropic.return_value = mock_client

        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}):
                with pytest.raises(SDKBackendError, match="Empty or non-text response"):
                    await backend.run("generate scenarios")

    @pytest.mark.asyncio
    async def test_run_openai_success(self) -> None:
        backend = SDKBackend(provider="openai", model="gpt-4", api_key_env="TEST_OPENAI_KEY")

        mock_message = MagicMock()
        mock_message.content = "- id: oai-test\n  name: OpenAI Test"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import sys

        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client

        with patch.dict(os.environ, {"TEST_OPENAI_KEY": "sk-test"}):
            with patch.dict(sys.modules, {"openai": mock_openai_module}):
                result = await backend.run("generate", system="sys")
        assert "oai-test" in result


class TestSDKGenerator:
    @pytest.mark.asyncio
    async def test_generate_parses_yaml(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        yaml_output = _make_yaml_response(
            [
                {
                    "id": "sdk-1",
                    "name": "SDK scenario",
                    "description": "SDK generated",
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
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(return_value=yaml_output)

        gen = SDKGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate(count=5)
        assert len(scenarios) == 1
        assert scenarios[0].id == "sdk-1"
        assert scenarios[0].generated_by == "llm"

    @pytest.mark.asyncio
    async def test_generate_with_focus_areas(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(return_value="[]")

        gen = SDKGenerator(descriptor, config, backend=mock_backend)
        await gen.generate(focus_areas=["locks"], count=3)

        prompt = mock_backend.run.call_args[0][0]
        assert "locks" in prompt
        assert "3" in prompt

    @pytest.mark.asyncio
    async def test_generate_with_feedback(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        feedback = EvalFeedback(
            iteration=1,
            failing_interfaces=["POST /locks/acquire"],
            suggested_focus=["error handling"],
        )
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(return_value="[]")

        gen = SDKGenerator(descriptor, config, backend=mock_backend, feedback=feedback)
        await gen.generate()

        prompt = mock_backend.run.call_args[0][0]
        assert "POST /locks/acquire" in prompt
        assert "error handling" in prompt

    @pytest.mark.asyncio
    async def test_generate_invalid_yaml(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(return_value="not yaml: [}")

        gen = SDKGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert scenarios == []

    @pytest.mark.asyncio
    async def test_generate_sdk_error_propagates(
        self, descriptor: InterfaceDescriptor, config: GenEvalConfig
    ) -> None:
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(side_effect=SDKBackendError("API error"))

        gen = SDKGenerator(descriptor, config, backend=mock_backend)
        with pytest.raises(SDKBackendError):
            await gen.generate()

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
        mock_backend = AsyncMock(spec=SDKBackend)
        mock_backend.run = AsyncMock(return_value=f"```yaml\n{yaml_content}\n```")

        gen = SDKGenerator(descriptor, config, backend=mock_backend)
        scenarios = await gen.generate()
        assert len(scenarios) == 1
