---
name: coordination-bridge
description: "HTTP fallback bridge for coordinator when MCP transport is unavailable"
category: Infrastructure
tags: [coordination, bridge, http, infrastructure]
user_invocable: false
---

# Coordination Bridge Infrastructure Skill

Non-user-invocable infrastructure skill that provides HTTP fallback for the coordinator when MCP transport is unavailable.

## Scripts

### scripts/coordination_bridge.py

Detects coordinator availability and provides HTTP-based fallback operations.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/coordination_bridge.py" <command> [args]
```

**Commands**:
| Command | Arguments | Description |
|---------|-----------|-------------|
| `detect` | | Check coordinator availability, output JSON status |
| `try_handoff_read` | `[--agent-name NAME] [--limit N]` | Read latest handoff (HTTP fallback) |
| `try_handoff_write` | `--summary TEXT [--completed JSON] [--next-steps JSON]` | Write handoff document |
| `try_recall` | `[--tags TAG,...] [--limit N]` | Recall memories by tags |
| `try_remember` | `--event-type TYPE --summary TEXT [--tags TAG,...]` | Store a memory |

**Stdout** (detect): JSON with `COORDINATOR_AVAILABLE`, transport, capabilities
**Exit codes**: 0 = success, 1 = coordinator unavailable or error
