# Add prime-agent harness (Prime Intellect)

> Change ID: `followup-add-prime-agent-harness`
> Effort: M–L
> Precedent: `openspec/changes/archive/2026-07-24-add-agy-grok-pi-harnesses/`

## Follow-up Lineage

This proposal carries forward all unimplemented work from
`add-prime-agent-harness`. PR #360 merged the reviewed planning artifacts on
2026-08-29, but none of the 33 implementation tasks had been completed. The
original change is being archived through post-merge cleanup; this follow-up
preserves its approved design, contracts, spec deltas, dependencies, and file
scopes without claiming implementation progress.

## Why

The dispatch/review roster currently holds five vendors — `claude_code`, `codex`,
`antigravity`, `grok`, `pi`. Two goals motivate a sixth:

1. **Test the current frontier of harness design.** Prime Intellect's `prime-agent`
   (MIT-licensed, [github.com/PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent))
   is architecturally unlike every harness on the roster: the model gets a single tool —
   a persistent IPython kernel — and file edits, shell, skills, and sub-agents are
   programmatic calls inside it (the "RLM" model: context as a variable, sub-agent
   delegation as `rlm(...)` function calls). Its Continual Harness treats prompts,
   skills, and memory as state the agent itself refines (`/refine`, with rollback
   history). Registering it makes those design ideas observable in our own review
   pipelines instead of only in benchmark write-ups.
2. **Strengthen the subscription-maximization split.** Operator policy is: Claude
   models run exclusively on the Claude subscription harness (`claude_code`);
   everything else runs on metered, non-subscription lanes. `prime-agent` is wired to
   **Prime Inference** (`https://api.pinference.ai/api/v1`, OpenAI-compatible,
   `PRIME_API_KEY`), reaching open-weight frontier models (Kimi, GLM, DeepSeek, Qwen,
   MiniMax families). That adds genuine training-distribution diversity to review
   quorum and gives the vendor-diversity policy (worker ≠ validator) a sixth
   independent voice.

`prime-agent` supports Claude Pro/Max OAuth, but per its provider docs that path
draws from **extra credits billed per token** — it does not consume the flat-rate
subscription allowance the way Claude Code does. Configuring it is therefore
explicitly out of policy for this change (design D2): Claude models stay on
`claude_code`; `prime` runs non-Claude models only.

## What Changes

### Registry / config (canonical source of truth)

- **ADD** a `prime-local` agent entry to `agent-coordinator/agents.yaml` with
  `type: prime`, `cli.command: prime-agent`, `cli.dispatch_modes` for `review`
  only if the P6 admission gate passes, plus `alternative` (write) and `quick`
  (write), headless invocation via `--mode json`, `cli.api_key_env:
  PRIME_API_KEY`, correct `model_flag` / `model` / `model_fallbacks`, and mirrored
  `capabilities` / `archetypes` / `trust_level: 3` / `transport: mcp` / `profile:
  prime_local` / `isolation`.
- **ADD** `prime` provider tier maps to `model_aliases`
  (`agent-coordinator/archetypes.yaml`) and `DEFAULT_PROVIDER_MODEL_MAP`
  (`agent-coordinator/src/agents_config.py`), resolving to Prime Inference model
  slugs chosen to minimize overlap with `pi`'s OpenRouter slugs (design D4).
- **UPDATE** `openspec/schemas/provider-model-map.schema.json`: the provider key set
  is closed to five roster keys with `minProperties: 5` — extend `propertyNames.enum`
  + `required` to six and bump `schema_version` to 3 (breaking schema change; see
  Rollback).
- **EXTEND** the canonical CLI dispatch config with an optional lifecycle cleanup
  object (`cleanup.args`, `cleanup.timeout_seconds`). The coordinator schema,
  parser, and HTTP/MCP projection preserve it losslessly; the dispatcher consumes
  it without a shell and runs it after every launched synchronous dispatch attempt.

### Hardcoded provider allow-lists (fail-closed; add `prime` to each)

- `skills/autopilot/scripts/provider_dispatch.py` (`_SUPPORTED_PROVIDERS`),
  `token_budget_check.py` + `smoke_provider_dispatch.py` (argparse `choices` +
  fallback model tables),
  `skills/autopilot-roadmap/scripts/orchestrator.py` (`available = [...]`),
  `skills/autopilot-roadmap/scripts/policy.py` (`_STATIC_COST_TIERS`),
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`_RELOGIN_COMMANDS`
  / `_MANUAL_REAUTH`, per empirical fact P5; plus an NDJSON envelope-unwrap branch in
  `_parse_findings` if P3 shows a novel shape),
  `agent-coordinator/scripts/seed_kanban_board.py` (`VENDORS`),
  `agent-coordinator/src/schemas/kanban_viz/saved-view.json` (vendor enum),
  `openspec/schemas/consensus-report.schema.json` + the mirrored
  `skills/parallel-infrastructure/install_assets/` copy (vendor enum).

