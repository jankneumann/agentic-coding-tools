# Change: coordinator-skill-integration

## Why

The agent-coordinator exposes coordination primitives (file locks, work queue, handoffs, memory, guardrails, audit) through MCP and HTTP, but workflow skills still run as standalone flows. Users invoking `explore → plan → implement → validate → cleanup` do not automatically benefit from those primitives.

The current proposal draft also under-specifies cross-agent execution. It is mostly phrased as Claude CLI + MCP integration, while this repository ships parallel skill runtimes for Claude Codex, Codex, and Gemini. It also needs explicit Web/Cloud behavior where MCP is unavailable and HTTP is the only coordination path.

Without runtime parity and transport-aware detection, we risk partial rollouts (one runtime updated, others stale), false negatives (`COORDINATOR_AVAILABLE=false` when only some tools are exposed), and unclear behavior for Web/Cloud agents.

## What Changes

### Approach: Transport-aware coordination with runtime parity

The core design principle is still **one skill set, two modes** (coordinated vs standalone), but now formalized across:
- Three runtimes: Claude Codex, Codex, Gemini
- Two transports: MCP (CLI) and HTTP API (Web/Cloud)

Each integrated skill determines:
- `COORDINATOR_AVAILABLE` (`true`/`false`)
- `COORDINATION_TRANSPORT` (`mcp` | `http` | `none`)
- Capability flags (`CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`)

Coordination hooks are executed only when the required capability flag is true. Missing capabilities degrade gracefully with informational logging and existing behavior.

### Changes

- **Add transport-aware coordination detection** to integrated skills:
  - CLI path: detect MCP tools by function name (`acquire_lock`, not server-prefixed names)
  - Web/Cloud path: detect HTTP coordinator reachability and capability availability via shared helper logic
  - Set transport + capability flags used by downstream skill steps

- **Add file locking hooks to `/implement-feature`**: acquire/release locks only when `CAN_LOCK=true`; otherwise continue local behavior unchanged

- **Add work queue hooks to `/implement-feature`**: submit/claim/complete work only when `CAN_QUEUE_WORK=true`; otherwise use existing local `Task()` parallelization

- **Add session handoff hooks to creative lifecycle skills** (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`): read at start and write completion summaries when `CAN_HANDOFF=true`

- **Add memory hooks**:
  - Recall at start for `/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature` when `CAN_MEMORY=true`
  - Remember on completion for `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature` when `CAN_MEMORY=true`

- **Add guardrail pre-checks to `/implement-feature` and `/security-review`** when `CAN_GUARDRAILS=true`: report violations informationally in phase 1, do not hard-block execution

- **Create `/setup-coordinator` skill for all runtimes** (`.claude`, `.codex`, `.gemini`, `skills`) covering:
  - CLI setup (MCP configuration + connectivity verification)
  - Web/Cloud setup (HTTP API URL/key, allowlist guidance, connectivity verification)
  - Capability summary and graceful-degradation expectations

- **Create shared `scripts/coordination_bridge.py`** as the stable HTTP contract layer for scripts and Web/Cloud-oriented checks. The bridge encapsulates endpoint paths, parameter mapping, response normalization, capability detection, and no-op fallback (`status="skipped"`) when the coordinator is unavailable.

- **Add runtime parity guardrails**: add a parity validation script/check so integrated skill files remain synchronized across runtime trees

- **Update docs**:
  - `docs/skills-workflow.md`: transport model, capability gating, runtime parity expectations
  - `docs/agent-coordinator.md`: skill integration patterns for MCP (CLI) and HTTP (Web/Cloud)

### API and Runtime Stability

Skills consume coordinator through two execution paths and one fallback:

1. **MCP path (CLI agents)**: Skill instructions call MCP tools by function name (`acquire_lock`, not server-prefixed aliases).
2. **HTTP path (Web/Cloud agents and helper scripts)**: Scripts call `scripts/coordination_bridge.py`, which owns HTTP endpoint/parameter compatibility.
3. **Fallback path**: If neither transport or capability is available, skills log informationally and continue with current standalone behavior.

Runtime parity is treated as a contract: the integrated skills in `.claude/skills`, `.codex/skills`, `.gemini/skills`, and `skills` must stay synchronized.

### Non-changes (explicit scope boundaries)

- Existing behavior without coordinator remains unchanged
- No mandatory coordinator dependency
- No changes to coordinator MCP or HTTP API interfaces
- No changes to OpenSpec CLI or spec format
- No duplicate workflow skill families; enhancements are additive to existing skills

## Impact

### Affected specs

| Spec | Capability | Delta |
|------|-----------|-------|
| `skill-workflow` | Workflow + adjacent skills across Claude Codex, Codex, Gemini runtimes | Add transport-aware detection, capability-gated hooks, and runtime parity expectations |
| `agent-coordinator` | Skill integration usage patterns | Document MCP and HTTP integration paths (CLI + Web/Cloud), with graceful fallback |

### Code touchpoints

| Path | Change |
|------|--------|
| `.claude/skills/{explore-feature,plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,cleanup-feature,security-review}/SKILL.md` | Add transport-aware detection and capability-gated hooks |
| `.codex/skills/{explore-feature,plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,cleanup-feature,security-review}/SKILL.md` | Same integration changes as Claude runtime |
| `.gemini/skills/{explore-feature,plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,cleanup-feature,security-review}/SKILL.md` | Same integration changes as Claude runtime |
| `skills/{explore-feature,plan-feature,implement-feature,iterate-on-plan,iterate-on-implementation,validate-feature,cleanup-feature,security-review}/SKILL.md` | Keep top-level skill mirror in sync |
| `.claude/skills/setup-coordinator/SKILL.md` | New onboarding skill |
| `.codex/skills/setup-coordinator/SKILL.md` | New onboarding skill |
| `.gemini/skills/setup-coordinator/SKILL.md` | New onboarding skill |
| `skills/setup-coordinator/SKILL.md` | New top-level skill mirror |
| `scripts/coordination_bridge.py` | New HTTP coordination helper and fallback contract |
| `scripts/tests/test_coordination_bridge.py` | Unit tests for transport/capability/fallback behavior |
| `scripts/validate_skill_runtime_parity.py` | New parity check script across runtime skill trees |
| `scripts/tests/test_validate_skill_runtime_parity.py` | Unit tests for parity checker |
| `docs/coordination-detection-template.md` | Shared preamble template with transport/capability flags |
| `docs/skills-workflow.md` | Add coordinator integration section with runtime/transport matrix |
| `docs/agent-coordinator.md` | Add skill integration section for CLI and Web/Cloud agents |

### Architecture layers affected

- **Execution layer**: runtime skills gain optional coordination calls
- **Coordination layer**: no API/interface changes (consumer-only integration)
- **Trust layer**: guardrail checks consumed conditionally when capability exists
- **Governance layer**: handoff/memory/audit events include skill lifecycle context when available
