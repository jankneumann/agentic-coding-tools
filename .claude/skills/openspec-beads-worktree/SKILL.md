---
name: openspec-beads-worktree
version: 1.0.0
description: Coordinate OpenSpec proposals with Beads task tracking and isolated git worktree execution. Implements systematic spec-driven development with parallel agent coordination.
author: Enterprise AI Strategy
tags: [openspec, beads, git-worktree, multi-agent, coordination]
requires:
  - openspec (CLI or manual)
  - beads (bd CLI >= 0.21.5)
  - git (2.x with worktree support)
triggers:
  - "implement openspec proposal"
  - "convert openspec to beads"
  - "setup worktree for"
  - "coordinate openspec work"
  - "parallel implementation"
---

# OpenSpec + Beads + Git Worktree Coordination

## Purpose

This skill coordinates the complete workflow from OpenSpec proposal through Beads task creation to isolated git worktree execution. It enables systematic spec-driven development with support for parallel agent coordination.

## When to Use This Skill

Activate this skill when:
- Starting work on an OpenSpec proposal
- Converting OpenSpec tasks to Beads issues
- Setting up isolated execution environments
- Coordinating multiple agents on one feature
- Implementing complex changes that span multiple sessions

## Workflow Overview

```
OpenSpec Proposal → Beads Issues → Git Worktrees → Execution → Merge → Archive
       ↓                ↓              ↓              ↓          ↓        ↓
   Planning        Tracking      Isolation      Implementation Review  Knowledge
```

## Phase 1: OpenSpec Proposal Review

### Step 1.1: Locate and Review Proposal

```bash
# Check if OpenSpec is initialized
if [ -d "openspec" ]; then
  echo "✓ OpenSpec initialized"
else
  echo "✗ OpenSpec not found - run: openspec init"
  exit 1
fi

# List available proposals
openspec list

# View specific proposal
openspec show <proposal-name>
```

**What to Check:**
- Proposal exists in `openspec/changes/<proposal-name>/`
- Has `proposal.md` with clear objectives
- Has `tasks.md` with implementation tasks
- Has `specs/` directory with spec deltas

### Step 1.2: Validate Proposal Structure

Read and validate:
1. `openspec/changes/<proposal-name>/proposal.md` - Feature description
2. `openspec/changes/<proposal-name>/tasks.md` - Task breakdown
3. `openspec/changes/<proposal-name>/specs/*/spec.md` - Specification changes

**Quality Checks:**
- [ ] Tasks are atomic and testable
- [ ] Dependencies are clearly marked
- [ ] Acceptance criteria are defined
- [ ] Estimated complexity is reasonable

## Phase 2: Convert OpenSpec to Beads

### Step 2.1: Initialize Beads (if needed)

```bash
# Check if Beads is initialized
if [ -d ".beads" ]; then
  echo "✓ Beads initialized"
  bd version
else
  echo "Initializing Beads..."
  bd init
fi

# Verify Beads is working
bd list --status open --json
```

### Step 2.2: Create Epic from Proposal

```bash
# Create epic for the OpenSpec proposal
PROPOSAL_NAME="<proposal-name>"
EPIC_TITLE="OpenSpec: $(grep -m 1 '^#' openspec/changes/$PROPOSAL_NAME/proposal.md | sed 's/^# //')"

# Create epic and capture ID
EPIC_ID=$(bd create "$EPIC_TITLE" \
  --type epic \
  --priority 1 \
  --description "Implementing OpenSpec proposal: $PROPOSAL_NAME" \
  --label "openspec,$PROPOSAL_NAME" \
  --json | jq -r '.id')

echo "Created epic: $EPIC_ID"

# Add reference to OpenSpec proposal
bd update $EPIC_ID --description "$(cat <<EOF
OpenSpec Proposal: $PROPOSAL_NAME
Location: openspec/changes/$PROPOSAL_NAME/

Proposal Summary:
$(head -n 10 openspec/changes/$PROPOSAL_NAME/proposal.md)

[Full proposal: openspec/changes/$PROPOSAL_NAME/proposal.md]
EOF
)"
```

### Step 2.3: Parse Tasks and Create Beads Issues

