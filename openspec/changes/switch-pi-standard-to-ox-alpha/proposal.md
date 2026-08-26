# Change: switch-pi-standard-to-ox-alpha

**Status**: Draft
**Created**: 2026-08-25
**Author**: Claude (direct authoring — single-slug config change, no multi-agent plan phase)

## Why

The `pi` vendor's `standard` tier is the roster's default OpenRouter route: it is
what `analyst`, `implementer`, `reviewer`, `runner`, and `documenter` archetypes
resolve to, so it carries most pi-dispatched work. The operator wants that route
pointed at `stealth/ox-alpha`.

The slug is not a free-floating setting. `openspec/specs/configuration/spec.md`
pins it as a SHALL (`its default model SHALL be qwen/qwen3-coder`), and
`test_pi_tiers_are_openrouter_slugs` asserts the literal with a comment stating
that the assertion *is* the spec's SHALL rather than an incidental value. Moving
the slug in config alone would leave code contradicting the spec and fail that
test; the correct unit of change is the requirement plus its four projections.

## What Changes

- **MODIFIED** `configuration` — the `pi` default model requirement no longer
  names a specific slug. It states the invariants that actually matter (OpenRouter
  `<publisher>/<model>` form; reaches models outside the subscription harnesses)
  and moves the concrete default into config, where an operator can change it
  without a spec amendment.
- `agent-coordinator/src/agents_config.py` — `pi.standard` → `stealth/ox-alpha`.
- `agent-coordinator/archetypes.yaml` — `pi.standard` → `stealth/ox-alpha`.
- `agent-coordinator/agents.yaml` — `pi-local` `model:` → `stealth/ox-alpha`.
- `agent-coordinator/tests/test_agents_config.py` — the `standard` assertion
  follows the requirement: it keeps asserting slug *form* for every tier, and
  stops asserting one hardcoded publisher.

Unchanged: `frontier` (`moonshotai/kimi-k3`), `premium`
(`qwen/qwen3-coder-plus`), `economy` (`qwen/qwen3-coder-flash`).

## Why the slug leaves the spec

Two options were available: amend the SHALL to name `stealth/ox-alpha`, or stop
naming a slug in the spec at all. This proposal takes the second.

A stealth/cloaked OpenRouter model is temporary by construction — it is retired
without notice when the cloak lifts. A spec requirement that names one guarantees
a spec amendment on someone else's schedule, and guarantees the repo will at some
point ship a spec whose SHALL names a slug OpenRouter no longer serves. The
durable requirement is the *shape* of the value and the reason the tier exists;
the specific model is configuration.

This narrows the spec's guarantee, which is a real trade-off: the spec no longer
lets a reader learn the default by reading the spec. That is the intended
outcome — the config file is the honest place to learn it — but it is a
deliberate loosening, not an oversight.

## Impact

- **Affected specs**: `configuration`
- **Affected code**: `agent-coordinator/{src/agents_config.py,archetypes.yaml,agents.yaml}`,
  `agent-coordinator/tests/test_agents_config.py`
- **Risk — prompt retention by an anonymous provider**: verified against the
  model's OpenRouter page rather than assumed. Its stated policy:

  > "Prompts and completions for this model are retained by the provider and are
  > not used for training; all other use is governed by the Stealth Model Terms."

  > "It is developed and operated by a third-party provider who has chosen to
  > remain anonymous during this preview. OpenRouter routes requests to it and is
  > not its developer, owner, or provider."

  So retention is confirmed and training is explicitly excluded. `pi-local`
  dispatches with repository context, which means this route sends repo content
  to a provider whose identity is undisclosed, retained for an unstated period,
  under terms OpenRouter does not own. The $0 pricing is the consideration for
  that arrangement. Recorded here so the trade is visible in the decision record;
  the operator has accepted it.
- **Risk — abrupt retirement**: when the cloak lifts, `stealth/ox-alpha` stops
  resolving. `pi-local` retains `model_fallbacks: ["qwen/qwen3-coder-flash"]`,
  which is deliberately left on a stable published slug so the fallback survives
  the primary's retirement. `premium` and `economy` staying in the qwen3-coder
  family serves the same purpose at the tier level.
- **Verified**: `stealth/ox-alpha` confirmed present on OpenRouter (2026-08-26),
  1,048,576-token context, $0/$0 pricing, with `tools` and `tool_choice` in
  `supported_parameters`. See task 4.3 for the full evidence.
- **Not affected**: `add-adaptive-model-router` (active) proposes replacing
  static tier config with a learned resolver. That change supersedes this one by
  design; this proposal deliberately does not anticipate it, because leaving a
  correct static default in place is what the router will migrate *from*.
