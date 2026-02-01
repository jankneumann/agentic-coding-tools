# Change: Add merge-pull-requests skill

## Why

Projects using multiple AI agents (Claude, Jules, Codex) accumulate open PRs from different sources with different conventions. Some PRs are OpenSpec-driven, others come from automated tools (Jules Sentinel for security, Bolt for performance, Palette for UX). Reviewing and merging these PRs requires:
1. Understanding each PR's origin and purpose
2. Checking whether automated fixes are still relevant given intervening changes
3. Addressing review comments on OpenSpec PRs
4. Safely merging in dependency order

There's currently no skill to orchestrate this PR triage-and-merge workflow.

## What Changes

- **New skill**: `skills/merge-pull-requests/SKILL.md` - Claude Code skill for PR triage and merge
- **New Python helper scripts** in `skills/merge-pull-requests/scripts/`:
  - `discover_prs.py` - List open PRs with classification (OpenSpec, Jules/Sentinel/Bolt/Palette, Codex, other)
  - `check_staleness.py` - Compare PR diff against current main to detect stale/conflicting fixes
  - `analyze_comments.py` - Extract and summarize unresolved PR review comments
  - `merge_pr.py` - Merge a single PR with pre-merge validation

## Impact

- Affected specs: None (new capability)
- Affected code: `skills/merge-pull-requests/` (new directory)
- No breaking changes
