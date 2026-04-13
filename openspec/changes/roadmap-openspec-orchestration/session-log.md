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

---

## Phase: Iterate-on-Plan (2026-04-13)

**Agent**: codex | **Session**: N/A

### Decisions
1. **Added explicit Impact section** — aligned proposal with affected capability, skills, and docs.
2. **Strengthened spec testability** — added failure/edge scenarios for each requirement area.
3. **Improved parallelizability** — replaced single `wp-main` with decomposed work packages and dependency DAG.
4. **Clarified assumptions as decisions** — made policy defaults and state authority explicit.

### Alternatives Considered
- Keep single-package sequential plan: rejected due to poor parallel execution clarity.
- Keep generic success-only scenarios: rejected due to weak testability.

### Trade-offs
- Added planning detail and structure at the cost of a longer artifact set.
- Increased upfront rigor to reduce ambiguity during `/implement-feature`.

### Open Questions
- [ ] Should policy thresholds be stored globally (config) or per-roadmap?

### Context
This refinement addressed plan-quality gaps: missing impact detail, limited failure-path coverage, and insufficient package decomposition for parallel execution.

---

## Phase: Plan Iteration 2 (2026-04-13)

**Agent**: claude_code | **Session**: N/A

### Decisions
1. **Added machine-readable artifact schemas** — Created JSON Schema definitions for roadmap.yaml, checkpoint.json, and learning-log entries. These are the primary interface contracts between plan-roadmap and autopilot-roadmap, enabling independent parallel implementation.
2. **Moved shared runtime to dedicated directory** — Created `skills/roadmap-runtime/` following the established `skills/parallel-infrastructure/` pattern. Avoids duplicating code across consumer skill directories.
3. **Defined canonical artifact location model** — Roadmap artifacts live under the roadmap's own OpenSpec change directory. Child changes reference parent via `parent_roadmap` field; bidirectional linking enables traceability.
4. **Redesigned learning-log as progressive disclosure** — Root `learning-log.md` index with per-item entries in `learnings/` subfolder. Bounds context assembly to O(k) where k = dependency fan-in + recency window. Compaction at 50-entry threshold.
5. **Added cascading vendor failover** — Policy evaluation is recursive across remaining eligible vendors up to `max_switch_attempts_per_item`, rather than single-hop only.
6. **Added item implementation failure handling** — Items can transition to `failed` with structured reason; dependents go to `blocked` or `replan_required`. Most common failure mode now has explicit spec coverage.
7. **Added observability and sanitization requirements** — Structured log events for state transitions, policy decisions, and checkpoint operations. Sanitization contract prevents secret exposure in persisted artifacts.
8. **Regenerated work-packages.yaml with executor fields** — Added task_type, locks, worktree, verification steps, outputs, scope.deny per established schema pattern.
9. **Added CLAUDE.md update task** — Task 4.3 for updating the workflow table with roadmap skill entry points. AGENTS.md is a symlink to CLAUDE.md so it updates automatically.

### Alternatives Considered
- Keep shared runtime in consumer directories (plan-roadmap + autopilot-roadmap): rejected — breaks skills/parallel-infrastructure/ pattern.
- Flat append-only learning log: rejected — unbounded growth for long roadmaps degrades context assembly.
- Single-hop vendor failover: rejected — cascading failures are likely over multi-hour executions.

### Trade-offs
- Added 3 JSON Schema files and 7 new spec scenarios at the cost of a larger artifact set, but this eliminates ambiguity for parallel implementation.
- Progressive disclosure learning log adds implementation complexity (index maintenance, compaction) but bounds runtime context loading.

### Open Questions
- [x] Should roadmap state eventually be persisted in coordinator DB? → Decided: filesystem canonical, coordinator is optional cache (D2).
- [x] What default thresholds should govern vendor switching? → Decided: wait is default; switch requires explicit cost ceiling (D3). Per-roadmap config via policy section in roadmap.yaml.
- [ ] Should policy thresholds be stored globally (config) or per-roadmap? → Per-roadmap in roadmap.yaml for now; global config can be added later.

### Context
This iteration addressed 11 findings from a multi-vendor plan review (Claude Code + Codex). The two highest-priority blockers were: (1) missing machine-readable artifact schemas that prevented independent parallel implementation, and (2) work-packages.yaml missing executor metadata required by /implement-feature. All 11 findings (2 high, 8 medium, 1 low) were addressed.
