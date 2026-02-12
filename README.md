# Agentic Coding Tools

Tools and workflows for AI-assisted software development. Enables structured feature development with human approval gates and safe multi-agent collaboration on shared codebases.

## Projects

### Agent Coordinator

Multi-agent coordination system for AI coding assistants. Provides file locking, work queues, session handoffs, and agent discovery backed by Supabase.

- [Overview](docs/agent-coordinator.md) — Architecture, capabilities, and design decisions
- [Quick Start](agent-coordinator/README.md) — Setup, installation, and MCP integration
- [Specification](openspec/specs/agent-coordinator/spec.md) — 33 formal requirements

### Skills Workflow

Structured feature development workflow using Claude Code slash commands. Guides features from planning through implementation to completion, with human approval gates at every stage.

- [Workflow Guide](docs/skills-workflow.md) — Stage-by-stage explanation and design principles
- [Specification](openspec/specs/skill-workflow/spec.md) — 14 formal requirements
- [Skills Directory](skills/) — All skill definitions

## Getting Started

**Agent Coordinator**: Follow the [Quick Start](agent-coordinator/README.md) to set up Supabase, install dependencies, and configure Claude Code's MCP integration.

**Skills Workflow**: The skills are Claude Code slash commands defined in [`skills/`](skills/). Each skill is a `SKILL.md` file that Claude Code reads when invoked with `/skill-name`. Start with [`/plan-feature`](skills/plan-feature/SKILL.md) to create a proposal for your next feature.

## Project Structure

```
agentic-coding-tools/
├── agent-coordinator/       # Multi-agent coordination system
│   ├── src/                 # MCP server, locking, work queue
│   ├── supabase/            # Database migrations
│   └── tests/               # Unit and integration tests
├── skills/                  # Claude Code slash commands
│   ├── plan-feature/        # Create OpenSpec proposal
│   ├── iterate-on-plan/     # Refine proposal
│   ├── implement-feature/   # Build and create PR
│   ├── iterate-on-implementation/  # Refine implementation
│   ├── validate-feature/    # Deploy and test locally
│   ├── cleanup-feature/     # Merge, archive, cleanup
│   ├── merge-pull-requests/ # Triage and merge PRs
│   ├── prioritize-proposals/# Rank active proposals
│   ├── update-specs/        # Sync specs with reality
│   └── openspec-beads-worktree/  # Coordinate with Beads
├── openspec/                # Specifications and proposals
│   ├── specs/               # Formal specifications
│   └── changes/             # Active and archived proposals
└── docs/                    # Documentation
    ├── skills-workflow.md   # Workflow guide
    └── agent-coordinator.md # Coordinator overview
```

## Specifications

All features are formally specified using [OpenSpec](https://github.com/fission-ai/openspec):

| Spec | Requirements | Description |
|------|-------------|-------------|
| [agent-coordinator](openspec/specs/agent-coordinator/spec.md) | 33 | File locking, work queue, MCP/HTTP, verification, guardrails |
| [skill-workflow](openspec/specs/skill-workflow/spec.md) | 14 | Iterative refinement, parallel execution, worktree isolation |
| [evaluation-framework](openspec/specs/evaluation-framework/spec.md) | — | Benchmarking harness for coordination effectiveness |
| [merge-pull-requests](openspec/specs/merge-pull-requests/spec.md) | — | PR triage, review, and merge from multiple sources |

## Contributing

This project uses a spec-driven development workflow:

1. **Plan** — Create a proposal with `/plan-feature` describing what you want to build
2. **Implement** — After approval, build it with `/implement-feature`
3. **Validate** — Optionally verify with `/validate-feature`
4. **Cleanup** — Merge and archive with `/cleanup-feature`

See [Skills Workflow](docs/skills-workflow.md) for the full guide.

## License

MIT
