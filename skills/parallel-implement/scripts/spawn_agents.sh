#!/bin/bash
# spawn_agents.sh - Spawn parallel Claude agents in isolated git worktrees
# Usage: ./spawn_agents.sh <change-id> [max-parallel]

set -e

CHANGE_ID="${1:?Usage: $0 <change-id> [max-parallel]}"
MAX_PARALLEL="${2:-4}"
LOGDIR="logs/openspec-$CHANGE_ID"
WORKTREE_BASE="../worktrees-$CHANGE_ID"
PROPOSAL="openspec/changes/$CHANGE_ID/proposal.md"

# Verify prerequisites
command -v bd >/dev/null 2>&1 || { echo "Error: beads (bd) not installed"; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Error: claude CLI not installed"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Error: jq not installed"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "Error: git not installed"; exit 1; }

[ -f "$PROPOSAL" ] || { echo "Error: Proposal not found: $PROPOSAL"; exit 1; }

# Setup
mkdir -p "$LOGDIR"
READY_BEADS=$(bd ready --json 2>/dev/null || echo "[]")
BEAD_COUNT=$(echo "$READY_BEADS" | jq length)

if [ "$BEAD_COUNT" -eq 0 ]; then
    echo "No ready beads found. Create beads first with 'bd add'"
    exit 0
fi

echo "=== Parallel Agent Spawner (with Worktrees) ==="
echo "Change ID:     $CHANGE_ID"
echo "Ready beads:   $BEAD_COUNT"
echo "Max parallel:  $MAX_PARALLEL"
echo "Worktree base: $WORKTREE_BASE"
echo "Log directory: $LOGDIR"
echo "==============================================="
echo ""

# Phase 1: Create worktrees
echo "Phase 1: Creating isolated worktrees..."
mkdir -p "$WORKTREE_BASE"

echo "$READY_BEADS" | jq -r '.[] | .id' | while read bead_id; do
    BRANCH="agent-$bead_id"
    WORKTREE_PATH="$WORKTREE_BASE/$bead_id"
    
    if [ -d "$WORKTREE_PATH" ]; then
        echo "  Worktree exists: $WORKTREE_PATH (skipping)"
    else
        git worktree add "$WORKTREE_PATH" -b "$BRANCH" 2>/dev/null || \
        git worktree add "$WORKTREE_PATH" "$BRANCH" 2>/dev/null || {
            echo "  Error creating worktree for $bead_id"
            exit 1
        }
        echo "  Created: $WORKTREE_PATH (branch: $BRANCH)"
    fi
done
echo ""

# Phase 2: Spawn agents
echo "Phase 2: Spawning agents..."
PIDS=()
active_count=0

spawn_agent() {
    local bead_id="$1"
    local task=$(bd show "$bead_id" --json | jq -r '.title')
    local logfile="$LOGDIR/${bead_id}.log"
    local agent_dir="$WORKTREE_BASE/$bead_id"
    
    echo "[$(date +%H:%M:%S)] Spawning: $task"
    echo "  Worktree: $agent_dir"
    
    (cd "$agent_dir" && claude -p "You are implementing OpenSpec $CHANGE_ID.

## Your Task
$task

## Environment
- You are in an isolated git worktree: $agent_dir
- Your branch: agent-$bead_id
- Other agents are working in parallel on separate branches

## Instructions
1. Read openspec/changes/$CHANGE_ID/proposal.md for full context
2. Check openspec/changes/$CHANGE_ID/design.md if it exists
3. Implement ONLY your assigned task
4. Write tests FIRST (TDD approach)
5. Run tests to verify your implementation
6. Commit your changes:
   git add .
   git commit -m 'feat: $task'

## Completion
When your task is complete, tests pass, and changes are committed:
bd close $bead_id

Do NOT close the bead until you have committed your changes.") > "$logfile" 2>&1 &
    
    local pid=$!
    PIDS+=($pid)
    echo "  PID: $pid, Log: $logfile"
}

echo "$READY_BEADS" | jq -r '.[] | .id' | while read bead_id; do
    # Simple concurrency: spawn up to MAX_PARALLEL
    spawn_agent "$bead_id"
done

# Wait for all to complete
echo ""
echo "[$(date +%H:%M:%S)] All agents spawned. Waiting for completion..."
wait

echo ""
echo "=== Execution Complete ==="
echo "Remaining beads: $(bd ready --json | jq length)"
CLOSED_COUNT=$(bd list --closed --json 2>/dev/null | jq length || echo "N/A")
echo "Closed beads:    $CLOSED_COUNT"
echo ""
echo "Logs: $LOGDIR"
echo ""
echo "Next steps:"
echo "  1. Review agent logs for any errors"
echo "  2. Merge branches: run merge_agents.sh $CHANGE_ID"
echo "  3. Or manually: git merge agent-<bead-id> for each"
