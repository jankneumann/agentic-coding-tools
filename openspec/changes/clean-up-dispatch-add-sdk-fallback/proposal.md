# Proposal: Clean Up Dispatch and Add SDK Fallback

## Why

The review dispatcher's vendor dispatch has a design flaw: the `*-remote` agent entries in `agents.yaml` use the **same CLI binary** as their `*-local` counterparts (`claude`, `codex`, `gemini`). This means:

- If the CLI is installed → both local and remote agents are "available", but local is always preferred → remote entries are redundant
- If the CLI is NOT installed → neither local nor remote agents work → the remote fallback is useless

The result is that multi-vendor review diversity depends entirely on which CLIs are installed locally. If only `claude` is installed (common case), no vendor diversity is achieved — the dispatcher finds no other available vendors and silently no-ops.

Adding SDK-based dispatch (using vendor APIs directly via Python SDKs) would provide a genuine fallback: when a vendor's CLI isn't installed, the dispatcher can still reach that vendor through its API. API keys must be resolved securely via OpenBao, using the `openbao_role_id` already declared on each agent in `agents.yaml`.

## What Changes

1. **Remove redundant remote CLI entries from dispatch logic** — The `*-remote` agent entries still exist in `agents.yaml` for identity/profile purposes, but the dispatcher should not consider them as separate dispatch targets. When the CLI is installed, local dispatch is sufficient; when it's not, CLI-based remote dispatch won't work either.

2. **Add `SdkVendorAdapter`** — A new adapter class alongside `CliVendorAdapter` that dispatches reviews via vendor Python SDKs (Anthropic, OpenAI, Google GenAI). It formats the review prompt as API messages, calls the vendor API, and parses the JSON findings response.

3. **API key resolution via OpenBao** — SDK dispatch resolves API keys at runtime from OpenBao using the `openbao_role_id` on the agent entry. No API keys are hardcoded in `agents.yaml` or anywhere in the codebase. Falls back to environment variables (e.g., `ANTHROPIC_API_KEY`) only when OpenBao is unavailable.

4. **Three-tier dispatch preference** — The dispatcher selects reviewers with this priority:
   - **Tier 1: Local CLI** — If the vendor's CLI binary is installed, use it (fastest, uses subscription)
   - **Tier 2: SDK/API** — If the CLI is not installed but an API key is resolvable (via OpenBao or env var), use the vendor's Python SDK
   - **Tier 3: Skip** — If neither CLI nor API key is available, skip this vendor

5. **SDK config in `agents.yaml`** — Add an optional `sdk` section to agent entries, specifying the Python SDK package, model name, and any vendor-specific parameters. Only `*-remote` agents get `sdk` sections (local agents use CLI).

## Impact

### Affected Specs
- `openspec/specs/skill-workflow/spec.md` — Review Dispatcher Protocol section needs new requirements for SDK dispatch
- `openspec/specs/agent-coordinator/spec.md` — `get_dispatch_configs` output format changes (adds `sdk` field)

### Affected Components
- `skills/parallel-infrastructure/scripts/review_dispatcher.py` — New `SdkVendorAdapter`, updated `ReviewOrchestrator`, updated `_select_reviewers`
- `agent-coordinator/src/agents_config.py` — Parse `sdk` section, include in `get_dispatch_configs` output
- `agent-coordinator/agents.yaml` — Add `sdk` sections to `*-remote` agents, keep `cli` sections for backward compatibility
- `agent-coordinator/src/profile_loader.py` — Reuse existing OpenBao resolution (no changes expected)
- `agent-coordinator/pyproject.toml` — Add optional SDK dependencies (`anthropic`, `openai`, `google-generativeai`)

### What Does NOT Change
- `CliVendorAdapter` — unchanged, still handles all CLI dispatch
- Local agent entries in `agents.yaml` — unchanged
- `consensus_synthesizer.py` — unchanged, it operates on findings JSON regardless of dispatch method
- Skill SKILL.md files — unchanged, they call `review_dispatcher.py` the same way
