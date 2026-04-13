---

## Phase: Plan (2026-04-13)

**Agent**: codex | **Session**: N/A

### Decisions
1. **Create dedicated roadmap skills** — Use `plan-roadmap` and `autopilot-roadmap` as new orchestrator skills that reuse current planning and autopilot capabilities.
2. **Adopt policy-based limit handling** — Encode time-vs-money trade-offs as explicit execution policies (`wait_if_budget_exceeded`, `switch_if_time_saved`).
3. **Use durable artifact-based context** — Keep roadmap state, checkpoints, and learning logs on disk to reduce dependence on a single context window.

### Alternatives Considered
- Extend `plan-feature`/`autopilot` directly: rejected due to complexity concentration and higher regression risk.
- Coordinator-only implementation: rejected for higher deployment complexity and slower iteration.

### Trade-offs
- Accepted a new skill surface area over fewer commands to preserve clarity and maintainability.
- Accepted additional state artifact management to gain resumability and context-window efficiency.

### Open Questions
- [ ] Should roadmap state eventually be persisted in coordinator DB when available, with filesystem as backup?
- [ ] What default thresholds should govern automatic vendor switching vs waiting?

### Context
The planning goal was to evaluate and structure a workflow for decomposing long model-authored proposals into iterative OpenSpec changes. The resulting direction is a roadmap orchestration layer that remains compatible with existing skills while adding adaptive execution and explicit learning feedback between phases.