```bash
# Function to parse OpenSpec tasks.md and create Beads issues
create_beads_from_tasks() {
  local proposal=$1
  local epic_id=$2
  local tasks_file="openspec/changes/$proposal/tasks.md"
  
  # Parse tasks.md structure
  # Format: ## Task X.Y: Title
  #         - Subtask details
  #         - Dependencies: Task X.Z
  
  while IFS= read -r line; do
    if [[ $line =~ ^##\ Task\ ([0-9.]+):\ (.+)$ ]]; then
      task_num="${BASH_REMATCH[1]}"
      task_title="${BASH_REMATCH[2]}"
      
      # Read description until next ## or end
      description=""
      while IFS= read -r desc_line; do
        [[ $desc_line =~ ^## ]] && break
        description+="$desc_line\n"
      done
      
      # Create Beads issue
      priority=$([[ $task_num =~ ^1\. ]] && echo "0" || echo "1")
      
      issue_id=$(bd create "$task_title" \
        --type task \
        --priority $priority \
        --parent $epic_id \
        --label "openspec,$proposal,task-$task_num" \
        --description "$description" \
        --json | jq -r '.id')
      
      echo "Created: $issue_id - Task $task_num: $task_title"
      
      # Store mapping for dependency linking
      echo "$task_num:$issue_id" >> /tmp/beads_task_map_$proposal.txt
    fi
  done < "$tasks_file"
}

# Execute conversion
create_beads_from_tasks "$PROPOSAL_NAME" "$EPIC_ID"
```

### Step 2.4: Link Dependencies

```bash
# Parse dependencies from tasks.md and create Beads deps
link_dependencies() {
  local proposal=$1
  local map_file="/tmp/beads_task_map_$proposal.txt"
  local tasks_file="openspec/changes/$proposal/tasks.md"
  
  # Look for "Dependencies: Task X.Y" patterns
  grep -n "Dependencies:" "$tasks_file" | while IFS=: read -r line_num dep_line; do
    # Get task number from nearby ## Task X.Y
    task_num=$(sed -n "$((line_num-5)),$((line_num))p" "$tasks_file" | \
               grep -o "Task [0-9.]*" | tail -1 | cut -d' ' -f2)
    
    # Extract dependency task numbers
    dep_tasks=$(echo "$dep_line" | grep -o "Task [0-9.]*" | cut -d' ' -f2)
    
    # Get Beads IDs from map
    task_id=$(grep "^$task_num:" "$map_file" | cut -d: -f2)
    
    for dep_task in $dep_tasks; do
      dep_id=$(grep "^$dep_task:" "$map_file" | cut -d: -f2)
      
      if [[ -n "$dep_id" ]] && [[ -n "$task_id" ]]; then
        bd dep add "$task_id" "$dep_id" --type blocks
        echo "Linked: $task_id blocks on $dep_id"
      fi
    done
  done
}

link_dependencies "$PROPOSAL_NAME"
```

### Step 2.5: Validate Beads Structure

```bash
# Show the created structure
echo -e "\n=== Epic and Tasks ==="
bd show $EPIC_ID
bd list --parent $EPIC_ID --json | jq -r '.[] | "\(.id): \(.title)"'

# Show ready work
echo -e "\n=== Ready Tasks (no blockers) ==="
bd ready --parent $EPIC_ID --json | jq -r '.[] | "\(.id): \(.title)"'

# Visualize dependencies
echo -e "\n=== Dependency Graph ==="
bd deps $EPIC_ID --graph
```

## Phase 3: Git Worktree Setup

### Step 3.1: Create Worktree Strategy

```bash
# Determine worktree strategy based on task count
TASK_COUNT=$(bd list --parent $EPIC_ID --status open --json | jq '. | length')

if [ $TASK_COUNT -le 3 ]; then
  STRATEGY="single"
  echo "Strategy: Single worktree (sequential execution)"
elif [ $TASK_COUNT -le 10 ]; then
  STRATEGY="parallel"
  echo "Strategy: Parallel worktrees (2-3 concurrent)"
else
  STRATEGY="swarm"
  echo "Strategy: Swarm worktrees (5+ concurrent)"
fi
```

### Step 3.2: Create Worktree(s)

