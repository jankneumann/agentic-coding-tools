# Vendor roster contract

The coordination boundary for this change. Every work package writes against this table; if a
package needs a string not listed here, that is a planning defect, not a licence to invent one.

## Canonical strings

Exactly one string identifies each vendor. A second form for the same vendor is what produced
the ~13 drifting allow-lists this change removes, so aliases are prohibited (proposal D3).

| Provider key | CLI binary | `agents.yaml` entry | `type:` | Auth model |
|---|---|---|---|---|
| `claude_code` | `claude` | `claude-local` | `claude_code` | subscription |
| `codex` | `codex` | `codex-local` | `codex` | subscription |
| `antigravity` | `agy` | `antigravity-local` | `antigravity` | subscription |
| `grok` | `grok` | `grok-local` | `grok` | subscription (xAI/X) |
| `pi` | `pi` | `pi-local` | `pi` | pay-per-token via OpenRouter |

**`agy` is never a provider key.** It appears only as `cli.command` and in the binary-detection
fallback (`which agy`).

**`gemini` is retired.** It is not a provider key, an `agents.yaml` entry, a model-map key, or a
valid `AUTOPILOT_PROVIDER` value. Configuration naming it MUST fail with a structured error
rather than falling back.

## Model tiers

`pi` resolves to OpenRouter slugs in `<publisher>/<model>` form; its `standard` tier is
`qwen/qwen3-coder`, fixed by roadmap item `ri-01`.

Tier entries are either a bare model id or `{model, thinking}` — thinking level is part of
the model definition (see `add-frontier-model-tier`; tiers optimize cost per successful
task, not cost per token). Operator direction for the new vendors (2026-07-22):

- **grok**: `premium` and `standard` are both `grok-4.5`, differentiated by thinking
  budget — task 1.2 resolves the budget flag/values empirically.
- **pi**: `frontier` candidate is **Kimi 3** (resolve the exact OpenRouter slug in task
  1.3 and check the OpenRouter cost-vs-performance Pareto data before finalizing);
  `standard` stays `qwen/qwen3-coder` (roadmap `ri-01` decision).
- **antigravity**: tiers resolved by task 1.1 (E1); `frontier` only if the model menu
  surfaces a clearly stronger reasoning option.

`antigravity` tier slugs are resolved by task **1.1** (E1); `grok` tier slugs by task **1.2**
(E5). Both are recorded in `design.md` § Empirical CLI findings. **No package may hardcode a
tier slug for these two vendors before checkpoint 1.4 (human review) passes.**

> Round 1 found this section crediting a stdin-delivery task with resolving model slugs; the
> slug facts (E1, E5) now have their own tasks. In revision 2 each vendor has one empirical
> task carrying all its facts (tasks 1.1–1.3), reviewed together at checkpoint 1.4.

## Runtime skill directories

No per-vendor runtime directory is committed. `install.sh` writes `.claude/skills/` and
`.agents/skills/`; those are the only mirrors.

| Vendor | Reads | Source |
|---|---|---|
| `claude_code` | `.claude/skills/` | `install.sh` target |
| `antigravity` | `.agents/skills/` | `install.sh` target |
| `pi` | `.agents/skills/` | `install.sh` target |
| `grok` | `.claude/skills/` | Claude Code compatibility, zero config — https://docs.x.ai/build/features/skills-plugins-marketplaces |

Pointing `grok` at the project's `.agents/skills/` additionally requires `[skills] paths` in
`~/.grok/config.toml`. That file is machine-local and outside the repository; it is documented
as optional operator setup (task 5.6), never committed.

## Dispatch shape

Every row below is a **hypothesis until its empirical task confirms it**. No package may encode
these shapes before checkpoint 1.4 (human review) passes.

| Vendor | Prompt delivery | Verified by | Structured output | Verified by |
|---|---|---|---|---|
| `antigravity` | `--print` + stdin (Claude-shaped) | task 1.1 (E7) | none declared | — |
| `grok` | `--prompt-file /dev/stdin`, `prompt_via_stdin: true` | task 1.2 (E2) | `--output-format json`, `--json-schema` | task 1.2 (E6) |
| `pi` | trailing positional, `--provider openrouter` | task 1.3 (E8) | none declared | — |

`grok`'s `--json-schema` is pointed at `review-findings.schema.json` for review dispatch —
**subject to task 1.2 confirming it emits a conforming envelope (E6).** Task 2.6 builds grok's eval
backend on that assumption; if E6 is refuted, 2.6 must be re-scoped to text parsing before it
starts.

> The "Verified by" columns were added in PLAN_REVIEW round 1 (finding C4/C10, confirmed by
> both vendors). Four of these shapes were asserted with no empirical task behind them while
> downstream packages consumed all of them.

## Downstream stability

Two later roadmap items edit code this change touches. Keep the following shapes stable so
their edits stay clean removals rather than rewrites:

- `skills/autopilot-roadmap/scripts/orchestrator.py` — the vendor list at line 319 is **deleted**
  by `ri-02` in favour of the vendor registry. Update its contents, not its structure.
- `skills/autopilot-roadmap/scripts/policy.py` — `_STATIC_COST_TIERS` is **replaced** by `ri-02`'s
  real cost table. Update its contents, not its structure.
