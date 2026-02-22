# Change: coordinator-skill-integration

## Why

The agent-coordinator exposes coordination primitives (file locks, work queue, handoffs, memory, guardrails, audit) through MCP and HTTP, but workflow skills still run as standalone flows. Users invoking `explore -> plan -> implement -> validate -> cleanup` do not automatically benefit from those primitives.

To work reliably across Claude Codex, Codex, and Gemini (CLI + Web/Cloud), we also need a strict authoring model for runtime parity. This repository already has that pattern: canonical skills in `skills/`, then `skills/install.sh` uses `rsync` to sync into `.claude/skills`, `.codex/skills`, and `.gemini/skills`.

Without that canonical-sync model, runtime drift and transport-specific regressions become likely.

## What Changes

### Approach: Transport-aware coordination with canonical skill sync

The design combines two rules:

1. **Transport-aware coordination**
- MCP for local CLI agents
- HTTP API for Web/Cloud agents
- Graceful fallback when coordinator/capabilities are unavailable

2. **Canonical skill distribution**
- Author coordinator integration only in `skills/`
- Propagate to runtime skill trees via existing `skills/install.sh` in `rsync` mode
- Treat runtime skill trees as generated mirrors for this feature work

### Changes

- **Add transport-aware coordination detection** to integrated skills:
  - Set `COORDINATOR_AVAILABLE` (`true|false`)
  - Set `COORDINATION_TRANSPORT` (`mcp|http|none`)
  - Set capability flags (`CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`)

- **Add file locking hooks to `/implement-feature`** when `CAN_LOCK=true`; keep existing behavior when unavailable

- **Add work queue hooks to `/implement-feature`** when `CAN_QUEUE_WORK=true`; keep local `Task()` fallback otherwise

- **Add session handoff hooks** to creative lifecycle skills (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`) when `CAN_HANDOFF=true`

- **Add memory hooks**:
  - Recall at start for `/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature` when `CAN_MEMORY=true`
  - Remember on completion for `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature` when `CAN_MEMORY=true`

- **Add guardrail pre-checks** to `/implement-feature` and `/security-review` when `CAN_GUARDRAILS=true`; informational-only in phase 1

- **Create canonical `skills/setup-coordinator/SKILL.md`** for onboarding:
  - CLI MCP setup/verification
  - Web/Cloud HTTP setup/verification
  - capability summary + fallback expectations

- **Create `scripts/coordination_bridge.py`** as stable HTTP contract layer for helper scripts/Web checks with normalized no-op fallback (`status="skipped"`)

- **Use existing `skills/install.sh` sync workflow** to propagate updated canonical skills to `.claude/.codex/.gemini` runtime mirrors

- **Update docs**:
  - `docs/skills-workflow.md`: transport model + canonical `skills/` -> runtime sync pattern
  - `docs/agent-coordinator.md`: skill integration patterns for MCP (CLI) and HTTP (Web/Cloud)

### API and Runtime Stability

Skills consume coordinator through two execution paths and one fallback:

1. **MCP path (CLI)**: skill instructions call MCP tools by function name (`acquire_lock`, not server-prefixed aliases)
2. **HTTP path (Web/Cloud and helper scripts)**: scripts call `scripts/coordination_bridge.py`
3. **Fallback path**: if transport/capability is unavailable, skills continue with existing standalone behavior

Runtime parity contract for this change:
- Canonical edits happen in `skills/`
- Runtime mirrors are refreshed via `skills/install.sh --mode rsync --agents claude,codex,gemini`

### Non-changes (explicit scope boundaries)

- Existing behavior without coordinator remains unchanged
- No mandatory coordinator dependency
- No changes to coordinator MCP or HTTP API interfaces
- No changes to OpenSpec CLI or spec format
- No duplicate workflow skill families

## Impact

### Affected specs

| Spec | Capability | Delta |
|------|-----------|-------|
| `skill-workflow` | Workflow + adjacent skills across Claude Codex, Codex, Gemini | Add transport-aware detection, capability-gated hooks, and canonical `skills/` sync distribution pattern |
| `agent-coordinator` | Skill integration usage patterns | Document MCP and HTTP integration paths with setup and fallback expectations |

### Code touchpoints

| Path | Change |
|------|--------|
| `skills/{explore-feature,plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,cleanup-feature,security-review}/SKILL.md` | Canonical coordinator integration changes |
| `skills/setup-coordinator/SKILL.md` | New canonical onboarding skill |
| `skills/install.sh` | Existing sync mechanism used to distribute canonical skills to runtime mirrors |
| `scripts/coordination_bridge.py` | New HTTP coordination helper and fallback contract |
| `scripts/tests/test_coordination_bridge.py` | Unit tests for transport/capability/fallback behavior |
| `docs/coordination-detection-template.md` | Shared preamble template with transport/capability flags |
| `docs/skills-workflow.md` | Add canonical distribution + transport matrix guidance |
| `docs/agent-coordinator.md` | Add skill integration section for CLI and Web/Cloud agents |
| `.claude/skills/*`, `.codex/skills/*`, `.gemini/skills/*` | Generated mirror updates via `skills/install.sh --mode rsync` |

### Architecture layers affected

- **Execution layer**: skills gain optional coordination calls
- **Coordination layer**: no API/interface changes (consumer-side integration only)
- **Trust layer**: guardrail checks consumed conditionally when capability exists
- **Governance layer**: handoff/memory/audit events include skill lifecycle context when available
