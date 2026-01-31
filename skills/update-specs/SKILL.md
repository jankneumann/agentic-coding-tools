---
name: update-specs
description: Update OpenSpec specs to reflect implementation reality after debugging, testing, and review
category: Git Workflow
tags: [openspec, specs, feedback, documentation, sync]
triggers:
  - "update specs"
  - "sync specs"
  - "update spec"
  - "specs out of date"
  - "spec drift"
  - "capture changes in specs"
---

# Update Specs

Update OpenSpec spec files to reflect what was actually built. Use this after implementation work where debugging, integration testing, code review, or interactive refinements revealed differences between the original spec and the final implementation.

## When to Use

- After `/implement-feature` when the implementation diverged from the spec
- After debugging sessions that uncovered and fixed bugs in specified behavior
- After integration testing revealed edge cases or corrected assumptions
- After code review feedback led to design changes
- Any time the implemented code no longer matches what `spec.md` or `design.md` describe

## Arguments

`$ARGUMENTS` - Spec capability name (e.g., "agent-coordinator") or path to spec directory. If omitted, detect from recent git history.

## Steps

### 1. Identify the Spec to Update

```bash
# From argument
SPEC_DIR=openspec/specs/$ARGUMENTS

# Or detect from recent commits
git log --oneline -10 --name-only | grep "openspec/specs\|src/"
```

Read the spec directory to understand which files exist:
- `spec.md` - Requirements, scenarios, behavior contracts
- `design.md` - Architecture, patterns, component descriptions
- `tasks.md` - Implementation tasks and status

### 2. Gather Implementation Reality

Compare what's documented vs what's implemented. Read the actual source code and tests:

```bash
# Find recently changed source files
git log --oneline -5 --name-only

# Review the implementation
# Read source files, test files, migrations, configs
```

Focus on discovering **spec drift** — places where the implementation differs from the spec:

- **Behavioral changes**: Functions that return different shapes than documented, error handling that works differently, edge cases the spec didn't anticipate
- **Architectural changes**: New files or components added during implementation, patterns that changed (e.g., a lock acquisition strategy), configuration options that were added
- **Bug fixes that changed contracts**: Race conditions fixed by changing the algorithm, error responses that now return different status codes or payloads
- **New infrastructure**: Bootstrap scripts, migration files, test infrastructure that the spec should acknowledge

### 3. Update spec.md

Open `spec.md` and update it to reflect implementation reality:

**Implementation Status** — Add or update a status table showing what's implemented vs planned:
```markdown
## Implementation Status

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 | Core feature X, Y | **Implemented** |
| Phase 2 | Extended feature Z | Specified |
```

**Requirements and Scenarios** — Fix any scenarios where the actual behavior differs from what was specified:
- Correct response shapes (e.g., `{success: false, reason: "..."}` not `{success: true, task_id: null}`)
- Update status codes and error messages
- Add scenarios discovered during testing that weren't originally specified

**Component Lists** — Update lists of tools, endpoints, tables, etc. to match what was actually built. Organize by implementation phase if some items are planned but not yet built.

**Remove Duplicates** — If sections were added during implementation that overlap with existing content, consolidate them.

### 4. Update design.md

Open `design.md` and update it to reflect implementation reality:

**Patterns and Algorithms** — If debugging or testing revealed that the original pattern didn't work and was replaced, document the actual pattern. Include the reasoning for the change:
```markdown
### Lock Acquisition Pattern
Uses INSERT ON CONFLICT DO NOTHING for race-safe acquisition.
Original SELECT FOR UPDATE approach caused PK violations under concurrent access.
```

**File Structure** — Update the file tree to show what actually exists. Split into "Implemented" and "Planned" sections if applicable.

**Component Descriptions** — Update descriptions of modules, services, and tools to match their actual capabilities. Note which are implemented vs planned.

### 5. Update tasks.md (if present)

If `tasks.md` exists in the spec directory, update task status:
- Mark completed tasks as `[x]`
- Add tasks that emerged during implementation
- Note any tasks that were descoped or deferred

### 6. Review Changes

```bash
# See what changed
git diff openspec/specs/

# Verify specs are internally consistent
# Check cross-references between spec.md and design.md
```

Ask yourself:
- Does spec.md accurately describe the system's current behavior?
- Does design.md reflect the actual architecture and patterns?
- Are phase boundaries clear (what's built vs what's planned)?
- Would a new developer reading these specs understand the system as it exists today?

### 7. Commit Spec Updates

```bash
git add openspec/specs/
git commit -m "$(cat <<'EOF'
docs: Update <capability> specs to reflect implementation

Sync spec.md and design.md with actual implemented behavior:
- <key change 1>
- <key change 2>
- <key change 3>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

## Common Spec Drift Patterns

| Drift Type | Where to Fix | Example |
|------------|-------------|---------|
| Response shape changed | spec.md scenarios | Error returns `{success: false}` not `{error: true}` |
| Algorithm replaced | design.md patterns | INSERT ON CONFLICT instead of SELECT FOR UPDATE |
| New config option added | spec.md requirements, design.md components | `rest_prefix` for direct PostgREST connections |
| New infrastructure file | design.md file structure | Bootstrap migration `000_bootstrap.sql` |
| Phase boundary shifted | spec.md status table, design.md components | Tool moved from Phase 2 to Phase 1 |
| Edge case discovered | spec.md scenarios | TTL=0 doesn't expire within same transaction |

## Output

- `spec.md` reflects actual implemented behavior and contracts
- `design.md` reflects actual architecture and patterns
- `tasks.md` reflects actual completion status (if present)
- Clear separation between implemented and planned phases
- Changes committed with descriptive message

## Workflow Context

This skill fits into the feature lifecycle as a feedback loop:

```
/plan-feature        → Proposal (spec is aspirational)
/implement-feature   → Build + PR (spec may drift)
/update-specs        → Sync specs with reality ← YOU ARE HERE
/cleanup-feature     → Merge + archive
```

Run `/update-specs` whenever implementation diverges from the original spec — whether during `/implement-feature`, after debugging sessions, or after code review feedback.
