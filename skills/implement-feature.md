---
name: implement-feature
description: Implement approved OpenSpec proposal through to PR creation
category: Git Workflow
tags: [openspec, implementation, pr]
triggers:
  - "implement feature"
  - "build feature"
  - "start implementation"
  - "begin implementation"
  - "code feature"
---

# Implement Feature

Implement an approved OpenSpec proposal. Ends when PR is created and awaiting review.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal exists at `openspec/changes/<change-id>/`
- Run `/plan-feature` first if no proposal exists

## Steps

### 1. Verify Proposal Exists

```bash
# Verify the proposal
openspec show <change-id>

# Check tasks
cat openspec/changes/<change-id>/tasks.md
```

Confirm the proposal is approved before proceeding.

### 2. Create Feature Branch

```bash
# Ensure on main with latest
git checkout main
git pull origin main

# Create branch using change-id
git checkout -b openspec/<change-id>
```

### 3. Implement Tasks

```
/openspec:apply <change-id>
```

This will:
- Read proposal.md, design.md, and tasks.md
- Work through tasks sequentially
- Keep edits minimal and focused on the requested change
- Mark tasks complete in tasks.md as `- [x]`

**TDD Approach:**
- Write tests first that define expected behavior
- Implement code to make tests pass
- Don't proceed until tests pass

### 4. Track Progress

Use TodoWrite to track implementation:
- Create todos from tasks.md
- Mark complete as you progress
- Use `openspec show <change-id>` for context when needed

### 5. Verify All Tasks Complete

```bash
# Check all tasks are marked done
grep -E "^\s*- \[ \]" openspec/changes/<change-id>/tasks.md

# Should return nothing (all boxes checked)
```

### 6. Quality Checks

```bash
# Run tests
pytest

# Type checking (if applicable)
mypy src/

# Linting (if applicable)
ruff check .

# Validate OpenSpec
openspec validate <change-id> --strict
```

Fix any failures before proceeding.

### 7. Commit Changes

```bash
# Review changes
git status
git diff

# Stage all changes
git add .

# Commit with OpenSpec reference
git commit -m "$(cat <<'EOF'
feat(<scope>): <description>

Implements OpenSpec: <change-id>

- <key change 1>
- <key change 2>
- <key change 3>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### 8. Push and Create PR

```bash
# Push branch
git push -u origin openspec/<change-id>

# Create PR
gh pr create --title "feat(<scope>): <title from proposal>" --body "$(cat <<'EOF'
## Summary

Implements OpenSpec proposal: `<change-id>`

**Proposal**: `openspec/changes/<change-id>/proposal.md`

### Changes
- <bullet points summarizing changes>

## Test Plan
- [ ] All tests pass (`pytest`)
- [ ] Type checks pass (`mypy src/`)
- [ ] Linting passes (`ruff check .`)
- [ ] OpenSpec validates (`openspec validate <change-id> --strict`)
- [ ] All tasks complete in `tasks.md`

## OpenSpec Tasks
<paste tasks.md checklist>

---
🤖 Generated with Claude Code
EOF
)"
```

**STOP HERE - Wait for PR approval before proceeding to cleanup.**

## Output

- Feature branch: `openspec/<change-id>`
- All tests passing
- PR created and awaiting review

## Next Step

After PR is approved:
```
/cleanup-feature <change-id>
```
