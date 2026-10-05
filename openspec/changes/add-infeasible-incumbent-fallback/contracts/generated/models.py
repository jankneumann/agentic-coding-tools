"""Pydantic models for the v1.4 overlay (contracts/openapi/v1.4.yaml).

The v1.3 models of split-no-evidence-retention-reason plus `incumbent-infeasible-configured-fallback`
and the optional `Retention.fallback` record (add-infeasible-incumbent-fallback D6).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RetentionReason = Literal[
    "challenger-evidenced-above-margin",
    "no-evidence",
    "no-evidenced-challenger",
    "below-margin",
    "incumbent-unresolved",
    "incumbent-infeasible-evidenced-alternative",
    "incumbent-infeasible-configured-fallback",
    "incumbent-infeasible-no-evidenced-alternative",
    "exploration-evidenced",
]


class Incumbent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor: str | None = Field(default=None, max_length=128)
    model: str = Field(min_length=1, max_length=256)


TransientExclusionReason = Literal[
    "lane:unavailable",
    "unavailable",
    "quota:exhausted",
    "lane:model-rate-limited",
]


class FallbackOrderApplied(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_order: list[str] = Field(min_length=1)
    location_order: list[str] | None = None
    isolation_order: list[str] | None = None
    dispatch_mode_order: list[str] | None = None


class RetentionFallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incumbent_exclusion_reason: TransientExclusionReason
    order_applied: FallbackOrderApplied


class Retention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retained: bool
    reason: RetentionReason
    margin: float = Field(ge=0)
    incumbent_score: float | None = None
    fallback: RetentionFallback | None = None
