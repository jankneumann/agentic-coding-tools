# Add optional `frontier` model tier

> Change ID: `add-frontier-model-tier`

## Why

The three-tier model vocabulary (`premium` / `standard` / `economy`) is now coarser than the
fleet. Frontier-class models exist above each vendor's premium tier (Claude Fable above Opus;
`gpt-5.6-sol` above `gpt-5.5`), and planning is empirically where premium-tier models get
lost, while frontier models are overkill for scoped implementation. There is currently no
addressable slot for "this vendor's best reasoning model", so operators either run whole
sessions on a frontier model or fall back to per-run `AUTOPILOT_PHASE_MODEL_OVERRIDE` env
vars.

This lands ahead of `add-agy-grok-pi-harnesses` so the roster expansion inherits the tier
vocabulary (each new vendor decides whether to define `frontier`) instead of retrofitting it.

## What Changes

- **ADD** optional `frontier` tier to the provider model map. Base tiers stay required per
  provider; `frontier` MAY be omitted. Resolution falls back to that provider's `premium`
  model when `frontier` is unmapped — archetypes can request frontier-class reasoning without
  every provider carrying one.
- **ADD** `frontier` aliases: `claude_code: fable`, `codex: gpt-5.6-sol`. `gemini` defines
  none (fallback path; it is being retired by the in-flight harness change anyway).
- **UPDATE** `architect` archetype `model: premium` → `model: frontier`. PLAN, PLAN_ITERATE,
  and PLAN_FIX now think at frontier tier; `implementer` stays `standard` with `premium`
  escalation, `reviewer`/`gatekeeper` stay `premium`. Frontier spend is planning-only.
- **ADD** `openspec/schemas/provider-model-map.schema.json` — the contract's stable home,
  `schema_version: 2` (optional `frontier` per provider; provider key set left open — the
  in-flight harness change closes it to the new roster). Contract tests are repointed here;
  tests must never resolve schemas inside change directories, which move on archive.
- **UPDATE** `agents_config.py`: `OPTIONAL_MODEL_TIERS`, schema enums accept `frontier`,
  `resolve_provider_model` fallback, `DEFAULT_PROVIDER_MODEL_MAP` at `schema_version: 2`.
- **UPDATE** `provider_dispatch.py` `_CLAUDE_ALIASES` gains `fable` (non-Claude-provider
  alias-leak guard covers it).
- **FIX** (baseline repair, absorbed): the 5 failing `skills/tests/vendor-neutral-autopilot`
  tests — schema path pointed at an archived change dir, `phase-dispatch-contract.md` path
  ditto, and a `write_capable`-less fixture. This subsumes task 0.2 of
  `add-agy-grok-pi-harnesses`, which should drop it on rebase.

## Impact

- Affected specs: `agent-archetypes` (ADDED requirement)
- Affected code: `agent-coordinator/src/agents_config.py`, `agent-coordinator/archetypes.yaml`,
  `skills/autopilot/scripts/provider_dispatch.py`, `openspec/schemas/` (new),
  `skills/tests/vendor-neutral-autopilot/`
- Coordination: `add-agy-grok-pi-harnesses` rebases on this — its task 0.2 becomes obsolete,
  its task 3.6 reduces to tightening the provider key set in the promoted schema, its task
  2.3's `schema_version` bump is already done here. Empirical caveat: the `fable` /
  `gpt-5.6-sol` slugs are exercised on first dispatched PLAN phase; if a CLI rejects the
  alias, the fix is a one-line `model_aliases` edit.
