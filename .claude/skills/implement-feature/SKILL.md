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

### 0. Detect Coordinator and Read Handoff

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_HANDOFF=true`, read recent handoff context before implementation:

- MCP path: `read_handoff`
- HTTP path: `scripts/coordination_bridge.py` `try_handoff_read(...)`

On handoff failure/unavailability, continue with standalone implementation and log informationally.

### 1. Verify Proposal Exists

```bash
# Verify the proposal
openspec show <change-id>

# Check tasks
cat openspec/changes/<change-id>/tasks.md
```

Confirm the proposal is approved before proceeding.

### 2. Setup Worktree for Feature Isolation

Create an isolated worktree for this feature to avoid conflicts with other CLI sessions:

```bash
# Determine paths — use git-common-dir to find the main repo even from a worktree
CHANGE_ID="<change-id>"
GIT_COMMON=$(git rev-parse --git-common-dir)
if [[ "$GIT_COMMON" == ".git" ]]; then
  # In main repo
  MAIN_REPO=$(git rev-parse --show-toplevel)
else
  # In worktree — git-common-dir returns /path/to/main/.git or /path/to/main/.git/worktrees/<name>
  MAIN_REPO="${GIT_COMMON%%/.git*}"
fi
REPO_NAME=$(basename "$MAIN_REPO")
WORKTREE_PARENT="$(dirname "$MAIN_REPO")/${REPO_NAME}.worktrees"
WORKTREE_PATH="${WORKTREE_PARENT}/${CHANGE_ID}"

# Check if already in the correct worktree
CURRENT_TOPLEVEL=$(git rev-parse --show-toplevel)
if [[ "$CURRENT_TOPLEVEL" == "$WORKTREE_PATH" ]]; then
  echo "Already in worktree for ${CHANGE_ID}"
else
  # Create worktree parent directory
  mkdir -p "$WORKTREE_PARENT"

  # Ensure on main with latest
  git checkout main
  git pull origin main

  # Create feature branch if it doesn't exist
  if ! git show-ref --verify --quiet "refs/heads/openspec/${CHANGE_ID}"; then
    git branch "openspec/${CHANGE_ID}" main
  fi

  # Create worktree (or reuse if exists)
  if [ -d "$WORKTREE_PATH" ]; then
    echo "Worktree already exists: $WORKTREE_PATH"
  else
    git worktree add "$WORKTREE_PATH" "openspec/${CHANGE_ID}"
    echo "Worktree created: $WORKTREE_PATH"
  fi

  # Change to worktree
  cd "$WORKTREE_PATH"
  echo "Working directory changed to: $(pwd)"
fi
```

After this step, you are working in an isolated directory. Other terminal sessions can work on different features without conflict.

### 3. Verify Feature Branch

```bash
# Should already be on feature branch from worktree setup
git branch --show-current  # Should show openspec/<change-id>

