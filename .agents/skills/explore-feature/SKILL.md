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

### 0.5. Focus Area Interview (vague input only)

If `$ARGUMENTS` is missing, single-word, or matches one of the known broad buckets (`performance`, `refactoring`, `cost`, `usability`, `security`, `quality`, `speed`, `reliability`, `tech-debt`), ask 2-4 short questions to localize the pain **before** running architectural analysis. A scored opportunity ranking is only useful if the scoring criteria match the user's actual itch.

```
RAW="$(echo "$ARGUMENTS" | xargs)"
WORD_COUNT=$(echo "$RAW" | wc -w | tr -d ' ')
BROAD_BUCKETS="performance refactoring cost usability security quality speed reliability tech-debt"

NEEDS_INTERVIEW=false
if [[ -z "$RAW" ]] || [[ "$WORD_COUNT" -le 1 ]]; then
  NEEDS_INTERVIEW=true
elif echo " $BROAD_BUCKETS " | grep -qw "$RAW"; then
  NEEDS_INTERVIEW=true
fi
```

If `NEEDS_INTERVIEW=true`, ask 2-4 questions in a **single batch** via AskUserQuestion. No confidence loop, no follow-ups -- this is a lightweight localization, not a full discovery interview (see `plan-feature` Step 3b.ii for that pattern).

**Question template** (pick the 2-4 most relevant, parameterized by the bucket):

| Bucket | Question 1 (localize "what") | Question 2 (localize "why now") |
|--------|------------------------------|----------------------------------|
| `performance` | "Whose performance? Build time / runtime latency / perceived UX / agent throughput / cost per run" | "What recent moment made you reach for this -- a slow build, a user complaint, a bill?" |
| `refactoring` | "Which axis of debt? Coupling / duplication / unclear naming / dead code / outdated patterns" | "Is there a feature you're avoiding because the surrounding code scares you?" |
| `cost` | "Which cost? LLM API spend / infra / engineering time / agent retries" | "What budget signal triggered this -- a bill, a forecast, a failed audit?" |
| `usability` | "Whose usability? End user / operator / developer / agent" | "Where do people get stuck -- onboarding, daily flow, edge cases, recovery from errors?" |
| `security` | "Which surface? Authn / authz / secrets handling / supply chain / data exfiltration" | "Is this driven by an audit, a recent incident, or proactive hardening?" |
| `reliability` | "Which failure mode? Crashes / data loss / silent corruption / cascading failures / flaky tests" | "What broke recently, or what are you afraid will break?" |
| `tech-debt` / `quality` | "Which symptom hurts most? Test gaps / fragile interfaces / spec drift / undocumented decisions" | "Which area of the codebase do you avoid editing, and why?" |
| `speed` | "Whose speed? Build / test / deploy / agent execution / human iteration" | "What slowness most often blocks you mid-task?" |

**Optional Question 3-4** (open-ended, pick if ambiguity remains):
- "Is there a specific file, module, or workflow you had in mind when you typed `<bucket>`?"
- "Are there approaches you've already tried or rejected for this?"

Capture the answers as `LOCALIZED_FOCUS` -- a short string (e.g., `"runtime latency in agent dispatch loop, triggered by 8s p95 in last week's traces"`) used in Step 3 scoring and Step 5 artifact persistence.

If `NEEDS_INTERVIEW=false`, skip this step entirely and set `LOCALIZED_FOCUS="$ARGUMENTS"`.

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

### 2.7. Reframe and Diversify Before Generating Candidates

Before producing the ranked list, run two short discipline steps. They widen the solution space so the ranking is not a vote among lookalikes.

#### "How Might We" Reframing

Take any concrete pain point surfaced in Steps 1-2.6 (slow build, fragile interface, missing test coverage, etc.) and reframe it as **"How might we ____?"** — a question, not a solution.

Why: a pain like "the dispatch loop is slow" implicitly suggests "make the dispatch loop faster" — which narrows you to one branch of solutions. Reframing as "How might we deliver work to agents without polling?" widens the space to include `pg_notify`, websockets, push-based queues, batched dispatch, etc.

For each candidate pain you surfaced, write at least one HMW reframe before brainstorming candidates. Capture the HMW question alongside the candidate in `opportunities.json` under a new `hmw_reframe` field — this makes the reasoning auditable and lets the next agent see why the candidate was even considered.

#### 8 Ideation Lenses

When generating candidates, deliberately apply each of the lenses below at least once. Don't stop at the first lens that returns a hit — diversity beats local-maxima fixation.

1. **Inversion** — what if we did the opposite? (Instead of "make X faster", "remove X entirely".)
2. **Constraint removal** — what becomes possible if X were free, instant, or unlimited? (e.g., infinite test budget → property tests for every interface.)
3. **Audience shift** — who else would want this, and how does it change? (Internal devs vs. external integrators vs. end users vs. agents.)
4. **Combination** — what if we combined two existing capabilities into one new one? (e.g., gen-eval + archive-intelligence → exemplar-driven scenario seeding.)
5. **Simplification** — what's the smallest version of this that still helps? (Ship the 20% that captures 80% of value.)
6. **10×** — what would it take to make this 10× better instead of 10% better? Forces architectural thinking, not parameter tuning.
7. **Expert** — how would <a person known for solving this class of problem> approach it? (e.g., "How would Hyrum Wright approach this refactor at scale?")
8. **Adjacent** — what's a 1-step-away problem we could solve in passing while we're already in this code?

