# Add headless mode to merge-pull-requests

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `add-headless-mode-to-merge-pull-requests`
> Effort: L
> Priority: 2

## Summary

A non-interactive mode consuming /expedite's READY/BLOCKED verdict, triaging with the existing classification scripts, merging only PRs that are Fresh, CI-green, validation-gated, and within the posture's auto-merge ceiling, and notifying-with-veto-window for everything else, reusing the --pipeline post-merge machinery.

## Dependencies

- `ri-05`
- `ri-11`

## Acceptance Outcomes

- A scheduled run merges qualifying PRs end-to-end with zero prompts and posts a merge-log digest notification.
- A PR outside the auto-merge ceiling is never merged unattended and produces an approval request instead.
- An induced main-CI failure after an unattended merge triggers the existing auto-rollback path.

## Rationale

Scheduled merge sync points need an execution path with zero prompts; the existing auto-rebase and 15-minute rollback monitor make unattended merging recoverable.
