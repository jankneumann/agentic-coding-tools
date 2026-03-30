"""Tests for interface descriptor models."""

from __future__ import annotations

from pathlib import Path

import yaml

from evaluation.gen_eval.descriptor import (
    AuthConfig,
    CommandDescriptor,
    EndpointDescriptor,
    FileInterfaceMapping,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
    StateVerifier,
    ToolDescriptor,
)


class TestAuthConfig:
    def test_defaults(self) -> None:
        auth = AuthConfig()
        assert auth.type == "none"
        assert auth.header == "X-API-Key"

    def test_api_key(self) -> None:
        auth = AuthConfig(type="api_key", env_var="MY_KEY")
        assert auth.type == "api_key"
        assert auth.env_var == "MY_KEY"


class TestEndpointDescriptor:
    def test_basic(self) -> None:
        ep = EndpointDescriptor(path="/health", method="GET")
        assert ep.path == "/health"
        assert not ep.auth_required

    def test_with_schemas(self) -> None:
        ep = EndpointDescriptor(
            path="/locks/acquire",
            method="POST",
            auth_required=True,
            request_schema={"type": "object"},
            tags=["locks"],
        )
        assert ep.auth_required
        assert "locks" in ep.tags


class TestServiceDescriptor:
    def test_http_service(self) -> None:
        svc = ServiceDescriptor(
            name="api",
            type="http",
            base_url="http://localhost:8081",
            endpoints=[EndpointDescriptor(path="/health")],
        )
        assert svc.type == "http"
        assert len(svc.endpoints) == 1

    def test_mcp_service(self) -> None:
        svc = ServiceDescriptor(
            name="mcp",
            type="mcp",
            transport="sse",
            mcp_url="http://localhost:8082/sse",
            tools=[ToolDescriptor(name="acquire_lock")],
        )
        assert svc.type == "mcp"
        assert svc.tools[0].name == "acquire_lock"

    def test_cli_service(self) -> None:
        svc = ServiceDescriptor(
            name="cli",
            type="cli",
            command="coordination-cli",
            json_flag="--output-format json",
            commands=[CommandDescriptor(name="lock", subcommands=["acquire", "release"])],
        )
        assert svc.commands[0].subcommands == ["acquire", "release"]


class TestStateVerifier:
    def test_postgres(self) -> None:
        sv = StateVerifier(
            name="pg",
            type="postgres",
            dsn_env="DATABASE_URL",
            tables=["file_locks"],
        )
        assert sv.type == "postgres"
        assert "file_locks" in sv.tables


class TestStartupConfig:
    def test_required_fields(self) -> None:
        sc = StartupConfig(
            command="docker-compose up -d",
            health_check="http://localhost:8081/health",
            teardown="docker-compose down -v",
        )
        assert sc.health_timeout_seconds == 60
        assert sc.seed_command is None

    def test_with_seed(self) -> None:
        sc = StartupConfig(
            command="docker-compose up -d",
            health_check="http://localhost:8081/health",
            teardown="docker-compose down -v",
            seed_command="python seed.py",
        )
        assert sc.seed_command == "python seed.py"


class TestInterfaceDescriptor:
    def test_all_interfaces(self, sample_descriptor: InterfaceDescriptor) -> None:
        interfaces = sample_descriptor.all_interfaces()
        assert "POST /locks/acquire" in interfaces
        assert "POST /locks/release" in interfaces
        assert "GET /health" in interfaces
        assert "mcp:acquire_lock" in interfaces
        assert "mcp:release_lock" in interfaces
        assert "cli:lock" in interfaces

    def test_total_interface_count(self, sample_descriptor: InterfaceDescriptor) -> None:
        assert sample_descriptor.total_interface_count() == 6  # 3 HTTP + 2 MCP + 1 CLI

    def test_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "project": "test-project",
            "version": "1.0",
            "services": [
                {
                    "name": "api",
                    "type": "http",
                    "base_url": "http://localhost:8080",
                    "endpoints": [
                        {"path": "/health", "method": "GET"},
                    ],
                }
            ],
            "startup": {
                "command": "docker-compose up -d",
                "health_check": "http://localhost:8080/health",
                "teardown": "docker-compose down -v",
            },
        }
        yaml_path = tmp_path / "descriptor.yaml"
        yaml_path.write_text(yaml.dump(data))
        desc = InterfaceDescriptor.from_yaml(yaml_path)
        assert desc.project == "test-project"
        assert len(desc.services) == 1
        assert desc.services[0].endpoints[0].path == "/health"

    def test_file_interface_mapping(self) -> None:
        mapping = FileInterfaceMapping(
            file_pattern="src/locks.py",
            interfaces=["POST /locks/acquire", "POST /locks/release", "mcp:acquire_lock"],
        )
        assert len(mapping.interfaces) == 3

    def test_browser_service_in_all_interfaces(self) -> None:
        desc = InterfaceDescriptor(
            project="browser-test",
            version="0.1",
            services=[
                ServiceDescriptor(
                    name="web-ui",
                    type="browser",
                    launch_url="http://localhost:3000",
                ),
            ],
            startup=StartupConfig(
                command="echo start",
                health_check="echo ok",
                teardown="echo stop",
            ),
        )
        interfaces = desc.all_interfaces()
        assert "browser:http://localhost:3000" in interfaces
        assert desc.total_interface_count() == 1

    def test_from_yaml_empty_file(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        import pytest as _pytest

        with _pytest.raises(ValueError, match="Expected YAML mapping"):
            InterfaceDescriptor.from_yaml(yaml_path)

    def test_from_yaml_non_dict(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "list.yaml"
        yaml_path.write_text("- item1\n- item2\n")
        import pytest as _pytest

        with _pytest.raises(ValueError, match="Expected YAML mapping"):
            InterfaceDescriptor.from_yaml(yaml_path)

    def test_empty_services(self) -> None:
        desc = InterfaceDescriptor(
            project="empty",
            version="0.1",
            services=[],
            startup=StartupConfig(
                command="echo start",
                health_check="echo ok",
                teardown="echo stop",
            ),
        )
        assert desc.total_interface_count() == 0
        assert desc.all_interfaces() == []
