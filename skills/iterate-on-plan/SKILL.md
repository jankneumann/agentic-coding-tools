---
name: iterate-on-plan
description: Iteratively refine an OpenSpec proposal by identifying and fixing completeness, clarity, feasibility, scope, consistency, testability, parallelizability, and assumptions issues
category: Git Workflow
tags: [openspec, refinement, iteration, planning, quality]
triggers:
  - "iterate on plan"
  - "refine plan"
  - "improve plan"
  - "iterate on proposal"
  - "refine proposal"
  - "linear iterate on plan"
---

# Iterate on Plan

Iteratively refine an OpenSpec proposal after `/plan-feature` creates it. Each iteration reviews the proposal documents, identifies plan quality issues, implements fixes, and commits — repeating until only low-criticality findings remain or max iterations are reached.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required), optionally followed by `--max <N>` (default: 3), `--threshold <level>` (default: "medium"; values: "critical", "high", "medium", "low"), and `--vendor-review` (dispatch multi-vendor review after iterate loop converges; automatic in coordinated tier)

## Prerequisites

- OpenSpec proposal exists at `openspec/changes/<change-id>/` with at least proposal.md, tasks.md, and one spec delta
- Run `/plan-feature` first if no proposal exists
- Proposal has NOT yet been approved (this skill refines before approval)

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

### 0. Detect Coordinator, Read Handoff, Recall Memory

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_HANDOFF=true`, read recent handoff context:

- MCP path: `read_handoff`
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_handoff_read(...)`

If `CAN_MEMORY=true`, recall relevant plan-iteration memories:

- MCP path: `recall`
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_recall(...)`

On recall/handoff failure, continue with standalone iteration and log informationally.

### 1. Determine Change ID and Configuration

```bash
# Parse change-id from argument
CHANGE_ID=${ARGUMENTS%% *}

# Defaults
MAX_ITERATIONS=3
THRESHOLD="medium"  # critical > high > medium > low
```

Parse optional flags from `$ARGUMENTS`:
- `--max <N>` overrides MAX_ITERATIONS
- `--threshold <level>` overrides THRESHOLD
- `--vendor-review` sets VENDOR_REVIEW=true

```bash
# Vendor review: explicit flag OR auto-enable in coordinated tier
VENDOR_REVIEW=false
if [[ "$ARGUMENTS" == *"--vendor-review"* ]] || [[ "$COORDINATOR_AVAILABLE" == "true" ]]; then
  VENDOR_REVIEW=true
fi
```

### 2. Verify Proposal Exists

```bash
# Verify proposal exists
openspec show $CHANGE_ID

