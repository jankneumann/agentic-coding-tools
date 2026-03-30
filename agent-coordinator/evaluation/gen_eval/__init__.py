"""Generator-Evaluator testing framework.

A general-purpose framework for testing software interfaces using
the generator-evaluator pattern. Generators produce test scenarios
(from templates or LLM), evaluators execute them against live services
and produce structured verdicts.

Supports HTTP APIs, MCP tools, CLI commands, and database state
verification through pluggable transport clients.
"""

from .config import BudgetConfig, BudgetTracker, GenEvalConfig, SDKBudget, TimeBudget
from .descriptor import InterfaceDescriptor, ServiceDescriptor, StartupConfig, StateVerifier
from .models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    ScenarioGenerator,
    ScenarioVerdict,
    StepVerdict,
)

__all__ = [
    "ActionStep",
    "BudgetConfig",
    "BudgetTracker",
    "ExpectBlock",
    "GenEvalConfig",
    "InterfaceDescriptor",
    "SDKBudget",
    "Scenario",
    "ScenarioGenerator",
    "ScenarioVerdict",
    "ServiceDescriptor",
    "StartupConfig",
    "StateVerifier",
    "StepVerdict",
    "TimeBudget",
]
