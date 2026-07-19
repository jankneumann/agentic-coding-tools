# Tasks: add-coordinator-llm-gateway

Sizing per plan-feature reference (no XL). Tests precede implementation (TDD). Spec scenario refs
use `<capability>.<n>` ordinals in file order. Depends on `add-adaptive-model-router` for the
ledger/policy this integrates with (design G2).

## Phase 0 — Prerequisite alignment

- [ ] 0.1 (S) Confirm the `add-adaptive-model-router` ledger + policy interfaces this consumes
  (spend write, budget/policy read); pin the integration points or stub them behind an adapter if
  that change has not landed yet
  **Design decisions**: G2
  **Dependencies**: none

## Phase 1 — Contracts (wp-contracts)

- [ ] 1.1 (S) Validate `contracts/openapi/v1.yaml`; generate Pydantic models into
  `contracts/generated/models.py`
  **Contracts**: contracts/openapi/v1.yaml
  **Dependencies**: 0.1
- [ ] Checkpoint: openapi validates, models import

## Phase 2 — Data plane deployable (wp-gateway-deployable)

- [ ] 2.1 (S) Write a smoke test that starts the gateway container and asserts `/health` +
  `/embeddings` respond for a configured model (skip-marked when Docker/model unavailable)
  **Spec scenarios**: llm-gateway.1 (separate deployable)
  **Design decisions**: G1, G7
  **Dependencies**: none
- [ ] 2.2 (M) Add `docker/llm-gateway/` — pinned LiteLLM proxy compose service +
  `config.yaml` (upstreams: OpenRouter, local Ollama/vLLM, direct providers) + langfuse callback;
  `make llm-gateway-up/down` targets mirroring the ParadeDB pattern
  **Spec scenarios**: llm-gateway.1
  **Design decisions**: G7, G8
  **Dependencies**: 2.1
- [ ] Checkpoint: gateway starts; embedding round-trips against a test upstream

## Phase 3 — Coordinator control service + surfaces (wp-control-service)

- [ ] 3.1 (M) Write tests for `llm_gateway.py` — trust-bounded issuance, vault-unavailable
  fail-closed, revoke, budget/spend reads delegate to the router ledger (mocked vault + gateway
  admin + ledger)
  **Spec scenarios**: llm-gateway.2 (scoped key), llm-gateway.2b (trust bound),
  llm-gateway.2c (vault fail-closed), llm-gateway.4 (single spend source), agent-coordinator.3 (audit)
  **Design decisions**: G2, G3, G10
  **Dependencies**: 0.1
- [ ] 3.2 (M) Implement `agent-coordinator/src/llm_gateway.py` — DI service over (vault, gateway
  admin client, router ledger); `issue/revoke/get_budget/get_spend`; issuance-audit writes
  **Design decisions**: G2, G3, G4, G10
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope (agent-coordinator only)
- [ ] 3.3 (S) Write surface tests — flag off hides MCP tools + 404s HTTP routes; op-kind
  classification (reads vs reversible-write); MCP/HTTP parity
  **Spec scenarios**: agent-coordinator.1 (both surfaces), agent-coordinator.2 (op kinds),
  agent-coordinator.4 (flag)
  **Design decisions**: G9
  **Dependencies**: 3.2
- [ ] 3.4 (S) Register `issue_llm_key/revoke_llm_key/get_llm_budget/get_llm_spend` in
  `coordination_mcp.py` (conditional on flag) and the HTTP routes in `coordination_api.py`; add
  `http_proxy` passthroughs
  **Spec scenarios**: agent-coordinator.1
  **Dependencies**: 3.3
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Enforcement + audit table (wp-enforcement)

- [ ] 4.1 (S) Migration test — `llm_gateway_keys` additive shape; asserts NO spend columns
  **Spec scenarios**: agent-coordinator.3 (audit, not spend)
  **Dependencies**: 0.1
- [ ] 4.2 (S) Add additive migration `NNN_llm_gateway_keys.sql`
  **Design decisions**: G10
  **Dependencies**: 4.1
- [ ] 4.3 (M) Wire the gateway spend callback → router ledger; buffer-and-reconcile on ledger
  outage; test inline budget-exhaustion rejection (gateway-level, mocked)
  **Spec scenarios**: llm-gateway.3 (inline enforcement), llm-gateway.4b (callback outage)
  **Design decisions**: G2, G4
  **Dependencies**: 3.2, 4.2

## Phase 5 — Consumer + integration (wp-integration)

- [ ] 5.1 (S) Repoint `code_search.py`'s embedder at the gateway `/embeddings` behind a config
  toggle (`CODE_SEARCH_EMBEDDER_BASE_URL`); default unchanged when gateway off
  **Spec scenarios**: llm-gateway.6 (code-search embeds via gateway)
  **Design decisions**: G6
  **Dependencies**: 3.4
- [ ] 5.2 (S) Docs: `docs/guides/llm-gateway.md` — control/data-plane split, the coverage
  boundary (G5), key issuance, and the code-search embedding wiring; CLAUDE.md tool entries
  **Spec scenarios**: llm-gateway.5 (coverage boundary documented)
  **Dependencies**: 5.1
- [ ] 5.3 (M) End-to-end (where a gateway + model are reachable): issue a key, embed via the
  gateway from code-search, confirm spend lands in the router ledger and budget enforces
  **Spec scenarios**: llm-gateway.3, llm-gateway.6
  **Dependencies**: all prior
- [ ] Checkpoint: suite green, diff maps to tasks, scope verified

## Deferred (recorded, not scheduled)

- Load-balancing / multi-instance gateway HA — after single-instance proves out.
- Per-work-package (not just per-agent) key granularity — if agent-level proves too coarse.
- Caching layer in the gateway — measure hit rates first.
