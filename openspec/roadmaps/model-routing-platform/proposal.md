# Model Routing & Vendor Platform

## Motivation

The repo has accumulated **seven in-flight OpenSpec proposals** that all touch the same
surface — how coding work is routed to a vendor, a location, and a model, and how vendor
cost/capability is known and enforced. Landed piecemeal they will collide: several edit or
delete the *same* files (`agents.yaml`, `orchestrator.py`'s hardcoded vendor list, `policy.py`'s
stub cost tiers, the CLI dispatch adapters). This roadmap sequences them into one coherent,
layered delivery with an explicit dependency DAG and a recommended merge order, so each change
lands on a stable base instead of rebasing against its siblings.

The triggering event: adding three new harnesses (`agy`, `grok`, `pi`) and retiring the
discontinued Gemini CLI exposed how many other proposals mutate the same vendor/routing
substrate.

## Capabilities

Each capability corresponds to an **existing** OpenSpec change (do not invent new work — map
items onto these change-ids; read each change's `proposal.md` under `openspec/changes/<id>/`):

1. **Vendor roster** — `add-agy-grok-pi-harnesses` — register `agy`/`grok`/`pi` harnesses and
   remove `gemini` from `agents.yaml`, the model maps, ~13 hardcoded `{claude,codex,gemini}`
   allow-lists, eval backends, transcript adapters, and the kanban UI. pi is a CLI vendor
   pointed at OpenRouter (default model `qwen/qwen3-coder`). Foundation for everything below
   because the registry and routers must enumerate a correct, live roster.

2. **Vendor registry** — `add-live-vendor-capability-and-cost-registry` — a coordinator
   `vendor_registry` holding static capabilities (from `agents.yaml`) + dynamic availability +
   a versioned real cost table; exposes `GET /vendors` and `/vendors/{id}/availability`;
   **deletes** the hardcoded vendor list in `orchestrator.py` and **replaces** `policy.py` stub
   cost tiers. Directly overlaps the roster change's edit sites — must be sequenced adjacent to it.

3. **Structured vendor result channel** — `build-structured-vendor-result-channel` — switch
   every CLI adapter to its vendor's structured JSON output mode with typed envelopes; replace
   stdout-regex completion polling with a coordinator completion ledger; extend SDK adapter
   coverage. Hardens the dispatch layer the routers depend on.

4. **Adaptive model router** — `add-adaptive-model-router` — tier-aware model/vendor selection
   with an OpenRouter/local `openai_compat_adapter.py` and a spend ceiling. **Absorbs**
   `cross-vendor-arbitrage-instrument` and `usage-stats-multi-model` (mark those superseded).

5. **Task router** — `implement-the-task-router-vendor-x-location-x-model` — `POST /route/task`
   returning vendor × location × model × isolation × dispatch_mode from deterministic
   `routing.yaml` rules, with an audit event type and a local static fallback table.

6. **Orchestrator obeys the router** — `make-the-orchestrator-obey-the-router` — call
   `route/task` before each dispatch, execute ledger-verified vendor-switch decisions, add a
   global iteration cap / no-progress detector, and un-stub cost/wait estimation against the
   registry. Closes the decide-but-don't-act gap; depends on the router + registry existing.

7. **Coordinator LLM gateway** — `add-coordinator-llm-gateway` — a self-hosted LiteLLM proxy
   fronting OpenRouter + local Ollama/vLLM as a data plane, turning the advisory spend ceiling
   into an enforced one. Infrastructure that the router/adapters can target.

## Constraints

- **No same-file merge collisions**: items that edit `orchestrator.py` / `policy.py` /
  `agents.yaml` / CLI adapters must be ordered so the second-to-merge rebases cleanly. Call out
  every such pair in `depends_on` or in the item rationale.
- **Foundation first**: the correct vendor roster and the vendor registry are prerequisites for
  any router that enumerates vendors or reads cost/capability.
- **Absorbed changes**: `cross-vendor-arbitrage-instrument` and `usage-stats-multi-model` are
  already absorbed by `add-adaptive-model-router` — represent them as superseded, not as
  separate roadmap items.
- **Each item is an existing change**: map roadmap items to the seven change-ids above; the
  roadmap sequences them, it does not create new implementation scope.

## Phases (suggested layering — the generator should refine dependencies by reading the proposals)

- **Phase 1 — Foundation (roster + registry)**: `add-agy-grok-pi-harnesses` then
  `add-live-vendor-capability-and-cost-registry` (registry consumes the corrected roster and
  removes the hardcoded lists the roster change last touched).
- **Phase 2 — Dispatch hardening**: `build-structured-vendor-result-channel`.
- **Phase 3 — Selection**: `add-adaptive-model-router`, then
  `implement-the-task-router-vendor-x-location-x-model` (reads registry capabilities/costs).
- **Phase 4 — Enforcement + data-plane**: `make-the-orchestrator-obey-the-router` (needs the
  task router + registry) and `add-coordinator-llm-gateway` (data plane the router targets).

## Out of Scope

- New routing/vendor features beyond the seven existing changes.
- Re-implementing or re-decomposing any change's internal tasks (each change owns its own
  `tasks.md`).
- Removing harnesses other than `gemini`.
