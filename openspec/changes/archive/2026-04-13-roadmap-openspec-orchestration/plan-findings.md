# Plan Findings: roadmap-openspec-orchestration

## Iteration 1 (2026-04-13)

| # | Type | Criticality | Description | Proposed Fix | Status |
|---|------|-------------|-------------|--------------|--------|
| 1 | consistency | high | Proposal lacked explicit Impact section mapping to spec deltas and touched docs/skills. | Add Impact section with affected specs/skills/docs. | Fixed |
| 2 | testability | high | Requirement groups had limited explicit failure-path scenarios. | Add failure/edge scenarios for decomposition, scheduling, and artifact corruption. | Fixed |
| 3 | parallelizability | medium | `work-packages.yaml` used only `wp-main`, limiting parallel planning and ownership clarity. | Split into runtime, plan-roadmap, autopilot-roadmap, and integration packages with dependencies. | Fixed |
| 4 | assumptions | medium | Policy defaults and canonical state assumptions were implicit. | Record explicit planning decisions in proposal and iterate log. | Fixed |
| 5 | consistency | medium | Task contract path reference did not match artifact location. | Correct task contract reference to `openspec/changes/.../contracts/README.md`. | Fixed |

## Iteration 2 (2026-04-13) — Multi-Vendor Review Remediation

Findings from `/parallel-review-plan` (Claude Code + Codex). 11 unique findings after cross-vendor deduplication.

| # | Source | Type | Criticality | Description | Proposed Fix | Status |
|---|--------|------|-------------|-------------|--------------|--------|
| C1 | Claude+Codex | contract_mismatch | high | Core artifact schemas (roadmap.yaml, checkpoint.json, learning-log.md) not defined machine-readably. Contracts/README.md was prose stub. | Add JSON Schema definitions: roadmap.schema.json, checkpoint.schema.json, learning-log.schema.json | Fixed |
| X1 | Codex | contract_mismatch | high | work-packages.yaml missing executor fields (task_type, locks, worktree, verification, outputs, scope.deny). /implement-feature cannot dispatch. | Regenerate with full executor metadata per established schema pattern. | Fixed |
| C2 | Claude+Codex | architecture | medium | wp-runtime write_allow split shared code across two consumer dirs, breaking skills/parallel-infrastructure/ pattern. | Create dedicated skills/roadmap-runtime/ for shared library. | Fixed |
| C3 | Claude+Codex | architecture | medium | Artifact storage location undefined — no canonical path for roadmap workspace or parent-child change references. | Add Artifact Location Model section to design.md with paths, references, worktree scope. | Fixed |
| C4 | Claude+Codex | resilience | medium | No spec scenario for individual roadmap item implementation failure (most common failure mode). | Add "Handle individual item failure" scenario with status transitions and learning entry. | Fixed |
| C5 | Claude+Codex | observability | medium | No structured logging requirements for long-running multi-vendor orchestration. | Add Artifact Observability requirement with scenarios for state transitions, policy decisions, checkpoints. | Fixed |
| X2 | Codex | security | medium | No sanitization requirement for persisted artifacts — learning logs may capture sensitive data. | Add Artifact Sanitization requirement with redaction scenarios for learning entries and checkpoints. | Fixed |
| X3 | Codex | performance | medium | Append-only learning-log.md with no compaction rules — unbounded growth degrades context assembly. | Redesign as root index + learnings/ subfolder per item; compaction at 50-entry threshold. | Fixed |
| Y1 | Claude | spec_gap | medium | No item size validation scenarios during decomposition (merge undersized, split oversized). | Add merge/split scenarios under Proposal Decomposition requirement. | Fixed |
| Y2 | Claude | resilience | medium | Cascading vendor failures not addressed — only single-hop failover specified. | Add "Cascading vendor failures with recursive policy evaluation" scenario with max switch attempts. | Fixed |
| Y3 | Claude | compatibility | low | CLAUDE.md workflow table (loaded every conversation) won't list new roadmap skills. AGENTS.md is symlinked. | Add task 4.3 for CLAUDE.md update with progressive disclosure. Added to wp-integration scope. | Fixed |

## Remaining Findings

- None at or above low threshold.
