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
| `LANGFUSE_ENABLED` | Yes (must equal `"true"`) | Master gate. Hook returns immediately if unset. The `run_stop_hook.sh` wrapper sets this for you when credentials are present. |
| `LANGFUSE_PUBLIC_KEY` | Yes | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | Yes | `sk-lf-...` |
| `LANGFUSE_HOST` | Yes | `https://cloud.langfuse.com`, regional variant, or self-hosted |
| `LANGFUSE_DEBUG` | No | Set to `true` for verbose logging to `~/.claude/state/langfuse_hook.log` |
| `CLAUDE_SESSION_ID` | No | Override the auto-detected session ID (rarely needed) |

The recommended source for the three `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` values is OpenBao via `skills/bao-vault/scripts/langfuse_env.sh` — `run_stop_hook.sh` calls it automatically. Otherwise export them from your shell profile or `.envrc`. The hook is gated on `LANGFUSE_ENABLED`, so leaving it unset is the off switch even when registration is in place.

## Wiring in `.claude/settings.json`

The supported path is the wrapper-plus-installer pair shipped with this skill:

```bash
python3 skills/langfuse/scripts/install_stop_hook.py            # project-scoped (.claude/settings.json)
python3 skills/langfuse/scripts/install_stop_hook.py --user     # user-scoped  (~/.claude/settings.json)
python3 skills/langfuse/scripts/install_stop_hook.py --remove   # uninstall
```

This appends a single Stop-hook entry whose command is `bash "$CLAUDE_PROJECT_DIR"/skills/langfuse/scripts/run_stop_hook.sh`. The installer is idempotent (re-runs are no-ops), preserves all existing Stop hooks, and `--remove` cleanly uninstalls.

### What `run_stop_hook.sh` does

1. Sources `skills/bao-vault/scripts/langfuse_env.sh` (silent no-op if OpenBao is not configured) — this populates `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `LANGFUSE_BASIC_AUTH`.
2. Bails (exit 0) if credentials are still missing — Stop hooks must never fail noisily.
3. Picks the Python invocation in priority order:
   - `agent-coordinator/.venv/bin/python` (fastest — uses pre-installed langfuse)
   - `uv run --with 'langfuse>=3.0,<4.0' python` (portable fallback; first run cold-installs)
   - `python3` (last resort; assumes `langfuse` is on `sys.path`)
4. Sets `LANGFUSE_ENABLED=true` and `exec`s `agent-coordinator/scripts/langfuse_hook.py`.

### Manual wiring (if you need a different shape)

If you can't use the wrapper, the two raw command patterns are still valid — paste either into the `Stop` array:

```json
{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/agent-coordinator/.venv/bin/python \"$CLAUDE_PROJECT_DIR\"/agent-coordinator/scripts/langfuse_hook.py" }
```

```json
{ "type": "command", "command": "uv run --with 'langfuse>=3.0,<4.0' python \"$CLAUDE_PROJECT_DIR\"/agent-coordinator/scripts/langfuse_hook.py" }
```

These bypass `run_stop_hook.sh`, so you must export `LANGFUSE_*` and `LANGFUSE_ENABLED=true` yourself in the shell that launches Claude Code.

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
