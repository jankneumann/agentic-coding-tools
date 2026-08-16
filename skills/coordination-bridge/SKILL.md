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

### `<skill-base-dir>/scripts/coordination_bridge.py`

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

## Work-Queue Truth / Projection Contract

The queue helpers this skill exposes (`try_get_work` → `/work/claim`,
`try_complete_work`, and the submit path) are a **distribution/claim mechanism
only**. They are NOT a source of execution truth.

**Contract**: `openspec/changes/<change-id>/loop-state.json` (schema:
`LoopState` in `skills/autopilot/scripts/autopilot.py`) is the **authoritative
execution state** — the source of truth for a run's current phase, iteration,
and package status. The coordinator work queue is a **derived projection** whose
entries are always re-derivable from loop-state. Truth flows loop-state → queue,
**never** queue → loop-state. A `try_get_work` / `/work/claim` result is a work
item to execute; it is never the record of what phase a run is in. No skill may
read authoritative phase/loop-state from the work queue.

This is the same asymmetry `coordinator-task-status-renderer` applies to the
`tasks.md` checkboxes (truth) vs. the rendered coordinator status block
(informational projection).

See the full contract — idempotent submission keyed by
`(change_id, phase, iteration)`, outbox ordering (persist loop-state, then
enqueue), resume re-derivation, and tier applicability (claim atomicity is
exercised only in the coordinated tier) — in the repo guide
`docs/guides/work-queue-truth-projection.md`. The invariant is guarded by
`skills/tests/coordination-bridge/test_work_queue_projection_invariant.py`,
an AST check that follows the name a claim result is bound to and fails on any
read of phase / iteration / package status off it — whatever the variable is
called (`change_id` is exempt; a worker needs it to locate loop-state).
