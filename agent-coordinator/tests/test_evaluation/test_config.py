"""Tests for evaluation configuration."""

import yaml

from evaluation.config import (
    AblationFlags,
    AgentBackendConfig,
    EvalConfig,
    TaskSource,
    TaskTier,
)


class TestAblationFlags:
    def test_all_on(self):
        flags = AblationFlags.all_on()
        assert all(flags.as_dict().values())
        assert flags.label() == "all-on"

    def test_all_off(self):
        flags = AblationFlags.all_off()
        assert not any(flags.as_dict().values())
        assert flags.label() == "all-off"

    def test_partial(self):
        flags = AblationFlags(locking=True, memory=False, handoffs=False,
                              parallelization=True, work_queue=False)
        label = flags.label()
        assert "only-" in label
        assert "locking" in label
        assert "parallelization" in label

    def test_from_dict(self):
        flags = AblationFlags.from_dict({"locking": False, "memory": True})
        assert flags.locking is False
        assert flags.memory is True
        assert flags.handoffs is True  # default

    def test_as_dict_roundtrip(self):
        original = AblationFlags(locking=False, parallelization=False)
        restored = AblationFlags.from_dict(original.as_dict())
        assert restored.locking == original.locking
        assert restored.parallelization == original.parallelization


class TestAgentBackendConfig:
    def test_from_dict(self):
        data = {
            "name": "claude_code",
            "command": "claude",
            "args": ["--print"],
            "timeout_seconds": 600,
        }
        config = AgentBackendConfig.from_dict(data)
        assert config.name == "claude_code"
        assert config.command == "claude"
        assert config.args == ["--print"]
        assert config.timeout_seconds == 600

    def test_defaults(self):
        config = AgentBackendConfig.from_dict({"name": "test", "command": "echo"})
        assert config.args == []
        assert config.env == {}
        assert config.timeout_seconds == 300


class TestEvalConfig:
    def test_defaults(self):
        config = EvalConfig()
        assert config.tiers == [TaskTier.TIER1]
        assert config.num_trials == 3
        assert config.temperature == 0.0
        assert config.enable_consensus_eval is False

    def test_from_dict(self):
        data = {
            "tiers": [1, 2],
            "num_trials": 5,
            "task_source": "swebench",
            "backends": [
                {"name": "claude_code", "command": "claude"},
            ],
            "ablation_configs": [
                {"locking": True, "memory": True},
                {"locking": False, "memory": True},
            ],
        }
        config = EvalConfig.from_dict(data)
        assert config.tiers == [TaskTier.TIER1, TaskTier.TIER2]
        assert config.num_trials == 5
        assert config.task_source == TaskSource.SWEBENCH
        assert len(config.backends) == 1
        assert len(config.ablation_configs) == 2

    def test_from_yaml(self, tmp_path):
        yaml_content = {
            "tiers": [1],
            "num_trials": 2,
            "backends": [{"name": "test", "command": "echo"}],
        }
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml.dump(yaml_content))

        config = EvalConfig.from_yaml(yaml_path)
        assert config.num_trials == 2
        assert len(config.backends) == 1
