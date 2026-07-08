"""Agent trajectory scenario harness.

Where ``gen-eval`` validates a deployed *service* via fixed transport-level step
sequences, ``agent-scenarios`` validates the *agents themselves*: run a skill
headless against a fixture repo (per vendor), score whether the agent achieved
the goal deterministically (files/branch/commit/PR/artifacts + prohibited side
effects — reusing gen-eval's ``ExpectBlock`` and the ``verify``/``prohibit``
split), and layer an injectable LLM-judge trajectory review on top.
"""

from .executor import (
    CLIVendorExecutor,
    FakeExecutor,
    Outcome,
    ScenarioExecutor,
    materialize_fixture,
)
from .findings_emitter import build_findings, emit_findings
from .judge import TrajectoryJudgeBackend, review_trajectory
from .loader import ScenarioLoadError, load_scenario, load_scenarios
from .models import (
    AgentScenario,
    ExpectBlock,
    FixtureSpec,
    GateVerdict,
    GoalGate,
    GoalGatesBlock,
    ParityMatrix,
    PRRef,
    RunResult,
    TrajectoryFinding,
    TrajectoryVerdict,
    VendorRunVerdict,
    WorkspaceState,
)
from .runner import run_scenario, run_scenarios
from .scorer import deterministic_status, score_gate, score_gates

__all__ = [
    "AgentScenario",
    "CLIVendorExecutor",
    "ExpectBlock",
    "FakeExecutor",
    "FixtureSpec",
    "GateVerdict",
    "GoalGate",
    "GoalGatesBlock",
    "Outcome",
    "PRRef",
    "ParityMatrix",
    "RunResult",
    "ScenarioExecutor",
    "ScenarioLoadError",
    "TrajectoryFinding",
    "TrajectoryJudgeBackend",
    "TrajectoryVerdict",
    "VendorRunVerdict",
    "WorkspaceState",
    "build_findings",
    "deterministic_status",
    "emit_findings",
    "load_scenario",
    "load_scenarios",
    "materialize_fixture",
    "review_trajectory",
    "run_scenario",
    "run_scenarios",
    "score_gate",
    "score_gates",
]
