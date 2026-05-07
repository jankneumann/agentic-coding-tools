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

**Never commit the resolved base64 token.** Use `${VAR}` interpolation in `.mcp.json` so the token is read from the environment at runtime.

Compute the base64 token once, export it from your shell profile (or `.envrc` / OpenBao), and reference it from `.mcp.json`:

```bash
export LANGFUSE_BASIC_AUTH=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)
```

## Registration scopes

Choose where to register based on how broadly the team uses Langfuse:

| Scope | File | Use when |
|---|---|---|
| **Project** (recommended for repos that ship Langfuse-instrumented code) | `<repo>/.mcp.json` | Want every contributor to share the same registration. Commit it. |
| **User** | `~/.claude.json` → `mcpServers` | "Use Langfuse everywhere" without per-repo config. Not version-controlled. |
| **Local override** | `<repo>/.claude/settings.local.json` | Per-developer overrides, secrets, or experimental setup. Gitignored. |

## Project-scoped registration (default)

`bash skills/langfuse/scripts/install-mcp.sh` produces this. Read/write by default — pass `--lock-read-only` to additionally insert deny rules for the three write tools.

### `<repo>/.mcp.json`

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
