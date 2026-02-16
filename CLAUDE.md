<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# Project Guidelines

## Workflow

Use the 5-skill feature workflow with natural approval gates:

```
/plan-feature <description>                    → Proposal approval gate
  /iterate-on-plan <change-id> (optional)      → Refines plan before approval
/implement-feature <change-id>                 → PR review gate
  /iterate-on-implementation <change-id> (optional)  → Refinement complete
  /validate-feature <change-id> (optional)     → Live deployment verification
/cleanup-feature <change-id>                   → Done
```

## Lessons Learned

### Skill Design Patterns

- **Match skills to approval gates**: Each skill should end at a natural handoff point where human approval is needed. This creates clean boundaries and supports async workflows.

- **Separate creative from mechanical work**: Planning and implementation are creative; cleanup/archival is mechanical. Different skills for different work types allows delegation and automation.

- **Use consistent frontmatter format**: Skills should have `name`, `description`, `category`, `tags`, and `triggers` in YAML frontmatter.

- **Flat skill directory structure**: Claude Code skills don't support nested directories. Each skill must be `<skill-name>/SKILL.md`. For namespaced skills, use hyphens: `openspec-proposal/SKILL.md` not `openspec/proposal/SKILL.md`. Symlink to `~/.claude/skills/` for global availability.

- **Iterate at both creative stages**: Plans and implementations both benefit from structured iteration loops with domain-specific finding types and quality checks. `/iterate-on-plan` refines proposals before approval; `/iterate-on-implementation` refines code before PR review.

- **Plan for parallel execution**: Task decomposition in proposals should explicitly identify dependencies and maximize independent work units. This enables `/parallel-implement` to spawn isolated agents without merge conflicts.

### Task() Parallelization Patterns

- **Use Task() for parallel work**: The native Task() tool with `run_in_background=true` replaces external CLI spawning (`claude -p`) and git worktrees. Send multiple Task() calls in a single message to run them concurrently.

- **Parallel quality checks**: Run pytest, mypy, ruff, and openspec validate concurrently. Collect all results before reporting—don't fail-fast on first error. This gives users a complete picture of issues.

- **Parallel exploration**: Use Task(Explore) agents to gather context from multiple sources concurrently. This is read-only and safe to parallelize unconditionally.

- **File scope isolation**: For parallel implementation tasks, each agent's prompt must explicitly list which files it may modify. Tasks with overlapping file scope must run sequentially, not in parallel.

- **No worktrees needed**: Task() agents are orchestrator-coordinated. The old worktree pattern was needed because external `claude -p` processes had no coordination. With Task(), logical file scoping via prompts replaces physical isolation via worktrees.

- **Result aggregation**: After parallel tasks complete, the orchestrator collects results via TaskOutput, verifies work, and commits. Don't let agents commit directly—the orchestrator should control the commit.

### OpenSpec Integration

- **All planning through OpenSpec**: Use `/openspec-proposal` for any non-trivial feature. This creates a traceable record of decisions and enables spec-driven development.

- **Spec deltas over ad-hoc docs**: Put requirements and scenarios in `openspec/changes/<id>/specs/` rather than separate planning documents. This ensures specs stay updated.

- **Archive after merge**: Always run `/openspec-archive` after PR merge to consolidate spec deltas into `openspec/specs/`.

### Local Validation Patterns

- **Parameterize docker-compose host ports**: Coordination stacks frequently run alongside other local services. Use env-driven host port mappings (for example `AGENT_COORDINATOR_REST_PORT`) instead of hardcoded ports so validation can run without stopping unrelated containers.

- **Keep E2E base URL configurable**: End-to-end tests should read `BASE_URL` and never hardcode `localhost:3000`. This allows validation against remapped ports (for example `BASE_URL=http://localhost:13000`).

- **Validate with remapped ports as a first-class path**: When defaults are occupied, run `docker compose` with `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, and `AGENT_COORDINATOR_REALTIME_PORT`, then execute e2e with matching `BASE_URL`.

### Language & Architecture Choices

- **Python for I/O-bound coordination services**: Despite Go/Rust being faster, Python is the right choice for services that spend most time waiting on databases and HTTP calls. FastMCP and Supabase SDKs are mature.

- **MCP for local agents, HTTP for cloud**: Local agents (Claude Code CLI) use MCP via stdio. Cloud agents can't use MCP and need HTTP API endpoints.

### Git Conventions

- **Branch naming**: `openspec/<change-id>` for OpenSpec-driven features
- **Commit format**: Reference the OpenSpec change-id in commit messages
- **PR template**: Include link to `openspec/changes/<change-id>/proposal.md`

## Architecture Artifacts

The `docs/architecture-analysis/` directory contains auto-generated structural analysis of the codebase. These artifacts are committed and should be consulted by agents during planning and validation.

### Key Files
- `docs/architecture-analysis/architecture.summary.json` — Compact summary with cross-layer flows, stats, disconnected endpoints
- `docs/architecture-analysis/architecture.graph.json` — Full canonical graph (nodes, edges, entrypoints)
- `docs/architecture-analysis/architecture.diagnostics.json` — Validation findings (errors, warnings, info)
- `docs/architecture-analysis/parallel_zones.json` — Independent module groups for safe parallel modification
- `docs/architecture-analysis/architecture.report.md` — Narrative architecture report
- `docs/architecture-analysis/views/` — Auto-generated Mermaid diagrams

### Usage
- **Before planning**: Read `architecture.summary.json` to understand component relationships and existing flows
- **Before implementing**: Check `parallel_zones.json` for safe parallel modification zones
- **After implementing**: Run `make architecture-validate` to catch broken flows
- **Refresh**: Run `make architecture` to regenerate all artifacts

### Refresh Commands
```bash
make architecture              # Full refresh
make architecture-validate     # Validate only
make architecture-views        # Regenerate views only
make architecture-diff BASE_SHA=<sha>  # Compare to baseline
make architecture-feature FEATURE="file1,file2"  # Feature slice
```

## Documentation

- [Skills Workflow](docs/skills-workflow.md) — Workflow guide, stage-by-stage explanation, design principles
- [Agent Coordinator](docs/agent-coordinator.md) — Architecture overview, capabilities, design pointers
