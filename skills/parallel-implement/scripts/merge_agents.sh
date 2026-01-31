#!/bin/bash
# merge_agents.sh - Merge all agent branches back to feature branch
# Usage: ./merge_agents.sh <change-id>

set -e

CHANGE_ID="${1:?Usage: $0 <change-id>}"
FEATURE_BRANCH="openspec/$CHANGE_ID"

echo "=== Merging Agent Branches ==="
echo "Change ID: $CHANGE_ID"
echo "Target branch: $FEATURE_BRANCH"
echo "=============================="
echo ""

# Ensure we're on the feature branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$FEATURE_BRANCH" ]; then
    echo "Switching to $FEATURE_BRANCH..."
    git checkout "$FEATURE_BRANCH"
fi

# Get closed beads (completed work)
CLOSED_BEADS=$(bd list --closed --json 2>/dev/null || echo "[]")
CLOSED_COUNT=$(echo "$CLOSED_BEADS" | jq length)

if [ "$CLOSED_COUNT" -eq 0 ]; then
    echo "No closed beads found. Nothing to merge."
    exit 0
fi

echo "Found $CLOSED_COUNT completed agent branches to merge."
echo ""

# Track merge results
MERGED=0
FAILED=0
FAILED_BRANCHES=""

echo "$CLOSED_BEADS" | jq -r '.[] | .id' | while read bead_id; do
    BRANCH="agent-$bead_id"
    TASK=$(bd show "$bead_id" --json 2>/dev/null | jq -r '.title' || echo "Unknown task")
    
    # Check if branch exists
    if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
        echo "⚠️  Branch not found: $BRANCH (skipping)"
        continue
    fi
    
    echo "Merging: $BRANCH"
    echo "  Task: $TASK"
    
    if git merge "$BRANCH" --no-edit -m "Merge $BRANCH: $TASK"; then
        echo "  ✓ Merged successfully"
        MERGED=$((MERGED + 1))
    else
        echo "  ✗ CONFLICT - requires manual resolution"
        FAILED=$((FAILED + 1))
        FAILED_BRANCHES="$FAILED_BRANCHES $BRANCH"
        
        # Abort this merge so we can continue with others
        git merge --abort
        echo "  (merge aborted, continue manually later)"
    fi
    echo ""
done

echo "=== Merge Summary ==="
echo "Merged: $MERGED"
echo "Failed: $FAILED"

if [ -n "$FAILED_BRANCHES" ]; then
    echo ""
    echo "Branches with conflicts (merge manually):"
    for branch in $FAILED_BRANCHES; do
        echo "  git merge $branch"
    done
fi

echo ""
echo "Next: Run cleanup_worktrees.sh $CHANGE_ID to remove worktrees"