```bash
# Get base branch
BASE_BRANCH=$(git branch --show-current)
FEATURE_BRANCH="openspec/${PROPOSAL_NAME}"

# Create feature branch
git checkout -b "$FEATURE_BRANCH"
git push -u origin "$FEATURE_BRANCH"
git checkout "$BASE_BRANCH"

# Function to create worktree for a task
create_task_worktree() {
  local task_id=$1
  local task_title=$2
  local task_num=$3
  
  # Sanitize title for branch name
  local branch_name=$(echo "$task_title" | \
    tr '[:upper:]' '[:lower:]' | \
    sed 's/[^a-z0-9]/-/g' | \
    sed 's/--*/-/g' | \
    sed 's/^-//;s/-$//')
  
  local worktree_path=".git-worktrees/${PROPOSAL_NAME}-${task_num}"
  local branch="${FEATURE_BRANCH}-task-${task_num}-${branch_name}"
  
  # Create worktree
  git worktree add -b "$branch" "$worktree_path" "$FEATURE_BRANCH"
  
  # Store worktree info in Beads
  bd update "$task_id" --description "$(bd show $task_id --json | jq -r '.description')

Worktree: $worktree_path
Branch: $branch
Base: $FEATURE_BRANCH"
  
  echo "Created worktree: $worktree_path"
  echo "$task_id|$worktree_path|$branch" >> /tmp/worktree_map_$PROPOSAL_NAME.txt
}

# Create worktrees for ready tasks
bd ready --parent $EPIC_ID --json | jq -r '.[] | "\(.id)|\(.title)"' | \
while IFS='|' read -r task_id task_title; do
  # Extract task number from labels
  task_num=$(bd show $task_id --json | jq -r '.labels[]' | grep -o 'task-[0-9.]*' | cut -d- -f2)
  
  create_task_worktree "$task_id" "$task_title" "$task_num"
done
```

### Step 3.3: Setup Worktree Environment

```bash
# For each worktree, setup CLAUDE.md or AGENTS.md
setup_worktree_context() {
  local worktree_path=$1
  local task_id=$2
  
  # Get task details
  local task_info=$(bd show $task_id --json)
  local task_title=$(echo "$task_info" | jq -r '.title')
  local task_desc=$(echo "$task_info" | jq -r '.description')
  
  # Create CLAUDE.md in worktree
  cat > "$worktree_path/CLAUDE.md" <<EOF
# Task Context: $task_title

## Beads Task ID: $task_id

## Objective
$task_desc

## OpenSpec Reference
See: openspec/changes/$PROPOSAL_NAME/

## Working Instructions

1. **Check Dependencies**
   \`\`\`bash
   bd show $task_id
   # Verify all blockers are resolved
   \`\`\`

2. **Update Status**
   \`\`\`bash
   bd update $task_id --status in_progress
   \`\`\`

3. **Reference Specs**
   - Read openspec/changes/$PROPOSAL_NAME/specs/
   - Follow acceptance criteria in tasks.md

4. **When Complete**
   \`\`\`bash
   # Run tests
   npm test # or appropriate test command
   
   # Commit changes
   git add .
   git commit -m "$task_title"
   
   # Update Beads
   bd close $task_id --reason "Implementation complete"
   
   # Push branch
   git push origin HEAD
   \`\`\`

5. **Coordination**
   - Use \`bd list --parent $EPIC_ID\` to see other tasks
   - Check \`bd ready --parent $EPIC_ID\` for next work
   - Communicate via Beads comments if blocked

## Implementation Checklist
$(echo "$task_desc" | grep -E '^- \[ \]' || echo "- [ ] Implement feature\n- [ ] Write tests\n- [ ] Update documentation")

---
Generated: $(date)
Worktree: $worktree_path
EOF

  # Initialize Beads in worktree (links to main .beads)
  cd "$worktree_path"
  bd onboard
  cd - > /dev/null
  
  echo "✓ Setup context in $worktree_path"
}

# Setup all worktrees
while IFS='|' read -r task_id worktree_path branch; do
  setup_worktree_context "$worktree_path" "$task_id"
done < /tmp/worktree_map_$PROPOSAL_NAME.txt
```

## Phase 4: Execution Coordination

### Step 4.1: Launch Execution Sessions

