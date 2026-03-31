---
name: iterate-on-implementation
description: Iteratively refine a feature implementation by identifying and fixing bugs, edge cases, and improvements
category: Git Workflow
tags: [openspec, refinement, iteration, quality]
triggers:
  - "iterate on implementation"
  - "refine implementation"
  - "improve implementation"
  - "improve and iterate"
  - "linear iterate on implementation"
---

# Iterate on Implementation

Iteratively refine a feature implementation after `/implement-feature` completes. Each iteration reviews the code, identifies improvements, implements fixes, and commits — repeating until only low-criticality findings remain or max iterations are reached.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required), optionally followed by `--max <N>` (default: 5), `--threshold <level>` (default: "medium"; values: "critical", "high", "medium", "low"), and `--vendor-review` (dispatch multi-vendor review after iterate loop converges; automatic in coordinated tier)

## Prerequisites

- Feature branch `openspec/<change-id>` exists with implementation commits
- Approved OpenSpec proposal exists at `openspec/changes/<change-id>/`
- Run `/implement-feature` first if no implementation exists

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

If `CAN_MEMORY=true`, recall relevant implementation-iteration memories:

- MCP path: `recall`
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_recall(...)`

On recall/handoff failure, continue with standalone iteration and log informationally.

### 1. Determine Change ID and Configuration

```bash
# Parse change-id from argument or current branch
BRANCH=$(git branch --show-current)
CHANGE_ID=${ARGUMENTS%% *}  # First arg, or detect from branch
CHANGE_ID=${CHANGE_ID:-$(echo $BRANCH | sed 's/^openspec\///')}

# Defaults
MAX_ITERATIONS=5
THRESHOLD="medium"  # critical > high > medium > low

# Detect worktree context and resolve OpenSpec path
# Note: detect auto-discovers context from the working directory;
# agent-id information is available via the worktree registry if needed.
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" detect)"
if [[ "$IN_WORKTREE" == "true" ]]; then
  echo "Running in worktree. OpenSpec path: $OPENSPEC_PATH"
fi
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

### 2. Verify Implementation Exists

```bash
# Verify on feature branch
git branch --show-current  # Should be openspec/<change-id>

# Verify proposal exists
openspec show $CHANGE_ID

# Verify implementation commits exist
git log --oneline main..HEAD
```

If not on the feature branch, check out `openspec/<change-id>`. If no implementation commits exist, abort and recommend running `/implement-feature` first.

### 2.5. Prepare Findings Artifact

Preferred path:
- Use the runtime-native continue/findings workflow (`opsx:continue` equivalent) to create or extend `impl-findings`.

CLI fallback path:

```bash
openspec instructions impl-findings --change "$CHANGE_ID"
openspec status --change "$CHANGE_ID"
```

Ensure `openspec/changes/<change-id>/impl-findings.md` exists and append each iteration's findings there.

### 3. Begin Iteration Loop

```
ITERATION=1
```

---

### 4. Review and Analyze

Read the following files to understand intent and current state:

- `$OPENSPEC_PATH/changes/<change-id>/proposal.md`
- `$OPENSPEC_PATH/changes/<change-id>/design.md`
- `$OPENSPEC_PATH/changes/<change-id>/tasks.md`
- All implementation source files changed on this branch (`git diff --name-only main..HEAD`)

Note: In worktree mode, OpenSpec files are in the main repository, not the worktree.

Produce a **structured improvement analysis** with findings in this format:

| # | Type | Criticality | Description | Proposed Fix |
|---|------|-------------|-------------|--------------|
| 1 | bug/edge-case/workflow/performance/UX | critical/high/medium/low | What the issue is | How to fix it |

**Type categories:**
- **bug**: Incorrect behavior, crashes, security issues
- **edge-case**: Unhandled inputs, boundary conditions, error paths
- **workflow**: Developer experience, tooling integration, process issues
- **performance**: Unnecessary work, slow paths, resource waste
- **UX**: Confusing output, missing feedback, poor error messages

**Criticality levels:**
- **critical**: Security vulnerabilities, data loss, crashes, incorrect core behavior
- **high**: Unhandled error paths, missing validation at system boundaries, race conditions
- **medium**: Missing edge cases, suboptimal error messages, incomplete logging
- **low**: Code style, minor naming, documentation polish, minor performance

### 5. Check Termination Conditions

**Stop iterating if:**
- All findings are below the criticality threshold → present summary and list remaining low-criticality findings for optional manual review
- ITERATION > MAX_ITERATIONS → present summary and list any unaddressed findings

**If stopping**, skip to the **After Loop** section below.

**Otherwise**, continue to step 6.

### 6. Implement Improvements

- Fix all findings at or above the criticality threshold
- For findings that require design changes beyond the current proposal scope:
  - Flag as "out of scope"
  - Recommend creating a new OpenSpec proposal
  - Do NOT implement out-of-scope changes