# If not (e.g., resumed session), checkout the branch
git checkout openspec/<change-id>
```

### 3. Implement Tasks

Preferred path:
- Use the runtime-native apply workflow (`opsx:apply` equivalent for the active agent) to execute tasks.

CLI fallback path:

```bash
openspec instructions apply --change "<change-id>" --json
openspec status --change "<change-id>"
```

Execution expectations:
- Read proposal/spec/design/tasks context from apply instructions
- Work through tasks sequentially unless safely parallelizable
- Keep edits minimal and focused
- Mark completed tasks in `tasks.md` (`- [ ]` -> `- [x]`)

Capability-gated coordinator hooks:

- **Guardrails (`CAN_GUARDRAILS=true`)**: before running high-risk operations, run a guardrail pre-check and report violations informationally (phase 1 does not hard-block)
- **File locking (`CAN_LOCK=true`)**: acquire locks before editing files and keep a local list of acquired locks for cleanup
- **Work queue (`CAN_QUEUE_WORK=true`)**: for independent tasks, optionally submit/claim/complete via coordinator queue APIs; if unavailable or unclaimed, fall back to local `Task()` execution

**TDD Approach:**
- Write tests first that define expected behavior
- Implement code to make tests pass
- Don't proceed until tests pass

#### Parallel Implementation (for independent tasks)

When tasks.md contains multiple **independent tasks** (no shared files), implement them concurrently:

```
# Spawn parallel agents (single message, multiple Task calls)
Task(
  subagent_type="general-purpose",
  description="Implement task 1: <brief>",
  prompt="You are implementing OpenSpec <change-id>, Task 1.

## Your Task
<TASK_DESCRIPTION from tasks.md>

## File Scope (CRITICAL)
You MAY modify: <list specific files>
You must NOT modify any other files.

## Context
- Read openspec/changes/<change-id>/proposal.md for full context
- Read openspec/changes/<change-id>/design.md for architectural decisions

## Process
1. Read the proposal and design docs
2. Write failing tests first (TDD)
3. Implement minimal code to pass tests
4. Run tests to verify
5. Report completion with summary of changes

Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)
```

**Rules for parallel implementation:**
- Each agent's prompt MUST list specific files it may modify
- Tasks with overlapping files MUST run sequentially
- Collect all results via TaskOutput before committing
- If an agent fails, use `Task(resume=<agent_id>)` to retry

Locking behavior details (`CAN_LOCK=true`):

- Acquire lock before editing each targeted file
- If lock acquisition is blocked, report owner/expiry information and skip that file
- Continue with unblocked files/tasks
- On completion/failure, release all acquired locks (best effort; warn on release failure)

**When to parallelize:**
- 3+ independent tasks with no file overlap
- Tasks targeting separate modules/packages
- Independent test suites

**When NOT to parallelize:**
- Tasks that share files or state
- Tasks with logical dependencies (B needs A's output)
- Small proposals where sequential is simpler

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

### 6. Quality Checks (Parallel Execution)

Run all quality checks concurrently using Task() with `run_in_background=true`:

```
# Launch all checks in parallel (single message, multiple Task calls)
Task(subagent_type="Bash", prompt="Run pytest and report pass/fail with summary", run_in_background=true)
Task(subagent_type="Bash", prompt="Run mypy src/ and report any type errors", run_in_background=true)
Task(subagent_type="Bash", prompt="Run ruff check . and report any linting issues", run_in_background=true)
Task(subagent_type="Bash", prompt="Run openspec validate <change-id> --strict", run_in_background=true)
Task(subagent_type="Bash", prompt="Run 'python scripts/validate_flows.py --diff main...HEAD' from the project root and report any architecture diagnostics (broken flows, missing tests, orphaned code). If the script is not available or docs/architecture-analysis/architecture.graph.json doesn't exist, report that architecture validation was skipped.", run_in_background=true)
```

**Result Aggregation:**
1. Wait for all TaskOutput results
2. Collect pass/fail status from each check
3. Report all results together (don't fail-fast on first error)
4. If any check fails, show all failures before fixing

**Example output format:**
```
Quality Check Results:
✓ pytest: 42 tests passed
✗ mypy: 3 type errors in src/auth.py
✓ ruff: No issues
✓ openspec validate: Valid
✓ architecture: No broken flows (2 warnings: orphaned functions)
```

Fix all failures before proceeding. Address issues in order of severity (type errors before style).

### 7. Document Lessons Learned

Document any lessons learned during implementation, such as repeatable patterns, gotchas in the code that are noteworthy, and any changes in design that came up during the implementation and test phases in documents in the CLAUDE.md and AGENTS.md files. 

If the CLAUDE.md and AGENTS.md files are getting beyond 300 lines each, then refactor the documentation into documents focused on certain aspects of the project or the development process in the docs/ folder such as DEVELOPMENT.md for development guidelines, SETUP.md for set up instructions, UX_DESIGN.md for front end design considerations, etc. and reference them in CLAUDE.md and AGENTS.md

### 8. Commit Changes

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

### 9. Push and Create PR

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

If `CAN_HANDOFF=true`, write a completion handoff after PR creation containing:

- Completed tasks and major design/implementation decisions
- Any blocked/skipped work (for example lock contention outcomes)
- Validation/test status
- Recommended next command (`/iterate-on-implementation`, `/validate-feature`, or `/cleanup-feature`)

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