```bash
# Create orchestrator script
cat > "execute_${PROPOSAL_NAME}.sh" <<'EOF'
#!/bin/bash
set -e

PROPOSAL_NAME="${1:-$PROPOSAL_NAME}"
MAP_FILE="/tmp/worktree_map_$PROPOSAL_NAME.txt"

echo "=== OpenSpec Execution Orchestrator ==="
echo "Proposal: $PROPOSAL_NAME"
echo "Strategy: $STRATEGY"
echo ""

# Function to execute task in worktree
execute_task() {
  local task_id=$1
  local worktree_path=$2
  local branch=$3
  
  echo "→ Starting task: $task_id in $worktree_path"
  
  cd "$worktree_path"
  
  # Update status
  bd update $task_id --status in_progress --assignee "@claude-$(hostname)"
  
  # Launch Claude Code
  claude -p "Review CLAUDE.md and implement this task. Follow all instructions in the file. When done, update Beads status."
  
  # Return to main directory
  cd - > /dev/null
}

# Execute based on strategy
case "$STRATEGY" in
  single)
    echo "Sequential execution..."
    while IFS='|' read -r task_id worktree_path branch; do
      execute_task "$task_id" "$worktree_path" "$branch"
    done < "$MAP_FILE"
    ;;
    
  parallel)
    echo "Parallel execution (max 3)..."
    cat "$MAP_FILE" | parallel -j 3 --colsep '|' execute_task {1} {2} {3}
    ;;
    
  swarm)
    echo "Swarm execution (max 5)..."
    cat "$MAP_FILE" | parallel -j 5 --colsep '|' execute_task {1} {2} {3}
    ;;
esac

echo ""
echo "=== Execution Complete ==="
bd list --parent $EPIC_ID --json | jq -r '.[] | "\(.id): \(.status)"'
EOF

chmod +x "execute_${PROPOSAL_NAME}.sh"

echo "Orchestrator created: execute_${PROPOSAL_NAME}.sh"
echo ""
echo "To execute:"
echo "  ./execute_${PROPOSAL_NAME}.sh"
```

### Step 4.2: Monitor Progress

```bash
# Create monitoring dashboard
cat > "monitor_${PROPOSAL_NAME}.sh" <<'EOF'
#!/bin/bash

PROPOSAL_NAME="${1:-$PROPOSAL_NAME}"
EPIC_ID=$(bd list --label "openspec,$PROPOSAL_NAME" --type epic --json | jq -r '.[0].id')

while true; do
  clear
  echo "=== OpenSpec Progress Dashboard ==="
  echo "Proposal: $PROPOSAL_NAME"
  echo "Epic: $EPIC_ID"
  echo "Time: $(date)"
  echo ""
  
  # Status summary
  echo "Status Summary:"
  bd list --parent $EPIC_ID --json | \
    jq -r 'group_by(.status) | map({status: .[0].status, count: length}) | .[] | "  \(.status): \(.count)"'
  
  echo ""
  echo "Active Tasks:"
  bd list --parent $EPIC_ID --status in_progress --json | \
    jq -r '.[] | "  [\(.id)] \(.title) - \(.assignee // "unassigned")"'
  
  echo ""
  echo "Ready Work:"
  bd ready --parent $EPIC_ID --limit 5 --json | \
    jq -r '.[] | "  [\(.id)] \(.title)"'
  
  echo ""
  echo "Blocked:"
  bd list --parent $EPIC_ID --status blocked --json | \
    jq -r '.[] | "  [\(.id)] \(.title)"'
  
  echo ""
  echo "[Refreshing in 30s... Ctrl+C to exit]"
  sleep 30
done
EOF

chmod +x "monitor_${PROPOSAL_NAME}.sh"

echo "Monitor created: monitor_${PROPOSAL_NAME}.sh"
echo "Run in separate terminal: ./monitor_${PROPOSAL_NAME}.sh"
```

## Phase 5: Integration and Review

### Step 5.1: Merge Worktree Branches

```bash
# Create merge orchestrator
merge_worktrees() {
  local proposal=$1
  local epic_id=$2
  local feature_branch="openspec/$proposal"
  
  echo "=== Merging Completed Tasks ==="
  
  # Get completed tasks
  bd list --parent $epic_id --status closed --json | jq -r '.[] | .id' | \
  while read -r task_id; do
    # Get worktree info
    worktree_info=$(bd show $task_id --json | jq -r '.description' | grep -A2 "Worktree:")
    branch=$(echo "$worktree_info" | grep "Branch:" | cut -d: -f2- | xargs)
    
    if [[ -n "$branch" ]]; then
      echo "→ Merging $branch into $feature_branch"
      
      git checkout "$feature_branch"
      git merge --no-ff "$branch" -m "Merge task $task_id: $(bd show $task_id --json | jq -r '.title')"
      
      if [ $? -eq 0 ]; then
        echo "  ✓ Merged successfully"
        bd update $task_id --label "+merged"
      else
        echo "  ✗ Merge conflict - manual resolution needed"
        bd update $task_id --status blocked --label "+merge-conflict"
      fi
    fi
  done
  
  git checkout $(git branch --show-current)
}

# Execute merge
merge_worktrees "$PROPOSAL_NAME" "$EPIC_ID"
```

