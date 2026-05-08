# Langfuse MCP Server — Setup

The Langfuse MCP server exposes prompt-management as native MCP tools, so the agent can fetch / create / version / label prompts via single tool calls instead of shelling out to the CLI.

Documentation: https://langfuse.com/docs/api-and-data-platform/features/mcp-server

## Tools exposed

| Tool | Mode | Purpose |
|---|---|---|
| `mcp__langfuse__getPrompt` | Read | Fetch a specific prompt by name + version (or label) |
| `mcp__langfuse__listPrompts` | Read | List all prompts in the project |
| `mcp__langfuse__createTextPrompt` | Write | Create a new text-prompt version |
| `mcp__langfuse__createChatPrompt` | Write | Create a new chat-prompt version |
| `mcp__langfuse__updatePromptLabels` | Write | Move labels (e.g. `production`) between versions |

## Endpoints by region

| Region | URL |
|---|---|
| EU cloud | `https://cloud.langfuse.com/api/public/mcp` |
| US cloud | `https://us.cloud.langfuse.com/api/public/mcp` |
| Japan cloud | `https://jp.cloud.langfuse.com/api/public/mcp` |
| HIPAA cloud | `https://hipaa.cloud.langfuse.com/api/public/mcp` |
| Self-hosted | `<your-langfuse-host>/api/public/mcp` |

## Authentication

Uses HTTP Basic auth with project-scoped API keys (`LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`), base64-encoded as `pk-lf-...:sk-lf-...`.

