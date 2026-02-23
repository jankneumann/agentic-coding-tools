# Coordination Detection Template

Use this preamble in coordinator-integrated skills to keep behavior consistent across:

- Claude Codex CLI (MCP)
- Codex CLI (MCP)
- Gemini CLI (MCP)
- Claude Web (HTTP)
- Codex Cloud/Web (HTTP)
- Gemini Web/Cloud (HTTP)

## Required Flags

Every integrated skill sets:

- `COORDINATOR_AVAILABLE` (`true|false`)
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK` (`true|false`)
- `CAN_QUEUE_WORK` (`true|false`)
- `CAN_HANDOFF` (`true|false`)
- `CAN_MEMORY` (`true|false`)
- `CAN_GUARDRAILS` (`true|false`)

## Capability Mapping

### MCP (CLI runtimes)

Set capability flags from discovered MCP tool names:

- `CAN_LOCK=true` when `acquire_lock` and `release_lock` are available
- `CAN_QUEUE_WORK=true` when `submit_work`, `get_work`, and `complete_work` are available
- `CAN_HANDOFF=true` when `write_handoff` and `read_handoff` are available
- `CAN_MEMORY=true` when `remember` and `recall` are available
- `CAN_GUARDRAILS=true` when `check_guardrails` is available

### HTTP (Web/Cloud runtimes)

Set capability flags from `scripts/coordination_bridge.py detect`:

- `CAN_LOCK` from `/locks/*`
- `CAN_QUEUE_WORK` from `/work/*`
- `CAN_HANDOFF` from `/handoff*` or `/handoffs*`
- `CAN_MEMORY` from `/memory/*`
- `CAN_GUARDRAILS` from `/guardrails/check`

## Template Preamble (Pseudo-shell)

```bash
# Defaults (standalone-safe)
COORDINATOR_AVAILABLE=false
COORDINATION_TRANSPORT=none
CAN_LOCK=false
CAN_QUEUE_WORK=false
CAN_HANDOFF=false
CAN_MEMORY=false
CAN_GUARDRAILS=false

# 1) MCP detection for CLI runtimes
#    Replace "runtime_has_tool" with runtime-native tool discovery for the active agent.
if runtime_has_tool "acquire_lock" || runtime_has_tool "submit_work" || runtime_has_tool "remember"; then
  COORDINATOR_AVAILABLE=true
  COORDINATION_TRANSPORT=mcp

  runtime_has_tool "acquire_lock" && runtime_has_tool "release_lock" && CAN_LOCK=true
  runtime_has_tool "submit_work" && runtime_has_tool "get_work" && runtime_has_tool "complete_work" && CAN_QUEUE_WORK=true
  runtime_has_tool "write_handoff" && runtime_has_tool "read_handoff" && CAN_HANDOFF=true
  runtime_has_tool "remember" && runtime_has_tool "recall" && CAN_MEMORY=true
  runtime_has_tool "check_guardrails" && CAN_GUARDRAILS=true
fi

# 2) HTTP detection fallback for Web/Cloud runtimes
if [ "$COORDINATION_TRANSPORT" = "none" ]; then
  # Optional env:
  #   COORDINATION_API_URL=https://coord.example.com
  #   COORDINATION_API_KEY=<secret>
  DETECT_JSON="$(python scripts/coordination_bridge.py detect)"

  # Use runtime-native JSON parsing where available (jq shown for readability).
  if echo "$DETECT_JSON" | jq -e '.COORDINATION_TRANSPORT == "http"' >/dev/null 2>&1; then
    COORDINATOR_AVAILABLE=true
    COORDINATION_TRANSPORT=http
    CAN_LOCK=$(echo "$DETECT_JSON" | jq -r '.CAN_LOCK')
    CAN_QUEUE_WORK=$(echo "$DETECT_JSON" | jq -r '.CAN_QUEUE_WORK')
    CAN_HANDOFF=$(echo "$DETECT_JSON" | jq -r '.CAN_HANDOFF')
    CAN_MEMORY=$(echo "$DETECT_JSON" | jq -r '.CAN_MEMORY')
    CAN_GUARDRAILS=$(echo "$DETECT_JSON" | jq -r '.CAN_GUARDRAILS')
  fi
fi
```

## Hook Rules

- Execute a coordination hook only when its `CAN_*` flag is `true`.
- If a hook call fails mid-skill (network outage, timeout, stale token), continue with standalone behavior.
- For HTTP helper calls, treat `status="skipped"` as expected degraded behavior, not a fatal error.
- Guardrail checks are informational in phase 1 and do not hard-block execution.

## HTTP Environment Defaults

`scripts/coordination_bridge.py` resolves coordinator settings in this order:

1. Explicit function/CLI args
2. `COORDINATION_API_URL` / `COORDINATION_API_KEY`
3. Fallback URL: `http://localhost:${AGENT_COORDINATOR_REST_PORT:-3000}`

This keeps local dev smooth while allowing explicit Web/Cloud endpoints in hosted runtimes.
