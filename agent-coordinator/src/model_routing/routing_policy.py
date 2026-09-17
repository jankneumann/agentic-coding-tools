"""Strict, versioned routing policy loader and deterministic rule evaluator."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Location = Literal["local", "cloud", "unknown"]
Isolation = Literal["none", "worktree", "sandbox"]
DispatchMode = Literal["review", "alternative", "quick", "sdk"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleWhen(_StrictModel):
    phase: str | None = None
    archetype: str | None = None
    scope: Literal["read-only", "bounded-write", "broad-write"] | None = None
    interactivity: Literal["interactive", "headless"] | None = None
    secret_need: Literal["none", "brokered", "direct"] | None = None
    min_duration_seconds: int | None = Field(default=None, ge=0)
    max_duration_seconds: int | None = Field(default=None, ge=0)
    min_parallelism: int | None = Field(default=None, ge=1)
    max_parallelism: int | None = Field(default=None, ge=1)
    repo_shape: Literal["single-package", "monorepo", "unknown"] | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> RuleWhen:
        if not self.model_fields_set:
            raise ValueError("routing rule predicate must not be empty")
        if (
            self.min_duration_seconds is not None
            and self.max_duration_seconds is not None
            and self.min_duration_seconds > self.max_duration_seconds
        ):
            raise ValueError("minimum duration exceeds maximum duration")
        if (
            self.min_parallelism is not None
            and self.max_parallelism is not None
            and self.min_parallelism > self.max_parallelism
        ):
            raise ValueError("minimum parallelism exceeds maximum parallelism")
        return self


class RuleConstraint(_StrictModel):
    location: Location | None = None
    isolation: Isolation | None = None
    dispatch_mode: DispatchMode | None = None

    @model_validator(mode="after")
    def validate_nonempty(self) -> RuleConstraint:
        if not self.model_fields_set:
            raise ValueError("routing rule constraint must not be empty")
        return self


class RoutingRule(_StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    when: RuleWhen
    constrain: RuleConstraint


class PolicyDefaults(_StrictModel):
    dispatch_mode: DispatchMode
    phase_dispatch_modes: dict[str, DispatchMode]


class FallbackOrder(_StrictModel):
    location_order: list[Location] = Field(min_length=1)
    isolation_order: list[Isolation] = Field(min_length=1)
    dispatch_mode_order: list[DispatchMode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique(self) -> FallbackOrder:
        for field_name in (
            "location_order",
            "isolation_order",
            "dispatch_mode_order",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate value in fallback {field_name}")
        return self


class RoutingPolicyDocument(_StrictModel):
    schema_version: Literal[1]
    policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,63}$")
    defaults: PolicyDefaults
    rules: list[RoutingRule]
    fallback: FallbackOrder


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    location: Location | None
    isolation: Isolation | None
    dispatch_mode: DispatchMode
    rule_dispatch_mode: DispatchMode | None
    matched_rule_ids: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    document: RoutingPolicyDocument
    checksum: str

    @property
    def version(self) -> str:
        return self.document.policy_version

    def evaluate(self, profile: dict[str, Any]) -> PolicyEvaluation:
        dimensions: dict[str, str | None] = {
            "location": None,
            "isolation": None,
            "dispatch_mode": None,
        }
        matched: list[str] = []
        rationale: list[str] = []
        for rule in self.document.rules:
            if not _matches(rule.when, profile):
                continue
            applied = False
            for dimension in dimensions:
                value = getattr(rule.constrain, dimension)
                if value is not None and dimensions[dimension] is None:
                    dimensions[dimension] = value
                    applied = True
                    rationale.append(f"rule:{rule.id}:{dimension}={value}")
            if applied:
                matched.append(rule.id)

        dispatch_mode = dimensions["dispatch_mode"]
        if dispatch_mode is None:
            phase = profile.get("phase")
            dispatch_mode = self.document.defaults.phase_dispatch_modes.get(
                str(phase), self.document.defaults.dispatch_mode
            )
            rationale.append(f"default:dispatch_mode={dispatch_mode}")
        return PolicyEvaluation(
            location=dimensions["location"],  # type: ignore[arg-type]
            isolation=dimensions["isolation"],  # type: ignore[arg-type]
            dispatch_mode=dispatch_mode,  # type: ignore[arg-type]
            rule_dispatch_mode=dimensions["dispatch_mode"],  # type: ignore[arg-type]
            matched_rule_ids=tuple(matched),
            rationale=tuple(rationale),
        )


def _matches(predicate: RuleWhen, profile: dict[str, Any]) -> bool:
    direct_fields = (
        "phase",
        "archetype",
        "scope",
        "interactivity",
        "secret_need",
        "repo_shape",
    )
    if any(
        expected is not None and profile.get(name) != expected
        for name in direct_fields
        if (expected := getattr(predicate, name)) is not None
    ):
        return False
    duration = profile.get("expected_duration_seconds")
    parallelism = profile.get("parallelism")
    return (
        _within(duration, predicate.min_duration_seconds, predicate.max_duration_seconds)
        and _within(parallelism, predicate.min_parallelism, predicate.max_parallelism)
    )


def _within(value: Any, minimum: int | None, maximum: int | None) -> bool:
    if minimum is None and maximum is None:
        return True
    if not isinstance(value, int):
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def _default_policy_path() -> Path:
    configured = os.environ.get("ROUTING_CONFIG")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "routing.yaml"


def load_routing_policy(
    path: Path | None = None,
    *,
    configured_phases: set[str] | None = None,
) -> RoutingPolicy:
    policy_path = path or _default_policy_path()
    raw_bytes = policy_path.read_bytes()
    raw = yaml.safe_load(raw_bytes)
    if not isinstance(raw, dict):
        raise ValueError("routing policy must be an object")
    document = RoutingPolicyDocument.model_validate(raw)
    rule_ids = [rule.id for rule in document.rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("duplicate routing rule id")
    if configured_phases is None:
        from ..agents_config import get_phase_mapping

        configured_phases = set(get_phase_mapping())
    unknown = set(document.defaults.phase_dispatch_modes) - configured_phases
    if unknown:
        raise ValueError(f"unconfigured phase dispatch default: {sorted(unknown)[0]}")
    return RoutingPolicy(
        document=document,
        checksum=hashlib.sha256(raw_bytes).hexdigest(),
    )
