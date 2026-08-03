"""``InterfaceDescriptor.startup`` is optional (UP-4).

It used to be required, so a project with nothing to start had to invent a
`StartupConfig` it never used. ACA's descriptor carried three no-ops purely
to satisfy the schema; agentic-assistant's carried the identical wart with a
comment saying so.

The health check made this worse than three inert strings: it runs even under
``--no-services`` (to verify externally-managed services are reachable), so
the placeholder ``health_check`` had to be a URL that genuinely *succeeded* —
typically a ``file://`` path chosen for no reason a later reader could infer.

Omitting the block now skips startup, health check, seeding and teardown.
There is nothing to do, so there is nothing to describe.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gen_eval.config import GenEvalConfig
from gen_eval.descriptor import InterfaceDescriptor, ServiceSpec, StartupConfig
from gen_eval.evaluator import Evaluator
from gen_eval.orchestrator import GenEvalOrchestrator

CLI_ONLY_YAML = """
project: cli-only
version: "1.0"
services:
  - name: my-cli
    type: cli
    command: my-tool
"""


class TestDescriptorAcceptsNoStartup:
    def test_model_defaults_startup_to_none(self) -> None:
        descriptor = InterfaceDescriptor(
            project="cli-only",
            version="1.0",
            services=[ServiceSpec(name="my-cli", type="cli", command="my-tool")],
        )
        assert descriptor.startup is None

    def test_yaml_without_startup_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "descriptor.yaml"
        path.write_text(CLI_ONLY_YAML)
        descriptor = InterfaceDescriptor.from_yaml(path)
        assert descriptor.startup is None
        assert descriptor.services[0].command == "my-tool"

    def test_startup_still_accepted_when_present(self, tmp_path: Path) -> None:
        """Widening must not break descriptors that do declare a startup block."""
        path = tmp_path / "descriptor.yaml"
        path.write_text(
            CLI_ONLY_YAML
            + """
startup:
  command: docker compose up -d
  health_check: http://127.0.0.1:8000/health
  teardown: docker compose down -v
"""
        )
        descriptor = InterfaceDescriptor.from_yaml(path)
        assert descriptor.startup is not None
        assert descriptor.startup.command == "docker compose up -d"

    def test_schema_no_longer_requires_startup(self) -> None:
        """The published contract must reflect the widening."""
        from gen_eval.contracts import load_schema

        schema = load_schema("interface-descriptor")
        assert "startup" not in schema["required"]
        assert "startup" in schema["properties"]


def _orchestrator(descriptor: InterfaceDescriptor, tmp_path: Path) -> GenEvalOrchestrator:
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text(CLI_ONLY_YAML)
    return GenEvalOrchestrator(
        config=GenEvalConfig(descriptor_path=descriptor_path, max_iterations=1),
        descriptor=descriptor,
        generator=AsyncMock(),
        evaluator=AsyncMock(spec=Evaluator),
    )


@pytest.fixture
def cli_only(tmp_path: Path) -> GenEvalOrchestrator:
    descriptor = InterfaceDescriptor(
        project="cli-only",
        version="1.0",
        services=[ServiceSpec(name="my-cli", type="cli", command="my-tool")],
    )
    return _orchestrator(descriptor, tmp_path)


class TestLifecycleSkippedWithoutStartup:
    """No startup block ⇒ nothing to start, check, seed or tear down."""

    def test_startup_runs_no_subprocess(self, cli_only: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            cli_only._run_startup()
        run.assert_not_called()

    def test_teardown_runs_no_subprocess(self, cli_only: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            cli_only._run_teardown()
        run.assert_not_called()

    def test_seed_runs_no_subprocess(self, cli_only: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            cli_only._seed_data()
        run.assert_not_called()

    async def test_health_check_is_skipped_entirely(
        self, cli_only: GenEvalOrchestrator
    ) -> None:
        """The crux of UP-4.

        The health check runs even under ``no_services``, so before this
        change a descriptor with nothing to start still had to supply a URL
        that genuinely resolved. Omitting the block must skip the check
        rather than fail it.
        """
        with patch("urllib.request.urlopen") as urlopen:
            await cli_only._health_check()
        urlopen.assert_not_called()

    async def test_health_check_still_runs_when_startup_declared(
        self, tmp_path: Path
    ) -> None:
        """Negative control: declaring a startup block keeps the old behaviour."""
        descriptor = InterfaceDescriptor(
            project="with-startup",
            version="1.0",
            services=[ServiceSpec(name="my-cli", type="cli", command="my-tool")],
            startup=StartupConfig(
                command="true",
                health_check="http://127.0.0.1:9/health",
                teardown="true",
            ),
        )
        orch = _orchestrator(descriptor, tmp_path)
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            await orch._health_check()
        urlopen.assert_called()
