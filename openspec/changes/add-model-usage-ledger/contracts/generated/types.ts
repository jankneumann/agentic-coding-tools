// TypeScript interfaces for the usage ledger contract (apps/usage-viz).
// Generated stub for task 1.4 of add-model-usage-ledger; regenerate from
// contracts/openapi/v1.yaml if the schemas change.

export interface TokenTotals {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  thinking_tokens: number;
  cost_usd: number | null;
  vendor_cost_usd: number | null;
  unpriced_records: number;
  pricing_version: string;
  estimated: true;
}

export interface ModelUsageRow extends TokenTotals {
  vendor: string;
  model: string;
  records: number;
}

export interface VendorUsageRow extends TokenTotals {
  vendor: string;
}

export interface UsageSummary {
  total: TokenTotals;
  by_vendor: VendorUsageRow[];
  by_model: ModelUsageRow[];
}

export interface PhaseUsageRow extends TokenTotals {
  change_id: string;
  phase: string;
  dispatch_id: string;
  archetype: string | null;
  intended_model: string;
  intended_thinking: string | null;
  override_source: "env" | "config" | null;
  actual_models: string[];
  actual_efforts: string[];
  model_mismatch: boolean;
  thinking_mismatch: boolean;
  unattributed: boolean;
}

export interface TranscriptEvent {
  ts: string;
  vendor: string;
  session_id: string;
  agent_id: string | null;
  parent_session_id: string | null;
  event_type: "user" | "assistant" | "tool_call" | "tool_result" | "system";
  schema_version: string;
  event: Record<string, unknown>;
  event_hash: string;
}

export interface EventsPage {
  events: TranscriptEvent[];
  next_cursor: string | null;
}
