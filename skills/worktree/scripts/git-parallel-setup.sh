#!/usr/bin/env bash
# Configure the local git repository for parallel agent development.
#
# Settings applied (all --local, never global):
#   rerere.enabled=true         — cache and reuse conflict resolutions
#   rerere.autoUpdate=true      — auto-stage rerere-resolved files
#   merge.conflictStyle=zdiff3  — show base version in conflict markers
#   diff.algorithm=histogram    — better diffs for repetitive code
#   rebase.updateRefs=true      — auto-update stacked branch pointers
#
# Idempotent: safe to run multiple times.

set -euo pipefail

# Verify we're in a git repo
git rev-parse --git-dir >/dev/null 2>&1 || {
    echo "Error: not in a git repository" >&2
    exit 1
}

configs=(
    "rerere.enabled=true"
    "rerere.autoUpdate=true"
    "merge.conflictStyle=zdiff3"
    "diff.algorithm=histogram"
    "rebase.updateRefs=true"
)

for entry in "${configs[@]}"; do
    key="${entry%%=*}"
    value="${entry#*=}"
    git config --local "${key}" "${value}"
    echo "Set ${key} = ${value}"
done

echo "Git parallel configuration applied."
