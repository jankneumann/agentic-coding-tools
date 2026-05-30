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
from .manifest import ManifestEntry, ScenarioPackManifest
from .models import (
    ActionStep,
    EvalFeedback,
    ExpectBlock,
    Scenario,
    ScenarioGenerator,
    ScenarioVerdict,
    SemanticBlock,
    SemanticVerdict,
    SideEffectsBlock,
    SideEffectStep,
    SideEffectVerdict,
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
    "SemanticBlock",
    "SemanticVerdict",
    "ServiceDescriptor",
    "SideEffectsBlock",
    "SideEffectStep",
    "SideEffectVerdict",
    "StartupConfig",
    "StateVerifier",
    "StepVerdict",
    "TimeBudget",
]

