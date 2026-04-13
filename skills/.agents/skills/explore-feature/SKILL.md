---
name: explore-feature
description: Identify high-value next features using architecture artifacts, code signals, and active OpenSpec context
category: Git Workflow
tags: [openspec, discovery, architecture, prioritization, parallel]
triggers:
  - "explore feature"
  - "what should we build next"
  - "identify next feature"
  - "feature discovery"
  - "linear explore feature"
  - "parallel explore feature"
  - "parallel explore"
  - "explore parallel feature"
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

## Coordinator Integration (Optional)

Use `docs/coordination-detection-template.md` as the shared detection preamble.

- Detect transport and capability flags at skill start
- Execute hooks only when the matching `CAN_*` flag is `true`
- If coordinator is unavailable, continue with standalone behavior

## Steps

### 0. Detect Coordinator and Recall Memory

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_MEMORY=true`, recall relevant history before analysis:

- MCP path: call `recall` with tags like `["feature-discovery", "<focus-area>"]`
- HTTP path: use `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_recall(...)`

On recall failure/unavailability, continue normally and log informationally.

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

### 2.5. Analyze Gen-Eval Signals (if available)

Check for recent gen-eval reports. These provide empirical evidence of interface reliability and coverage gaps:

```bash
# Look for gen-eval reports in the project
# Use -newer filter only if opportunities.json exists; otherwise find any report
if [ -f docs/feature-discovery/opportunities.json ]; then
  GENEVAL_REPORT=$(find . -name "gen-eval-report.json" -type f -newer docs/feature-discovery/opportunities.json 2>/dev/null | head -1)
else
  GENEVAL_REPORT=$(find . -name "gen-eval-report.json" -type f 2>/dev/null | sort -t/ -k1 | head -1)
fi
```

If a report exists, extract:
- **Failing interfaces**: Endpoints/tools with `fail` or `error` verdicts — these represent concrete bugs or regressions that could become fix opportunities
- **Coverage gaps**: Interfaces in the descriptor with 0% scenario coverage — these are untested and risky
- **Category pass rates**: Categories with pass rates below 95% indicate areas needing attention
- **Cross-interface inconsistencies**: Scenarios where the same operation produces different results across transports (HTTP vs MCP vs CLI)

Incorporate these signals into opportunity ranking:
- A failing interface that matches an existing opportunity **increases its impact score**
- A coverage gap with no existing opportunity **creates a new `add-` opportunity** with `quick-win` bucket (writing scenarios is low effort)
- Cross-interface inconsistencies suggest `fix-` opportunities targeting the inconsistent service layer

If no report exists, skip this step and note "No gen-eval data available" in the output.

### 2.6. Archive Intelligence Signals

Check for an archive-intelligence index that provides exemplars and patterns from completed changes:

```bash
ARCHIVE_INDEX="docs/factory-intelligence/archive-index.json"
EXEMPLAR_REGISTRY="docs/factory-intelligence/exemplars.json"
```

If the archive index exists, use it to:
- **Identify recurring patterns**: Changes that share capability areas with opportunities suggest proven implementation approaches
- **Reference exemplars**: Link opportunities to similar past changes for estimation calibration
- **Detect coverage gaps**: Capabilities with archived changes but no exemplars may need better test coverage
- **Seed scenario suggestions**: Archived scenario seeds relevant to an opportunity's capability area

Include archive signals in the opportunity output when relevant. If neither file exists, skip and note "No archive intelligence available."

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

### 3.5. Enumerate Active Resource Claims [coordinated only]

**Coordinator-dependent step** (requires `CAN_DISCOVER` and `CAN_LOCK`). Skip if coordinator is unavailable.

- Call `check_locks()` to get all active file and logical locks
- Call `discover_agents()` to enumerate in-flight features and their claimed resources
- Build a resource occupation map: which files, API endpoints, DB schemas, and events are currently claimed

### 3.6. Assess Parallel Feasibility [coordinated only]

For each candidate from Step 3, if resource claims were enumerated in Step 3.5:

1. **Estimate scope**: Identify likely files, API endpoints, DB tables, and events the feature would touch
2. **Check lock overlap**: Compare estimated scope against the resource occupation map
3. **Classify feasibility**:
   - `FULL` -- No resource overlap; safe for full parallel execution
   - `PARTIAL` -- Some overlap; can run in parallel with serialized access to shared resources
   - `SEQUENTIAL` -- Heavy overlap; must wait for in-flight features to complete

Add these fields to the ranked output when available:

| Field | Description |
|-------|-------------|
| Parallel Feasibility | `FULL` / `PARTIAL` / `SEQUENTIAL` (or `N/A` if coordinator unavailable) |
| Resource Conflicts | List of overlapping locks (if any) |
| Independent Zones | Which `parallel_zones.json` groups are available |

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
- If gen-eval signals were available (step 2.5), include a `gen_eval_signals` field in `opportunities.json` with: `{ "report_path": "<path>", "failing_interfaces": [...], "coverage_pct": <float>, "categories_below_threshold": [...] }`

## Output

- Prioritized feature opportunity list with rationale
- One recommended next feature and concrete follow-up command
- Machine-readable discovery output path(s) and whether recommendation history altered ranking
