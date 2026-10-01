"""Pydantic models for the v1.3 overlay (contracts/openapi/v1.3.yaml).

Identical to the v1.2 models of retain-static-model-until-routing-evidence except that
`RetentionReason` adds `no-evidenced-challenger` (split-no-evidence-retention-reason D3).
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
