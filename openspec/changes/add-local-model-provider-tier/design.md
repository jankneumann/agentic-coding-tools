# Design: add-local-model-provider-tier

## Context

Per-phase dispatch resolves an archetype and provider-specific model via
`agent-coordinator/archetypes.yaml` (`model_aliases` + `phase_mapping`), served by
`POST /archetypes/resolve_for_phase` (`agents_config.py`), and dispatched skills-side
through `provider_dispatch.py` (`_SUPPORTED_PROVIDERS`, adapter runners, structured
fallback). Five providers exist; `pi` is the OpenAI-compatible-slug precedent. The
always-on host (ASUS Ascent GX10, NVIDIA GB10: 128 GB unified LPDDR5x at ~273 GB/s,
prefill compute-rich, decode bandwidth-bound) has no provider entry, while two active
changes (`add-adaptive-model-router`, `implement-the-task-router-vendor-x-location-x-model`)
assume local model supply exists. Source evaluation:
`docs/proposals/magnitude-local-model-harness.md`.

## Goals / Non-Goals

**Goals**

- A sixth first-class provider `local` reachable through the existing dispatch contract.
- The two durable rules encoded as enforced config, not prose: MoE-first hardware
  matching and the archetype trust boundary.
- Zero behavior change for existing providers; inert until an endpoint is configured.

**Non-Goals**

- Serving-stack deployment on the GX10 (llama.cpp `llama-server` / vLLM / Ollama is
  operator deployment config; magnitude's ICN excluded until its recorded triggers fire).
- Adaptive/learned routing (owned by `add-adaptive-model-router`; this change is its
  supply side).
- Location-axis routing policy (owned by the task-router change).
- New coordinator endpoints; `/archetypes/resolve_for_phase` keeps its shape.

## Decisions

- **D1 — `local` is a first-class provider** in `_SUPPORTED_PROVIDERS` and
  `model_aliases`, following the `pi` pattern (Gate 1 selection). Keeps local a distinct
  vendor for trust, routing, audit, and rate-limit policy.
- **D2 — Adapter dispatches through the existing Pi coding-agent harness.** A
  one-shot extension registers the distinct `local` provider against
  `LOCAL_INFERENCE_BASE_URL` (optional `LOCAL_INFERENCE_API_KEY`) using Pi OpenAI
  completions support. Pi supplies the file, command, edit, and handoff tool loop;
  stdlib HTTP is used only for the bounded health probe. The serving stack behind
  the URL is out of scope.
- **D3 — Trust boundary enforced in the resolver**, not the caller:
  `resolve_archetype_for_phase` fails with a structured error (naming the permitted list
  `runner`, `analyst`, `documenter`, `validator`) when provider `local` pairs with
  `architect`, `reviewer`, or `gatekeeper`, and the refusal is audit-logged. A prose-only
  gate would be invisible to unattended loops.
- **D4 — Hardware matching is roster-entry metadata validated at startup.** `local`
  roster entries use an extended object form
  `{model, total_params_b, active_params_b, reviewed}`; validation fails fast (same
  mechanism as undefined-archetype errors) when `active_params_b` exceeds the host-class
  ceiling (`local_host_class.active_params_ceiling_b`, GB10 default 12) or when a dense
  entry (`active_params_b == total_params_b`) has `total_params_b >= 30`. Machine-readable
  fields, not comments, so the rule is enforceable.
- **D5 — Health probe and concurrency cap live in the adapter.** One probe (`GET
  /models` or equivalent) per session before first dispatch; failure → adapter
  unavailability → existing structured `fallback` result (never a hang, never a dispatch
  error). `LOCAL_INFERENCE_MAX_CONCURRENCY` (default 4) bounds simultaneous local
  dispatches; excess queues. Probe status is exposed so the roadmap policy engine will
  not switch to a dead endpoint.
- **D6 — Byte-identical regression guard.** A snapshot test resolves every
  (archetype × existing provider) pair before/after the roster addition and asserts
  equality, making the "no behavior change" requirement executable.
- **D7 — Initial roster (operator-reviewed, rotating):** `economy` =
  Qwen3-coder-30B-A3B-class (~30B total / ~3B active), `standard` = gpt-oss-120b-class
  (~117B total / ~5B active); `premium`/`frontier` omitted → existing graceful
  degradation. Both resident simultaneously in 128 GB with KV headroom, so no model-swap
  scheduling is needed in v1.

## Alternatives Considered

- **Local endpoints inside the `pi` provider** — rejected: conflates trust and cost
  domains; local-only restrictions become special cases keyed on model slug instead of
  provider (proposal Approach 2).
- **Defer to `add-adaptive-model-router`** — rejected: inverts the dependency; that
  change assumes local supply exists and is 21/71 tasks (proposal Approach 3).
- **Enforce the trust boundary in `provider_dispatch.py` only** — rejected: skills-side
  enforcement can be bypassed by any other resolver client; the coordinator is the
  single decision point and already owns structured resolution errors.
- **Roster rule as YAML comments** — rejected: comments can't fail validation; D4 makes
  the rule machine-checkable.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|---|---|---|
| Endpoint down or reloading mid-run | Phases stall or fail | D5: probe → structured fallback; policy engine sees probe status; adapter never blocks indefinitely |
| Local model quality below cloud economy tier on some phases | Silent quality drift in unattended runs | Trust boundary (D3) restricts to downstream-verified archetypes; start `runner`-only in `phase_mapping` guidance; expand after gen-eval parity runs |
| Single-box fan-out saturation | Queued dispatches slow wall-clock | D5 cap with queueing; aggregate GB10 throughput under concurrency is the favorable regime |
| Roster staleness as local models rotate | Suboptimal tier assignments | D4 `reviewed` date; operator re-signs on rotation (mirrors antigravity/pi roster notes) |
| Tier-degradation surprise (premium request served by standard-class local model) | Capability mismatch | Degradation reasons recorded in resolution output (existing mechanism); trust boundary keeps premium-critical archetypes off `local` entirely |

## Migration Plan

Config-and-code-only, no data migration. Rollout: land roster + validation + adapter
with `LOCAL_INFERENCE_BASE_URL` unset — provider is inert (structured fallback), CI
proves byte-identical resolution for other providers (D6). Operator enables by
deploying a serving stack on the GX10, installing the `pi` CLI, and setting the
env vars; smoke path
(`local` selector, dry-run then real mode) verifies before any autopilot use.
Rollback: unset the env vars (adapter degrades to fallback immediately); full removal
is deleting the roster entry and provider constant — no persisted state.
