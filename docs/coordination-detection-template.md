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

## Concrete Detection Script

Run the check script from the project root:

```bash
python3 agent-coordinator/scripts/check_coordinator.py --json
```

This outputs JSON with all flags pre-computed:

```json
{
  "COORDINATOR_AVAILABLE": true,
  "COORDINATION_TRANSPORT": "http",
  "coordinator_url": "http://localhost:8081",
  "health": {"status": "ok", "db": "connected", "version": "0.2.0"},
  "CAN_LOCK": true,
  "CAN_QUEUE_WORK": true,
  "CAN_DISCOVER": true,
  "CAN_GUARDRAILS": true,
  "CAN_MEMORY": true,
  "CAN_HANDOFF": true,
  "CAN_POLICY": true,
  "CAN_AUDIT": true
}
```

Exit code 0 = coordinator available, 1 = unavailable.

For human-readable output, omit `--json`:

```bash
python3 agent-coordinator/scripts/check_coordinator.py
```

Override the coordinator URL with `--url` or `COORDINATION_API_URL`:

```bash
python3 agent-coordinator/scripts/check_coordinator.py --url https://coord.example.com --json
```

## MCP Detection (CLI runtimes)

When running in a CLI with MCP configured, capability flags can also be derived from discovered MCP tool names:

- `CAN_LOCK=true` when `acquire_lock` and `release_lock` are available
- `CAN_QUEUE_WORK=true` when `submit_work`, `get_work`, and `complete_work` are available
- `CAN_HANDOFF=true` when `write_handoff` and `read_handoff` are available
- `CAN_MEMORY=true` when `remember` and `recall` are available
- `CAN_GUARDRAILS=true` when `check_guardrails` is available

The `check_coordinator.py` script is the preferred method — it works in all runtimes and produces deterministic output.

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

## Profile-Based Configuration

When `COORDINATOR_PROFILE` is set (or `profiles/` directory exists), the coordinator loads a YAML deployment profile that pre-populates environment variables as defaults. Profiles support inheritance (`extends: base`) and `${VAR}` interpolation from `.secrets.yaml`. Agent identity and API key mappings can also be declared in `agents.yaml` instead of scattered env vars. See `agent-coordinator/profiles/` and `agent-coordinator/agents.yaml`.