### Step 5.2: Cleanup Worktrees

```bash
# Remove completed worktrees
cleanup_worktrees() {
  local proposal=$1
  
  while IFS='|' read -r task_id worktree_path branch; do
    # Check if task is merged
    if bd show $task_id --json | jq -e '.labels[] | select(. == "merged")' > /dev/null; then
      echo "Removing worktree: $worktree_path"
      git worktree remove "$worktree_path"
      git branch -d "$branch"
      
      bd update $task_id --description "$(bd show $task_id --json | jq -r '.description')

[Worktree cleaned up: $(date)]"
    fi
  done < "/tmp/worktree_map_$proposal.txt"
}

# Prompt before cleanup
read -p "Remove merged worktrees? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  cleanup_worktrees "$PROPOSAL_NAME"
fi
```

## Phase 6: Archive OpenSpec Proposal

### Step 6.1: Final Validation

```bash
# Verify all tasks complete
validate_completion() {
  local epic_id=$1
  
  echo "=== Completion Validation ==="
  
  # Check for open tasks
  open_count=$(bd list --parent $epic_id --status open --json | jq '. | length')
  in_progress=$(bd list --parent $epic_id --status in_progress --json | jq '. | length')
  blocked=$(bd list --parent $epic_id --status blocked --json | jq '. | length')
  
  if [[ $open_count -gt 0 ]] || [[ $in_progress -gt 0 ]] || [[ $blocked -gt 0 ]]; then
    echo "✗ Not ready for archive:"
    echo "  - Open: $open_count"
    echo "  - In Progress: $in_progress"
    echo "  - Blocked: $blocked"
    return 1
  fi
  
  echo "✓ All tasks complete"
  
  # Verify tests pass
  echo "Running tests..."
  git checkout "openspec/$PROPOSAL_NAME"
  npm test  # or appropriate test command
  
  if [ $? -eq 0 ]; then
    echo "✓ Tests pass"
    return 0
  else
    echo "✗ Tests failing"
    return 1
  fi
}

validate_completion "$EPIC_ID"
```

### Step 6.2: Archive OpenSpec

```bash
# Archive the proposal
archive_openspec() {
  local proposal=$1
  
  echo "Archiving OpenSpec proposal: $proposal"
  
  # If using OpenSpec CLI
  if command -v openspec &> /dev/null; then
    openspec archive "$proposal" --yes
  else
    # Manual archive
    mv "openspec/changes/$proposal" "openspec/changes/.archived/$proposal"
    
    # Consolidate specs
    for spec in openspec/changes/.archived/$proposal/specs/*/spec.md; do
      capability=$(basename $(dirname "$spec"))
      target="openspec/specs/$capability/spec.md"
      
      echo "Consolidating $capability spec..."
      cat "$spec" >> "$target"
    done
  fi
  
  git add openspec/
  git commit -m "Archive OpenSpec proposal: $proposal"
}

# Execute archive
read -p "Archive OpenSpec proposal? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  archive_openspec "$PROPOSAL_NAME"
fi
```

### Step 6.3: Close Epic

```bash
# Close the epic
bd close $EPIC_ID --reason "OpenSpec proposal implemented and archived"

# Add summary
bd comment $EPIC_ID "Implementation Summary:
- Total tasks: $(bd list --parent $EPIC_ID --json | jq '. | length')
- Duration: [manual entry]
- Worktrees used: $(wc -l < /tmp/worktree_map_$PROPOSAL_NAME.txt)
- Final branch: openspec/$PROPOSAL_NAME
- Archived: $(date)
"

echo "✓ Epic closed: $EPIC_ID"
```

## Best Practices

### Beads Discipline

1. **Always update status**
   ```bash
   bd update <id> --status in_progress  # When starting
   bd close <id>                         # When done
   ```

