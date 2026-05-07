# Claude Code Stop Hook → Langfuse Traces

Wire the Claude Code Stop hook to send each session's transcript to Langfuse as a trace, with nested spans per tool call. Combined with server-side instrumentation, this gives a unified Langfuse timeline covering both local Claude Code sessions and any HTTP API calls those sessions make.

## What the hook does

After every assistant turn, the hook:

1. Reads the session transcript file (Claude Code writes JSONL transcripts under `~/.claude/transcripts/`).
2. Diffs against a per-session state file in `~/.claude/state/` so only **new** turns are sent.
3. Sends each new turn as a Langfuse trace with nested spans for every tool invocation.
4. Sanitizes well-known secret patterns before upload.
5. Silently no-ops when `LANGFUSE_ENABLED != "true"` — safe to register unconditionally.

## Reference implementation

A working hook ships in this repo at `agent-coordinator/scripts/langfuse_hook.py` (copied or vendored when you adopt this pattern in another project).

The script is self-contained — single Python file, no internal imports beyond stdlib + `langfuse>=3.0,<4.0`.

## Required environment variables

| Variable | Required | Notes |
|---|---|---|
| `LANGFUSE_ENABLED` | Yes (must equal `"true"`) | Master gate. Hook returns immediately if unset. |
| `LANGFUSE_PUBLIC_KEY` | Yes | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | Yes | `sk-lf-...` |
| `LANGFUSE_HOST` | Yes | `https://cloud.langfuse.com`, regional variant, or self-hosted |
| `LANGFUSE_DEBUG` | No | Set to `true` for verbose logging to `~/.claude/state/langfuse_hook.log` |
| `CLAUDE_SESSION_ID` | No | Override the auto-detected session ID (rarely needed) |

Export these from your shell profile, `.envrc`, or your secret manager. The hook is gated on `LANGFUSE_ENABLED`, so leaving it unset is the off switch.

## Wiring in `.claude/settings.json`

Add to the `Stop` matcher alongside any existing hooks. Two invocation patterns:

### Pattern A — use an existing project venv (fastest)

When the project has a venv with `langfuse` installed:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/agent-coordinator/.venv/bin/python \"$CLAUDE_PROJECT_DIR\"/agent-coordinator/scripts/langfuse_hook.py"
          }
        ]
      }
    ]
  }
}
```

### Pattern B — `uv run` (portable, no venv needed)

```json
{
  "type": "command",
  "command": "uv run --with 'langfuse>=3.0,<4.0' python \"$CLAUDE_PROJECT_DIR\"/agent-coordinator/scripts/langfuse_hook.py"
}
```

`uv` resolves the env on each invocation; first run is slow, subsequent runs are cached.

### Adding alongside existing hooks

If the Stop matcher already has entries (e.g. a status reporter), append to the `hooks` array — both will run on each Stop event:

```json
{
  "matcher": "",
  "hooks": [
    { "type": "command", "command": "python3 .../report_status.py" },
    { "type": "command", "command": ".../python .../langfuse_hook.py" }
  ]
}
```

## Verifying it works

1. `export LANGFUSE_ENABLED=true LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... LANGFUSE_HOST=...`
2. Start a Claude Code session, send one prompt, wait for the response.
3. Check the Langfuse UI — a new trace should appear under the project, named after the session.
4. If nothing appears, set `LANGFUSE_DEBUG=true` and re-run; check `~/.claude/state/langfuse_hook.log`.

## Disabling without uninstalling

`unset LANGFUSE_ENABLED` (or set it to anything other than `"true"`). The hook continues to be registered but is a silent no-op.

## When to use a Stop hook vs. server-side tracing

| Scenario | Mechanism |
|---|---|
| Local Claude Code sessions on a developer machine | **Stop hook** (this document) |
| Server-side API calls (FastAPI, etc.) | Langfuse middleware / SDK in the application |
| Cloud-harness Claude Code sessions | Stop hook still works; container needs the env vars |
| Cloud agents (Codex, Gemini, automation) | Server-side instrumentation in whatever orchestrator dispatches them |

Both can run side-by-side and emit traces under the same project — group them with consistent `session_id` / `user_id` for a unified timeline.
