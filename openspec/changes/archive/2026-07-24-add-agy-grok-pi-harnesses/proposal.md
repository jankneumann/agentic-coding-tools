# Add agy / grok / pi harnesses, remove Gemini

> Change ID: `add-agy-grok-pi-harnesses`

## Why

The multi-vendor dispatch/review system currently supports three coding harnesses —
`claude` (Claude Code), `codex`, and `gemini` (Gemini CLI). **The Gemini CLI has been
discontinued**, and three new harnesses are installed on the operator's machine and should
become first-class dispatch/review targets:

- **antigravity** (`agy`, v1.1.3) — subscription-backed, local CLI. Claude-Code-shaped
  interface (`--print` + stdin, `--model`, `--mode plan`). Its model menu spans Gemini 3.x,
  Claude 4.6, and GPT-OSS — so it also restores Gemini-family model coverage through a
  different harness after the standalone gemini vendor is retired.
- **grok** (`grok`, "Grok Build" v0.2.106) — subscription-backed (xAI/X), local CLI.
  Headless via `-p`/`--prompt-file` with `--output-format json` and native `--json-schema`
  structured output. Default model `grok-4.5`.
- **pi** (`pi`, v0.80.10) — pay-per-token via **OpenRouter**, local CLI. First-class
  OpenRouter provider support (`--provider openrouter`, `OPENROUTER_API_KEY`). Adds genuine
  training-distribution diversity by reaching models outside the subscription harnesses.

Vendor diversity (worker ≠ validator vendor, per `policies.vendor_diversity`) is only as
strong as the roster. Growing from 2 healthy vendors (claude, codex) to 5 (claude, codex,
antigravity, grok, pi) materially strengthens review convergence, and retiring a dead
harness removes a class of silent-failure (dispatch to a discontinued service).

## What Changes

### Registry / config (canonical source of truth)
- **ADD** `antigravity-local`, `grok-local`, `pi-local` agent entries to
  `agent-coordinator/agents.yaml`, each with `cli.dispatch_modes` for `review` (read-only),
  `alternative` (write), and `quick` (write), correct `model_flag` / `model` /
  `model_fallbacks` / `prompt_via_stdin`, and mirrored `capabilities` / `archetypes` /
  `trust_level` / `transport` / `isolation`.
- **REMOVE** `gemini-local` and `gemini-remote` from `agents.yaml`.
- **UPDATE** `DEFAULT_PROVIDER_MODEL_MAP` (`agent-coordinator/src/agents_config.py`) and
  `model_aliases` (`agent-coordinator/archetypes.yaml`): add `antigravity` / `grok` / `pi`
  provider tier maps, remove `gemini`.

### Hardcoded provider allow-lists (swap gemini → new roster)
- `skills/autopilot/scripts/provider_dispatch.py` (`_SUPPORTED_PROVIDERS`),
  `token_budget_check.py` + `smoke_provider_dispatch.py` (argparse `choices`),
  `skills/autopilot-roadmap/scripts/orchestrator.py` (`available=[...]`),
  `skills/autopilot-roadmap/scripts/policy.py` (`_STATIC_COST_TIERS`),
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`_RELOGIN_COMMANDS`;
  and remove the Gemini `-o json` envelope-unwrap special case),
  `agent-coordinator/scripts/seed_kanban_board.py` (`VENDORS`).

