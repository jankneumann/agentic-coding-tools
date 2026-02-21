---
name: explore-feature
description: Identify high-value next features using architecture artifacts, code signals, and active OpenSpec context
category: Git Workflow
tags: [openspec, discovery, architecture, prioritization]
triggers:
  - "explore feature"
  - "what should we build next"
  - "identify next feature"
  - "feature discovery"
---

# Explore Feature

Analyze the current codebase and workflow state to recommend what to build next.

## Arguments

`$ARGUMENTS` - Optional focus area (for example: "performance", "refactoring", "cost", "usability", "security")

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Steps

### 1. Gather Current State

```bash
openspec list --specs
openspec list
```

Collect:
- Existing capabilities and requirement density
- Active changes already in progress
- Gaps between specs and current priorities

### 2. Analyze Architecture and Code Signals

```bash
test -f docs/architecture-analysis/architecture.summary.json || make architecture
```

Use:
- `docs/architecture-analysis/architecture.summary.json`
- `docs/architecture-analysis/architecture.diagnostics.json` (if present)
- `docs/architecture-analysis/parallel_zones.json`

Look for:
- Structural bottlenecks and high-impact nodes
- Refactoring opportunities and coupling hotspots
- Code smell clusters and maintainability risks
- Usability gaps, reliability risks, performance/cost hotspots

### 3. Produce Ranked Opportunities

Generate a ranked shortlist (3-7 items), each with:
- Problem statement
- User/developer impact
- Estimated effort (S/M/L)
- Risk level (low/med/high)
- Strategic fit (`low`/`med`/`high`)
- Weighted score using a reproducible formula:
  - `score = impact*0.4 + strategic_fit*0.25 + (4-effort)*0.2 + (4-risk)*0.15`
  - Use numeric mapping: `low=1`, `med=2`, `high=3`; `S=1`, `M=2`, `L=3`
- Category bucket:
  - `quick-win` (high score, low effort/risk)
  - `big-bet` (high potential impact with medium/high effort)
- Suggested OpenSpec change-id prefix (`add-`, `update-`, `refactor-`, `remove-`)
- `blocked-by` dependencies (existing change-ids, missing infra, unresolved design decisions)
- Recommended next action (`/plan-feature` now, or defer)

### 4. Recommend Next Execution Path

For the top recommendation, include:
- Why now
- Dependencies or blockers
- Suggested starter command:
  - `/plan-feature <description>`
  - or `/iterate-on-plan <change-id>` if a related proposal exists

### 5. Persist Discovery Artifacts

Write/update machine-readable discovery artifacts:
- `docs/feature-discovery/opportunities.json` (current ranked opportunities)
- `docs/feature-discovery/history.json` (recent top recommendations with timestamps/status)

Rules:
- If an opportunity from recent history is still deferred and unchanged, lower its default priority unless new evidence justifies reranking
- Include stable IDs so `/prioritize-proposals` can reference opportunities without text matching

## Output

- Prioritized feature opportunity list with rationale
- One recommended next feature and concrete follow-up command
- Machine-readable discovery output path(s) and whether recommendation history altered ranking