#### Parallel Fixes (for independent findings)

When multiple findings target **different files**, fix them concurrently:

```
# Spawn parallel agents for independent fixes
Task(
  subagent_type="general-purpose",
  description="Fix finding 1: <type> in <file>",
  prompt="Fix this issue in OpenSpec <change-id> implementation:

## Finding
Type: <type>
Criticality: <criticality>
Description: <description>
Proposed Fix: <fix>

## File Scope
You MAY modify: <specific file(s)>
You must NOT modify any other files.

## Process
1. Read the file and understand the issue
2. Implement the fix
3. Run relevant tests
4. Report changes made

Do NOT commit - the orchestrator handles commits.",
  run_in_background=true
)
```

**Rules:**
- Only parallelize fixes targeting different files
- Fixes to the same file must be sequential
- Collect all results before running quality checks

### 7. Run Quality Checks (Parallel Execution)

Run all quality checks concurrently using Task() with `run_in_background=true`:

```
# Launch all checks in parallel (single message, multiple Task calls)
Task(subagent_type="Bash", prompt="Run pytest and report pass/fail with summary", run_in_background=true)
Task(subagent_type="Bash", prompt="Run mypy src/ and report any type errors", run_in_background=true)
Task(subagent_type="Bash", prompt="Run ruff check . and report any linting issues", run_in_background=true)
Task(subagent_type="Bash", prompt="Run openspec validate $CHANGE_ID --strict", run_in_background=true)
```