In `opportunities.json`, tag each candidate with the lens(es) that surfaced it (`lenses_applied: ["inversion", "10x"]`). Candidates surfaced by 2+ lenses are stronger signals than candidates surfaced by one.

#### NOT DOING list

Every candidate report MUST include a top-level `NOT DOING:` section listing the most-tempting alternatives that were considered and rejected, each with a one-line rationale.

```
NOT DOING:
- Rewrite dispatch in Rust — too costly for the latency win available; revisit if profiling shows CPU-bound bottleneck.
- Add a second cache layer — overlaps with planned `cache-unification` change; would create competing surfaces.
- Defer to next quarter — error budget is already burning; deferring compounds the cost.
```

Why this matters: an explore report that lists only what we *will* do hides the alternatives the team rejected. Future agents (and the operator) cannot evaluate the recommendation without seeing the rejected branches. The `NOT DOING:` list is the antidote to confirmation bias.

This section is required: `opportunities.json` MUST have a `not_doing` array (parallel to the ranked list) with `{ "alternative": "...", "rationale": "..." }` entries. The skill's invariant test asserts this section is present in the SKILL.md and the JSON output.

### 3. Produce Ranked Opportunities

Generate a ranked shortlist (3-7 items), each with:
- Problem statement
- User/developer impact
- Estimated effort (S/M/L)
- Risk level (low/med/high)
- Strategic fit (`low`/`med`/`high`)
- Weighted score using a reproducible formula:
  - `score = impact*0.4 + strategic_fit*0.25 + (4-effort)*0.2 + (4-risk)*0.15 + focus_match*0.1`
  - Use numeric mapping: `low=1`, `med=2`, `high=3`; `S=1`, `M=2`, `L=3`
  - `focus_match` (0-3): how directly the opportunity addresses `LOCALIZED_FOCUS` (set either by Step 0.5's interview answers or by the direct `$ARGUMENTS` string when the interview was skipped). `3` = directly addresses the named pain (e.g., focus is "runtime latency in agent dispatch" and opportunity reduces dispatch latency); `2` = addresses the broader bucket but not the specific pain; `1` = tangentially related; `0` = unrelated. Only set `focus_match=0` for all items when `LOCALIZED_FOCUS` is empty/unset — a non-empty focus from $ARGUMENTS is just as valid a scoring anchor as one from the interview.
- `localized_focus_alignment`: one-line note on why the opportunity received its `focus_match` score (e.g., "Reduces dispatch loop p95 by replacing polling with pg_notify -- direct hit on stated pain")
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
- If Step 0.5 ran, include a top-level `localized_focus` field in `opportunities.json` capturing the interview output (raw input, bucket detected, questions asked, answers, derived focus string). This makes the ranking reproducible and gives `/prioritize-proposals` the same context the user provided

## Output

- Prioritized feature opportunity list with rationale
- One recommended next feature and concrete follow-up command
- Machine-readable discovery output path(s) and whether recommendation history altered ranking

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I already know what we should build — skip the lenses" | Pre-loaded answers come from the most recently active mental model, not the highest-value option. The lenses are how you discover alternatives you wouldn't have generated otherwise. |
| "The HMW reframe is just rewording — it doesn't change the answer" | "Make X faster" anchors you to optimization. "How might we eliminate X?" surfaces removal candidates that are usually 10× cheaper. The reframe is the work. |
| "Listing NOT DOING items is filler — the report is about what we WILL do" | The rejected branches ARE the audit trail. Without them, future agents cannot tell whether the recommendation was a considered choice or a default. |
| "Only 1 lens hit — that's enough, ship the candidate" | One-lens hits are local maxima. A genuinely strong candidate surfaces from 2+ lenses (e.g., simplification AND 10×). One-lens hits should be marked low-confidence, not headlined. |
| "Focus interview is for vague input — my $ARGUMENTS is specific" | "Performance" looks specific but is a bucket. Run the interview anyway when the bucket name matches one of the broad buckets in Step 0.5; the cost is 30 seconds, the upside is a focus_match score that actually means something. |

## Red Flags

- The opportunities.json output has `lenses_applied: []` for all candidates (the lenses were skipped or fabricated).
- `NOT DOING:` section is missing or contains only "<none>" (no alternatives were considered, or the author is performing the form without the substance).
- Every candidate is in the `quick-win` bucket — strongly suggests inversion / 10× / big-bet lenses were not applied.
- HMW reframes are absent, or every reframe is "How might we make X faster?" (mechanical, not generative).
- The ranked list's top candidate is the first one the agent thought of (no evidence of comparison to alternatives).
- `localized_focus` is empty even when `$ARGUMENTS` was non-empty (the interview was run unnecessarily, or the focus from $ARGUMENTS was discarded).

## Verification

1. Each candidate in `opportunities.json` has at least one `hmw_reframe` entry AND at least one entry in `lenses_applied` from the 8 named lenses.
2. The output report contains a top-level `NOT DOING:` section with ≥2 rejected alternatives, each with a one-line rationale (cite the file path and section).
3. At least 3 of the 8 ideation lenses appear at least once across the candidate set (`opportunities.json | jq '[.[] | .lenses_applied[]] | unique | length'` returns ≥3).
4. The recommended next action cites the candidate's `focus_match` score and `localized_focus_alignment` note — not just the raw ranking.
5. If `$ARGUMENTS` matched a broad bucket, the focus interview ran and `localized_focus` is populated with the interview output (not the raw bucket name).

