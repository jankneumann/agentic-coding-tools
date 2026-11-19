# Sandbox the interactive lead session

> Parent roadmap: `sandboxed-flow`
> Change ID: `sandbox-the-interactive-lead-session`
> Effort: M
> Priority: 1

## Summary

Enable the harness's native Bash sandbox for the operator's interactive Claude Code sessions on the laptop and the GX10 so sandboxed commands run without asking, and reduce the permission rules to the irreversible set (force-push, deletion, merge, deploy, migration, secret writes), which keeps ask or deny. Setting names are confirmed against current harness documentation before they are written.

## Dependencies

- None

## Acceptance Outcomes

- A local interactive session runs uv run, pytest, git read commands and worktree-scoped writes with no approval prompt.
- A sandboxed command cannot read ~/.ssh, ~/.aws or another repository's checkout; a test demonstrates the denial.
- Every command class in the irreversible set still prompts or is denied, verified by a test that enumerates the set.
- The allow list in .claude/settings.json shrinks, and the guide on writing matchable Bash commands is updated to match.
- Under the managed cloud harness, which provides its own sandbox and proxy, local sandbox wrapping is detected as unnecessary and skipped.

## Rationale

Most approval prompts occur in the interactive lead session, which is not a dispatched vendor CLI and so is not covered by dispatch-governance dg-07. This item has no dependencies and delivers relief before anything else lands.
