---
name: plan-feature
description: Create OpenSpec proposal for a new feature and await approval
category: Git Workflow
tags: [openspec, planning, proposal]
triggers:
  - "plan feature"
  - "plan a feature"
  - "design feature"
  - "propose feature"
  - "start planning"
---

# Plan Feature

Create an OpenSpec proposal for a new feature. Ends when proposal is approved.

## Arguments

`$ARGUMENTS` - Feature description (e.g., "add user authentication")

## Steps

### 1. Verify Clean State

```bash
# Pull latest from main
git pull origin main

# Ensure clean working directory
git status
```

Resolve any uncommitted changes before proceeding.

### 2. Review Existing Context

```bash
# Review project context
cat openspec/project.md

# List existing specs
openspec list --specs

# List any in-progress changes
openspec list
```

Understand the current state before proposing changes.

### 3. Create OpenSpec Proposal

```
/openspec:proposal $ARGUMENTS
```

This will:
- Choose a unique verb-led change-id
- Scaffold `openspec/changes/<id>/`:
  - `proposal.md` - Feature description and objectives
  - `tasks.md` - Ordered, verifiable work items
  - `design.md` - Architectural reasoning (if needed)
- Draft spec deltas in `changes/<id>/specs/<capability>/spec.md`
- Each requirement includes `#### Scenario:` blocks

### 4. Validate Proposal

```bash
# Strict validation
openspec validate <change-id> --strict

# Review the proposal
openspec show <change-id>
```

Fix any validation errors before presenting for approval.

### 5. Present for Approval

Share the proposal with stakeholders:
- `openspec/changes/<change-id>/proposal.md` - What and why
- `openspec/changes/<change-id>/tasks.md` - Implementation plan
- `openspec/changes/<change-id>/design.md` - How (if applicable)

**STOP HERE - Wait for approval before proceeding to implementation.**

## Output

- Validated OpenSpec proposal in `openspec/changes/<change-id>/`
- Change-id ready for `/implement-feature <change-id>`

## Next Step

After approval:
```
/implement-feature <change-id>
```
