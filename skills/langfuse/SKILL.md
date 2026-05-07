---
name: langfuse
description: >
  One front door for Langfuse — combines the Langfuse Agent Skill (best
  practices + docs), the Langfuse CLI (full API surface via npx), and the
  Langfuse MCP server (native prompt-management tool calls). Use when
  instrumenting an app, querying or modifying Langfuse data (traces, prompts,
  datasets, scores, sessions, evals), looking up Langfuse documentation, or
  configuring Langfuse for a new repo. Routes between Skill knowledge / CLI /
  MCP based on intent.
allowed-tools: Bash(npx langfuse-cli:*), Bash(npx:*), Bash(curl:*), Bash(bash:*), mcp__langfuse__*
---

# Langfuse

Langfuse is the team's default LLM observability and prompt-management platform. This skill is the single front door for every Langfuse interaction — instrumentation, debugging traces, managing prompts, running evals, capturing user feedback.

## Three mechanisms, one front door

Langfuse is reachable three ways. They are complementary, not redundant — pick the right one per intent:

| Mechanism | What it is | When to use |
|---|---|---|
| **Skill knowledge** (this file + `references/`) | Best-practice playbooks, docs index, instrumentation patterns | "How do I…?" / "What's the right way to…?" — anything that needs conditioning before action |
| **Langfuse CLI** (`npx langfuse-cli`) | Wraps the full Langfuse REST API. Every endpoint reachable from the terminal. | Querying or mutating arbitrary resources (traces, datasets, scores, sessions, metrics, evals); batch ops; CI scripting |
| **Langfuse MCP server** (`mcp__langfuse__*` tools) | Native MCP tools for prompt management — `getPrompt`, `listPrompts`, `createTextPrompt`, `createChatPrompt`, `updatePromptLabels` | Fetch / create / version / label a prompt during a conversation. One tool call instead of a Bash → npx → JSON-parse round-trip. |

**Default routing:**
- Reading or mutating **a prompt** → MCP first (cheaper). Fall back to CLI only if MCP isn't registered or the operation isn't covered.
- Reading or mutating **anything else** (traces, scores, datasets, sessions, evals, metrics) → CLI.
- Anything that's not data access (instrumentation, migration design, debugging methodology) → load the relevant `references/*.md` file.

## Core principles

Apply these to every Langfuse task:

1. **Documentation first** — Langfuse evolves frequently. Never implement from memory. Fetch current docs before writing code (see "Documentation access" below).
2. **CLI for arbitrary data access; MCP for prompts** — see routing table above.
3. **Use latest SDK versions** — unless the user pins a version or there's a stated reason. See [references/sdk-upgrade.md](references/sdk-upgrade.md).
4. **Best practices by use case** — load the matching reference before implementing.

## Preflight

Before any Langfuse operation, verify the surface you intend to use:

### Credentials (required for CLI and MCP)

```bash
echo "${LANGFUSE_PUBLIC_KEY:?missing}"   # pk-lf-...
echo "${LANGFUSE_SECRET_KEY:?missing}"   # sk-lf-...
echo "${LANGFUSE_HOST:?missing}"         # https://cloud.langfuse.com (EU), https://us.cloud.langfuse.com (US), or self-hosted URL
```

If unset, ask the user for their project keys (Langfuse UI → Settings → API Keys) and the host they're using. Never hardcode keys in committed files — use `${VAR}` interpolation.

### CLI reachable

```bash
npx langfuse-cli --version    # should print a version string
```

`npx` will fetch the package on first run; no global install required. If the user prefers a global install: `npm i -g langfuse-cli`.

### MCP server registered (optional but recommended for prompt work)

Verify by attempting a read-only call:

```
mcp__langfuse__listPrompts({})
```

If it errors with "tool not found" or "MCP server not configured", the server isn't registered. See [references/mcp-setup.md](references/mcp-setup.md) to add it (or run `bash skills/langfuse/scripts/install-mcp.sh` for an idempotent setup).

## Resource model

Shared vocabulary used across CLI args, MCP tools, and the UI:

- **Project** — top-level container; all keys are project-scoped.
- **Session** — a logical conversation grouping multiple traces (e.g. one Claude Code session).
- **Trace** — a single request/response cycle. Has nested observations.
- **Observation** — a unit of work inside a trace. Subtypes: `span` (generic), `generation` (LLM call, has model/usage), `event` (point-in-time).
- **Score** — a quality signal attached to a trace or observation. Numeric, categorical, or boolean. Can be model-graded, human-graded, or programmatic.
- **Prompt** — versioned text or chat template, addressed by `name` + `version` (or `name` + `label`, e.g. `production`).
- **Dataset** — a labeled set of inputs + expected outputs, used for evals.
- **Dataset Run** — one execution of an experiment against a dataset, producing scored items.

## Quick operations

