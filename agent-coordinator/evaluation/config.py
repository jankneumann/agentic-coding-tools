"""Evaluation configuration for benchmarking runs.

Defines all configuration needed to run an evaluation:
task selection, agent backends, ablation flags, and trial count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class TaskTier(Enum):
    """Task complexity tiers for evaluation."""

    TIER1 = 1  # Isolated, single-file tasks
    TIER2 = 2  # Parallelizable, multi-file tasks
    TIER3 = 3  # Coordinated, dependent tasks


class TaskSource(Enum):
    """Where tasks originate from."""

    CURATED = "curated"
    SWEBENCH = "swebench"
    CONTEXTBENCH = "contextbench"
    MARBLE = "marble"


@dataclass
class AblationFlags:
    """Toggle coordination mechanisms for ablation studies.

    Each flag controls whether a coordination mechanism is active.
    When OFF, the mechanism is bypassed to measure its contribution.
    """

    locking: bool = True
    memory: bool = True
    handoffs: bool = True
    parallelization: bool = True
    work_queue: bool = True
    # Phase 3 safety mechanisms
    guardrails: bool = True
    profiles: bool = True
    audit: bool = True
    network_policies: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "locking": self.locking,
            "memory": self.memory,
            "handoffs": self.handoffs,
            "parallelization": self.parallelization,
            "work_queue": self.work_queue,
            "guardrails": self.guardrails,
            "profiles": self.profiles,
            "audit": self.audit,
            "network_policies": self.network_policies,
        }

    @classmethod
    def all_on(cls) -> AblationFlags:
        return cls()

    @classmethod
    def all_off(cls) -> AblationFlags:
        return cls(
            locking=False,
            memory=False,
            handoffs=False,
            parallelization=False,
            work_queue=False,
            guardrails=False,
            profiles=False,
            audit=False,
            network_policies=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, bool]) -> AblationFlags:
        return cls(
            locking=data.get("locking", True),
            memory=data.get("memory", True),
            handoffs=data.get("handoffs", True),
            parallelization=data.get("parallelization", True),
            work_queue=data.get("work_queue", True),
            guardrails=data.get("guardrails", True),
            profiles=data.get("profiles", True),
            audit=data.get("audit", True),
            network_policies=data.get("network_policies", True),
        )

    def label(self) -> str:
        """Human-readable label for this configuration."""
        if all(self.as_dict().values()):
            return "all-on"
        if not any(self.as_dict().values()):
            return "all-off"
        on_flags = [k for k, v in self.as_dict().items() if v]
        return "only-" + "+".join(on_flags)


@dataclass
class AgentBackendConfig:
    """Configuration for an agent backend."""

    name: str  # e.g. "claude_code", "codex", "gemini_jules"
    command: str  # CLI command to invoke
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentBackendConfig:
        return cls(
            name=data["name"],
            command=data["command"],
            args=data.get("args", []),
            env=data.get("env", {}),
            timeout_seconds=data.get("timeout_seconds", 300),
        )


@dataclass
class EvalConfig:
    """Complete configuration for an evaluation run.

    Controls task selection, agent backends, ablation flags,
    and trial parameters.
    """

    # Task selection
    tiers: list[TaskTier] = field(default_factory=lambda: [TaskTier.TIER1])
    task_ids: list[str] | None = None  # Specific tasks (overrides tier filter)
    max_tasks: int | None = None  # Limit total tasks (for cost control)
    task_source: TaskSource = TaskSource.CURATED

    # Agent backends to evaluate
    backends: list[AgentBackendConfig] = field(default_factory=list)

    # Ablation configurations to run
    ablation_configs: list[AblationFlags] = field(
        default_factory=lambda: [AblationFlags.all_on()]
    )

    # Trial parameters
    num_trials: int = 3
    temperature: float = 0.0  # For reproducibility

    # Evaluation options
    enable_consensus_eval: bool = False  # Multi-LLM qualitative assessment
    consensus_judges: list[str] = field(
        default_factory=lambda: ["claude-sonnet-4-5-20250929", "gpt-4o"]
    )

    # Output
    output_dir: Path = field(default_factory=lambda: Path("evaluation/reports"))
    run_id: str | None = None  # Auto-generated if not provided

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvalConfig:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalConfig:
        tiers = [TaskTier(t) for t in data.get("tiers", [1])]

        backends = [
            AgentBackendConfig.from_dict(b) for b in data.get("backends", [])
        ]

        ablation_configs = []
        for ac in data.get("ablation_configs", [{}]):
            ablation_configs.append(AblationFlags.from_dict(ac))

        output_dir = Path(data.get("output_dir", "evaluation/reports"))

        return cls(
            tiers=tiers,
            task_ids=data.get("task_ids"),
            max_tasks=data.get("max_tasks"),
            task_source=TaskSource(data.get("task_source", "curated")),
            backends=backends,
            ablation_configs=ablation_configs,
            num_trials=data.get("num_trials", 3),
            temperature=data.get("temperature", 0.0),
            enable_consensus_eval=data.get("enable_consensus_eval", False),
            consensus_judges=data.get(
                "consensus_judges", ["claude-sonnet-4-5-20250929", "gpt-4o"]
            ),
            output_dir=output_dir,
            run_id=data.get("run_id"),
        )
