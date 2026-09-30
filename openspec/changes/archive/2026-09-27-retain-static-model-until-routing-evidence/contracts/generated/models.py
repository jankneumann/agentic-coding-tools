"""Pydantic models for the v1.2 incumbent-retention overlay (contracts/openapi/v1.2.yaml).

Additive over the v1.1 models of implement-the-task-router-vendor-x-location-x-model:
only the new and changed shapes are declared here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RetentionReason = Literal[
    "challenger-evidenced-above-margin",
    "no-evidence",
    "below-margin",
    "incumbent-unresolved",
    "incumbent-infeasible-evidenced-alternative",
    "incumbent-infeasible-no-evidenced-alternative",
    "exploration-evidenced",
]


class Incumbent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor: str | None = Field(default=None, max_length=128)
    model: str = Field(min_length=1, max_length=256)


class Retention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retained: bool
    reason: RetentionReason
    margin: float = Field(ge=0)
    incumbent_score: float | None = None
