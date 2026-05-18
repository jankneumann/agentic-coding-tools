# Agentic Coding Tools

The bottleneck in software engineering is no longer model intelligence — it's **human attention**. This repo gives you the primitives to decide *what* to build, then run the *how* asynchronously for hours or days, with safety rails that survive long-horizon execution.

Three roles do the work: **Orchestrators** plan and define correctness, **Workers** implement against clean context, **Validators** verify adversarially. Features run with **scope-isolated parallelism** (one agent, one worktree, one branch) to avoid stepping on each other; reads, research, and reviews always run in parallel. State survives long pauses through **structured handoffs** at milestone boundaries.

The skills here are **harness-agnostic**: they install into Claude Code (`.claude/skills/`), Codex (`.agents/skills/`), Gemini (`.gemini/`), and any other harness that can discover Markdown-based skill definitions. The same `SKILL.md` file drives the same workflow regardless of which assistant invokes it.

## Three Roles

### Orchestrators
Plan work, define correctness up-front via OpenSpec scenarios, decompose into work packages, dispatch and converge.
- `/explore-feature` — surface high-value next features from architecture artifacts and code signals
- `/plan-feature` — create an OpenSpec proposal with approaches considered + work packages
- `/iterate-on-plan` — refine the proposal via structured self-review before approval
- `/prototype-feature` — dispatch N parallel variant skeletons for human pick-and-choose convergence
- `/implement-feature` — orchestrate work-package dispatch (also a Worker for sequential tier)
- `/plan-roadmap` / `/autopilot-roadmap` — decompose a multi-feature proposal and execute it iteratively
- `/autopilot` — drive the full plan → review → implement → validate → PR lifecycle with multi-vendor convergence

### Workers
Implement work packages against clean context, scoped to non-overlapping `write_allow` globs.
- `/implement-feature` — write code, tests, and docs per work package
- `/iterate-on-implementation` — refine the implementation via structured self-review
- `/quick-task` — delegate small ad-hoc tasks to any configured vendor without OpenSpec ceremony

### Validators
Verify correctness adversarially across two surfaces:
- **Scrutiny validators** — `/parallel-review-plan` and `/parallel-review-implementation` dispatch vendor-diverse reviewers (Claude, Codex, Gemini) and merge their structured findings against `review-findings.schema.json` via `consensus_synthesizer.py`
- **Behavioral validators** — `/gen-eval` runs scenarios against the live deployment (HTTP/MCP/CLI surfaces); the Playwright validator covers frontend surfaces. Both produce findings in the same schema, merged into a single ranked list
- **Quality validators** — `/bug-scrub`, `/security-review`, `/tech-debt-analysis`, `/simplify` for cross-cutting health checks

## Projects

### Agent Coordinator

Multi-agent coordination system for AI coding assistants. Provides file locking, work queues, session handoffs, and agent discovery backed by PostgreSQL (ParadeDB by default for local development; Supabase supported as an optional cloud-managed backend).

The coordinator pairs with **worktree isolation** (`.git-worktrees/<change-id>/<agent-id>/`) so that multiple agents can write in parallel without colliding on the shared checkout. Each agent gets its own checkout, its own branch (`openspec/<change-id>--<agent-id>`), and a heartbeat-backed lease in the worktree registry. When the work converges, `merge_worktrees.py` integrates the per-package branches back into the feature branch. In cloud-harness environments where each agent already gets an isolated container, worktree operations short-circuit transparently — see [`docs/cloud-vs-local-execution.md`](docs/cloud-vs-local-execution.md).

- [Overview](docs/agent-coordinator.md) — Architecture, capabilities, and design decisions
- [Quick Start](agent-coordinator/README.md) — Setup, installation, and MCP integration
- [Parallel Agentic Development](docs/parallel-agentic-development.md) — Worktree isolation, scope discipline, parallel DAG execution
- [Specification](openspec/specs/agent-coordinator/spec.md) — formal requirements

### Skills Framework

Structured feature development workflow distributed as **harness-agnostic skills**. Each skill is a `SKILL.md` file with YAML frontmatter (`name`, `description`, `triggers`, `user_invocable`, `related`) and Markdown body. `skills/install.sh` rsyncs the canonical sources at `skills/` into harness-specific runtime directories (`.claude/skills/`, `.agents/skills/` for Codex, plus per-vendor variants). The same skill drives the same workflow whether invoked via Claude Code's `/skill-name`, Codex's slash palette, or Gemini's tooling.

- [Workflow Guide](docs/skills-workflow.md) — Stage-by-stage explanation and design principles
- [Skills Catalogue](docs/skills-catalogue.md) — Discoverable index of every skill grouped by purpose
- [Project Guidelines](CLAUDE.md) — Workflow tables, conventions, worktree contract, git conventions
- [Specification](openspec/specs/skill-workflow/spec.md) — formal requirements

## Getting Started

**Agent Coordinator**: Follow the [Quick Start](agent-coordinator/README.md) to start PostgreSQL (ParadeDB via Docker Compose, or Supabase), install dependencies, and configure your harness's MCP integration.

