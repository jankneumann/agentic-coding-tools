# Design: add-coordinator-llm-gateway

Numbered decisions (G1…) for a coordinator-managed LLM gateway. Referenced by tasks/tests.

## Architecture: control plane vs data plane

```
  ┌──────────────────────── coordinator (control plane, low-QPS) ────────────────────────┐
  │  add-adaptive-model-router: catalog · select_model · policy · SPEND LEDGER (truth)   │
  │  llm_gateway.py: issue_llm_key / revoke / get_budget / get_spend   (MCP + HTTP)      │
  │        │ mints virtual keys (budget+model scope)     ▲ spend callbacks → ledger      │
  └────────┼────────────────────────────────────────────┼───────────────────────────────┘
           │ admin API                                   │ /spend/logs callback
  ┌────────▼─────────────────────── LiteLLM proxy (data plane, separate container) ──────┐
  │  OpenAI-compatible /chat/completions · /embeddings · virtual keys · inline budgets   │
  │  upstreams: OpenRouter (metered) · Ollama/vLLM (local) · direct provider APIs        │
  └──────────────────────────────────────────────────────────────────────────────────────┘
           ▲ base_url + virtual key
  agents / skills (metered dispatch) ·  code_search.py embedder ·  cocoindex LiteLLM embedder
```

Subscription-CLI sessions (Claude Code/Codex/Gemini) do **not** appear here — they call vendors
directly (G5).

## Decisions

### G1 — Coordinator is control plane only; inference never flows through it

The coordinator process administers the gateway (issue/revoke keys, read spend) but never proxies
`/chat/completions` or `/embeddings` traffic. Inference is high-QPS, streaming, and latency-
critical; coordination is low-QPS and outage-tolerant. Keeping them separate preserves the
coordinator's profile and blast radius (a coordination hiccup must not halt inference). This is why
Approach B (proxy inside `coordination_api.py`) is rejected.

### G2 — The router's ledger + policy are the single source of truth

Budgets are **derived from** the `add-adaptive-model-router` policy engine (policy decision →
virtual-key `max_budget`), and actual spend flows **back** from the gateway's spend callback into
the **same** ledger the router already maintains. The gateway holds no independent spend truth — it
is an enforcement mirror. This is the "don't build two spend systems" constraint made concrete.

### G3 — Virtual keys minted from vault-held provider keys; agents never see master keys

Provider master keys live in OpenBao/bao-vault. `issue_llm_key` mints a **short-lived LiteLLM
virtual key** scoped to `(budget_usd, model_allowlist, ttl)` and tied to the requesting agent's id
+ trust level. Agents receive only the virtual key; rotation/revocation is central. Trust level
bounds the maximum issuable budget and model set (reuses the coordinator profiles/trust model).

### G4 — Inline budget enforcement for proxied traffic

Because every proxied call carries a virtual key with a `max_budget`, the gateway rejects calls
once the key's spend crosses its budget — the router's "monthly spend ceiling" becomes real-time
for the meterable slice, instead of reconciled after. Enforcement granularity: per-key (per agent
or per work-package, issuer's choice).

### G5 — Coverage boundary is explicit and documented

The gateway covers **metered provider APIs + local endpoints + embeddings**. Subscription-CLI
dispatch cannot be routed through an HTTP proxy and remains on vendor auth governed by the router's
*advisory* selection + post-hoc reconciliation. Docs and metrics MUST NOT imply the gateway is a
universal choke point. This boundary is inherited from the router's rejected Approach C.

### G6 — First consumer: the semantic code-search embedder

`code_search.py`'s server-side embedder and cocoindex-code's LiteLLM embedder point their
`base_url` at the gateway `/embeddings` with a coordinator-issued key. This retires the
`add-semantic-code-search` spike's environment block (no reachable embedder) with the same
infrastructure — one provisioned, allowlisted, keyed endpoint serves embeddings + completions. The
`code_search_registry.embedder_model` (D4 there) records the gateway-served model.

### G7 — Separate deployable, provider-pluggable data plane

The data plane is a pinned LiteLLM proxy container (`docker/llm-gateway/`, compose service mirroring
`agent-coordinator/docker-compose.yml`). Its `config.yaml` lists upstreams: OpenRouter (metered,
using the router's standing OpenRouter key), local Ollama/vLLM, and/or direct provider APIs. The
coordinator control surface is provider-agnostic — swapping OpenRouter for direct providers is
gateway config, not coordinator code. (OpenRouter alone, with no self-hosted proxy, was considered
but rejected as the default: it can't front local Ollama/vLLM and can't mint scoped virtual keys.)

### G8 — Observability via existing langfuse integration

The gateway is configured with a success/failure callback that emits to the coordinator's langfuse
(`langfuse_tracing.py` / `langfuse_middleware.py` already exist). No new tracing substrate.

### G9 — Flag-gated, off by default; existing dispatch is the fallback

`LLM_GATEWAY_ENABLED` (default off) gates control-surface registration and consumer opt-in. While
off: MCP key tools unlisted, HTTP key routes 404, and `code_search.py` uses its direct embedder
config. Additive migrations only. No behavior change when off.

### G10 — Key-issuance audit, not a spend duplicate

The only new coordinator table is an **issuance audit** (`llm_gateway_keys`: key_id, agent_id,
budget_usd, model_allowlist, issued_at, expires_at, revoked_at). Spend stays in the router ledger
(G2). This table answers "which agent holds which scoped key" for revocation and audit, not "how
much was spent."

## Surfaces

Control-plane MCP tools / HTTP endpoints (gated by `LLM_GATEWAY_ENABLED`):

| Operation | MCP tool | HTTP | Kind |
|---|---|---|---|
| Issue scoped virtual key | `issue_llm_key` | `POST /llm/keys/issue` | reversible-write |
| Revoke a key | `revoke_llm_key` | `POST /llm/keys/revoke` | reversible-write |
| Read agent budget | `get_llm_budget` | `GET /llm/budget/{agent_id}` | read |
| Read agent spend (from router ledger) | `get_llm_spend` | `GET /llm/spend/{agent_id}` | read |

The data-plane API is LiteLLM's own OpenAI-compatible spec — **not** re-specified here; agents use
it directly with their issued key.

## Failure modes

- **Gateway unreachable** → `issue_llm_key` returns the standard unavailable envelope; consumers
  (e.g. code-search) fall back to their configured direct embedder or degrade gracefully.
- **Budget exhausted** → gateway returns HTTP 429/402 to the *agent*; the coordinator surface is
  uninvolved (enforcement is inline at the valve, G4).
- **Router ledger unavailable for spend callback** → gateway buffers callbacks; spend is eventually
  reconciled (never silently dropped). Enforcement continues on the key's local budget counter.
- **Vault unavailable** → key issuance fails closed (no key minted); never falls back to a raw
  master key in an agent's hands (G3).
