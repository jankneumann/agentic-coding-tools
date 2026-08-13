# Change: add-atomic-harness

## Why

Atomic (`bastani-inc/atomic`, MIT, a fork of the already-integrated pi harness) adds the one
capability no roster vendor has: a durable, checkpointed workflow engine whose runs are
versioned TypeScript with schema-validated stage handoffs, resumable execution, and
machine-parseable terminal snapshots. An empirical probe (2026-08-12, findings A1–A20)
confirmed it is dispatchable through our existing config-driven CLI adapter seam
(`-p --mode json` NDJSON, pi-style parsing) **and** that headless workflow runs emit
structured `workflow.run.end {runId, status, result}` events — a clean contract for
dispatching whole multi-stage workflows as single sub-agent calls. Integrating it now
(a) adds reviewer diversity via distinct OpenRouter models, and (b) lets us pilot
durable workflow execution for long-running phases, where our `loop-state.json` resume
is weakest. Doing this as a trial also motivates a reusable **experimental-vendor tier**,
so future harness evaluations stop requiring a four-spec roster reopening each time.

## What Changes

- Introduce an **experimental provider class** in `agents.yaml` / `agents_config.py`:
  experimental vendors are dispatchable through `CliVendorAdapter` and review rotation,
  and carry an optional tier map, but are exempt from the closed provider-model-map
  schema enum, eval-backend parity, and the manual-smoke-path roster until promoted to
  first-class. Unknown *non-experimental* providers still fail loudly (roster integrity
  preserved).
- Add `atomic-local` agent entry (`type: atomic`, `trust_level` per experimental policy,
  `isolation: worktree`) with `cli.command: atomic`, three dispatch modes
  (`review`/`alternative`/`quick`), `--provider openrouter` pinned explicitly per probe
  fact A10 (ambient credential auto-detection), and model slugs **distinct from pi's
  qwen3-coder lineup** (candidates from the GLM/DeepSeek/MiniMax families; final slugs
  fixed by the live re-probe task).
- Extend `review_dispatcher.py` support surface for atomic: reuse the NDJSON parsing
  path (probe A3/A4: prompt echoed back as user message — take last assistant terminal
  message), reauth hint "set OPENROUTER_API_KEY or run interactive `/login`" (A6), and
  discovery via `which atomic`.
- **Level 2 pilot — workflow-executor dispatch**: a new `workflow_dispatch.py` adapter in
  `skills/parallel-infrastructure/scripts/` that launches
  `atomic -p --mode json --approve '/workflow <name> k=v ...'` in a worktree, budgets for
  first-run TS compile latency (A13), and parses `workflow.run.start`/`workflow.run.end`
  events into a typed result. Piloted on exactly one seam: an alternative review/repair
  loop executor selectable in `fix-scrub` (behind an opt-in flag), using Atomic's builtin
  `adversarial-verification` workflow or a repo-authored `.atomic/workflows/*.ts`
  definition. No autopilot phase switches executors in this change.
- Add `atomic_cli.py` transcript adapter (`~/.atomic/agent/sessions/<cwd-slug>/*.jsonl`,
  session `version: 3`, probe A16), written against the
  `build-structured-vendor-result-channel` envelope contract where applicable.
- Record the empirical probe evidence table (A1–A20) in `design.md`; live-dispatch
  enablement is gated on a network-permitted re-probe (A18: model calls were
  environment-blocked in the probe container).
- Docs: vendor roster prose, provider-smoke docs, kanban-viz vendor swimlane entry
  (experimental badge).
- **Non-goals**: no eval backend in this change (experimental tier defers it); no
  autopilot phase executor switch; no promotion of atomic to first-class; no Anthropic
  subscription login through atomic (probe A20: bills as per-token extra usage).

## Approaches Considered

### Approach 1: Sixth first-class provider (pi playbook verbatim)

**Description**: Mirror `2026-07-24-add-agy-grok-pi-harnesses` exactly — reopen the closed
5-provider enum in `provider-model-map.schema.json`, add MODIFIED requirements to all four
roster specs, ship an eval backend, extend every allow-list.

- **Pros**: Uniform roster, no new concepts; eval framework can benchmark atomic
  immediately; proven decomposition to copy.
- **Cons**: Largest spec surface (4 delta specs + schema version bump) for what is
  explicitly a trial; roster reopening repeats for every future harness experiment;
  eval-backend parity is wasted work if the trial fails; collides hardest with
  `add-adaptive-model-router`.
- **Effort**: L

### Approach 2: Experimental-vendor tier + scoped workflow-executor pilot

