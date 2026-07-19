# Contracts: add-coordinator-llm-gateway

| Sub-type | Applies | Artifact |
|---|---|---|
| OpenAPI | Yes — coordinator control-plane endpoints (issue/revoke key, budget, spend) | `openapi/v1.yaml` |
| Database | Yes — additive `llm_gateway_keys` issuance-audit table (DDL lives in the migration task; no separate schema.sql needed for one additive table) | migration `NNN_llm_gateway_keys.sql` |
| Events | **No** — spend flows via the gateway's spend callback into the existing router ledger; no new coordination event type in v1. |
| Type generation | Deferred to `wp-contracts` — Pydantic models generated from `openapi/v1.yaml`. |

**Not our contract**: the *data-plane* API (`/chat/completions`, `/embeddings`, virtual-key
semantics) is LiteLLM's own OpenAI-compatible spec — referenced, not redefined here.
