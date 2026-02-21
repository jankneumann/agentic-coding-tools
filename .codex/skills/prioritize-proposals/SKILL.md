---
name: prioritize-proposals
description: Analyze active OpenSpec proposals and produce a prioritized "what to do next" report
category: Git Workflow
tags: [openspec, prioritization, triage, planning]
triggers:
  - "prioritize proposals"
  - "what to do next"
  - "rank proposals"
  - "triage proposals"
---

# Prioritize Proposals

Analyze all active OpenSpec change proposals against recent code history and produce a prioritized "what to do next" ordered list optimized for minimal file conflicts and parallel agent work.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--change-id <id>[,<id>]` — limit analysis to specific change IDs (comma-separated)
- `--since <git-ref>` — analyze commits since this ref (default: `HEAD~50`)
- `--format <md|json>` — output format (default: `md`)

## Prerequisites

- At least one active OpenSpec proposal exists under `openspec/changes/`
- Git repository with commit history

## Steps

### 1. Parse Arguments

```bash
# Defaults
SINCE_REF="HEAD~50"
FORMAT="md"
CHANGE_IDS=""  # empty = all active proposals

# Parse flags from $ARGUMENTS
# --change-id add-foo,update-bar → CHANGE_IDS="add-foo,update-bar"
# --since HEAD~20 → SINCE_REF="HEAD~20"
# --format json → FORMAT="json"
```

### 2. Inventory Active Proposals

List all active OpenSpec change proposals and gather metadata:

```bash
# List active changes
openspec list

# For each active change, gather:
# - proposal.md contents (the Why and What)
# - tasks.md contents (implementation status)
# - spec deltas (which specs are affected)
# - design.md (if present)
```

For each proposal, extract and record:
- **Change ID**: Directory name under `openspec/changes/`
- **Title**: First heading from `proposal.md`
- **Why**: The motivation section
- **What Changes**: The list of planned changes
- **Affected Specs**: From `## Impact` section
- **Affected Code**: Files/modules mentioned in proposal and design docs
- **Task Status**: Count of completed vs total tasks from `tasks.md`
- **Has Design Doc**: Whether `design.md` exists

If `--change-id` was provided, limit inventory to those specific IDs only. Verify each requested ID exists; warn if any are not found.

### 3. Analyze Recent Commits

Gather recent commit history and file changes:

```bash
# Get recent commits with files changed
git log --oneline --name-only $SINCE_REF..HEAD

# Get summary of files changed
git diff --stat $SINCE_REF..HEAD

# Get the list of unique files changed
git diff --name-only $SINCE_REF..HEAD | sort -u
```

Build a map of **recently changed files** and their commit frequency.

### 4. Assess Each Proposal

For each active proposal, evaluate three dimensions:

#### 4a. Relevance Assessment

Compare the proposal's target files/specs against recent commits:

- **Likely Addressed**: Recent commits touch the same files AND the same requirements described in the proposal. Recommend archiving or verification.
- **Needs Verification**: Recent commits touch some overlapping files but the proposal's core requirements may not be fully addressed. Recommend review.
- **Still Relevant**: No significant overlap with recent changes. The proposal's goals remain unaddressed.
- **Needs Refinement**: The proposal's target files or assumptions have changed since it was authored (code drift). Flag which documents need updating (proposal.md, tasks.md, or spec deltas).

#### 4b. Dependency and Readiness Assessment

Evaluate implementation readiness:

- **Ready**: Proposal is approved, tasks are defined, no blockers
- **Partially Ready**: Some tasks are complete, others remain
- **Blocked**: Depends on another proposal being implemented first
- **Needs Planning**: Proposal exists but lacks tasks or design detail

#### 4c. File Conflict Assessment

For each pair of proposals, compare their target files:

- **Conflicting**: Two proposals modify overlapping files or specs — order matters
- **Independent**: Proposals touch distinct files — safe to parallelize

Build a conflict matrix showing which proposals overlap.

### 5. Score and Rank Proposals

Assign a composite priority score based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| Relevance | High | Still Relevant > Needs Verification > Needs Refinement > Likely Addressed |
| Readiness | High | Ready > Partially Ready > Needs Planning > Blocked |
| Task completion | Medium | Higher % complete = higher priority (momentum) |
| Conflict isolation | Medium | Fewer conflicts with other proposals = higher priority |
| Scope size | Low | Smaller scope = quicker wins = slightly higher priority |

