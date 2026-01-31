#!/bin/bash
# cleanup_worktrees.sh - Remove worktrees and agent branches after merge
# Usage: ./cleanup_worktrees.sh <change-id> [--force]

set -e

CHANGE_ID="${1:?Usage: $0 <change-id> [--force]}"
FORCE="${2:-}"
WORKTREE_BASE="../worktrees-$CHANGE_ID"

echo "=== Cleaning Up Worktrees ==="
echo "Change ID: $CHANGE_ID"
echo "Worktree base: $WORKTREE_BASE"
echo "============================="
echo ""

# Check if worktree directory exists
if [ ! -d "$WORKTREE_BASE" ]; then
    echo "No worktree directory found at $WORKTREE_BASE"
    echo "Nothing to clean up."
    exit 0
fi

# Get list of worktrees for this change
WORKTREES=$(ls -1 "$WORKTREE_BASE" 2>/dev/null || echo "")

if [ -z "$WORKTREES" ]; then
    echo "No worktrees found in $WORKTREE_BASE"
    rmdir "$WORKTREE_BASE" 2>/dev/null || true
    exit 0
fi

# Confirm unless --force
if [ "$FORCE" != "--force" ]; then
    echo "This will remove the following worktrees and branches:"
    for bead_id in $WORKTREES; do
        echo "  - $WORKTREE_BASE/$bead_id (branch: agent-$bead_id)"
    done
    echo ""
    read -p "Continue? [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

# Remove worktrees and branches
REMOVED=0
ERRORS=0

for bead_id in $WORKTREES; do
    WORKTREE_PATH="$WORKTREE_BASE/$bead_id"
    BRANCH="agent-$bead_id"
    
    echo "Removing: $WORKTREE_PATH"
    
    # Remove worktree
    if git worktree remove "$WORKTREE_PATH" --force 2>/dev/null; then
        echo "  ✓ Worktree removed"
    else
        echo "  ⚠️  Failed to remove worktree (may not exist)"
    fi
    
    # Delete branch
    if git branch -d "$BRANCH" 2>/dev/null; then
        echo "  ✓ Branch deleted"
        REMOVED=$((REMOVED + 1))
    elif git branch -D "$BRANCH" 2>/dev/null; then
        echo "  ✓ Branch force-deleted (had unmerged changes)"
        REMOVED=$((REMOVED + 1))
    else
        echo "  ⚠️  Branch not found or already deleted"
    fi
    echo ""
done

# Remove base directory
rmdir "$WORKTREE_BASE" 2>/dev/null && echo "Removed: $WORKTREE_BASE" || true

echo "=== Cleanup Complete ==="
echo "Removed: $REMOVED branches/worktrees"

# Prune worktree metadata
echo ""
echo "Pruning stale worktree references..."
git worktree prune
echo "Done."
