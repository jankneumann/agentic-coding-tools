# Change: add-coordinator-llm-gateway

**Status**: Draft
**Created**: 2026-07-19
**Author**: Claude (plan-feature, coordinated tier)
**Depends on**: `add-adaptive-model-router` (control-plane brain — catalog, selection, spend ledger, policy)

## Why

`add-adaptive-model-router` gives the coordinator a **control plane** for model choice: a catalog,
a `select_model_for_task` resolver (`POST /routing/select_model` + MCP tool), a spend ledger, a
policy engine with a monthly spend ceiling, and an OpenAI-compatible `base_url` dispatch adapter
for OpenRouter + local Ollama/vLLM. But that ceiling is **advisory** — enforced by post-hoc
reconciliation, not at request time — and agents still hold raw provider keys and call models
directly. There is no **data plane**: no single point where metered inference actually flows, so
budgets can be exceeded before reconciliation catches them, keys can't be scoped or rotated
centrally, and each call must be individually instrumented for spend/observability.

Separately, `add-semantic-code-search` is blocked in cloud sessions because **no embedder is
reachable** (PyPI-only network policy; huggingface.co / provider APIs return 403). It needs a
provisioned, allowlisted embedding endpoint.

A **coordinator-managed LLM gateway** closes both gaps with one piece of infrastructure: a
self-hosted LiteLLM proxy (optionally fronting OpenRouter and local endpoints) that the
coordinator *configures and meters but does not run inference through*. The router stays the brain
(which model, what budget); the gateway becomes the **valve** that enforces those decisions inline
for the traffic that can be proxied — and its `/embeddings` route is the reachable embedder
`add-semantic-code-search` needs.

**Latent intent (from discussion)**: keep control/enforcement in the coordinator; use LiteLLM /
OpenRouter purely as data planes that connect to models, so model choice can be optimized and
budgets enforced without the coordinator becoming an inference hot path.

## What Changes

- **New capability `llm-gateway`** owning virtual-key issuance, inline budget enforcement, spend
  accounting, and the embedding endpoint — all as coordinator control-plane operations.
- **Separate LiteLLM proxy deployable** (`docker/llm-gateway/`, compose service like the ParadeDB
  pattern) — the data plane. The coordinator process **never proxies inference tokens**; it only
  administers the gateway. OpenRouter and local Ollama/vLLM sit *behind* the gateway as upstreams.
- **Coordinator control surface** (MCP tools + HTTP endpoints, gated by `LLM_GATEWAY_ENABLED`):
  - `issue_llm_key(agent_id, budget_usd, models, ttl)` → a short-lived LiteLLM virtual key scoped
    to a budget + model allowlist, minted from provider master keys held in OpenBao/bao-vault.
  - `revoke_llm_key(key_id)`; `get_llm_budget(agent_id)`; `get_llm_spend(agent_id, window)`.
- **Single source of truth = the router's ledger/policy.** Budgets come *from* the
  `add-adaptive-model-router` policy engine (policy → virtual-key limit); actual spend flows *back*
  via the gateway's spend callback into the **same** ledger. No second spend system.
- **Inline enforcement** for proxied traffic (metered APIs, local endpoints, embeddings): the
  gateway blocks a call when its virtual key's budget is exhausted — the ceiling becomes real-time,
  not reconciled-after.
- **Embedding endpoint for `add-semantic-code-search`**: `code_search.py`'s embedder (and
  cocoindex's LiteLLM embedder) point at the gateway `/embeddings` with a coordinator-issued key —
  the first consumer, and the fix for the spike's environment block.
- **Observability**: gateway success/failure callbacks route into the coordinator's existing
  langfuse integration (`langfuse_tracing.py`), so every proxied call is traced centrally.
- **Coverage boundary (explicit non-goal)**: subscription-CLI dispatch (Claude Code / Codex /
  Gemini CLIs) **cannot** be proxied and stays on vendor auth + the router's *advisory* path. The
  gateway centralizes the **meterable** slice only (metered API + local + embeddings).
- **BREAKING**: none while off. `LLM_GATEWAY_ENABLED=off` by default; existing dispatch is the
  fallback. Additive migrations only.

## Approaches Considered

### Selected Approach

**Approach A — coordinator-managed LiteLLM proxy as data plane, router as control plane**
(selected from the design discussion: control/enforcement in the coordinator, LiteLLM/OpenRouter
as data planes connecting to models).

### Approach A — Managed LiteLLM proxy data plane + coordinator control plane — **Recommended**

Self-hosted LiteLLM proxy as a separate deployable; coordinator issues virtual keys, sets budgets
from the router policy, consumes spend callbacks into the router ledger; agents point `base_url` at
the gateway. OpenRouter/Ollama/vLLM are upstreams behind it.

- **Pros**: inline budget enforcement; virtual keys (no raw provider keys in agent hands, ties to
  bao-vault + trust levels); one provisioned embedding endpoint (unblocks code-search); central
  langfuse tracing; router stays the brain (keeps feedback posteriors + subscription-aware
  selection); coordinator keeps its low-QPS control-plane profile.
- **Cons**: a new always-on service to operate; only covers meterable traffic (not subscription
  CLIs); virtual-key/budget sync between router policy and gateway must be kept consistent.
- **Effort**: L

### Approach B — Fold proxying into the coordination API process

Proxy `/chat/completions` + `/embeddings` directly through `coordination_api.py`.

- **Pros**: no new deployable; one service.
- **Cons**: puts the coordinator in the **inference hot path** — high-QPS streaming traffic on a
  service tuned for low-QPS coordination; a coordination outage would halt all inference and vice
  versa (blast-radius regression); streaming/backpressure is a different operational profile.
- **Effort**: M

### Approach C — Gateway *as* the router (already rejected upstream)

Let the gateway make model/budget decisions; coordinator only records outcomes. This is
`add-adaptive-model-router`'s **already-rejected Approach C**: it cannot route subscription-CLI
dispatch (the majority of traffic and the whole arbitrage edge), and gateway config cannot consume
task-specific feedback posteriors.

- **Pros**: least custom code.
- **Cons**: loses the learning asset + subscription-CLI coverage — the reasons it was rejected for
  the router. Kept here only to record it is out of scope.
- **Effort**: M

## Impact

- **Affected specs**: `llm-gateway` (new), `agent-coordinator` (control-plane surface + flag).
- **Affected code**: `docker/llm-gateway/` (new), `agent-coordinator/src/llm_gateway.py` (new),
  `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/src/coordination_api.py`,
  `agent-coordinator/database/migrations/` (virtual-key/issuance audit table), integration hooks
  into the `add-adaptive-model-router` ledger, and (consumer) `agent-coordinator/src/code_search.py`.
- **Rollback**: `LLM_GATEWAY_ENABLED=off` (default) reverts to existing direct dispatch; the proxy
  is a separate container that can be stopped without affecting coordination; migrations additive.