### Peripheral (Core + peripheral scope)
- **Eval backends**: remove `agent-coordinator/evaluation/backends/gemini_jules.py` and its
  `__all__` export; add `grok` / `pi` / `antigravity` backends (or record as an explicit
  follow-up if live eval coverage is deferred — removal of gemini's is required either way).
- **Transcript adapters**: remove `skills/collect-transcripts/scripts/adapters/gemini_cli.py`
  (+ `tests/fixtures/gemini_cli/`); add `agy_cli` / `grok_cli` / `pi_cli` adapters.
- **Kanban UI**: update `apps/kanban-viz/src/components/VendorSwimlanes.tsx` (+ test) vendor
  color/label map — add three, remove gemini.
- **Wrappers / harness dirs**: remove `agent-coordinator/scripts/gemini_wrapper.sh` and the
  repo-root `.gemini/` harness config dir.

### pi → OpenRouter
- Register `pi-local` as a CLI vendor with `--provider openrouter`; ensure
  `OPENROUTER_API_KEY` is resolvable by the API-key resolver / env passthrough for the pi
  subprocess. (Per operator decision: pi CLI → OpenRouter, **not** the direct
  `openai_compat_adapter.py` HTTP path.)

### Docs & tests
- Update supported-vendor prose (`README.md`, `agent-coordinator/CLAUDE.md`,
  `docs/skills-workflow.md`, `docs/autopilot-provider-smoke.md`, skill docs) to the new roster.
- Update all vendor-name fixtures/asserts in the dispatch/vendor/autopilot/roadmap/kanban test
  suites (see `tasks.md` for the enumerated list).

## Approaches Considered

### A. Config-driven via the generic `CliVendorAdapter` (Recommended)
Add the three harnesses purely through `agents.yaml` + the hardcoded allow-list edits, relying
on the existing generic dispatcher (`review_dispatcher.py`). grok is fitted with
`--prompt-file /dev/stdin` + `prompt_via_stdin: true` (its trailing positional would otherwise
open the interactive TUI); agy uses `--print` + stdin like claude; pi passes the prompt as a
trailing positional with `--provider openrouter`.
- **Pros**: Minimal/zero new dispatch code; leverages the vendor-agnostic adapter the repo
  already ships; smallest diff; no new wrapper scripts (consistent with retiring
  `gemini_wrapper.sh`); grok gets clean structured output via `--output-format json` +
  `--json-schema` pointed at `review-findings.schema.json`.
- **Cons**: Depends on `--prompt-file /dev/stdin` behaving correctly under a subprocess pipe
  (verified in VALIDATE); exact `agy --model` slug strings must be confirmed empirically.
- **Effort**: M

### B. Config + thin per-harness wrapper scripts
Add `agy_wrapper.sh` / `grok_wrapper.sh` that normalize prompt/stdin/output quirks, mirroring
the (retired) `gemini_wrapper.sh` pattern.
- **Pros**: Most robust to CLI idiosyncrasies; isolates quirks behind a stable interface.
- **Cons**: Reintroduces the wrapper pattern this change is removing; more moving parts; extra
  indirection to maintain per harness.
- **Effort**: M–L

### C. Config for agy/grok as CLI + route pi through `OpenAICompatAdapter`
Register agy/grok as CLI vendors but dispatch pi via the in-flight
`openai_compat_adapter.py` (direct HTTP to OpenRouter) instead of the `pi` CLI.
- **Pros**: No `pi` CLI dependency; captures OpenRouter `generation_id` for spend
  reconciliation.
- **Cons**: Couples this change to the unmerged `add-adaptive-model-router` proposal (schema +
  orchestrator wiring not yet on main); contradicts the operator decision to use the pi CLI.
- **Effort**: L

**Recommended: Approach A**, with **Approach B applied narrowly to grok only** as a fallback
if `--prompt-file /dev/stdin` proves unreliable during VALIDATE. Matches all four operator
decisions (full OpenSpec flow, gemini removed entirely, Core + peripheral scope, pi CLI →
OpenRouter).

### Selected Approach

**Approach A — config-driven via the generic `CliVendorAdapter`** (Gate 1, approved by
operator during roadmap item `ri-01` execution). Approach B stays available as a narrow
fallback for grok only, if `--prompt-file /dev/stdin` proves unreliable under a subprocess
pipe during VALIDATE. Approach C is rejected: it couples this change to the unmerged
`add-adaptive-model-router` proposal (roadmap `ri-04`) and contradicts the operator decision
to dispatch pi through its CLI.

Two decisions were settled at Gate 1 that the original proposal left open:

#### D1. Spec delta covers the full gemini surface, not just the normative roster

Gemini appears in **37 requirements across 8 specs**. Roughly a third are *normative* — they
declare the supported vendor roster contractually (`configuration` provider discovery and
model mapping, `coordinator-kanban-viz` swimlanes and seeding, `agent-archetypes`,
`agent-identity` `gemini-cloud` profile seeding, `evaluation-framework` backend abstraction,
and the `skill-workflow` requirements naming gemini as a supported provider). The remainder
are *illustrative* — gemini appears as a stand-in vendor name in WHEN/THEN scenario prose
(`Cross-Vendor Finding Matching`, `Consensus Synthesizer`, `Vendor Diversity`,
`Total Failure Warning`, and similar).

**Decision**: rewrite both categories in this change. Leaving illustrative prose behind would
keep a discontinued CLI referenced across the spec tree as if it were a live dispatch target,
which is precisely the silent-failure class this change exists to remove. The scenario-hygiene
edits are mechanical substitutions and are isolated into their own work package so they do not
gate the normative roster edits.

#### D2. No per-vendor runtime asset directories — `.gemini/` is deleted, nothing replaces it

The original proposal removed the repo-root `.gemini/` harness config dir without saying
whether agy/grok/pi need equivalents. They do not.

- **grok** reads Claude Code assets with no configuration: *"Grok is fully compatible with
  Claude Code with zero configuration needed. Grok automatically reads Claude Code
  marketplaces, plugins, skills, MCPs, agents, hooks, and instruction files (`CLAUDE.md`, …)
  alongside `.grok/`."* — https://docs.x.ai/build/features/skills-plugins-marketplaces
  `install.sh` already writes `.claude/skills/`, so grok is served today.
- **agy** and **pi** read `.agents/skills/`, which is already an `install.sh` target
  (`skills/install.sh:189`).
- Pointing grok additionally at the project's `.agents/skills/` requires `[skills] paths` in
  `~/.grok/config.toml` — a **machine-local operator file outside the repository**. Per the
  same xAI page, grok's automatic `~/.agents/skills/` discovery is *user-level* only, not the
  project tree. This is therefore documented as optional operator setup, **not** a repo change.

#### D3. `antigravity` is the single canonical provider key; `agy` is only a binary name

The proposal originally wrote `antigravity-local` while roadmap `ri-01`'s acceptance criteria
wrote `agy`. Existing provider keys follow product names, not binaries — `claude_code` for the
`claude` binary, `codex`, `gemini` (`agent-coordinator/src/agents_config.py:36-50`).

**Decision**: `antigravity` is the one canonical string. It is used for the
`DEFAULT_PROVIDER_MODEL_MAP` provider key, the `archetypes.yaml` `model_aliases` key, the
`agents.yaml` entry `antigravity-local` and its `type:`, the transcript adapter
(`antigravity_cli.py`), the kanban vendor label, and every allow-list. `agy` appears **only**
as `cli.command`. No short form, no alias — a second string for one vendor would reintroduce
exactly the roster-drift class this change removes. Roadmap `ri-01`'s acceptance wording is
updated to match.

#### D4. Eval backends reach full roster parity in this change

The proposal left new eval backends as "or record as an explicit follow-up".

**Decision**: remove `gemini_jules.py` **and** add `AgentBackend` implementations for
`grok`, `pi`, and `antigravity`, with tests. Rationale: `evaluation-framework`'s
*Agent Backend Abstraction* requirement enumerates a backend per first-class provider, so
shipping the roster without backends would land the spec and the code in disagreement — the
same drift D3 exists to prevent. grok is cheapest (native `--output-format json` +
`--json-schema`); pi and antigravity follow the generic CLI shape.

**Consequence**: this change also corrects a pre-existing spec drift. `skill-workflow`'s
*Canonical Skill Distribution* requirement names runtime trees `.claude/skills/`,
`.codex/skills/`, `.gemini/skills/` and an `install.sh --agents claude,codex,gemini`
invocation. `install.sh` supports only `claude` → `.claude/skills` and `agents` →
`.agents/skills` (`skills/install.sh:188-189`), and `.gemini/` contains only `commands/opsx`
— no skills tree ever existed there. The requirement is realigned to what `install.sh`
actually does.

## Risks / Overlap with in-flight changes

This change edits surfaces that several **active (unmerged) proposals** also target. On `main`
the hardcoded lists still exist, so these edits are valid today; whoever merges second rebases.

| In-flight change | Overlap | Mitigation |
|---|---|---|
| `add-live-vendor-capability-and-cost-registry` | Plans to **delete** the hardcoded vendor list in `orchestrator.py` and **replace** `policy.py` stub tiers — two of our edit sites | Our edits keep the same structure; if it lands first, we drop those two edits and register the new vendors in its registry instead |
| `add-adaptive-model-router` | Touches `agents.yaml` / `archetypes.yaml` tiers + adds `openai_compat_adapter.py` | Our roster additions are additive to the tier maps; no schema change |
| `add-coordinator-llm-gateway` | OpenRouter/LiteLLM data-plane | Our pi→OpenRouter is CLI-level, independent of the gateway |
| `build-structured-vendor-result-channel` | Switches every CLI adapter to structured JSON envelopes | grok already emits `--output-format json`; aligns rather than conflicts |

**Recommendation**: proceed now (additive roster change, orthogonal intent), record this overlap
in the session log, and coordinate merge order with the registry/router changes.

## Open Decisions

1. ~~**Default OpenRouter model for `pi`**~~ — **RESOLVED**: `qwen/qwen3-coder`, fixed by
   roadmap item `ri-01` in `openspec/roadmaps/model-routing-platform/roadmap.yaml`. Satisfies
   the diversity goal (non-Claude, non-OpenAI, non-Gemini, non-xAI).
2. **Exact `agy --model` slug strings** — still open. `agy models` prints display names
   ("Claude Sonnet 4.6 (Thinking)", "Gemini 3.1 Pro (High)", …); the precise `--model` value
   must be verified empirically during IMPLEMENT/VALIDATE. Tracked as task 1.1 (E1).
3. **grok `--prompt-file /dev/stdin` under a subprocess pipe** — still open, verified in
   VALIDATE. If it fails, fall back to Approach B for grok only (task 1.2, fact E2).
