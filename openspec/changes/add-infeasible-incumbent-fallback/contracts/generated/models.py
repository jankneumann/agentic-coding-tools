"""Pydantic models for the v1.4 overlay (contracts/openapi/v1.4.yaml).

The v1.3 models of split-no-evidence-retention-reason plus `incumbent-infeasible-configured-fallback`
and the optional `Retention.fallback` record (add-infeasible-incumbent-fallback D6).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """Verbatim copy of the routing policy's `fallback:` block as applied (design D6)."""

    model_config = ConfigDict(extra="forbid")

    vendor_order: list[str] = Field(min_length=1)
    location_order: list[str] = Field(min_length=1)
    isolation_order: list[str] = Field(min_length=1)
    dispatch_mode_order: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _lists_unique(self) -> "FallbackOrderApplied":
        for name in ("vendor_order", "location_order", "isolation_order", "dispatch_mode_order"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"order_applied.{name} must not contain duplicates")
        return self


class RetentionFallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Unique reasons of the incumbent's excluded rows; all transient (design D3). Sorting is
    # a producer invariant (asserted by the service-level test), not a wire-validation rule:
    # JSON Schema cannot express it, so the three contracts agree on uniqueness only.
    incumbent_exclusion_reasons: list[TransientExclusionReason] = Field(min_length=1)
    order_applied: FallbackOrderApplied

    @model_validator(mode="after")
    def _reasons_unique(self) -> "RetentionFallback":
        if len(self.incumbent_exclusion_reasons) != len(set(self.incumbent_exclusion_reasons)):
            raise ValueError("incumbent_exclusion_reasons must be unique")
        return self


KEPT_REASONS: frozenset[str] = frozenset(
    {
        "no-evidence",
        "no-evidenced-challenger",
        "below-margin",
        "incumbent-unresolved",
        "incumbent-infeasible-no-evidenced-alternative",
    }
)


class Retention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retained: bool
    reason: RetentionReason
    margin: float = Field(ge=0)
    incumbent_score: float | None = None
    # Required when reason is incumbent-infeasible-configured-fallback, forbidden otherwise.
    # Omit the key rather than sending null: the wire schemas type it as object.
    fallback: RetentionFallback | None = None

    @model_validator(mode="after")
    def _retained_matches_reason(self) -> "Retention":
        expected = self.reason in KEPT_REASONS
        if self.retained != expected:
            raise ValueError(f"retained must be {expected} for reason {self.reason}")
        return self

    @model_validator(mode="after")
    def _fallback_presence(self) -> "Retention":
        configured = self.reason == "incumbent-infeasible-configured-fallback"
        if configured and self.fallback is None:
            raise ValueError("retention.fallback is required for incumbent-infeasible-configured-fallback")
        if not configured and ("fallback" in self.model_fields_set):
            raise ValueError("retention.fallback is only allowed for incumbent-infeasible-configured-fallback")
        return self