**Result Aggregation:**
1. Wait for all TaskOutput results
2. Collect pass/fail status from each check
3. Report ALL results together (don't fail-fast on first error)
4. Present failures with their check type for targeted fixes

**Example output format:**
```
Quality Check Results:
✓ pytest: 42 tests passed
✗ mypy: 3 type errors in src/auth.py
✓ ruff: No issues
✓ openspec validate: Valid

Failures to address this iteration:
- mypy: src/auth.py:15 - Missing return type annotation
```

Fix any failures before proceeding. If fixes introduce new issues, address them within this iteration.

### 8. Update Documentation

Review whether genuinely new patterns, lessons, or gotchas were discovered in this iteration. If so, update:

- **CLAUDE.md** — project guidelines, workflow patterns, lessons learned
- **AGENTS.md** — AI assistant instructions
- **docs/** — focused documentation files

Follow the existing convention:
- Update CLAUDE.md or AGENTS.md directly if they are under 300 lines each
- If either file exceeds 300 lines, refactor into focused documents in docs/ and reference them

**Do NOT add redundant documentation** for findings that are variations of already-documented patterns.

### 9. Update OpenSpec Documents

Review whether the current OpenSpec documents accurately reflect the refined implementation. When this iteration's findings reveal spec drift, incorrect assumptions, or missing requirements, update:

- **`openspec/changes/<change-id>/proposal.md`** — if the proposal's described behavior no longer matches reality
- **`openspec/changes/<change-id>/design.md`** — if design decisions or trade-offs changed during refinement
- **Spec deltas in `openspec/changes/<change-id>/specs/`** — if requirements or scenarios need correction
- **`openspec/changes/<change-id>/change-context.md`** — if this iteration added new files, tests, or changed requirement mappings, update the Requirement Traceability Matrix rows (Files Changed, Test(s) columns). Update Coverage Summary if new tests were added or requirements were discovered. If a finding reveals a missing spec requirement, add a new row to the matrix and write the corresponding test before fixing.

**Do NOT make unnecessary changes** if the OpenSpec documents are still accurate after this iteration's fixes.

### 9.5. Append Session Log

Append an `Implementation Iteration <N>` phase entry to the session log, capturing review findings addressed and changes made.

**Determine iteration number:**
- Read `openspec/changes/<change-id>/session-log.md` (if it exists)
- Count existing `## Phase: Implementation Iteration` headers
- N = count + 1

**Phase entry template:**

```markdown
---

## Phase: Implementation Iteration <N> (<YYYY-MM-DD>)

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
<2-3 sentences: what review findings were addressed, what changed>
```

**Focus on**: Review findings addressed, changes made, remaining issues, test improvements.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip session log and proceed.

The session-log.md is included in `git add .` in the existing commit step.

### 10. Commit Iteration

```bash
# Review all changes
git status
git diff

# Stage all changes
git add .

# Commit with structured message
git commit -m "$(cat <<'EOF'
refine(<scope>): iteration <N> - <summary of key changes>

Iterate-on-implementation: <change-id>, iteration <N>/<max>

Findings addressed:
- [<criticality>] <type>: <description>
- [<criticality>] <type>: <description>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Increment and loop
ITERATION=$((ITERATION + 1))
```

**Loop back to Step 4.**

---

## After Loop

### 11. Multi-Vendor Review (Conditional)

**Skip this step** if `VENDOR_REVIEW=false`.

After the iterate loop converges (all findings below threshold) or max iterations are reached, dispatch a multi-vendor review for a final independent validation pass.

#### 11a. Dispatch Reviews

For implementations with work packages (`work-packages.yaml` exists), dispatch per-package reviews via `/parallel-review-implementation`. For simpler implementations, dispatch a whole-branch review.

**Per-package dispatch** (if work-packages.yaml exists):

```bash
# Dispatch per-package reviews to other vendors
for PKG_ID in $(python3 -c "
import yaml
pkgs = yaml.safe_load(open('openspec/changes/$CHANGE_ID/work-packages.yaml'))
for p in pkgs.get('packages', []): print(p['id'])
"); do
  python3 "<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py" \
    --review-type implementation \
    --mode review \
    --prompt-file "openspec/changes/$CHANGE_ID/reviews/review-prompt-$PKG_ID.md" \
    --cwd "$(pwd)" \
    --output-dir "openspec/changes/$CHANGE_ID/reviews" \
    --exclude-vendor claude_code \
    --timeout 600
done
```

**Whole-branch dispatch** (no work packages):

```bash
# Create review prompt for the full implementation diff
mkdir -p openspec/changes/$CHANGE_ID/reviews

cat > openspec/changes/$CHANGE_ID/reviews/review-prompt.md <<'PROMPT'
Review the implementation on this branch against the OpenSpec proposal.
Run: git diff main..HEAD to see all changes.
Read openspec/changes/$CHANGE_ID/proposal.md and spec deltas for requirements.
Output ONLY valid JSON conforming to review-findings.schema.json.
Focus on: correctness, security, contract compliance, test coverage, and performance.
PROMPT

python3 "<skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py" \
  --review-type implementation \
  --mode review \
  --prompt-file "openspec/changes/$CHANGE_ID/reviews/review-prompt.md" \
  --cwd "$(pwd)" \
  --output-dir "openspec/changes/$CHANGE_ID/reviews" \
  --exclude-vendor claude_code \
  --timeout 600
```

Also produce your own findings as the primary reviewer: review the implementation diff against spec requirements and write findings to `openspec/changes/$CHANGE_ID/review-findings-impl.json`.

#### 11b. Synthesize Consensus

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/consensus_synthesizer.py" \
  --review-type implementation \
  --target "$CHANGE_ID" \
  --findings "openspec/changes/$CHANGE_ID/review-findings-impl.json" \
             "openspec/changes/$CHANGE_ID/reviews/findings-"*"-implementation.json" \
  --output "openspec/changes/$CHANGE_ID/reviews/consensus-impl.json"
```

Present consensus summary:
- **Confirmed findings** (2+ vendors agree) — high confidence
- **Unconfirmed findings** (single vendor) — lower confidence, warnings
- **Disagreements** (vendors disagree on disposition) — escalate to human

If no other vendors are available (CLIs not installed), skip dispatch and proceed with single-vendor findings only.

#### 11c. Feed Back Findings Above Remediation Threshold

The remediation threshold is the user's `--threshold` setting if provided, otherwise medium.

If the consensus or vendor review surfaces new findings **at or above the remediation threshold**:

1. Append the new findings to `openspec/changes/$CHANGE_ID/impl-findings.md`
2. Run **one additional iterate cycle** (Steps 4-10) to address them
3. Commit with message: `refine(<scope>): vendor-review remediation - <summary>`
4. Do NOT re-dispatch vendor review (prevents infinite recursion)

If all vendor review findings are below the remediation threshold, proceed to the summary.

---

### 12. Present Summary

Present a summary of all iterations:

```

If `CAN_MEMORY=true`, remember implementation iteration outcomes:

- MCP path: `remember`
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_remember(...)`

If `CAN_HANDOFF=true`, write a completion handoff containing:

- Fixes applied and critical findings resolved
- Remaining risks or manual follow-ups
- Validation status and recommended next command
## Iteration Summary

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

### Vendor Review (if dispatched)
- Vendors dispatched: <list or "skipped">
- Consensus findings: <confirmed count> confirmed, <unconfirmed count> unconfirmed, <disagreement count> disagreements
- Remediation cycle: <ran / not needed>
- New findings addressed in remediation: <count or "N/A">
```

## Output

- Iteration commits on branch `openspec/<change-id>`
- Structured findings summary for each iteration
- Updated documentation (CLAUDE.md, AGENTS.md, docs/ as applicable)
- Updated OpenSpec documents (proposal.md, design.md, spec deltas as applicable)
- Final state assessment
- Vendor review consensus (if `--vendor-review` or coordinated tier): `openspec/changes/<change-id>/reviews/consensus-impl.json`

## Next Step

Validate the deployed feature (recommended):
```
/validate-feature <change-id>
```

Or skip validation and proceed to cleanup:
```
/cleanup-feature <change-id>
```
