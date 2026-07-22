# Vendor roster contract

The coordination boundary for this change. Every work package writes against this table; if a
package needs a string not listed here, that is a planning defect, not a licence to invent one.

## Canonical strings

Exactly one string identifies each vendor. A second form for the same vendor is what produced
the ~13 drifting allow-lists this change removes, so aliases are prohibited (proposal D3).

| Provider key | CLI binary | `agents.yaml` entry | `type:` | Auth model |
|---|---|---|---|---|
| `claude_code` | `claude` | `claude-local` | `claude` | subscription |
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

`antigravity` tier slugs are resolved by task **2.1**; `grok` tier slugs by task **2.6**. Both
are recorded in `design.md` § Empirical CLI findings. **No package may hardcode a tier slug for
these two vendors before task 2.10 completes.**

> Corrected in PLAN_REVIEW round 1 (finding C6/C4, confirmed by both vendors). This section
> previously credited tasks 2.1 and 2.2 with resolving both vendors' slugs. Task 2.2 verifies
> grok's *stdin delivery*, not its model names — so grok's slugs had no empirical source at all
> while tasks 3.5 and 3.8 depended on having them. Task 2.6 was added to close the gap.

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
as optional operator setup (task 9.3), never committed.

## Dispatch shape

Every row below is a **hypothesis until its empirical task confirms it**. No package may encode
these shapes before task 2.10 completes.

| Vendor | Prompt delivery | Verified by | Structured output | Verified by |
|---|---|---|---|---|
| `antigravity` | `--print` + stdin (Claude-shaped) | task 2.8 (E7) | none declared | — |
| `grok` | `--prompt-file /dev/stdin`, `prompt_via_stdin: true` | task 2.2 (E2) | `--output-format json`, `--json-schema` | task 2.7 (E6) |
| `pi` | trailing positional, `--provider openrouter` | task 2.9 (E8) | none declared | — |

`grok`'s `--json-schema` is pointed at `review-findings.schema.json` for review dispatch —
**subject to task 2.7 confirming it emits a conforming envelope.** Task 5.2 builds grok's eval
backend on that assumption; if 2.7 refutes it, 5.2 must be re-scoped to text parsing before it
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