`agent-coordinator/scripts/setup_cloud.py` is deliberately not a vendor allow-list.
Its registry projection already derives `prime-local` into `prime_local_key`,
`--prime-local-key`, a `COORDINATION_API_KEY_IDENTITIES` entry, and the
`cprime-agent` alias. This change adds regression coverage for that generic behavior;
it does not teach setup-cloud to provision `PRIME_API_KEY`. The latter remains an
operator-supplied model-provider credential exposed only through `cli.api_key_env`,
secrets templates, and provider-authentication documentation.

### Peripheral (Core + peripheral scope, per precedent D4 parity rule)

- **Eval backend**: add `agent-coordinator/evaluation/backends/prime.py`
  (`AgentBackend` implementation over `prime-agent --mode json`, stream-parsing the
  NDJSON event stream) and register it in `backends/registry.py`. `backends/pi.py`
  is the structural template.
- **Transcript adapter**: add `skills/collect-transcripts/scripts/adapters/prime_cli.py`
  (subclass `AdapterBase`; `HARNESS_ID`, `discover_sessions`, `normalize_session`
  over `prime-agent`'s JSONL session transcripts) + fixtures.
- **Kanban UI**: add the `prime` vendor color/label to
  `apps/kanban-viz/src/components/VendorSwimlanes.test.tsx` fixtures
  (`VendorSwimlanes.tsx` itself holds no roster, per precedent D5).
- **Agent-scenarios**: add the `prime` argv template to
  `packages/agent-scenarios/src/agent_scenarios/executor.py` `vendor_commands`.

### Docs & tests

- Update supported-vendor prose (`README.md`, `agent-coordinator/CLAUDE.md`,
  `docs/skills-workflow.md`, `docs/autopilot-provider-smoke.md`, lifecycle SKILL.md
  files), `.secrets.yaml.example` (+`PRIME_API_KEY`), `config.yaml.example`,
  `openspec/config.yaml` vendor list, and all vendor-roster fixtures/asserts in the
  dispatch/vendor/autopilot/roadmap/kanban test suites.

## Impact

| Spec capability | Delta | Nature |
|---|---|---|
| `configuration` | `specs/configuration/spec.md` | MODIFIED: Provider Dispatch Configuration Discovery, Provider Model Mapping Configuration (six-provider roster, schema v3, prime → Prime Inference slugs); ADDED: typed CLI cleanup configuration and lossless HTTP/MCP projection |
| `evaluation-framework` | `specs/evaluation-framework/spec.md` | MODIFIED: Agent Backend Abstraction (six backends; prime NDJSON scenario) |
| `coordinator-kanban-viz` | `specs/coordinator-kanban-viz/spec.md` | MODIFIED: Demo Data Seeding for the Kanban Board (six-vendor swimlane coverage) |
| `skill-workflow` | `specs/skill-workflow/spec.md` | ADDED: Prime Harness Dispatch (dispatch modes, NDJSON parsing, non-blind review guard, subscription-lane policy, daemon hygiene) |
| `agent-identity` | — no delta | Existing generic registry profile/assignment sync materializes `prime_local`, while setup-cloud derives the separate `prime_local_key`; tests prove both projections. `PRIME_API_KEY` is not coordinator identity. |

Architecture layers affected: **Execution** (CLI dispatch, adapters), **Coordination**
(registry, archetype resolution), **Governance** (schema roster closure, subscription
policy). Trust: unchanged (`trust_level: 3`, same as other local CLI vendors).

Roster prose in existing `skill-workflow` scenarios that enumerates the five-vendor
roster illustratively will be swept in the plan phase, following precedent D1
(normative vs illustrative split; mechanical substitutions isolated in their own
work package).

## Approaches Considered

### A. Config-driven via the generic `CliVendorAdapter`, headless `--mode json` (Recommended)

Register `prime-agent` purely through `agents.yaml` + the allow-list edits, using the
existing vendor-agnostic dispatcher. Empirical evidence from the `pi` integration
(archive design §L7) already proved the dispatcher handles NDJSON event streams;
prime-agent's `--mode json` emits the same family of shapes (`message_end` /
`agent_end` events with assistant `content[]`).

- **Pros**: minimal-to-zero new dispatch code; identical to how all five current
  vendors integrate; prompt passes as a trailing positional (the dispatcher's default
  shape); one possible `_parse_findings` branch is the only code risk.
- **Cons**: prime-agent's daemon/worker architecture is unlike the other CLIs — a
  subprocess dispatch may leave resident worker processes (empirical fact P7 gates
  this); read-only review mode needs explicit verification (P6) because the harness
  executes model-generated Python and its docs state it is *not* a security sandbox.
- **Effort**: M

### B. ACP adapter (`prime-agent --mode acp`)

Build a new `AcpVendorAdapter` speaking Agent Client Protocol (JSON-RPC 2.0 over
stdio: `initialize` / `session/new` / `session/prompt`), which prime-agent serves
natively.

- **Pros**: protocol-typed sessions, streamed tool-call visibility, and a reusable
  adapter for every future ACP-speaking harness — would also close the known
  thinking-flag translation gap generically.
