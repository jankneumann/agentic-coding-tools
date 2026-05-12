#!/bin/bash
#
# This installer is obsolete.
#
# The skill formerly known as "openspec-beads-worktree" was migrated to
# "openspec-coordinator-worktree" — issue tracking now goes through the
# agent coordinator's HTTP API (see skills/coordination-bridge/scripts/
# coordination_bridge.py for the try_issue_* helpers).
#
# No separate binary install is required. The coordinator exposes issue
# endpoints automatically, and Claude Code picks up the skill from
# ~/.claude/skills/ once it has been synced by skills/install.sh.
#
# To sync all repo-canonical skills into the Claude Code and Codex runtime
# paths, run from the repo root:
#
#     bash skills/install.sh --mode rsync --deps none --python-tools none
#
# Exiting with a non-zero status so anyone invoking the old installer sees
# the message rather than silently proceeding.

set -e

cat <<'EOF'
====================================================================
  openspec-beads-worktree/install.sh is obsolete.
  See the comment in this file for the coordinator-based replacement.
====================================================================
EOF

exit 1
