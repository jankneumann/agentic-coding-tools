"""Tests for vendor health check."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vendor_health import (
    HealthReport,
    VendorHealth,
    check_all_vendors,
    check_vendor,
    format_table,
)


class TestCheckVendor:
    def test_cli_installed(self):
        config = {
            "type": "claude_code",
            "cli": {
                "command": "python3",  # python3 should be available
                "dispatch_modes": {"review": {"args": ["--print"]}},
                "model": "test-model",
            },
        }
        health = check_vendor("test-agent", config)
        assert health.cli_installed is True
        assert health.agent_id == "test-agent"
        assert "review" in health.dispatch_modes

    def test_cli_not_installed(self):
        config = {
            "type": "codex",
            "cli": {
                "command": "nonexistent-cli-tool-xyz",
                "dispatch_modes": {"review": {"args": []}},
            },
        }
        health = check_vendor("missing-agent", config)
        assert health.cli_installed is False
        assert health.dispatch_modes == []
        assert health.healthy is False

    def test_api_key_from_env(self):
        config = {
            "type": "claude_code",
            "cli": {"command": "nonexistent-xyz", "dispatch_modes": {}},
            "sdk": {"api_key_env": "TEST_VENDOR_HEALTH_KEY"},
        }
        with patch.dict("os.environ", {"TEST_VENDOR_HEALTH_KEY": "sk-test"}):
            health = check_vendor("sdk-agent", config)
            assert health.api_key_available is True
            assert health.healthy is True  # API key alone is enough

    def test_no_api_key(self):
        config = {
            "type": "codex",
            "cli": {"command": "nonexistent-xyz", "dispatch_modes": {}},
            "sdk": {"api_key_env": "NONEXISTENT_KEY_XYZ"},
        }
        health = check_vendor("no-key-agent", config)
        assert health.api_key_available is False

    def test_models_collected(self):
        config = {
            "type": "codex",
            "cli": {
                "command": "nonexistent-xyz",
                "dispatch_modes": {},
                "model": "gpt-5.4",
                "model_fallbacks": ["gpt-5.3"],
            },
        }
        health = check_vendor("model-agent", config)
        assert "gpt-5.4" in health.models
        assert "gpt-5.3" in health.models


class TestCheckAllVendors:
    def test_skips_agents_without_cli(self, tmp_path):
        yaml_content = """
agents:
  agent-with-cli:
    type: test
    cli:
      command: nonexistent-xyz
      dispatch_modes: {}
  agent-without-cli:
    type: test
    capabilities: [memory]
"""
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(yaml_content)

        report = check_all_vendors(yaml_file)
        assert report.total_count == 1
        assert report.vendors[0].agent_id == "agent-with-cli"


class TestFormatTable:
    def test_table_format(self):
        report = HealthReport(
            vendors=[
                VendorHealth(
                    agent_id="claude-local",
                    vendor_type="claude_code",
                    cli_command="claude",
                    cli_installed=True,
                    api_key_available=True,
                    dispatch_modes=["review", "quick"],
                    models=["claude-sonnet-4-6"],
                    healthy=True,
                ),
                VendorHealth(
                    agent_id="codex-local",
                    vendor_type="codex",
                    cli_command="codex",
                    cli_installed=False,
                    api_key_available=False,
                    dispatch_modes=[],
                    models=[],
                    healthy=False,
                ),
            ],
            healthy_count=1,
            total_count=2,
        )
        table = format_table(report)
        assert "claude-local" in table
        assert "codex-local" in table
        assert "ok" in table
        assert "Healthy: 1/2" in table

    def test_json_output(self):
        report = HealthReport(
            vendors=[
                VendorHealth(
                    agent_id="test",
                    vendor_type="test",
                    cli_command="test",
                    healthy=True,
                ),
            ],
            healthy_count=1,
            total_count=1,
        )
        data = report.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["healthy_count"] == 1
        assert len(parsed["vendors"]) == 1
