# Exploration

Feature area: a `local` dispatch provider backed by GX10-hosted models, with a
hardware-matched model roster (MoE-first) and archetype routing for the phases where
local models are cost-effective and failure is caught downstream.

## Objective

Record and operationalize the idea from `docs/proposals/magnitude-local-model-harness.md`:
the always-on host (ASUS Ascent GX10, NVIDIA GB10) should serve local models to the
existing dispatch stack for low-tier archetype work. The evaluation established that
(a) this does not require building a new agent harness — the existing Pi coding-agent
harness can register the OpenAI-compatible endpoint and retain its tool loop — and (b) model selection on GB10-class
hardware is **bandwidth-bound, not capacity-bound**: ~273 GB/s LPDDR5x means dense
models crawl (~10 t/s at 32B) while sparse MoE models with small active-parameter
counts run an order of magnitude faster (~89 t/s for Qwen3-30B-A3B-class). The roster
must therefore be chosen by architecture (MoE-first), not by size-that-fits-128GB.

## Existing Context

### Related Specs

- **agent-archetypes** — owns the archetype/tier vocabulary (`frontier/premium/standard/economy`),
  `write_capable` enforcement, and phase mapping. A local provider adds a roster, not new tiers.
- **agent-coordinator** — `agents_config` loads `archetypes.yaml`; `/archetypes/resolve_for_phase`
  serves per-phase resolution. New provider entries flow through this path unchanged.
- **roadmap-orchestration** — usage-limit policy engine (wait/switch/fail-closed); a local
  provider is a rate-limit-immune switch target for `runner`-class phases.
- **harness-engineering / vendor-ux** — conventions for adding provider harnesses and their
  CLI dispatch surfaces.

### Active Changes

- **add-adaptive-model-router (21/71)** — explicitly anticipates this capability: success
  criterion "(b) local models absorb a meaningful share of economy-tier traffic", catalog
  covers "local endpoints (Ollama/vLLM)". That change owns *scoring and selection*; it needs
  a local provider to exist as a routable target. Complementary, not conflicting — this
  change is the supply side, the router is the demand side.
- **implement-the-task-router-vendor-x-location-x-model (0/10)** — owns the location axis
  (`routing.yaml`, `POST /route/task`). A `local` provider gives the `location=local-gpu`
  option a concrete meaning. No file-level conflict expected (routing.yaml vs archetypes.yaml).
- **add-frontier-model-tier (11/13)** — established the pattern for tier-vocabulary changes
  and graceful degradation when a provider omits a tier. A local provider omitting
  `frontier`/`premium` follows the same degradation path (documented in `archetypes.yaml`
  header: omitted tiers resolve to the provider's best available).
- **add-live-vendor-capability-and-cost-registry (0/10)** — a local provider's "cost" is
  power + opportunity cost, not tokens; registry entries will need a marginal-cost-zero
  vendor kind eventually. Out of scope here; noted as a consumer-side follow-up.

### Architecture Context

- Dispatch flow: `autopilot.py` → `coordination_bridge.try_resolve_archetype_for_phase`
  → `POST /archetypes/resolve_for_phase` → `agents_config.resolve_archetype_for_phase`
  (reads `agent-coordinator/archetypes.yaml`) → `ResolvedArchetype{model, system_prompt,
  archetype}` → `provider_dispatch.dispatch_phase` with a provider adapter runner.
- Provider enumeration: `skills/autopilot/scripts/provider_dispatch.py::_SUPPORTED_PROVIDERS`
  = `{claude_code, codex, antigravity, grok, pi}`. The `pi` provider is the closest
  precedent: OpenAI-compatible `publisher/model` slugs via OpenRouter.
- Parallel zones: `agents_config` and its archetype/agents YAML loaders sit in their own
  independent group (`parallel_zones.json` group 0/1); `provider_dispatch.py` is
  skills-side. Neither touches the high-impact `config.get_config` fan-out beyond
  existing patterns — safe to develop in parallel with the router changes.

### Codebase Patterns

- `archetypes.yaml` `model_aliases` shows two roster styles: bare model ids and
  `{model, thinking}` objects; per-file comment states tiers are "tuned for cost per
  successful task, not cost per token" — exactly the framing under which local models
  win economy-tier work.
- Tier omission with graceful degradation is an established, tested pattern (antigravity
  omits `frontier`).
- `DEFAULT_PROVIDER_MODEL_MAP` (referenced in `archetypes.yaml:29`) must stay in sync
  with any roster addition.
- Dispatch adapters normalize tuple/dict results (`normalize_dispatch_result`) and fall
  back cleanly when no runner is configured — a `local` provider without a reachable
  endpoint degrades to the same structured `fallback` result as any unconfigured provider.

## Context Synthesis

### Constraints

- GB10 hardware envelope: 128 GB unified LPDDR5x at ~273 GB/s; prefill compute-rich
  (~11k t/s), decode bandwidth-poor. Roster rule: **small-active-parameter MoE only**;
  no dense ≥30B models regardless of fitting in memory.
- Serving stack must be CUDA-proven on Linux/aarch64 today: llama.cpp `llama-server`,
  vLLM, or Ollama. Magnitude's ICN engine is explicitly out (Metal-only bindings;
  re-evaluation triggers recorded in `docs/proposals/magnitude-local-model-harness.md`).