Sort proposals by composite score (descending).

### 6. Identify Parallelizable Workstreams

After ranking, group proposals by conflict status:

- **Parallel Group A**: Top-priority proposals that are independent (no file overlap)
- **Parallel Group B**: Next set of independent proposals
- **Sequential**: Proposals that conflict with higher-priority ones — must wait

Present these groupings in the report.

### 7. Generate Report

Produce the prioritization report.

#### Markdown Format (`--format md`)

```markdown
# Proposal Prioritization Report

**Date**: YYYY-MM-DD HH:MM:SS
**Analyzed Range**: <SINCE_REF>..HEAD (<N> commits)
**Proposals Analyzed**: <count>

## Priority Order

### 1. <change-id> — <title>
- **Relevance**: Still Relevant
- **Readiness**: Ready (0/5 tasks complete)
- **Conflicts**: None
- **Recommendation**: Implement next
- **Next Step**: `/implement-feature <change-id>`

### 2. <change-id> — <title>
- **Relevance**: Needs Refinement (target files changed since proposal)
- **Readiness**: Ready (0/3 tasks complete)
- **Conflicts**: Overlaps with #1 on `src/auth.py`
- **Recommendation**: Implement after #1, update proposal.md first
- **Next Step**: `/iterate-on-plan <change-id>`

### 3. <change-id> — <title>
- **Relevance**: Likely Addressed (recent commits cover core requirements)
- **Readiness**: N/A
- **Conflicts**: N/A
- **Recommendation**: Verify and archive
- **Next Step**: `openspec archive <change-id>`

## Parallel Workstreams

### Stream A (start immediately)
- <change-id-1>: <title>
- <change-id-4>: <title>

### Stream B (after Stream A completes)
- <change-id-2>: <title>

### Sequential (conflicts with higher-priority proposals)
- <change-id-3>: Wait for <change-id-1>

## Conflict Matrix

| | proposal-a | proposal-b | proposal-c |
|---|---|---|---|
| proposal-a | — | `src/auth.py` | none |
| proposal-b | `src/auth.py` | — | none |
| proposal-c | none | none | — |

## Proposals Needing Attention

### Likely Addressed
- <change-id>: Recent commits appear to cover this. Verify and consider archiving.

### Needs Refinement
- <change-id>: Code drift detected. Update: proposal.md, tasks.md
```

#### JSON Format (`--format json`)

Output a JSON object with the same structure:
```json
{
  "date": "YYYY-MM-DDTHH:MM:SS",
  "analyzed_range": { "from": "<ref>", "to": "HEAD", "commit_count": N },
  "proposals": [
    {
      "rank": 1,
      "change_id": "<id>",
      "title": "<title>",
      "relevance": "still_relevant",
      "readiness": "ready",
      "task_progress": { "completed": 0, "total": 5 },
      "conflicts": [],
      "recommendation": "implement_next",
      "next_step": "/implement-feature <id>"
    }
  ],
  "parallel_streams": {
    "A": ["<id-1>", "<id-4>"],
    "B": ["<id-2>"],
    "sequential": [{ "id": "<id-3>", "blocked_by": "<id-1>" }]
  },
  "conflict_matrix": { "<id-a>": { "<id-b>": ["src/auth.py"] } },
  "needs_attention": {
    "likely_addressed": ["<id>"],
    "needs_refinement": ["<id>"]
  }
}
```

### 8. Persist Report

Write the report to the standard location:

```bash
REPORT_FILE="openspec/changes/prioritized-proposals.md"
```

Write the markdown report to this file (even if `--format json` was used, always persist the markdown version). Include the timestamp and analyzed git range in the header.

If `--format json` was requested, also write `openspec/changes/prioritized-proposals.json`.

### 9. Present Results

Display the report to the user with actionable next steps:

```
Prioritization complete. <N> proposals analyzed.

Top recommendation: /implement-feature <top-change-id>

Full report: openspec/changes/prioritized-proposals.md
```

## Output

- Prioritized list of proposals printed to console
- Report persisted to `openspec/changes/prioritized-proposals.md`
- JSON report at `openspec/changes/prioritized-proposals.json` (if `--format json`)
- Actionable next steps for the top-ranked proposal

## Next Step

After reviewing the prioritization:
```
/implement-feature <top-change-id>
```

Or to refine a proposal that needs updates:
```
/iterate-on-plan <change-id>
```