Common enough to handle inline without loading a reference.

### Prompts (prefer MCP)

```
mcp__langfuse__listPrompts({})
mcp__langfuse__getPrompt({"name": "chat-assistant", "version": 3})
mcp__langfuse__getPrompt({"name": "chat-assistant", "label": "production"})
mcp__langfuse__createTextPrompt({"name": "chat-assistant", "prompt": "...", "labels": ["production"]})
mcp__langfuse__updatePromptLabels({"name": "chat-assistant", "version": 4, "newLabels": ["production"]})
```

CLI fallback when MCP isn't available:

```bash
npx langfuse-cli api prompts list --json
npx langfuse-cli api prompts get --name chat-assistant --version 3 --json
```

### Traces, observations, scores (CLI)

```bash
npx langfuse-cli api traces list --limit 20 --json
npx langfuse-cli api traces get --trace-id <id> --json
npx langfuse-cli api observations-v2s list --trace-id <id> --json   # prefer v2
npx langfuse-cli api score-v2s list --trace-id <id> --json          # prefer v2
npx langfuse-cli api sessions list --limit 20 --json
npx langfuse-cli api metrics-v2s list --json                        # prefer v2
```

### Discovery

```bash
npx langfuse-cli api __schema                          # all resources
npx langfuse-cli api <resource> --help                 # actions on a resource
npx langfuse-cli api <resource> <action> --help        # args for an action
npx langfuse-cli api <resource> <action> --curl        # preview HTTP without sending
```

## Routing — load the right reference

For anything beyond quick operations, load **at most one or two** of these:

| Intent | Reference |
|---|---|
| Instrument a new or existing app with Langfuse tracing | [references/instrumentation.md](references/instrumentation.md) |
| Move hardcoded prompts in a codebase into Langfuse | [references/prompt-migration.md](references/prompt-migration.md) |
| Capture user feedback (thumbs, ratings, implicit signals) as scores | [references/user-feedback.md](references/user-feedback.md) |
| Upgrade or migrate a Langfuse SDK to the latest version | [references/sdk-upgrade.md](references/sdk-upgrade.md) |
| Deeper CLI patterns, pagination, batching, complex queries | [references/cli.md](references/cli.md) |
| Register the MCP server in a new repo (or change scope) | [references/mcp-setup.md](references/mcp-setup.md) |
| Wire Claude Code session transcripts into Langfuse via Stop hook | [references/stop-hook.md](references/stop-hook.md) |
| Submit feedback about this skill itself | [references/skill-feedback.md](references/skill-feedback.md) |

## Composition patterns

Multi-step Langfuse workflows chain naturally:

- **Ship a new prompt** → MCP `createTextPrompt` → reference it in code → CLI `traces list` to verify it ran → CLI `scores create` to grade it.
- **Migrate a hardcoded prompt** → CLI to inventory traces using the literal string → MCP `createTextPrompt` for the externalized version → refactor code to call `get_prompt()` → CLI `traces list` to confirm the new prompt name appears.
- **Debug a regression** → CLI `traces list --limit 50 --json` filtered by name → CLI `traces get` for the suspect trace → CLI `observations-v2s list` for the failing span → MCP `getPrompt` to inspect the prompt version that ran.
- **Onboard a new repo to Langfuse** → set credentials → `bash scripts/install-mcp.sh` (registers MCP) → optionally enable Stop hook (see references/stop-hook.md) → instrument app code (see references/instrumentation.md).

When composing, return one unified response covering all steps. Don't ask the user to invoke each step separately.

## Documentation access

Three methods, in preference order. Always prefer your application's native fetch tool (`WebFetch`, `mcp_fetch`, etc.) over `curl` when available — the URL patterns below work with any tool.

### 1. Documentation index (`llms.txt`)

```
https://langfuse.com/llms.txt
```

Structured list of every doc page with titles and URLs. Scan for relevant titles, then fetch the page directly.

### 2. Fetch a page as markdown

Append `.md` to any doc path, or send `Accept: text/markdown`:

```
https://langfuse.com/docs/observability/overview.md
```

### 3. Search across docs + GitHub Issues/Discussions

```
https://langfuse.com/api/search-docs?query=<url-encoded-query>
```

Returns JSON with matching pages and excerpts. Useful when debugging — issues and discussions are indexed alongside docs. Responses can be large; extract only relevant portions.

**Workflow:** start with `llms.txt` to orient → fetch specific pages once you know which ones → fall back to search when the topic is unclear.

## Skill feedback

When the user says this skill gave wrong/outdated guidance, missed a workflow, or could be improved, offer to submit feedback to the upstream Langfuse skill maintainers. Process: [references/skill-feedback.md](references/skill-feedback.md).

Do **not** trigger this for issues with Langfuse the product — only for issues with this skill's instructions and behavior.
