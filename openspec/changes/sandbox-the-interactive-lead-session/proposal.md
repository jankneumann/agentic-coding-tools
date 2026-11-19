# Sandbox the interactive lead session

> Parent roadmap: `sandboxed-flow`
> Change ID: `sandbox-the-interactive-lead-session`
> Effort: M
> Priority: 1

## Why

Most approval prompts occur in the operator's interactive Claude Code session
on the laptop and the GX10. That session is not a dispatched vendor CLI, so
none of the dispatch-sandbox changes (`add-dispatch-sandbox-enforcement`,
`add-sandboxed-harness-execution`) reach it. Today its Bash commands run
unsandboxed, and friction is managed with a long `permissions.allow` list in
`.claude/settings.json`: about fifty `runner.py` variants, `uv run *`,
`pytest *` and general readers such as `cat *` and `grep *`. Each of those is
both a maintenance burden and an unsandboxed grant.

The harness has a native Bash sandbox. With it on and auto-allow set, a
command that runs inside the sandbox needs no prompt; deny rules,
content-scoped ask rules and PreToolUse hooks still apply. The irreversible
classifier already exists (`irreversible_guard.py`). The missing piece is the
sandbox layer its own docstring says "comes first".

## What Changes

- Add a `sandbox` block to `.claude/settings.json`: enabled, auto-allow for
  sandboxed Bash, credential and sibling-checkout read denial, a short network
  allowlist, write grants for the uv and npm caches.
- Keep outward commands (`git push`, `git fetch`, `git pull`, `gh`, `railway`,
  `docker`) out of the sandbox through `excludedCommands`, and keep git remote
  hosts out of `allowedDomains`, so they run only through the existing
  permission rules.
- Shrink `permissions.allow`: remove every rule that grants a general reader
  or an interpreter (`cat`, `grep`, `find`, `uv run`, `pytest`, the
  `runner.py` variants). Keep `ask` and `deny` as they are.
- Add `sandbox_probe.py` to `session-bootstrap`: run from a local session, it
  attempts the reads, writes and connections the sandbox must refuse and
  reports each as enforced or not. Under the cloud harness it reports
  `skipped`.
- Add tests that parse the real settings file and enumerate the irreversible
  set.
- Replace the "matchable Bash commands" section of `CLAUDE.md` and add
  `docs/guides/lead-session-sandbox.md` (prerequisites, probe, rollback).

## Assumptions

This item was approved by the operator in the roadmap, and `/autopilot-roadmap`
dispatched this plan, so the discovery questions were not asked. These are the
choices made in their place:

1. Configuration ships in the project-shared settings file, so it applies to
   every checkout and worktree of this repository on both hosts.
2. A host without the sandbox prerequisites keeps working, unsandboxed, with
   prompts. The change does not set `failIfUnavailable`.
3. Vendor CLI dispatch from the lead session (codex, antigravity, grok) is not
   solved here. Those subprocesses need vendor credentials and network the
   sandbox denies, so a dispatch runs unsandboxed and prompts once. ri-03 and
   ri-05 own that.
4. `permissions.defaultMode: "auto"` is left alone. The harness documentation
   reportedly says `auto` has no effect from project settings; the guide tells
   the operator where to set it.

## Approaches Considered

### A. Project-shared sandbox block, allow list reduced to non-readers (Recommended)

`sandbox` in `.claude/settings.json`; outward commands excluded from the
sandbox and gated by the existing rules; readers and interpreters removed from
`allow`.

- Pros: one file, versioned, same on both hosts and in every worktree;
  removes the unsandboxed bypass that reader allow rules create; reuses the
  existing hook and deny rules.
- Cons: sandbox enforcement cannot be exercised in CI or the cloud container,
  only by the probe on the operator's hosts; relative `denyRead` semantics
  need confirming there.
- Effort: M

### B. User-level settings only (`~/.claude/settings.json` on each host)

- Pros: absolute paths can be used for sibling checkouts; no effect on other
  contributors.
- Cons: not versioned, drifts between laptop and GX10, cannot be tested from
  the repository, and the project allow list would still carry the bypass.
- Effort: S

### C. Wrapper that launches the whole harness inside a container or `bwrap`

- Pros: covers hooks, MCP servers and file tools, which the native sandbox
  does not.
- Cons: the subscription login would have to be bound into the container,
  which `claude-auth-strategy.md` rule 1 forbids; breaks IDE and keychain
  integration; large. This is what the dispatch-sandbox items do for workers.
- Effort: L

## Selected Approach

A. It delivers the prompt relief with the smallest change and leaves the
operator a one-line rollback (`"sandbox": {"enabled": false}` in
`.claude/settings.local.json`).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by |
|---|---|---|---|
| Operability | Approval prompts for `uv run`, `pytest`, git read commands in a sandboxed local session | 0 | Operator run of the guide's checklist |
| Security | Probe checks reported `enforced` on a sandboxed host | all | `sandbox_probe.py` on laptop and GX10 |
| Maintainability | Entries in `permissions.allow` | fewer than half the current count | settings test |

## Impact

- Affected spec: `harness-engineering`
- Affected files: `.claude/settings.json`, `CLAUDE.md`,
  `docs/guides/lead-session-sandbox.md`,
  `skills/session-bootstrap/scripts/sandbox_probe.py`,
  `skills/tests/session-bootstrap/`
- Not verifiable in this change's CI: that the OS sandbox denies the reads.
  The probe exists so the operator can verify it in one command.

## Dependencies

- None