**Skills Framework**: Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to sync skills into the harness directories present in your repo. Each skill is then invocable via your harness's slash-command palette. Start with [`/plan-feature`](skills/plan-feature/SKILL.md) to create a proposal for your next feature, or [`/explore-feature`](skills/explore-feature/SKILL.md) if you don't yet know what to build.

**Cross-repo usage**: To use these skills from a different repository, see [`docs/cross-repo-setup.md`](docs/cross-repo-setup.md).

## Project Structure

```
agentic-coding-tools/
├── agent-coordinator/       # Multi-agent coordination system (MCP server, locking, work queue)
├── skills/                  # Canonical skill sources (≈55 skills, harness-agnostic)
│   ├── plan-feature/        #   Feature workflow: plan → implement → validate → cleanup
│   ├── autopilot/           #   Multi-vendor convergence orchestrators
│   ├── parallel-review-*/   #   Vendor-diverse adversarial review
│   ├── worktree/            #   Worktree lifecycle (setup/teardown/merge/GC)
│   ├── references/          #   Shared checklists cited by multiple skills
│   └── tests/               #   Skill tests (excluded from install.sh rsync)
├── openspec/                # Specifications and proposals
│   ├── specs/               #   21 formal specifications
│   └── changes/             #   Active and archived proposals
├── docs/                    # Documentation (see CLAUDE.md § Documentation for the index)
├── evaluation/              # Benchmarking harness for coordination effectiveness
├── formal/                  # Formal models and verification artifacts
├── scripts/                 # Cross-cutting helper scripts
├── .agents/skills/          # Codex runtime copy (regenerated by skills/install.sh)
├── .claude/skills/          # Claude Code runtime copy (regenerated by skills/install.sh)
├── .codex/                  # Codex harness config
├── .gemini/                 # Gemini harness config
└── .githooks/               # pre-commit / post-merge hooks (incl. coordinator-task-status-renderer)
```

**Important**: `.claude/skills/` and `.agents/skills/` are **runtime copies** rsynced from `skills/` by `install.sh`. Never edit them directly — changes will be overwritten. Always edit the canonical sources at `skills/<skill-name>/SKILL.md`.

## Specifications

All features are formally specified using [OpenSpec](https://github.com/fission-ai/openspec). The full set lives at [`openspec/specs/`](openspec/specs/). Headline specs:

| Spec | Description |
|------|-------------|
| [agent-coordinator](openspec/specs/agent-coordinator/spec.md) | File locking, work queue, MCP/HTTP, verification, guardrails |
| [skill-workflow](openspec/specs/skill-workflow/spec.md) | Iterative refinement, parallel execution, worktree isolation |
| [worktree](openspec/specs/worktree/spec.md) | Worktree lifecycle, registry, branch resolution, GC |
| [coordination-bridge](openspec/specs/coordination-bridge/spec.md) | HTTP fallback when MCP transport is unavailable |
| [agent-archetypes](openspec/specs/agent-archetypes/spec.md) / [agent-identity](openspec/specs/agent-identity/spec.md) | Vendor routing and agent identity model |
| [evaluation-framework](openspec/specs/evaluation-framework/spec.md) / [gen-eval-framework](openspec/specs/gen-eval-framework/spec.md) | Behavioural validation harnesses |
| [live-service-testing](openspec/specs/live-service-testing/spec.md) / [observability](openspec/specs/observability/spec.md) | Validation against deployed services |
| [merge-pull-requests](openspec/specs/merge-pull-requests/spec.md) | PR triage, review, and merge from multiple sources |
| [roadmap-orchestration](openspec/specs/roadmap-orchestration/spec.md) | Multi-feature decomposition and autopilot execution |

See [`docs/skills-catalogue.md`](docs/skills-catalogue.md) for the complete skill inventory and [`CLAUDE.md`](CLAUDE.md) for the canonical workflow tables.

## Workflow

The canonical single-feature flow with all optional refinement and review gates:

```
/explore-feature [focus-area] (optional)                  → Candidate shortlist for next work
/plan-feature <description>                               → Proposal approval gate
  /iterate-on-plan <change-id> (optional)                 → Refines plan before approval
  /parallel-review-plan <change-id> (optional)            → Independent plan review (vendor-diverse)
  /prototype-feature <change-id> (optional)               → N parallel variant skeletons + human pick-and-choose
/implement-feature <change-id>                            → PR review gate (runs spec + evidence validation)
  /iterate-on-implementation <change-id> (optional)       → Refinement before merge
  /parallel-review-implementation <change-id> (optional)  → Per-package review (vendor-diverse)
/cleanup-feature <change-id>                              → Done (runs deploy + security validation before merge)
```

Each skill auto-selects an execution tier (**coordinated** / **local-parallel** / **sequential**) based on coordinator availability and feature complexity. For long-running multi-feature work, `/plan-roadmap` + `/autopilot-roadmap` automate the loop with learning feedback between iterations.

For deeper detail see [`CLAUDE.md`](CLAUDE.md), [`docs/skills-workflow.md`](docs/skills-workflow.md), and [`docs/parallel-agentic-development.md`](docs/parallel-agentic-development.md).

## License

MIT
