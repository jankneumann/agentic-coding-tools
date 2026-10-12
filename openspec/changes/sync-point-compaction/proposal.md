# Compact at natural sync points, measured on the live window

> Change ID: `sync-point-compaction`
> Effort: S

## Summary

Make compaction phase-aware and bounded at about 200k tokens:

- set `autoCompactWindow: 200000` in the project `.claude/settings.json`, so Claude Code compacts at 200k on its own;
- change the `check_compact.py` Stop hook to request **state capture** at natural sync points once the live window passes 150k, with a 200k backstop;
- measure only the window after the last compaction.

## Why

- **Cost.** Every turn re-sends the whole context, and input above 250k tokens is billed at the long-context rate. Compacting near 200k keeps every turn below that step.
- **The hook mis-measured.** It summed the whole transcript file, which keeps every message from before each compaction. A supervisor session reported "86% of 1M" with a live window of about 80k, and after any compaction the hook would re-request `/compact` on every turn.
- **The hook cannot compact.** Neither the model nor a hook can run `/compact`. Its old "run /compact now" reason stalled unattended sessions waiting for a person. Compaction now comes from `autoCompactWindow`. The hook's job is to make sure that when it lands, state is already committed: checkpoint, roadmap learnings, next steps.
- **Compact at seams, not mid-task.** A sync point (an applied phase handoff, a push, a PR merge or a PR opened) is where the most work is already persisted, so a compaction there loses the least. Below the sync threshold a phase boundary no longer interrupts.

## Acceptance Outcomes

- The hook measures only rows after the last `compact_boundary`.
- At a sync point at or above 15% of `CLAUDE_CONTEXT_LIMIT`, the hook requests state capture. At or above 20% it requests it anywhere. Below 15% it is silent, even at a phase boundary.
- `.claude/settings.json` sets `autoCompactWindow: 200000`.
- All thresholds remain overridable by env: `CLAUDE_CONTEXT_LIMIT`, `CLAUDE_COMPACT_SYNC_PCT`, `CLAUDE_COMPACT_THRESHOLD_PCT`.
