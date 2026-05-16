"""Provider-neutral autopilot phase dispatch adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class PhaseDispatchPayload:
    schema_version: int
    change_id: str
    phase: str
    provider: str
    archetype: str | None
    model: str | None
    prompt: str
    system_prompt: str | None
    isolation: str | None
    expected_outcomes: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhaseDispatchPayload":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            change_id=str(data["change_id"]),
            phase=str(data["phase"]),
            provider=str(data["provider"]),
            archetype=data.get("archetype"),
            model=data.get("model"),
            prompt=str(data["prompt"]),
            system_prompt=data.get("system_prompt"),
            isolation=data.get("isolation"),
            expected_outcomes=list(data.get("expected_outcomes") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PhaseDispatchResult:
    schema_version: int = 1
    outcome: str = "failed"
    handoff_id: str = ""
    provider: str = ""
    model_used: str | None = None
    dispatch_tier: str = "fallback"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProviderRunner = Callable[[PhaseDispatchPayload], Any]

_SUPPORTED_PROVIDERS = {"claude_code", "codex", "gemini"}
_CLAUDE_ALIASES = {"opus", "sonnet", "haiku"}


def normalize_dispatch_result(
    raw: Any,
    payload: PhaseDispatchPayload,
    dispatch_tier: str,
) -> PhaseDispatchResult:
    """Normalize tuple/dict adapter output into the contract result shape."""
    warnings: list[str] = []
    outcome: str | None = None
    handoff_id: str | None = None
    model_used = payload.model

    if isinstance(raw, tuple) and len(raw) == 2:
        outcome, handoff_id = raw
    elif isinstance(raw, dict):
        outcome = raw.get("outcome")
        handoff_id = raw.get("handoff_id")
        model_used = raw.get("model_used", model_used)
        raw_warnings = raw.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(item) for item in raw_warnings]

    if not isinstance(outcome, str) or not outcome:
        outcome = "failed"
        warnings.append("adapter returned missing outcome")
    if not isinstance(handoff_id, str) or not handoff_id:
        digest = hashlib.sha256(
            json.dumps(payload.to_dict(), sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        handoff_id = f"{dispatch_tier}:{payload.provider}:{payload.phase}:{digest}"
        warnings.append("adapter returned missing handoff_id")

    return PhaseDispatchResult(
        outcome=outcome,
        handoff_id=handoff_id,
        provider=payload.provider,
        model_used=model_used,
        dispatch_tier=dispatch_tier,
        warnings=warnings,
    )


def _dry_run_result(payload: PhaseDispatchPayload) -> PhaseDispatchResult:
    if payload.provider != "claude_code" and payload.model in _CLAUDE_ALIASES:
        return PhaseDispatchResult(
            outcome="failed",
            handoff_id=f"dry-run:{payload.provider}:{payload.phase}:invalid-model",
            provider=payload.provider,
            model_used=payload.model,
            dispatch_tier="dry_run",
            warnings=[
                f"Claude alias {payload.model!r} is not valid for provider {payload.provider!r}",
            ],
        )
    outcome = "complete"
    if payload.expected_outcomes and outcome not in payload.expected_outcomes:
        outcome = payload.expected_outcomes[0]
    digest = hashlib.sha256(
        f"{payload.provider}:{payload.phase}:{payload.model}".encode("utf-8")
    ).hexdigest()[:12]
    return PhaseDispatchResult(
        outcome=outcome,
        handoff_id=f"dry-run:{payload.provider}:{payload.phase}:{digest}",
        provider=payload.provider,
        model_used=payload.model,
        dispatch_tier="dry_run",
        warnings=[],
    )


def dispatch_phase(
    payload: PhaseDispatchPayload,
    *,
    runner: ProviderRunner | None = None,
    dry_run: bool = False,
) -> PhaseDispatchResult:
    """Dispatch a phase payload through a provider adapter.

    Production harnesses can pass *runner* to invoke their provider-specific
    execution surface. Without a runner, unsupported/nonconfigured adapters
    return a structured fallback result so the SKILL.md layer can continue
    through inline execution.
    """
    if dry_run:
        return _dry_run_result(payload)
    if payload.provider not in _SUPPORTED_PROVIDERS:
        return PhaseDispatchResult(
            outcome="failed",
            handoff_id=f"fallback:{payload.provider}:{payload.phase}",
            provider=payload.provider,
            model_used=payload.model,
            dispatch_tier="fallback",
            warnings=[f"adapter unavailable for provider {payload.provider!r}"],
        )
    if runner is None:
        return PhaseDispatchResult(
            outcome="failed",
            handoff_id=f"fallback:{payload.provider}:{payload.phase}",
            provider=payload.provider,
            model_used=payload.model,
            dispatch_tier="fallback",
            warnings=[
                f"adapter unavailable for provider {payload.provider!r} in this runtime",
            ],
        )
    return normalize_dispatch_result(runner(payload), payload, "harness")
