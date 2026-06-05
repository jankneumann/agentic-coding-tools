# Workflow

Unified skills with **tiered execution** — each skill auto-selects its tier at startup based on coordinator availability and feature complexity:

| Tier | When | Planning Artifacts | Execution |
|------|------|-------------------|-----------|
| **Coordinated** | Coordinator available | Contracts + work-packages + resource claims | Multi-agent DAG via coordinator |
| **Local parallel** | No coordinator, complex feature | Contracts + work-packages (no claims) | DAG via built-in Agent parallelism |
| **Sequential** | Simple feature | Tasks.md + contracts + work-packages (single package) | Single-agent sequential |

```
/explore-feature [focus-area] (optional)               → Candidate shortlist for next work
/plan-feature <description>                            → Proposal approval gate
  /iterate-on-plan <change-id> (optional)              → Refines plan before approval
  /parallel-review-plan <change-id> (optional)         → Independent plan review (vendor-diverse)
  /prototype-feature <change-id> (optional)            → N parallel variant skeletons + human pick-and-choose
  /iterate-on-plan <change-id> --prototype-context <change-id>  → Convergence: synthesize variants into design.md/tasks.md
/implement-feature <change-id>                         → PR review gate (runs spec + evidence validation)
  /iterate-on-implementation <change-id> (optional)    → Refinement complete
  /parallel-review-implementation <change-id> (optional) → Per-package review (vendor-diverse)
/cleanup-feature <change-id>                           → Done (runs deploy + security validation before merge)

# Roadmap orchestration (multi-change decomposition + iterative execution)
/plan-roadmap <proposal-path>                          → Decompose proposal into prioritized roadmap
/autopilot-roadmap <workspace-path>                    → Execute roadmap items with learning feedback
```

Validation is automatic: `/implement-feature` runs environment-safe checks (spec, evidence), `/cleanup-feature` and `/merge-pull-requests` run Docker-dependent checks (deploy, smoke, security, E2E) before merge. Both delegate to `/validate-feature` with `--phase` selectors. `/validate-feature` can also be invoked directly for a full manual pass.

Old `linear-*` and `parallel-*` prefixed names are accepted as trigger aliases (e.g., "parallel plan feature" triggers `/plan-feature` with at least local-parallel tier).

## Infrastructure Skills

- **`coordination-bridge`** — Coordinator detection (`check_coordinator.py`) and HTTP fallback bridge
- **`parallel-infrastructure`** — Shared parallel execution scripts: DAG scheduler, review dispatcher, consensus synthesizer, scope checker
- **`roadmap-runtime`** — Shared roadmap library: artifact models, checkpoint management, learning-log helpers, sanitization, context assembly
- **`validate-feature`** — Validation phases (spec, evidence, deploy, smoke, security, e2e); called by implement-feature, cleanup-feature, and merge-pull-requests with `--phase` selectors
- **`parallel-review-plan`** / **`parallel-review-implementation`** — Vendor-diverse review utilities (used by implement-feature and autopilot)
- **`coordinator-task-status-renderer`** — Renders the coordinator-owned status block inside `openspec/changes/<id>/tasks.md`. The block (between `<!-- GENERATED: begin coordinator:tasks-status -->` / `end` markers) is an *informational projection* of coordinator state; the hand-authored checkboxes outside the block remain the authoritative source. Wired into `.githooks/pre-commit` (re-render on staged tasks.md), `.githooks/post-merge` (refresh after merges that touch tasks.md), and `/plan-feature` Gate 2 (seeds coordinator issues on Approve).

See [Parallel Agentic Development](../parallel-agentic-development.md) for the full implementation reference.

## Observability Frontends

- **`apps/kanban-viz`** — Real-time Kanban board for coordinator work-queue state. Connects to the coordinator API via SSE for live updates; shows vendor swimlanes, sync-point gate banner, and saved views. This is an observability surface, not a skill — it lives in `apps/` not `skills/`. Dev server: `cd apps/kanban-viz && npm run dev`. See [`docs/kanban-viz/README.md`](../kanban-viz/README.md).
