# Session Log: cli-help-discovery

---

## Phase: Plan (2026-04-09)

**Agent**: claude-opus-4-6 | **Session**: planning

### Decisions
1. **Pure service layer approach** — Static in-code registry of HelpTopic dataclasses, shared across all three transports. Zero infrastructure dependencies. Selected over auto-generation (quality ceiling too low for workflow guidance) and DB-backed (overkill for 15 topics).
2. **Static now, extensible later** — The `get_help_overview` / `get_help_topic` / `list_topic_names` interface is designed so runtime extension (plugin registration) can be added without breaking changes.
3. **Transport-agnostic content** — Same help content regardless of caller transport (MCP, HTTP, CLI). Avoids content branching complexity.
4. **Show all topics always** — No capability-aware filtering. Agents see all 15 topics regardless of which services are online, enabling discovery of capabilities they might want enabled.
5. **No auth on help endpoints** — Help is a discovery mechanism; requiring auth would defeat the purpose for agents that haven't authenticated yet.

### Alternatives Considered
- Auto-generation from tool introspection: rejected because the most valuable content (workflow choreography, best practices, anti-patterns) can't be extracted from docstrings
- Database-backed registry: rejected because it adds infrastructure dependency for a feature that changes infrequently
- Capability-aware filtering: rejected because showing all topics helps agents learn about capabilities they might want enabled

### Trade-offs
- Accepted manual content maintenance over auto-generation because workflow guidance quality matters more than sync guarantees
- Accepted sequential tier over parallel because the feature is scoped to a single component (agent-coordinator)

### Open Questions
- [ ] Should help content include MCP resource documentation (locks://current, etc.) in addition to tools?
- [ ] Should the help system version track independently from the coordinator version?

### Context
The feature addresses the problem of MCP's eager schema loading consuming ~6-8K tokens of agent context for 53 tool schemas. By adding a two-tier progressive discovery system (compact overview + detailed per-topic help), agents can pull capability documentation on-demand, reducing context consumption by 10-20x for typical workflows. Implementation already exists on the `claude/add-cli-help-feature-3dmTC` branch with 24 passing tests.
