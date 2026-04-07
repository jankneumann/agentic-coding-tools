"""Generator-Evaluator testing framework.

A general-purpose framework for testing software interfaces using
the generator-evaluator pattern. Generators produce test scenarios
(from templates or LLM), evaluators execute them against live services
and produce structured verdicts.

Supports HTTP APIs, MCP tools, CLI commands, and database state
verification through pluggable transport clients.
"""

from .change_detector import ChangeDetector
from .config import BudgetConfig, BudgetTracker, GenEvalConfig, SDKBudget, TimeBudget
from .descriptor import InterfaceDescriptor, ServiceDescriptor, StartupConfig, StateVerifier
from .feedback import FeedbackSynthesizer
from .models import (
    ActionStep,
    EvalFeedback,
    ExpectBlock,
    ManifestEntry,
    Scenario,
    ScenarioGenerator,
    ScenarioPackManifest,
    ScenarioVerdict,
    StepVerdict,
)

__all__ = [
    "ActionStep",
    "BudgetConfig",
    "BudgetTracker",
    "ChangeDetector",
    "EvalFeedback",
    "ExpectBlock",
    "FeedbackSynthesizer",
    "GenEvalConfig",
    "InterfaceDescriptor",
    "ManifestEntry",
    "SDKBudget",
    "Scenario",
    "ScenarioGenerator",
    "ScenarioPackManifest",
    "ScenarioVerdict",
    "ServiceDescriptor",
    "StartupConfig",
    "StateVerifier",
    "StepVerdict",
    "TimeBudget",
]

