"""Generated-model stub derived from contracts/openapi/v1.yaml.

Consumed by the coordinator API routes and the collector push client. Keep in
sync with the OpenAPI schemas; regenerate rather than hand-edit once a codegen
step exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Vendor = Literal["claude", "codex", "gemini", "antigravity"]


class UsageRecord(BaseModel):
    ts: datetime
    vendor: Vendor
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None
    session_id: str
    project: str | None = None
    principal: str | None = None
    agent_id: str | None = None
    host: str | None = None
    record_hash: str


class IngestBatch(BaseModel):
    records: list[UsageRecord]


class IngestResult(BaseModel):
    submitted: int
    inserted: int
    duplicates: int


class UsageSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None
    cost_is_estimate: bool = True


class DailyBucket(BaseModel):
    day: str
    vendor: Vendor
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class GroupTotal(BaseModel):
    key: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    cost_is_estimate: bool = True