# Verify core files exist
ls openspec/changes/$CHANGE_ID/proposal.md
ls openspec/changes/$CHANGE_ID/tasks.md
ls openspec/changes/$CHANGE_ID/specs/
```

If any core files are missing, abort and recommend running `/plan-feature` first.

### 3. Run Baseline Validation

```bash
# Strict validation as starting point
openspec validate $CHANGE_ID --strict
```

Record any validation failures. These become automatic critical-level findings in the first iteration.

### 3.5. Prepare Findings Artifact

Preferred path:
- Use the runtime-native continue/findings workflow (`opsx:continue` equivalent) to create or extend `plan-findings`.

CLI fallback path:

```bash
openspec instructions plan-findings --change "$CHANGE_ID"
openspec status --change "$CHANGE_ID"
```

Ensure `openspec/changes/<change-id>/plan-findings.md` exists and append each iteration's findings there.

### 4. Begin Iteration Loop

```
ITERATION=1
```

---

### 5. Review and Analyze (Parallel Analysis Option)

Read all proposal documents to understand intent and current quality. For complex proposals, use parallel Task(Explore) agents to analyze different quality dimensions:

**Sequential approach (default for simple proposals):**
- Read `openspec/changes/<change-id>/proposal.md`
- Read `openspec/changes/<change-id>/tasks.md`
- Read `openspec/changes/<change-id>/design.md` (if exists)
- Read all spec deltas in `openspec/changes/<change-id>/specs/*/spec.md`
- Read existing specs in `openspec/specs/` for capabilities referenced in the proposal's Impact section

**Parallel approach (for complex proposals with 5+ tasks or 3+ spec deltas):**

Resolve the analyst archetype before dispatching:

```python
from src.agents_config import load_archetypes_config, resolve_model
archetypes = load_archetypes_config()
analyst = archetypes.get("analyst")
analyst_model = resolve_model(analyst, {}) if analyst else "sonnet"
```

```
# Launch parallel analysis agents (single message, multiple Task calls)
Task(subagent_type="Explore", model=analyst_model, prompt="Analyze openspec/changes/$CHANGE_ID/ for COMPLETENESS issues: missing requirements, unaddressed edge cases, gaps in impact analysis, requirements without scenarios", run_in_background=true)
Task(subagent_type="Explore", model=analyst_model, prompt="Analyze openspec/changes/$CHANGE_ID/ for CLARITY and CONSISTENCY issues: ambiguous wording, vague scenarios, contradictions between documents", run_in_background=true)
Task(subagent_type="Explore", model=analyst_model, prompt="Analyze openspec/changes/$CHANGE_ID/tasks.md for FEASIBILITY and PARALLELIZABILITY: task size, dependencies, file overlap that would cause merge conflicts", run_in_background=true)
Task(subagent_type="Explore", model=analyst_model, prompt="Analyze openspec/changes/$CHANGE_ID/ for TESTABILITY: scenarios that can't be verified, subjective language like 'properly' or 'correctly'", run_in_background=true)
Task(subagent_type="Explore", model=analyst_model, prompt="Analyze openspec/changes/$CHANGE_ID/ for SECURITY and PERFORMANCE issues: missing auth/authorization for endpoints, secrets in config, unvalidated inputs, unbounded queries, missing pagination, sync where async needed", run_in_background=true)
```

**Analysis Synthesis:**
1. Wait for all TaskOutput results (if parallel)
2. Merge findings, deduplicate, and assign criticality levels
3. Produce the structured plan analysis below

Produce a **structured plan analysis** with findings in this format:

| # | Type | Criticality | Description | Proposed Fix |
|---|------|-------------|-------------|--------------|
| 1 | completeness/clarity/feasibility/scope/consistency/testability/parallelizability/assumptions/security/performance | critical/high/medium/low | What the issue is | How to fix it |

**Type categories:**
- **completeness**: Missing requirements, unaddressed edge cases, gaps in impact analysis, missing spec deltas for affected capabilities, requirements without scenarios
- **clarity**: Ambiguous requirement wording, vague WHEN/THEN scenarios, unclear task descriptions, missing context in proposal.md Why section, requirements not using SHALL/MUST
- **feasibility**: Tasks too large to implement atomically, unrealistic scope, missing technical constraints, undocumented dependencies between tasks
- **scope**: Scope creep beyond stated goals, mixing unrelated concerns, non-goals that should be explicit, tasks that don't trace back to any requirement
- **consistency**: Contradictions between proposal.md and design.md, requirement wording mismatches across documents, affected specs listed in Impact but no corresponding delta (or vice versa), duplicate requirements
- **testability**: Scenarios that can't be verified, requirements without measurable acceptance criteria, WHEN/THEN using subjective language ("properly", "correctly", "as expected")
- **parallelizability**: How well the task decomposition supports parallel multi-agent execution via `/parallel-implement`. Evaluates whether tasks have explicit dependency declarations, whether task scopes are isolated to separate modules/files (no shared-file overlap that would cause merge conflicts), whether tasks are granular enough for independent agent assignment, and whether sequencing maximizes concurrent execution width
- **assumptions**: Implicit decisions that could reasonably go either way — assumed authentication mechanism, data format, deployment target, backward-compatibility requirement, performance threshold, technology choice, or scope boundary. When an assumption is identified that has multiple valid interpretations, it MUST be surfaced to the user via **AskUserQuestion** rather than documented and moved on from. Present the assumption, the alternatives, and ask the user to decide.
- **security**: Missing authentication/authorization for new endpoints, secrets in configuration or code, unvalidated inputs at system boundaries, OWASP top-10 considerations not addressed, missing threat model for new attack surface, no encryption for sensitive data in transit or at rest
- **performance**: Unbounded queries or loops in design, missing pagination for list operations, synchronous processing where async is needed, missing caching strategy for hot paths, no rate limiting for public endpoints, O(n^2) or worse algorithms in design without justification

**Criticality levels:**
- **critical**: `openspec validate --strict` failures, missing spec deltas for capabilities listed in Impact, requirements without any scenarios, proposal.md missing required sections (Why, What Changes, Impact), authentication bypass or missing auth on endpoints handling sensitive data
- **high**: Ambiguous requirements that could be implemented multiple valid ways, tasks not traceable to requirements, scenarios using subjective/unmeasurable criteria, contradictions between documents, tasks with implicit shared-state or shared-file dependencies that would cause merge conflicts if parallelized, unstated assumptions about scope or technology choice that could invalidate the plan if wrong, secrets in configuration without secret management, unbounded queries on large datasets
- **medium**: Missing edge-case scenarios (only success path covered), tasks too coarse for single-commit implementation, design.md needed but absent, incomplete impact analysis, tasks missing explicit dependency annotations, tasks that could be split into independent units for better parallelism, missing pagination for list endpoints, missing monitoring requirements for new services
- **low**: Wording polish, minor formatting, task ordering optimization for parallel execution, optional design.md sections, missing caching considerations

**Plan smells to check for:**
- Giant task (spans multiple systems or modules)
- Orphan requirement (requirement in spec delta with no corresponding task)
- Orphan task (task with no corresponding requirement)
- Vague scenario (WHEN/THEN using words like "appropriate", "correctly", "properly", "as expected")
- Missing failure path (only success scenarios, no error/edge-case scenarios)
- Scope leak (tasks or requirements that extend beyond the stated What Changes)
- Impact mismatch (affected specs listed in proposal.md but no spec delta created, or vice versa)
- Design gap (multiple complex decisions without a design.md)
- Implicit dependency (tasks that modify the same files or shared state without explicit ordering — would cause merge conflicts in parallel execution)
- Monolithic task (single task that could be decomposed into independent subtasks for parallel agents)
- Missing dependency graph (tasks lack explicit dependency annotations needed by `/parallel-implement` and Beads `--blocked-by`)
- Coupled scope (tasks that modify overlapping files or modules, preventing isolated worktree execution)
- Unstated assumption (plan proceeds on an assumption about scope, technology choice, or constraint that was never confirmed with the user — could validly go multiple ways)
- Unprotected endpoint (new API endpoint without authentication/authorization requirement stated)
- Secret in config (credentials or API keys referenced in configuration without secret management)
- Missing input validation (system boundary input accepted without validation requirement in spec)
- Missing pagination (list operation returning unbounded results without pagination or size limits)
- Missing observability (new service or endpoint without monitoring, logging, or alerting requirements)

**Schema type mapping** (for translating plan findings to `review-findings.schema.json` types at the dispatch/consensus boundary):

| Plan Dimension | Schema Type(s) | Notes |
|---|---|---|
| completeness | `spec_gap` | Missing requirements = spec gap. Use `observability`/`resilience`/`compatibility` when the missing content is specifically about those concerns. |
| clarity | `spec_gap`, `style` | Ambiguous wording = spec_gap; formatting = style |
| feasibility | `architecture`, `performance` | Infeasible designs are usually architectural or performance-bound |
| scope | `spec_gap`, `correctness` | Scope creep = spec_gap; scope leak = correctness |
| consistency | `contract_mismatch`, `correctness` | Cross-document contradictions |
| testability | `spec_gap` | Untestable requirement = incomplete spec |
| parallelizability | `architecture` | Task decomposition is architectural |
| assumptions | `architecture`, `security`, `compatibility` | Map to the schema type matching the assumption's subject |
| security | `security` | Direct mapping |
| performance | `performance` | Direct mapping |

### 6. Check Termination Conditions

**Stop iterating if:**
- All findings are below the criticality threshold → present summary and list remaining low-criticality findings for optional manual review
- ITERATION > MAX_ITERATIONS → present summary and list any unaddressed findings

**If stopping**, skip to the **After Loop** section below.

**Otherwise**, continue to step 7.

### 7. Implement Improvements

Fix all findings at or above the criticality threshold by modifying the proposal documents:

- **proposal.md**: Add missing Why context, expand What Changes, correct Impact section
- **tasks.md**: Split giant tasks, add missing tasks for orphan requirements, add explicit ordering and dependency notes, improve verifiability, restructure for parallel execution where possible
- **design.md**: Create if needed (per criteria below), add missing decision rationale, document alternatives considered, add risks/trade-offs
- **Spec deltas**: Add missing requirements, add WHEN/THEN scenarios for uncovered paths, fix requirement wording to use SHALL/MUST, add failure/edge-case scenarios, split monolithic spec files
- **Assumptions**: For each assumption-type finding, use **AskUserQuestion** to surface it interactively. Present the implicit assumption, explain why it matters (what would change if the assumption is wrong), and offer the alternatives as selectable options. Wait for the user's response. Then update the relevant document (proposal.md, design.md, or spec delta) to convert the assumption into an explicit, documented decision with rationale.

**When to create design.md** (if one does not exist):
- Change affects multiple capabilities or introduces a new pattern
- New external dependency or significant data model changes
- Security, performance, or migration concerns
- Multiple technical decisions that need documented rationale

For findings that are outside the scope of the current proposal:
- Flag as "out of scope"
- Recommend creating a new OpenSpec proposal
- Do NOT expand the current proposal to address them

### 8. Run Quality Checks

```bash
# Validate proposal structure
openspec validate $CHANGE_ID --strict
```

Additionally verify:
- **Scenario coverage**: Every requirement has at least one success and one failure/edge scenario
- **Requirement completeness**: All requirements use SHALL/MUST, all have clear subjects
- **Task granularity**: Each task could reasonably be completed in a single commit
- **Task traceability**: Every task maps to at least one requirement, every requirement maps to at least one task
- **Cross-document consistency**: Impact section matches actual spec deltas, proposal.md describes all spec delta changes
- **Design rationale**: If design.md exists, each decision has at least one alternative considered
- **Parallelizability**: Every task either (a) is independent (no shared files/state with other tasks) or (b) has explicit dependency annotation. Produce a dependency graph summary:
  - `Independent: N tasks | Sequential chains: M | Max parallel width: W`
  - Identify tasks that modify the same files — these need explicit sequencing or scope restructuring to avoid merge conflicts during `/parallel-implement`
  - If all tasks are purely sequential with no parallelism possible, flag as medium finding

Fix any failures before proceeding. If fixes introduce new issues, address them within this iteration.

### 8.5. Append Session Log

Append a `Plan Iteration <N>` phase entry to the session log, capturing what changed in this iteration and why.

**Determine iteration number:**
- Read `openspec/changes/<change-id>/session-log.md` (if it exists)
- Count existing `## Phase: Plan Iteration` headers
- N = count + 1

**Phase entry template:**

```markdown
---

## Phase: Plan Iteration <N> (<YYYY-MM-DD>)

**Agent**: <agent-type> | **Session**: <session-id-or-N/A>

### Decisions
1. **<Decision title>** — <rationale>

### Alternatives Considered
- <Alternative>: rejected because <reason>

### Trade-offs
- Accepted <X> over <Y> because <reason>

### Open Questions
- [ ] <unresolved question>

### Context
<2-3 sentences: what findings were addressed, what changed>
```

**Focus on**: Which findings were addressed, which were deferred, key decisions about proposal changes.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip session log and proceed.

The session-log.md is inside `openspec/changes/$CHANGE_ID/` so it will be picked up by the existing `git add` in Step 9.

### 9. Commit Iteration

```bash
# Review all changes
git status
git diff

# Stage proposal document changes only
git add openspec/changes/$CHANGE_ID/

# Commit with structured message
git commit -m "$(cat <<'EOF'
refine(plan): iteration <N> - <summary of key changes>

Iterate-on-plan: <change-id>, iteration <N>/<max>

Findings addressed:
- [<criticality>] <type>: <description>
- [<criticality>] <type>: <description>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Increment and loop
ITERATION=$((ITERATION + 1))
```

**Loop back to Step 5.**

---

## After Loop

### 10. Multi-Vendor Review (Conditional)

**Skip this step** if `VENDOR_REVIEW=false`.

After the iterate loop converges (all findings below threshold) or max iterations are reached, dispatch a multi-vendor review for a final independent validation pass.

#### 10a. Dispatch `/parallel-review-plan`

Write a review prompt and dispatch to other vendor CLIs:

```bash
# Create review prompt for vendor dispatch
mkdir -p openspec/changes/$CHANGE_ID/reviews

cat > openspec/changes/$CHANGE_ID/reviews/review-prompt.md <<'PROMPT'
Review the OpenSpec plan artifacts in openspec/changes/$CHANGE_ID/.
Read proposal.md, tasks.md, design.md (if present), and all spec deltas.
Output ONLY valid JSON conforming to review-findings.schema.json.
Focus on: specification completeness, contract consistency, architecture alignment, security, and work package validity.
PROMPT

# Dispatch to other vendors (excludes current agent's vendor)
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py" \
  --review-type plan \
  --mode review \
  --prompt-file "openspec/changes/$CHANGE_ID/reviews/review-prompt.md" \
  --cwd "$(pwd)" \
  --output-dir "openspec/changes/$CHANGE_ID/reviews" \
  --exclude-vendor claude_code \
  --timeout 600
```

Also produce your own findings as the primary reviewer (Steps 1-5 of `/parallel-review-plan`): read plan artifacts, evaluate against the review checklist, and write findings to `openspec/changes/$CHANGE_ID/review-findings-plan.json`.

#### 10b. Synthesize Consensus

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/consensus_synthesizer.py" \
  --review-type plan \
  --target "$CHANGE_ID" \
  --findings "openspec/changes/$CHANGE_ID/review-findings-plan.json" \
             "openspec/changes/$CHANGE_ID/reviews/findings-"*"-plan.json" \
  --output "openspec/changes/$CHANGE_ID/reviews/consensus-plan.json"
```

Present consensus summary:
- **Confirmed findings** (2+ vendors agree) — high confidence
- **Unconfirmed findings** (single vendor) — lower confidence, warnings
- **Disagreements** (vendors disagree on disposition) — escalate to human

If no other vendors are available (CLIs not installed), skip dispatch and proceed with single-vendor findings only.

#### 10c. Feed Back Findings Above Remediation Threshold

The remediation threshold is the user's `--threshold` setting if provided, otherwise medium.

If the consensus or vendor review surfaces new findings **at or above the remediation threshold**:

1. Append the new findings to `openspec/changes/$CHANGE_ID/plan-findings.md`
2. Run **one additional iterate cycle** (Steps 5-9) to address them
3. Commit with message: `refine(plan): vendor-review remediation - <summary>`
4. Do NOT re-dispatch vendor review (prevents infinite recursion)

If all vendor review findings are below the remediation threshold, proceed to the summary.

---

### 11. Present Summary

Present a summary of all iterations:

```

If `CAN_MEMORY=true`, remember iteration outcomes (for example findings counts, key fixes, and residual risks):

- MCP path: `remember`
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_remember(...)`

If `CAN_HANDOFF=true`, write a completion handoff containing:

- Iterations performed and findings addressed
- Remaining below-threshold findings (if any)
- Validation status and proposal readiness
- Recommended next command
## Plan Iteration Summary

### Iteration 1
- Findings: <count> (<count by criticality>)
- Fixed: <list>

### Iteration 2
- Findings: <count> (<count by criticality>)
- Fixed: <list>

...

### Final State
- Total iterations: <N>
- Total findings addressed: <count>
- Remaining findings (below threshold): <list or "none">
- Termination reason: <threshold met | max iterations reached>
- Validation status: <openspec validate --strict result>

### Vendor Review (if dispatched)
- Vendors dispatched: <list or "skipped">
- Consensus findings: <confirmed count> confirmed, <unconfirmed count> unconfirmed, <disagreement count> disagreements
- Remediation cycle: <ran / not needed>
- New findings addressed in remediation: <count or "N/A">

### Parallelizability Assessment
- Independent tasks: <N>
- Sequential chains: <M>
- Max parallel width: <W>
- File overlap conflicts: <list or "none">

### Proposal Readiness
- [ ] openspec validate --strict passes
- [ ] All requirements have success + failure scenarios
- [ ] All tasks are traceable to requirements
- [ ] All tasks are single-commit sized
- [ ] Impact section matches spec deltas
- [ ] design.md present if complexity warrants it
- [ ] Task dependencies are explicit (ready for /parallel-implement)
- [ ] No file-overlap conflicts between independent tasks
```

## Output

- Iteration commits modifying `openspec/changes/<change-id>/` documents
- Structured findings summary for each iteration
- Parallelizability assessment with dependency graph summary
- Final proposal readiness checklist
- Validated, refined OpenSpec proposal ready for human approval
- Vendor review consensus (if `--vendor-review` or coordinated tier): `openspec/changes/<change-id>/reviews/consensus-plan.json`

## Next Step

Present the refined proposal for approval. After approval:
```
/implement-feature <change-id>
```