- Local models are restricted to archetypes whose failure is cheap or caught downstream:
  `runner`, `analyst`, `documenter`, `validator`. `architect`/`reviewer`/`gatekeeper`
  stay on cloud frontier/premium — same trust division the always-on proposal draws.
- Keep the roster small enough for simultaneous residency (one small MoE + one large MoE
  fit in 128 GB with KV headroom) so no model-swap scheduling is needed in v1.
- OpenSpec branch convention `openspec/<change-id>`; coordinator config changes must not
  alter behavior for existing providers (byte-identical resolution when provider ≠ local).

### Integration Points

- `agent-coordinator/archetypes.yaml` — add `local` roster under `model_aliases`.
- `agent-coordinator/src/agents_config.py` — roster validation; `DEFAULT_PROVIDER_MODEL_MAP` sync.
- `skills/autopilot/scripts/provider_dispatch.py` — add `local` to `_SUPPORTED_PROVIDERS`;
  adapter runner speaking the OpenAI protocol to a configured base URL.
- Endpoint configuration — env-var surface consistent with coordinator conventions
  (e.g. `LOCAL_INFERENCE_BASE_URL`, optional API key), fail-closed to `fallback` dispatch.
- Consumers: adaptive-model-router catalog rows; task-router `location` axis; roadmap
  policy engine switch targets.

### Risks

- **Endpoint liveness**: the GX10 server may be down/reloading; dispatch must degrade to
  the structured fallback path, and the roadmap policy engine must not switch *to* a dead
  local target (health probe before switch).
- **Quality drift**: economy-tier local models may underperform cloud economy models on
  specific phases; without the adaptive router's feedback loop (separate change), tier
  assignment is static judgment. Mitigation: start with `runner` only, expand per phase
  after gen-eval parity runs.
- **Concurrency limits**: single box; fan-out dispatch beyond the server's parallel
  capacity queues or degrades throughput. Aggregate-throughput behavior on GB10 is good
  but bounded; needs a documented concurrency cap in the adapter.
- **Roster staleness**: local model landscape moves fast; roster should carry a review
  date, mirroring the operator-signed roster notes already present for antigravity/pi.

## Recommendation

**Proceed to proposal.** The capability is small, precedent-backed (`pi` pattern,
frontier-tier degradation pattern), explicitly demanded by two active changes
(adaptive router's success criterion, task router's location axis), and the hardware
analysis is done. The proposal should record the MoE-first hardware-matching rule and
the archetype trust boundary as requirements, not just implementation notes — they are
the durable ideas; specific model names are roster entries that will rotate.
