"""Generator-Evaluator testing framework.

A general-purpose framework for testing software interfaces using
the generator-evaluator pattern. Generators produce test scenarios
(from templates or LLM), evaluators execute them against live services
and produce structured verdicts.

Supports HTTP APIs, MCP tools, CLI commands, and database state
verification through pluggable transport clients.
"""

from typing import Any

from .change_detector import ChangeDetector
from .config import BudgetConfig, BudgetTracker, GenEvalConfig, SDKBudget, TimeBudget
from .descriptor import (
    CommandSpec,
    EndpointSpec,
    InterfaceDescriptor,
    McpToolSpec,
    ServiceSpec,
    StartupConfig,
    StateVerifier,
)
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
    "CommandSpec",
    "EndpointSpec",
    "EvalFeedback",
    "ExpectBlock",
    "FeedbackSynthesizer",
    "GenEvalConfig",
    "InterfaceDescriptor",
    "ManifestEntry",
    "McpToolSpec",
    "SDKBudget",
    "Scenario",
    "ScenarioGenerator",
    "ScenarioPackManifest",
    "ScenarioVerdict",
    "SemanticBlock",
    "SemanticVerdict",
    "ServiceSpec",
    "SideEffectsBlock",
    "SideEffectStep",
    "SideEffectVerdict",
    "StartupConfig",
    "StateVerifier",
    "StepVerdict",
    "TimeBudget",
]

# The pre-rename names stay importable from the package for one release, but
# deliberately leave ``__all__``: ``from gen_eval import *`` should hand a new
# consumer only names that are not on their way out.
#
# Resolution is delegated to ``descriptor.__getattr__`` rather than duplicated
# here, so there is exactly one warning per access and one place that owns the
# message.
from .descriptor import _DEPRECATED_ALIASES as _DEPRECATED_ALIASES  # noqa: E402


def __getattr__(name: str) -> Any:
    if name in _DEPRECATED_ALIASES:
        from . import descriptor

        return getattr(descriptor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