**Never commit the resolved base64 token to a project-scoped file.** For `.mcp.json` (Claude Code), use `${VAR}` interpolation so the token is read from the environment at runtime. User-global config files for Codex and Gemini do hold a literal token — see [Cross-agent registration](#cross-agent-registration) below.

### Resolving credentials from OpenBao

The recommended source of `LANGFUSE_*` values is OpenBao (matches the rest of this repo's secret-management pattern — see `docs/openbao-secret-management.md`). The bao-vault skill ships a one-line bridge:

```bash
eval "$(skills/bao-vault/scripts/langfuse_env.sh)"
```

This reads `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` from your OpenBao KV path (defaults: `secret/coordinator`), computes `LANGFUSE_BASIC_AUTH` from the public+secret pair, and emits four `export` lines into the current shell. It is safe to run unconditionally — when `BAO_ADDR` is unset or the keys are already in the environment, it falls back silently.

### Computing the token by hand

If OpenBao is not configured, do it manually:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_BASIC_AUTH=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)
```

## Cross-agent registration

`bash skills/langfuse/scripts/install-mcp.sh` registers the server with **all three agents in one shot** (Claude Code, Codex, Gemini). Pass `--claude-only`, `--no-codex`, or `--no-gemini` to skip any.

| Agent | File | Scope | Auth header value |
|---|---|---|---|
| Claude Code | `<repo>/.mcp.json` | Project (committed) | `Basic ${LANGFUSE_BASIC_AUTH}` (env var ref — interpolated at server start) |
| Codex CLI | `~/.codex/config.toml` | **User-global** (Codex has no project-scope MCP file) | `Basic <literal-token>` (Codex's TOML reader does not interpolate env vars in headers) |
| Gemini CLI | `~/.gemini/settings.json` | **User-global** | `Basic <literal-token>` (same reason) |

The literal token written into Codex/Gemini configs is `base64(LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY)` — i.e. exactly what Claude Code computes at runtime. It is sensitive but not _more_ sensitive than the keys themselves: rotate the keys in the Langfuse UI to invalidate.

The `install-mcp.sh` script is idempotent and reversible per-target — re-running updates only the `langfuse` entry, leaves other MCP servers alone, and `git restore .mcp.json` (or hand-deleting the section in user-global files) cleanly uninstalls.

## Registration scopes

Choose where to register based on how broadly the team uses Langfuse:

| Scope | File | Use when |
|---|---|---|
| **Project** (recommended for repos that ship Langfuse-instrumented code) | `<repo>/.mcp.json` | Want every contributor to share the same registration. Commit it. |
| **User** | `~/.claude.json` → `mcpServers` | "Use Langfuse everywhere" without per-repo config. Not version-controlled. |
| **Local override** | `<repo>/.claude/settings.local.json` | Per-developer overrides, secrets, or experimental setup. Gitignored. |

## Project-scoped registration for Claude Code (`.mcp.json`)

`bash skills/langfuse/scripts/install-mcp.sh --claude-only` produces this. Read/write by default — pass `--lock-read-only` to additionally insert deny rules for the three write tools.

```json
{
  "mcpServers": {
    "langfuse": {
      "type": "http",
      "url": "https://cloud.langfuse.com/api/public/mcp",
      "headers": {
        "Authorization": "Basic ${LANGFUSE_BASIC_AUTH}"
      }
    }
  }
}
```

Notes:
- `${LANGFUSE_BASIC_AUTH}` is interpolated at runtime; the literal string stays in the file. Do **not** run `claude mcp add` — it has been observed to expand `${VAR}` placeholders and write resolved tokens back to the file (see anthropics/claude-code#18692).
- Swap the `url` for your region or self-hosted host.

## Codex registration (`~/.codex/config.toml`)

`install-mcp.sh` writes:

```toml
[mcp_servers.langfuse]
url = "https://cloud.langfuse.com/api/public/mcp"

[mcp_servers.langfuse.headers]
Authorization = "Basic <literal-base64-token>"
```

User-global; Codex CLI loads it on every invocation. Re-running `install-mcp.sh` strips and replaces the `[mcp_servers.langfuse]` (and `.headers`) sections in place — adjacent sections are preserved.

## Gemini registration (`~/.gemini/settings.json`)

`install-mcp.sh` writes/merges:

```json
{
  "mcpServers": {
    "langfuse": {
      "httpUrl": "https://cloud.langfuse.com/api/public/mcp",
      "headers": {
        "Authorization": "Basic <literal-base64-token>"
      }
    }
  }
}
```

User-global. Re-running updates only the `langfuse` key; other MCP servers in `mcpServers` are preserved.

### Optional: lock to read-only via deny rules

By default, the install script does not modify `.claude/settings.json` — both reads and writes are allowed. If you want a hard guard against mutations (useful for shared projects where prompt versioning is gated through a release process), pass `--lock-read-only`:

```bash
bash skills/langfuse/scripts/install-mcp.sh --lock-read-only
```

This adds the three write tools to the `permissions.deny` list:

```json
{
  "permissions": {
    "deny": [
      "mcp__langfuse__createTextPrompt",
      "mcp__langfuse__createChatPrompt",
      "mcp__langfuse__updatePromptLabels"
    ]
  }
}
```

With `"defaultMode": "bypassPermissions"`, allowlists are advisory; only the deny list is enforced. The `ask` list is an alternative — it prompts the user before each invocation instead of denying outright.

## Self-hosted Langfuse

Replace `url` with your host's `/api/public/mcp` endpoint. Auth and tools are identical.

## Verifying registration

After updating `.mcp.json`, restart Claude Code and try a read-only call:

```
mcp__langfuse__listPrompts({})
```

Successful response → registered. "Tool not found" → check `.mcp.json` JSON validity, restart Claude Code, and confirm `LANGFUSE_BASIC_AUTH` is exported in the shell where you launched the CLI.

## Known issues to avoid

- **`claude mcp add` may expand env vars and write resolved secrets** — see anthropics/claude-code#18692. Hand-edit `.mcp.json` (or use `scripts/install-mcp.sh`) to keep `${VAR}` placeholders intact.
- **Headers without env interpolation will commit secrets** — always reference `${LANGFUSE_BASIC_AUTH}`, never paste the base64 string.
- **Different auth per region** — auth header is identical across regions, but the project keys themselves are region-scoped. Use the keys from the same region as the `url`.
