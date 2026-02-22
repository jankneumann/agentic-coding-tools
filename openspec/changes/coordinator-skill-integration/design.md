# Design: coordinator-skill-integration

## Context

This change integrates coordinator primitives into workflow skills. The repository maintains parallel skill trees for Claude Codex, Codex, and Gemini, and supports both local CLI and Web/Cloud agent execution contexts.

The design must prevent runtime drift, avoid MCP-only assumptions, and preserve standalone behavior when coordinator services are unavailable.

## Goals

- Enable optional coordination hooks in workflow skills across all supported runtimes
- Support both MCP (CLI) and HTTP (Web/Cloud) transport paths
- Keep behavior safe and deterministic under partial capability availability
- Keep skill trees synchronized to avoid runtime-specific regressions

## Non-Goals

- Changing coordinator MCP or HTTP API contracts
- Making coordinator mandatory for workflow execution
- Replacing existing workflow skills with new parallel skill families

## Decision 1: Use transport-aware capability detection

### Decision

Integrated skills use a transport-aware detection preamble that sets:
- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp`, `http`, `none`)
- capability flags (`CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`)

Each hook is gated by the relevant capability flag.

### Alternatives considered

- Single boolean availability check against a fixed MCP tool set
  - Rejected: fails under partial capability rollouts and does not support Web/Cloud HTTP-only contexts
- Separate per-skill ad hoc checks
  - Rejected: high drift risk and inconsistent fallback semantics

## Decision 2: Keep runtime skill trees explicitly synchronized

### Decision

Use `skills/` as the canonical authoring location for coordinator-integration edits, then sync runtime mirrors with the existing install workflow:

`skills/install.sh --mode rsync --agents claude,codex,gemini`

Runtime trees (`.claude/skills`, `.codex/skills`, `.gemini/skills`) are treated as generated mirrors for this change.

### Alternatives considered

- Edit all runtime trees manually in every change
  - Rejected: higher drift risk and unnecessary duplicate editing burden
- Introduce a new custom parity-distribution mechanism
  - Rejected: existing `skills/install.sh` already provides tested rsync-based synchronization

## Decision 3: Split coordination access by transport

### Decision

- Skill instructions use MCP tool calls in CLI contexts
- Scripted validation and Web/Cloud checks use `scripts/coordination_bridge.py` for HTTP interactions
- Both paths use the same capability model and no-op fallback semantics

### Alternatives considered

- Route all coordination calls through HTTP only
  - Rejected: unnecessary indirection for CLI MCP-native usage
- Route all coordination calls through MCP only
  - Rejected: incompatible with Web/Cloud runtimes

## Decision 4: Scope memory and handoff hooks to high-value skills

### Decision

- Handoffs: `plan-feature`, `implement-feature`, `iterate-on-plan`, `iterate-on-implementation`, `cleanup-feature`
- Memory recall: `explore-feature`, `plan-feature`, `iterate-on-plan`, `iterate-on-implementation`, `validate-feature`
- Memory write: `iterate-on-plan`, `iterate-on-implementation`, `validate-feature`

This preserves utility without adding low-value coordination noise to all skills.

### Alternatives considered

- Attach memory/handoff to every skill uniformly
  - Rejected: higher complexity with low marginal value for some skills

## Risks and Mitigations

- Risk: Runtime drift across skill trees
  - Mitigation: canonical `skills/` edits + mandatory `skills/install.sh` sync + post-sync drift checks
- Risk: False negatives in availability detection
  - Mitigation: transport-aware detection plus per-capability flags
- Risk: Web/Cloud incompatibility due MCP assumptions
  - Mitigation: explicit HTTP setup and bridge-based validation path
- Risk: Operational regressions when coordinator is unavailable
  - Mitigation: required `status="skipped"` no-op behavior and standalone fallback

## Open Questions

- Whether runtime skill trees should be generated from templates in a future follow-up
- Whether guardrail enforcement should become blocking in a later phase
