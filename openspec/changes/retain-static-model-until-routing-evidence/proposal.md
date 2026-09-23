# Change: retain-static-model-until-routing-evidence

## Why

The adaptive model router from `add-adaptive-model-router` (PR #417, roadmap item dg-00) is
deployed but cannot safely be enabled. The live catalog lists 15 models, and every one of them
has an empty `benchmark_priors`, price, latency and quota value. `score_and_rank` treats a
missing prior as `0.0` and collapses missing cost and latency to zero, so every candidate
scores the same. The tie is then broken by sort order: vendor name, then model name. Separately, `choose()` explores
with ε = 0.10 among non-top candidates, and the dollar-based exploration budget never runs out
when every price is empty. The result is that setting `ROUTING_ADAPTIVE=on` would replace the tuned
static model with an arbitrary one. For example, an Opus-tier architect phase could be routed to
`antigravity/gemini-3.6-flash-low` because "antigravity" sorts first, and about 10% of
resolutions would switch to a random model on top of that. The D2 fallback does not catch this,
because it triggers only on errors, timeouts and malformed responses, and a confident arbitrary
pick is none of those.

This change makes the static model the **incumbent**. The router may replace it only with a
challenger that has evidence and beats it by a margin. Until real routing evidence exists
(benchmark priors or posterior feedback, tracked as follow-ups DT-1 #609 and DT-4 #612),
turning the flag on changes nothing. That makes the flag safe to enable now, and it gives
the evidence pipeline a live place to take effect as soon as data arrives.

## What Changes

- `POST /routing/select_model` accepts an optional `incumbent` object (`vendor`, `model`). The
  field is additive: callers that omit it keep today's behavior exactly.
- `resolve_phase_model` forwards the static model and provider as the incumbent. When the
  static model can be resolved to a catalog identity (provider known), the vendor sent is the
  agent's `catalog_vendor`, so pi maps to `openrouter`.
- Selection with an incumbent keeps it unless a challenger is **evidenced**, meaning
  posterior `sample_size >= 1` or `benchmark_prior > 0`, **and** outscores the incumbent by
  `ROUTING_INCUMBENT_MARGIN`. That is a server-side environment variable, default `0.05` on the
  0–1 utility scale, where `0` means any strict improvement.
- If the incumbent is infeasible (unavailable, rate-limited lane, quota exhausted, or
  Cedar-excluded), the router takes the best **evidenced** feasible challenger. If there is
  none, it returns the incumbent. It never makes an evidence-free pick.
- If the incumbent cannot be identified (no provider, so the static model is a tier name such
  as `premium`), or is missing from the catalog, the router returns the incumbent with the
  reason `incumbent-unresolved`.
- Exploration only ever selects evidenced challengers. With an empty catalog it never fires.
- The response and the persisted decision record gain a `retention` object
  (`retained: bool`, `reason`). Reasons are `challenger-evidenced-above-margin`,
  `no-evidence`, `below-margin`, `incumbent-unresolved`, `incumbent-infeasible-no-evidenced-alternative`,
  `incumbent-infeasible-evidenced-alternative`, and `exploration-evidenced`. This makes every "kept static" outcome
  auditable in the decision ledger instead of invisible on the client.
- `selected` becomes nullable, but only when static is kept and there is no feasible catalog
  row for it (design D5). Pre-change clients treat a null `selected` as an error and
  fall back to the exact static result, so the change is backward-compatible by construction.
- Retaining the incumbent is a normal selection: the router returns the incumbent as the chosen
  candidate, and the client does not treat it as a fallback. The D2 kill switch and
  error/timeout fallback are unchanged, and `ROUTING_ADAPTIVE=off` still returns the exact static
  object.

No breaking changes. Every new request and response field is optional or additive.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Compatibility | Selection outcome for requests without `incumbent` | Identical to pre-change `score_and_rank` + `choose` output for the same inputs and RNG seed | Unit tests (test_service.py, test_resolver.py) |
| Resilience | Phase resolutions whose model differs from static when the catalog has zero evidence | 0 of N across every archetype/phase with `ROUTING_ADAPTIVE=on` | Unit test over all phase mappings + validate-feature smoke against live catalog |
| Observability | Decisions made with an incumbent that carry a `retention.reason` | 100% of persisted `routing_decisions` rows | Unit test on persisted record + schema bound test |
| Performance | Added latency in `select_model` | O(n) over candidates; no extra DB round trip; stays inside the existing 2 s client bound | Code review + existing timeout test |

## Approaches Considered

### Approach 1: Server-side incumbent retention in `select_model` (Recommended)

**Description**: Add an optional `incumbent` field to the request. `RoutingService.select_model`
applies the evidence, margin, feasibility and exploration rules after ranking, and records the outcome
in the response and the decision row as `retention`.

**Pros**:
- Every retention decision is persisted and auditable in the existing decision ledger.
- One implementation serves every caller (phase resolution, MCP `select_model_for_task`,
  direct HTTP), so no caller can bypass the gate.
- Exploration gating lives next to `choose()`, where the budget is already enforced.
- The margin knob lives server-side with the other `ROUTING_*` selection knobs.

**Cons**:
- Changes the request and response contract, which means updating the OpenAPI source,
  generated models, MCP tool, HTTP proxy, parity tests and the decision-record schema together.
- Requires resolving the static model to a catalog identity on the client (`catalog_vendor`).

**Effort**: M

### Approach 2: Client-side retention in `resolve_archetype_for_phase`

**Description**: Leave the API unchanged. After `select_model` returns, the client compares the
selection with the static model and keeps static unless the selected candidate shows evidence
(`posterior_sample_size`, `quality`) and a score gap over the static model's entry in
`alternatives`.

**Pros**:
- No API or contract change. The edit is confined to `agents_config.py`.
- Fastest path to a flag that is safe to enable for phase resolution.

**Cons**:
- The ledger records the arbitrary pick as the decision, while the client silently uses
  something else, so provenance becomes wrong.
- Direct `select_model` and MCP callers keep getting arbitrary picks.
- The static model's score is available only if it appears in the truncated `alternatives` list.
- Exploration still fires server-side and is merely overridden, which distorts the exploration budget.

**Effort**: S

### Approach 3: Evidence floor inside `score_and_rank`

**Description**: No incumbent concept. Candidates without evidence are excluded as infeasible,
and when nothing survives, the caller falls back to static through the existing D2 error path.

**Pros**:
- Smallest conceptual change, with no new request field.
- Also fixes direct callers.

**Cons**:
- Turns "no data" into an error path (HTTP 503), so a normal state becomes a fallback and D2
  error metrics fill up with noise.
- No margin: the first model to receive any prior wins outright over an unevidenced static
  model, even by a tiny amount.
- Loses the distinction between "kept static because it's better" and "kept static because
  we know nothing".

**Effort**: S

### Selected Approach

**Approach 1: Server-side incumbent retention in `select_model`**, selected at Gate 1 on 2026-09-23 without modification.
Discovery answers that shape it:
- An infeasible incumbent gives way to the best *evidenced* feasible challenger, or else stays static.
- Exploration may select only evidenced challengers.
- Evidence means posterior `sample_size >= 1` or `benchmark_prior > 0`, with an absolute margin `ROUTING_INCUMBENT_MARGIN` (default `0.05`).
- An unidentifiable incumbent (no provider) is kept with the reason `incumbent-unresolved`.

Approaches 2 and 3 were rejected. Approach 2 records false provenance and leaves direct callers arbitrary. Approach 3 turns "no data" into a 503 fallback and has no margin.

## Impact

- **Architecture layers**: Coordination (routing service, MCP and HTTP surface) and Governance
  (decision provenance).
- **Affected specs**:
  - `model-routing`: ADDED requirement "Incumbent Retention Until Routing Evidence"
    (delta `specs/model-routing/spec.md`).
  - `agent-archetypes`: MODIFIED requirement "Archetype Resolution Delegates to Adaptive Router",
    which now forwards the incumbent (delta `specs/agent-archetypes/spec.md`).
- **Code**: `agent-coordinator/src/model_routing/api.py` (request, response, `select_model`,
  `resolve_phase_model`), `model_routing/exploration.py` (evidenced-only exploration),
  `model_routing/resolver.py` (evidence predicate), `agents_config.py` (incumbent
  identity), `coordination_mcp.py` and `http_proxy.py` (parity), `database/migrations/044_routing_decision_retention.sql`
  (nullable `retention` column, nullable `selected` guarded by a CHECK, updated audit RPC; design D8,
  added during implementation), and the contracts:
  OpenAPI routing contract plus generated models and the routing decision record schema.
- **Related changes**:
  - `add-harbor-benchmark-routing` (plan only) contains a "flag on ranks by priors" scenario.
    This change tightens it with the evidence and margin gate, and harbor's delta should be
    rebased onto this requirement when it is implemented.
  - `implement-the-task-router-vendor-x-location-x-model` (merged in #605, not yet archived)
    owns the separate `task-routing` capability. There is no delta collision, and retention runs
    after its feasibility and assignment step.
- **Rollback**: migration 044 is additive (a nullable column, a relaxed NOT NULL guarded by a CHECK, and a
  replaced RPC), so it can stay in place after a code revert. To neutralize at runtime, set `ROUTING_INCUMBENT_MARGIN` very high so challengers effectively never win, or
  leave `ROUTING_ADAPTIVE` off. Reverting the change restores the pre-change behavior, because
  the new fields are optional.
