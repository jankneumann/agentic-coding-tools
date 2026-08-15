# Change: add-local-model-provider-tier

## Why

The always-on-host plan (`docs/proposals/always-on-agent-automation.md`) puts an ASUS
Ascent GX10 (NVIDIA GB10, 128 GB unified memory) at the center of unattended operation,
and two active changes already assume local models exist as dispatch targets — the
adaptive model router's success criterion is "local models absorb a meaningful share of
economy-tier traffic", and the task router defines a location axis with nothing local to
route to. Yet no provider in `_SUPPORTED_PROVIDERS` can reach a local endpoint. The
evaluation in `docs/proposals/magnitude-local-model-harness.md` closed the harness
question (no new agent harness needed; an OpenAI-compatible endpoint behind the existing
provider pattern suffices) and surfaced the non-obvious hardware constraint this change
must encode: on GB10-class machines, model choice is **bandwidth-bound, not
capacity-bound** (~273 GB/s LPDDR5x; dense 32B ≈ 10 t/s vs ~89 t/s for a 30B-total/3B-active
MoE), so the roster must be selected by architecture — small-active-parameter MoE — not by
what fits in 128 GB. That rule, and the trust boundary limiting local models to archetypes
whose failure is cheap or caught downstream, are the durable ideas this change records as
requirements; individual model names are rotating roster entries.

## What Changes

- **ADD** `local` provider to `skills/autopilot/scripts/provider_dispatch.py::_SUPPORTED_PROVIDERS`
  with an adapter runner speaking the OpenAI wire protocol to a configured base URL
  (`LOCAL_INFERENCE_BASE_URL`, optional key), degrading to the existing structured
  `fallback` result when unset or unreachable.
- **ADD** `local` roster to `agent-coordinator/archetypes.yaml::model_aliases`, kept in
  sync with `DEFAULT_PROVIDER_MODEL_MAP`. Initial shape: `economy` = small MoE
  (Qwen3-coder-30B-A3B-class), `standard` = large MoE (gpt-oss-120b-class);
  `premium`/`frontier` omitted → existing graceful degradation resolves them to the
  provider's best tier. Roster entries carry an operator-signed review date.
- **ADD** requirement-level roster rule (agent-archetypes spec delta): local rosters on
  bandwidth-bound hardware MUST be MoE-first (documented active-parameter ceiling);
  dense ≥30B models MUST NOT be roster entries even when they fit in memory.
- **ADD** requirement-level trust boundary (agent-archetypes spec delta): `local` provider
  resolution is permitted only for archetypes `runner`, `analyst`, `documenter`,
  `validator`; `architect`/`reviewer`/`gatekeeper` phases MUST NOT resolve to `local`.
- **ADD** concurrency cap and health-probe contract for the adapter (single-box fan-out
  bound; the roadmap policy engine must not switch to a dead local endpoint).
- **No behavior change** for existing providers: resolution output is byte-identical when
  provider ≠ `local`.
- Serving stack on the GX10 (llama.cpp `llama-server` / vLLM / Ollama) is deployment
  configuration, not code owned by this change; magnitude's ICN engine is excluded until
  its recorded re-evaluation triggers fire (headless CLI; documented CUDA).

## Approaches Considered

### Approach 1: `local` as a first-class provider (roster in archetypes.yaml, adapter in provider_dispatch)

Follow the `pi` precedent exactly: OpenAI-compatible slugs per tier, provider entry,
dispatch adapter.

- Pros: smallest delta; reuses tier-degradation, roster-sync, and fallback machinery
  already tested for five providers; immediately routable by the task router and
  catalogable by the adaptive router; trust boundary expressible in the same YAML the
  resolver already enforces.
- Cons: static tier assignment until the adaptive router lands (mitigated by starting
  `runner`-only and expanding after gen-eval parity runs); provider list grows by one.
- Effort: S

### Approach 2: Local endpoints as extra models inside the `pi` provider

Point selected `pi` tier slugs at the GX10 endpoint (OpenRouter-style base-URL override),
no new provider.

- Pros: zero provider-surface change.
- Cons: conflates two trust and cost domains under one provider id — the archetype trust
  boundary and the router's location axis both key on provider/vendor, so local-only
  restrictions become special cases; usage-limit policy can no longer treat local as a
  distinct rate-limit-immune switch target; audit records lose the local/cloud distinction.
- Effort: S (but with lasting modeling debt)

### Approach 3: Defer to the adaptive-model-router change and land local support there

Let `add-adaptive-model-router` introduce local endpoints as catalog entries when it ships.

- Pros: one owner for all model-selection concerns; no interim static tiers.
- Cons: that change is 21/71 tasks and large; the always-on proposal's Phase-2+ timeline
  needs a local target sooner; the router explicitly assumes local providers exist as
  routable supply — deferring inverts the dependency; the durable hardware-matching and
  trust-boundary requirements would live nowhere in the meantime.
- Effort: none now, L later

### Recommended

**Approach 1.** It is the established extension pattern (five providers, two roster
styles, tested degradation), keeps local a distinct vendor for trust, routing, audit,
and rate-limit-policy purposes — precisely the distinctions Approach 2 erases — and
supplies the routable target that both in-flight routing changes assume rather than
waiting on the largest of them (Approach 3).

### Selected Approach

**Approach 1** (first-class `local` provider), selected at Gate 1 on 2026-08-15: the
operator reviewed the approach comparison and directed the plan to completion with the
recommended approach, no modifications requested. Approaches 2 and 3 are retained above
as brief rejected entries: Approach 2 erases the local/cloud vendor distinction that
trust, routing, audit, and rate-limit policy key on; Approach 3 inverts the dependency
the adaptive router assumes.

## Impact

- **Specs**: `agent-archetypes` (roster rule + trust-boundary requirements, ADDED);
  `agent-coordinator` (provider roster validation touchpoint, MODIFIED).
- **Code**: `skills/autopilot/scripts/provider_dispatch.py`,
  `agent-coordinator/archetypes.yaml`, `agent-coordinator/src/agents_config.py`
  (`DEFAULT_PROVIDER_MODEL_MAP`), adapter env-var surface, tests deriving expectations
  from `archetypes.yaml`.
- **Docs**: `docs/proposals/magnitude-local-model-harness.md` (source evaluation;
  re-evaluation triggers), `docs/proposals/always-on-agent-automation.md` (consumer),
  hardware-matching rationale recorded here.
- **Related changes**: supply side for `add-adaptive-model-router` and
  `implement-the-task-router-vendor-x-location-x-model`; follows patterns from
  `add-frontier-model-tier`. No file-level conflicts identified.
