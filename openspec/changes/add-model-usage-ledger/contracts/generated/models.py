"""Pydantic models for the usage ledger contract.

Generated stub for task 1.4 of add-model-usage-ledger. Hand-written to match
contracts/openapi/v1.yaml; regenerate from the OpenAPI file if the schemas change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UsageRecord(BaseModel):
    ts: datetime
    vendor: str
    model: str
    effort: str | None = None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    thinking_tokens: int | None = None
    vendor_cost_usd: float | None = None
    session_id: str
    agent_id: str | None = None
    parent_session_id: str | None = None
    project: str | None = None
    principal: str | None = None
    host: str | None = None
    git_branch: str | None = None
    message_id: str | None = None
    record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class TranscriptEvent(BaseModel):
    ts: datetime
    vendor: str
    session_id: str
    agent_id: str | None = None
    parent_session_id: str | None = None
    event_type: Literal["user", "assistant", "tool_call", "tool_result", "system"]
    schema_version: str
    event: dict[str, Any]
    event_hash: str


class IngestCursor(BaseModel):
    file_path: str
    vendor: str
    last_mtime: float
    line_offset: int = Field(ge=0)


class IngestBatch(BaseModel):
    host: str
    sanitized: bool
    records: list[UsageRecord]
    events: list[TranscriptEvent] = Field(default_factory=list)
    cursors: list[IngestCursor] = Field(default_factory=list)


class IngestResult(BaseModel):
    inserted_records: int
    duplicate_records: int
    inserted_events: int
    unpriced_records: int
    pricing_version: str


class DispatchRecordUpsert(BaseModel):
    dispatch_id: str
    change_id: str | None = None
    phase: str | None = None
    archetype: str | None = None
    intended_tier: str | None = None
    intended_model: str | None = None
    intended_thinking: str | None = None
    provider: str | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    override_source: Literal["env", "config"] | None = None
    session_id: str | None = None
    agent_id: str | None = None
    transcript_path: str | None = None
    completed_at: datetime | None = None


class DispatchRecord(DispatchRecordUpsert):
    dispatched_at: datetime
    created_at: datetime
    updated_at: datetime


class TokenTotals(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float | None = None
    vendor_cost_usd: float | None = None
    unpriced_records: int = 0
    pricing_version: str
    estimated: Literal[True] = True


class ModelUsageRow(TokenTotals):
    vendor: str
    model: str
    records: int


class VendorUsageRow(TokenTotals):
    vendor: str


class UsageSummary(BaseModel):
    total: TokenTotals
    by_vendor: list[VendorUsageRow]
    by_model: list[ModelUsageRow]


class PhaseUsageRow(TokenTotals):
    change_id: str
    phase: str
    dispatch_id: str
    archetype: str | None = None
    intended_model: str
    intended_thinking: str | None = None
    override_source: str | None = None
    actual_models: list[str]
    actual_efforts: list[str]
    model_mismatch: bool
    thinking_mismatch: bool
    unattributed: bool
