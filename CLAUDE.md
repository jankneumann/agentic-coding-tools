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

Use the 4-skill feature workflow with natural approval gates:

```
/plan-feature <description>                    → Proposal approval gate
  /iterate-on-plan <change-id> (optional)      → Refines plan before approval
/implement-feature <change-id>                 → PR review gate
  /iterate-on-implementation <change-id> (optional)  → Refinement complete
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

### OpenSpec Integration

- **All planning through OpenSpec**: Use `/openspec-proposal` for any non-trivial feature. This creates a traceable record of decisions and enables spec-driven development.

- **Spec deltas over ad-hoc docs**: Put requirements and scenarios in `openspec/changes/<id>/specs/` rather than separate planning documents. This ensures specs stay updated.

- **Archive after merge**: Always run `/openspec-archive` after PR merge to consolidate spec deltas into `openspec/specs/`.

### Language & Architecture Choices

- **Python for I/O-bound coordination services**: Despite Go/Rust being faster, Python is the right choice for services that spend most time waiting on databases and HTTP calls. FastMCP and Supabase SDKs are mature.

- **MCP for local agents, HTTP for cloud**: Local agents (Claude Code CLI) use MCP via stdio. Cloud agents can't use MCP and need HTTP API endpoints.

### Git Conventions

- **Branch naming**: `openspec/<change-id>` for OpenSpec-driven features
- **Commit format**: Reference the OpenSpec change-id in commit messages
- **PR template**: Include link to `openspec/changes/<change-id>/proposal.md`