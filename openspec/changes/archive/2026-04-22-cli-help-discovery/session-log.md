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
The feature addresses the problem of MCP eager schema loading consuming 6-8K tokens of agent context for 53 tool schemas. By adding a two-tier progressive discovery system (compact overview plus detailed per-topic help), agents can pull capability documentation on-demand, reducing context consumption by 10-20x for typical workflows. Implementation already exists on the dev branch with 24 passing tests.

---

## Phase: Implementation (2026-04-09)

**Agent**: claude-opus-4-6 | **Session**: implement-feature

### Decisions
1. **Cherry-pick from dev branch** — Reused the existing implementation from the dev branch rather than reimplementing from scratch, since all 24 tests and the full service layer were already complete and passing.
2. **Manual conflict resolution for coordination_api.py** — The cherry-pick had merge conflicts in the health endpoint section. Resolved by keeping the worktree's original inline health endpoint and removing duplicate `/live`, `/ready`, `/health` endpoints that referenced a non-existent `_database_health()` helper.
3. **Runtime import pattern for TestClient** — Used `TYPE_CHECKING` guard for type hints with runtime import inside the fixture to avoid import-time dependency on FastAPI in the test module header.

### Alternatives Considered
- Full reimplementation in the worktree: rejected because identical code already existed and was tested on the dev branch
- Keeping both health endpoint patterns: rejected because the `_database_health()` helper doesn't exist on the feature branch

### Trade-offs
- Accepted cherry-pick complexity over reimplementation because it preserved the exact tested code
- Accepted manual conflict resolution over automated merge because only one file had conflicts and the resolution was straightforward

### Open Questions
- [ ] Should help content include MCP resource documentation (locks://current, etc.) in addition to tools?
- [ ] Should the help system version track independently from the coordinator version?

### Context
Implementation was cherry-picked from the dev branch into the OpenSpec worktree. The main deviation from plan was resolving a merge conflict in `coordination_api.py` where the health endpoint section differed between branches. After resolution, all 46 tests pass (24 help-specific + 22 coordination API) and ruff reports no issues across all modified files.

---

## Phase: Implementation Iteration 1 (2026-04-09)

**Agent**: claude-opus-4-6 | **Session**: iterate-on-implementation

### Decisions
1. **Remove repr formatting from error messages** — All three transports used `f"Unknown topic: {topic!r}"` which embeds Python-specific quoting in API responses. Changed to plain `f"Unknown topic: {topic}"` for cleaner, transport-neutral output.
2. **Add hint field to CLI JSON error response** — The MCP and HTTP transports included a `hint` field in unknown-topic errors, but CLI JSON mode omitted it. Added for cross-transport schema consistency per spec scenario 9.

### Alternatives Considered
- Keeping `!r` formatting: rejected because it embeds Python-specific syntax in a transport-neutral API
- Omitting hint from all transports: rejected because hints improve agent self-correction behavior

### Trade-offs
- Accepted slight verbosity in error responses over minimalism because the hint actively helps agents recover from bad topic names

### Open Questions
- None new

### Context
Iteration 1 identified 4 findings (2 medium, 2 low). Fixed both medium-criticality findings: cross-transport error schema consistency (missing hint in CLI JSON) and inconsistent error message formatting (repr vs plain). Added 1 new test for CLI JSON error hint field. All 47 tests pass.
