# Session Log: specialized-workflow-agents

---

## Phase: Plan (2026-04-04)

**Agent**: claude-local | **Session**: N/A

### Decisions
1. **Full three-phase scope** — Deliver all phases (model hints, archetype registry, coordinator routing) rather than Phase 1 only. Rationale: centralized archetypes avoid config duplication and enable complexity-based escalation.
2. **Extend existing fallback chains** — Archetypes override primary model but reuse agents.yaml fallback sequences. Avoids duplicating fallback config per archetype.
3. **System prompts per archetype** — Each archetype carries a role-specific system prompt prefix composed with task prompts. Improves output quality by framing agent behavior per role.
4. **Complexity-based escalation** — Implementer archetype auto-escalates sonnet to opus when work-package exceeds thresholds (>3 write dirs, >2 deps, >500 LOC, or explicit complexity flag).
5. **Layered Archetype System (Approach A)** — Selected over skill-embedded mapping (B) and work-package driven (C) for centralized config and coordinator routing.

### Alternatives Considered
- Approach B (Skill-Embedded Mapping): rejected because model config duplicated across 15+ skills, no coordinator awareness, no escalation
- Approach C (Work-Package Driven): rejected because requires manual model decisions per package, no reusable archetypes, system prompts bloat work-packages.yaml

### Trade-offs
- Accepted larger scope (3 phases, L effort) over immediate-only delivery (Phase 1, S effort) because full archetype system provides centralized control and quality-preserving escalation
- Accepted new config file (archetypes.yaml) over inline skill config because centralized tuning outweighs one-file maintenance cost

### Open Questions
- [ ] Escalation threshold tuning: initial values (3 dirs, 2 deps, 500 LOC) need empirical validation
- [ ] Whether custom user-defined archetypes should be supported beyond the 6 predefined ones

### Context
Planned a three-phase feature to introduce agent archetypes mapping workflow stages to model selection. Phase 1 adds model= parameters to skill Task() calls (zero infra changes). Phase 2 creates archetypes.yaml with loader/validator/escalation in agents_config.py. Phase 3 extends the coordinator work queue with agent_requirements routing and updates the work-packages.yaml schema.

---

## Phase: Refinement (2026-04-10)

**Agent**: claude-local | **Session**: N/A

### Decisions
1. **Rebase on main after 19 commits** — Cherry-picked original plan commit onto current main (5089f60) to incorporate speculative merge trains, autopilot rename, and other recent changes.
2. **Document merge train coexistence (D7)** — Added design decision D7 establishing that archetype routing and merge train routing are orthogonal filtering dimensions in `claim()`. Archetype filters by agent capability; merge trains filter by partition/wave ordering.
3. **Keep all 3 phases in scope** — Confirmed full scope (model hints → archetype registry → coordinator routing) rather than scoping down to Phase 1 only.
4. **Elevate from Draft to Approved** — Status changed after validating all artifacts pass OpenSpec validation, work-packages schema/DAG/locks, and parallel zones checks.

### Alternatives Considered
- Phase 1 only scope: rejected because centralized archetypes and coordinator routing provide the main value
- Amending original commit: rejected in favor of preserving git history with a refinement commit on top

### Trade-offs
- Accepted additional complexity notes in tasks (merge train coexistence) over keeping tasks pristine, because implementers need awareness of the new MCP tools and API endpoints in the same files

### Open Questions
- [ ] Escalation threshold tuning: initial values (3 dirs, 2 deps, 500 LOC) still need empirical validation
- [ ] Whether custom user-defined archetypes should be supported beyond the 6 predefined ones

### Context
Elevated draft PR #65 to full plan. Rebased onto current main (19 new commits including speculative merge trains). Validated all artifacts — OpenSpec, work-packages, and parallel zones all pass. Updated design.md with D7 (merge train coexistence), tasks.md with merge train context notes on tasks 3.2.1/3.3.1/3.3.2, and proposal.md status from Draft to Approved.

---

## Phase: Plan Iteration 1 (2026-04-10)

**Agent**: claude-local | **Session**: N/A

### Decisions
1. **Remove `fallback_strategy` from spec** — Field was listed in Requirement 1 but undefined elsewhere. Fallback behavior is fully covered by design decision D4 (extend existing fallback chains).
2. **Add missing fallback chain test task (3.4.0)** — Requirement 5 had no corresponding test task. Added with `respx` mock approach for 429 simulation.
3. **Fix `wp-skill-archetype-refs` dependency** — Added `wp-skill-model-hints` to depends_on to prevent parallel file conflicts on shared SKILL.md files.
4. **Clarify prompt composition ownership** — Expanded task 2.2.2 to include `compose_prompt()` function, resolving the ownership gap for design decision D2.
5. **Clarify escalation metadata flow** — Updated task 2.2.3 to specify that dispatching skills pass package metadata as a dict; `resolve_model()` does not load YAML itself.
6. **Measurable scenario criteria** — Replaced subjective "focused on cross-cutting concerns" and "report results concisely" with pattern-matchable phrases.

### Alternatives Considered
- Creating separate task for prompt composition utility: rejected because it naturally belongs in the same module as `load_archetypes_config()`
- Adding escalation metadata to Task dataclass: rejected because dispatch-time resolution (D3) is simpler

### Trade-offs
- Accepted more verbose task descriptions over terseness, because implementers need clarity on metadata flow and test approach

### Open Questions
- [ ] Escalation threshold tuning: initial values (3 dirs, 2 deps, 500 LOC) still need empirical validation
- [ ] Whether custom user-defined archetypes should be supported beyond the 6 predefined ones

### Context
Parallel 5-agent analysis across completeness, clarity/consistency, feasibility/parallelizability, security/performance, and testability. 15 findings at medium+ severity. Fixed: missing test task for fallback chain, work-package dependency gap, phantom contract references, subjective scenario language, prompt composition ownership, escalation metadata flow, verification command coverage, and spec field cleanup.

---

## Phase: Plan Iteration 2 (2026-04-10)

**Agent**: claude-local | **Session**: N/A

### Decisions
1. **Add failure scenario for fallback chain exhaustion** — Requirement 5 only had a 429-fallback success scenario. Added scenario for when all models in the chain are exhausted.
2. **Add failure scenario for invalid archetype in work package** — Requirement 7 only had success scenarios. Added validation failure scenario for invalid archetype name pattern.

### Alternatives Considered
- Skipping Req 5 failure scenario: rejected because the boundary between archetype fallback and existing chain exhaustion needs explicit specification

### Trade-offs
- None significant — both additions are small, targeted scenario additions

### Open Questions
- [ ] Escalation threshold tuning: initial values (3 dirs, 2 deps, 500 LOC) still need empirical validation

### Context
Focused scenario coverage pass. Found 2 requirements (Fallback Chain Integration, Work Package Archetype Field) with only success-path scenarios. Added failure/edge-case scenarios for both. All 7 requirements now have success + failure coverage.