**Description**: Introduce a reusable "experimental" provider class exempt from roster
parity requirements, register atomic under it for review dispatch, and pilot the workflow
engine through one opt-in seam (`fix-scrub`) with a dedicated `workflow_dispatch.py`
adapter parsing `workflow.run.end` events.

- **Pros**: Spec deltas are additive (define the experimental class once) instead of
  editing "exactly five" wording in four places; the class is reusable for every future
  harness trial; exercises the actually-novel capability (durable workflows) instead of
  only duplicating pi's review role; cheap to retire if the trial fails (delete one
  agents.yaml entry + one adapter).
- **Cons**: Introduces a new concept the specs must define precisely (promotion criteria,
  exemption boundaries); atomic can't be benchmarked by the eval framework until promoted;
  two-tier roster adds a conditional to smoke/validation paths.
- **Effort**: M–L

### Approach 3: Workflow-executor only (no roster entry)

**Description**: Skip the vendor roster entirely; add only the `workflow_dispatch.py`
adapter and treat atomic as an external workflow runtime invoked by skills, like a build
tool.

- **Pros**: Smallest footprint — no roster/spec changes at all; pure capability
  experiment.
- **Cons**: Atomic gets no review-rotation exposure, so we learn nothing about it as a
  reviewer; bypasses vendor-diversity, health-check, and audit machinery, creating an
  unmanaged dispatch path (exactly what the config-driven adapter seam exists to prevent);
  a later roster addition would redo the auth/parsing work.
- **Effort**: M

### Recommended

**Approach 2.** It spends effort on the two things that are genuinely new — the
experimental-vendor concept (reusable, directly serves the "explore how useful it can be"
goal) and the workflow-executor pilot (the only capability pi doesn't already provide) —
while avoiding Approach 1's four-spec reopening for a trial vendor and Approach 3's
unmanaged dispatch path. The falsifiable pilot gives a concrete promote-or-retire
decision point.

### Selected Approach

**Approach 2 selected at Gate 1 (2026-08-12), with the four discovery-gate parameters
confirmed**: (1) scope = Level 1 roster entry + scoped Level 2 pilot in one change;
(2) roster semantics = experimental-vendor tier; (3) models = OpenRouter with slugs
distinct from pi, finalized at live re-probe; (4) sequencing = land after
`add-frontier-model-tier`; write the transcript adapter to the
`build-structured-vendor-result-channel` envelope contract; accept rebase risk against
`add-adaptive-model-router`.

## Impact

**Affected specs (delta files in this change):**

| Capability | Delta | Nature |
| --- | --- | --- |
| `configuration` | `specs/configuration/spec.md` | ADDED: Experimental Provider Class requirement; MODIFIED: Provider Model Mapping Configuration (experimental vendors exempt from closed enum) |
| `skill-workflow` | `specs/skill-workflow/spec.md` | ADDED: Workflow-Executor Dispatch (atomic `/workflow` headless contract), Experimental Vendor Dispatch; MODIFIED: Reviewer Discovery Fallback (`which atomic`), Manual Provider Smoke Path (experimental selector handling) |
| `agent-archetypes` | `specs/agent-archetypes/spec.md` | MODIFIED: provider-aware resolution covers roster **plus registered experimental providers** (optional tier map) |
| `vendor-ux` | `specs/vendor-ux/spec.md` | MODIFIED: vendor selection/health surfaces show experimental badge |
| `harness-engineering` | `specs/harness-engineering/spec.md` | ADDED: atomic session transcript mining (`atomic_cli` adapter) |

`evaluation-framework/spec.md` is deliberately **not** touched (experimental exemption).

**Affected code (primary touchpoints):**
- Coordination layer: `agent-coordinator/agents.yaml`, `agent-coordinator/src/agents_config.py`
  (experimental class + optional atomic tier map), `openspec/schemas/provider-model-map.schema.json`
  (experimental exemption note only — the closed enum for first-class keys is unchanged)
- Execution layer: `skills/parallel-infrastructure/scripts/review_dispatcher.py`,
  new `skills/parallel-infrastructure/scripts/workflow_dispatch.py`,
  `skills/fix-scrub/scripts/vendor_dispatch.py` (opt-in executor flag),
  `skills/collect-transcripts/scripts/adapters/atomic_cli.py` (+ fixtures/tests)
- Governance/observability: `apps/kanban-viz` vendor map (experimental badge), docs
  (`docs/autopilot-provider-smoke.md`, roster prose)

**Rollback**: no breaking changes; retire by removing the `atomic-local` entry, the two
adapters, and the experimental-class definitions. First-class roster behavior is untouched.

**Dependencies / sequencing**: after `add-frontier-model-tier` lands; coordinate adapter
shape with `build-structured-vendor-result-channel`; rebase-watch on
`add-adaptive-model-router`.
