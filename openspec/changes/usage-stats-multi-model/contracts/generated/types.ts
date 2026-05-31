// Generated-type stub derived from contracts/openapi/v1.yaml.
// Consumed by apps/usage-stats/src (useUsage hook + chart components).
// Keep in sync with the OpenAPI schemas; regenerate rather than hand-edit
// once a codegen step exists.

export type Vendor = "claude" | "codex" | "gemini" | "antigravity";

export interface UsageRecord {
  ts: string; // ISO-8601 UTC
  vendor: Vendor;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
  session_id: string;
  project: string | null;
  principal: string | null;
  agent_id: string | null;
  host: string | null;
  record_hash: string;
}

export interface UsageSummary {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
  cost_is_estimate: boolean;
}

export interface DailyBucket {
  day: string; // YYYY-MM-DD
  vendor: Vendor;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
}

export interface GroupTotal {
  key: string; // vendor or model identifier
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  cost_is_estimate: boolean;
}

export interface UsageFilters {
  vendor?: Vendor;
  model?: string;
  principal?: string;
  since?: string;
  until?: string;
}
