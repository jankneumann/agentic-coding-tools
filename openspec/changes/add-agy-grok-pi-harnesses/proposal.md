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

## Open Decisions (to confirm at Gate 1)
1. **Default OpenRouter model for `pi`** (pay-per-token). Recommended: a strong non-Claude,
   non-OpenAI, non-Gemini, non-xAI model to maximize vendor diversity (the whole point of pi).
2. **Exact `agy --model` slug strings** — `agy models` prints display names ("Claude Sonnet
   4.6 (Thinking)", "Gemini 3.1 Pro (High)", …); the precise `--model` value is verified
   empirically during IMPLEMENT/VALIDATE.
