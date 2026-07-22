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

`antigravity` and `grok` tier slugs are resolved empirically in tasks 2.1 and 2.2 and are
recorded in `design.md` § Empirical CLI findings. **No package may hardcode a tier slug for
these two vendors before task 2.5 completes.**

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

| Vendor | Prompt delivery | Structured output |
|---|---|---|
| `antigravity` | `--print` + stdin (Claude-shaped) | none declared |
| `grok` | `--prompt-file /dev/stdin`, `prompt_via_stdin: true` | `--output-format json`, `--json-schema` |
| `pi` | trailing positional, `--provider openrouter` | none declared |

`grok`'s `--json-schema` is pointed at `review-findings.schema.json` for review dispatch.

## Downstream stability

Two later roadmap items edit code this change touches. Keep the following shapes stable so
their edits stay clean removals rather than rewrites:

- `skills/autopilot-roadmap/scripts/orchestrator.py` — the vendor list at line 319 is **deleted**
  by `ri-02` in favour of the vendor registry. Update its contents, not its structure.
- `skills/autopilot-roadmap/scripts/policy.py` — `_STATIC_COST_TIERS` is **replaced** by `ri-02`'s
  real cost table. Update its contents, not its structure.