2. **Track blockers immediately**
   ```bash
   bd update <id> --status blocked
   bd comment <id> "Blocked by: [reason]"
   ```

3. **Use labels for filtering**
   ```bash
   --label "openspec,urgent"
   --label "frontend,review-needed"
   ```

### Git Worktree Hygiene

1. **One feature branch, multiple task branches**
   ```
   feature/openspec-xxx
     ├─ feature/openspec-xxx-task-1.1
     ├─ feature/openspec-xxx-task-1.2
     └─ feature/openspec-xxx-task-2.1
   ```

2. **Always merge to feature branch first**
   - Test integration before main branch merge
   - Resolve conflicts incrementally

3. **Clean up regularly**
   ```bash
   git worktree list
   git worktree remove <path>
   ```

### OpenSpec Integration

1. **Keep specs as source of truth**
   - Reference `openspec/changes/<name>/specs/` in all Beads issues
   - Don't duplicate spec content in Beads descriptions

2. **Archive only when complete**
   - All Beads closed
   - All tests passing
   - Feature branch merged

3. **Document decisions**
   ```bash
   bd comment <id> "Decision: [architectural choice]
   Rationale: [reasoning]
   Reference: [spec section]"
   ```

## Troubleshooting

### Beads Issues

**Problem**: Can't find issue
```bash
bd list --json | grep -i "search-term"
```

**Problem**: Dependency cycle
```bash
bd deps <id> --graph  # Visualize
bd dep remove <id1> <id2>  # Break cycle
```

### Worktree Issues

**Problem**: Worktree won't remove
```bash
git worktree remove --force <path>
```

**Problem**: Branch merge conflicts
```bash
# In feature branch
git merge --no-commit --no-ff <task-branch>
# Resolve conflicts
git merge --continue
```

### OpenSpec Issues

**Problem**: Tasks out of sync with Beads
```bash
# Re-run Phase 2 with --force flag
# Or manually update Beads to match
```

## Quick Reference

### Common Commands

```bash
# Check status
bd ready --parent <epic-id>
bd list --parent <epic-id> --status in_progress

# Update task
bd update <id> --status <status>
bd comment <id> "Progress update"

# Worktree management
git worktree list
git worktree add -b <branch> <path> <base>

# OpenSpec
openspec list
openspec show <proposal>
openspec archive <proposal>
```

### Workflow Checklist

- [ ] Phase 1: Review OpenSpec proposal
- [ ] Phase 2: Convert to Beads epic + tasks
- [ ] Phase 3: Create git worktrees
- [ ] Phase 4: Execute in parallel/sequence
- [ ] Phase 5: Merge and integrate
- [ ] Phase 6: Archive proposal, close epic

## Performance Tips

1. **Limit parallel execution**: 3-5 concurrent agents max
2. **Use `bd ready` filtering**: Only show relevant tasks
3. **Batch Beads operations**: Update multiple issues at once
4. **Reuse worktrees**: Keep active for related tasks

## Integration with Other Tools

### CI/CD
```bash
# In CI pipeline
bd list --label "openspec,$PROPOSAL" --status closed --json
# Verify all tasks complete before deploy
```

### Slack/Notifications
```bash
# On task completion
bd close <id> && \
  slack-cli chat send --channel dev \
  --text "Task completed: $(bd show <id> --json | jq -r '.title')"
```

### Monitoring
```bash
# Export metrics
bd list --parent <epic-id> --json | \
  jq '{total: length, by_status: group_by(.status) | map({status: .[0].status, count: length})}'
```

---

## Example Usage

```bash
# 1. Start with OpenSpec proposal
openspec show add-user-authentication

# 2. Invoke this skill
# "Implement the add-user-authentication OpenSpec proposal using Beads and worktrees"

# 3. Claude will:
#    - Convert OpenSpec tasks to Beads issues
#    - Create git worktrees for parallel work
#    - Set up execution environment
#    - Coordinate implementation
#    - Handle merging and archival

# 4. Monitor progress
./monitor_add-user-authentication.sh

# 5. Execute (manual or automated)
./execute_add-user-authentication.sh
```

---

**Last Updated**: January 2026  
**Skill Version**: 1.0.0  
**Compatibility**: OpenSpec 1.x, Beads 0.21+, Git 2.x