- **Cons**: a whole new adapter class for one vendor today; prime-agent's ACP mode is
  one-session-per-connection and refuses concurrent turns, which fights the
  dispatcher's fan-out model; premature until a second ACP harness is on the roster.
- **Effort**: L

### C. No CLI harness; route Prime Inference through `OpenAICompatAdapter` only

Skip `prime-agent` entirely and add Prime Inference as an HTTP endpoint
(`endpoint_kind` + `base_url` + `PRIME_API_KEY`) via the in-flight
`add-adaptive-model-router` adapter.

- **Pros**: no new binary dependency; direct spend accounting.
- **Cons**: abandons the primary goal — testing prime-agent's harness design (RLM,
  continual harness) is the point, and raw inference reaches none of it; couples this
  change to an unmerged proposal; the adapter is not yet wired into
  `discover_reviewers`.
- **Effort**: M (but delivers a different outcome, not a cheaper version of this one)

**Recommended: Approach A.** Approach C is complementary, not alternative — it is
recorded as an explicit follow-up under `add-adaptive-model-router` (Prime Inference
as an `endpoint_kind`), and Approach B as a deferred spike gated on a second ACP
harness.

## Risks / Overlap with in-flight changes

| In-flight change | Overlap | Mitigation |
|---|---|---|
| `add-live-vendor-capability-and-cost-registry` | Plans to delete the hardcoded vendor list in `orchestrator.py` and replace `policy.py` stub tiers — two of our edit sites | Shape-stable additive edits; whoever merges second rebases, same protocol as the precedent |
| `add-adaptive-model-router` | `agents.yaml` / `archetypes.yaml` tiers; Prime Inference is a natural `endpoint_kind` there | Our roster addition is additive; the Prime Inference HTTP lane is filed as a follow-up under that change, not duplicated here |
| `add-coordinator-llm-gateway` | LiteLLM data plane; a `PRIME_API_KEY` would be an upstream behind the gateway | CLI-level integration is independent of the gateway |
| `build-structured-vendor-result-channel` | Switches CLI adapters to structured JSON envelopes | prime-agent already emits structured NDJSON; aligns rather than conflicts |
| `add-dispatch-sandbox-enforcement` / `pin-isolation-contract` | `isolation:` is declared but unenforced today | Do **not** predicate the review mode's safety on `isolation: sandbox`; P6 must find a harness-native read-only guard or the review mode is withheld (see Open Decisions 2) |

Additional named risks:

- **Vendor-string collision**: `prime` and the existing `pi` share a prefix. Any grep
  gate or fixture matching `pi` unanchored will match `prime`; all roster grep gates
  in this change use word-bounded patterns, and a test SHALL assert the two vendor
  keys resolve to distinct providers end-to-end.
- **Blind-reviewer failure class** (`agents.yaml:322-340`): `pi --no-tools` once
  returned `success=True` with empty findings, having read nothing, and counted
  toward quorum. prime-agent's everything-is-Python model makes this failure mode
  *more* likely under a mis-configured review mode, so P6 requires positive evidence
  the review dispatch actually read repository files before the vendor joins quorum.
- **Daemon residue**: `prime-agent` runs daemon-backed sessions that survive terminal
  detach. Dispatch must not leak resident workers on CI or operator machines (P7;
  `prime-agent shutdown` semantics recorded in design.md).

## Rollback

The schema bump (`provider-model-map.schema.json` v2 → v3) is **BREAKING** for any
consumer validating provider maps against the closed five-key set. Rollback is a
single revert commit: the roster entry, tier maps, and allow-list additions are all
additive, and reverting restores the v2 schema unchanged. No data migration exists in
either direction (profile seeding is additive and survives roster removal by
contract).

## Open Decisions

1. **Exact Prime Inference model slugs for the four tiers** — resolved empirically in
   Phase 1 (P4) against the live Prime Inference catalog, applying design D4
   (minimize model overlap with `pi`'s OpenRouter tiers; omit `frontier` unless a
   clearly stronger reasoning model exists, per precedent).
2. **Read-only review mode** — open until P6. If prime-agent exposes no reliable
   harness-native way to prevent writes during review dispatch, the `review`
   dispatch mode is **withheld** (vendor ships with `alternative` + `quick` only and
   does not join review quorum) and a follow-up records what would unblock it. It is
   NOT acceptable to rely on the unenforced `isolation:` field.
3. **`rlm()` sub-agent cost policy** — prime-agent can spawn child agents with their
   own models from inside a dispatched session, bypassing archetype-resolved model
   policy. P8 records whether child model selection can be pinned or disabled via
   settings; the dispatch config applies that pin if it exists, else the risk is
   documented and budget-gated.
4. **Re-auth story** — P5 records whether `PRIME_API_KEY` env inheritance suffices in
   all dispatch paths and what `/login`-based OAuth state (if any operator uses it)
   means for `_RELOGIN_COMMANDS` vs `_MANUAL_REAUTH`.
