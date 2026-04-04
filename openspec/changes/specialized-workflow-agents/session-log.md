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
