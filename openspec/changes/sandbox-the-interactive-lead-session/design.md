# Design: sandbox the interactive lead session

## Context

`.claude/settings.json` has no `sandbox` key. Bash commands in the lead session
run unsandboxed and are approved by a long allow list. A PreToolUse hook,
`irreversible_guard.py`, already denies or prompts for irreversible commands
and is kept in step with `agent-coordinator/src/guardrails.py` by tests.
`skills/shared/environment_profile.py` already detects provided isolation.

Facts about the harness sandbox come from its documentation, read through a
summarising fetch tool. Items marked **[unverified]** were not seen verbatim
and are checked by the probe or the guide's checklist on the operator's hosts.

## Goals / Non-Goals

Goals: no prompt for sandboxed development commands; credential and
sibling-checkout reads refused; irreversible classes still gated; shorter
allow list; no regression in cloud sessions.

Non-goals: sandboxing dispatched vendor CLIs (ri-03, ri-05, dg-07);
sandboxing hooks, MCP servers or the Read/Edit tools, which the native sandbox
does not cover; changing `defaultMode`; changing `irreversible_guard.py`.

## Decisions

**D1. Configuration lives in project-shared settings.** Documentation states
project settings may set `enabled`, `autoAllowBashIfSandboxed`, `denyRead`,
`allowWrite`, `allowedDomains` and `excludedCommands`; they are ignored only
when managed settings make the sandbox admin-required. Rejected: user-level
settings (unversioned, untestable).

**D2. `failIfUnavailable` and `allowUnsandboxedCommands` keep their defaults.**
On a host without `bubblewrap`/`socat`, or in the cloud container, commands
run unsandboxed and the permission rules decide them. Because D5 removes the
broad allow rules, that fallback prompts rather than running freely: the
failure direction is more prompts, not less control. Setting
`allowUnsandboxedCommands: false` was rejected: vendor dispatch from the lead
session would fail outright, and whether a project-level `false` is honoured
is not stated.

**D3. Read denial.** `denyRead`: `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.netrc`,
`~/.kube`, `~/.docker`, `~/.config/gh`, `~/.config/gcloud`,
`~/.claude/.credentials.json`, `~/.codex`, and `..` (the directory holding the
checkout). `allowRead`: `.`. `~/.config` as a whole is not denied because uv
and git read configuration there; `~/.claude` as a whole is not denied because
skills read transcripts from it. Vendor credential paths beyond `~/.codex` are
added by ri-03 after the ri-02 audit. **[unverified]** that `allowRead` takes
precedence over a `denyRead` parent given as a relative path. If it does not,
sandboxed commands cannot read the checkout, every command falls back to a
prompt, and the probe's `project_readable` check fails; the remedy is to drop
`..` and record the sibling-checkout outcome as unmet.

**D4. Outward commands leave the sandbox; git hosts stay off the allowlist.**
`excludedCommands`: `git push *`, `git fetch *`, `git pull *`, `gh *`,
`railway *`, `docker *`. Excluded commands go through the normal permission
flow, so the existing `git push` allow, ask and deny rules keep their meaning.
`allowedDomains`: `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`,
`coord.rotkohl.ai`. `excludedCommands` matches on the command text and is not
a boundary by itself; the boundary is that `github.com` is absent from the
allowlist, so `bash -c 'git push …'` inside the sandbox cannot connect.
`git fetch *` and `git pull *` are added to `allow`.

**D5. The allow list loses readers and interpreters.** A rule such as
`Bash(cat *)` or `Bash(uv run *)` approves the command when it is retried with
the sandbox disabled, which defeats D3. Removed: read commands, `uv run *`,
`pytest *`, venv pytest paths, all `runner.py` variants, the `bash …railway-vars`
rule. Kept: WebFetch domains, git log/status/diff/show/branch/add/commit, the
`git push` rules. Observed in this cloud session: commands outside the allow
list ran without prompts, so cloud sessions do not depend on the list.

**D6. The hook stays the second layer.** No change to `irreversible_guard.py`.
The new test asserts agreement: each irreversible class is covered by a deny
rule, a content-scoped ask rule or a guard verdict. **[unverified]** that a
hook `ask` verdict prompts for a command the sandbox would auto-allow; it is
on the guide's checklist. Deny (exit 2) is independent of permission flow.

**D7. Cloud skip is detection plus fallback, not a second settings file.**
The harness skips wrapping where prerequisites are missing (D2). The probe
calls `environment_profile.detect()` and reports `skipped` when isolation is
provided. Rejected: a SessionStart hook writing `settings.local.json` in the
cloud, since local settings are reportedly not read there.

**D8. The probe reads its targets from the settings file** and prints paths
and verdicts only. Checks: each `denyRead` entry that exists on the host; a
sibling of the project root; project root readable; write outside the project
and temp directories refused; TCP connect to `github.com:443` refused. Exit
non-zero on any `not_enforced`. Standard library only.

**D9. `allowLocalBinding: true`** so test suites that bind a localhost port
run sandboxed. macOS only per documentation; ignored elsewhere.

**D10. Gate recording gets an explicit ask rule.** Added during
implementation. The removed allow list covered six `runner.py` subcommands
and left `gate-answer` out, so recording a gate approval prompted only because
nothing allowed it. Under auto-allow that omission gates nothing: the command
writes project files and would run sandboxed without a prompt. Ask rules
`*runner.py* gate-answer*` and `*cycle_state.py* gate-answer*` restore the
prompt. `relayed-gate-answer` was allowed before and stays promptless; the
pattern requires a space before `gate-answer` so it does not match. A wrapper
such as `bash -c` or a renamed copy of the script evades the pattern, as it
evaded the old allow-list gate; the durable control is the approval-gate
service, not this rule.

**D11. Hook gaps are closed with ask rules, not hook changes.** The guard
returns no verdict for `alembic upgrade` reached through `uv run` or
`python -m`, `gh secret set`, `gh api … merge` and `git branch -D`. Ask rules
`*alembic upgrade*`, `*alembic downgrade*`, `gh secret *`, `gh api *merge*`
and `git branch -D *` cover them. `irreversible_guard.py` is unchanged because
it is kept in step with `agent-coordinator/src/guardrails.py` by tests and
that pairing is outside this change.

## Risks

| Risk | Mitigation |
|---|---|
| Sandbox semantics differ from the summarised documentation | Probe and checklist on first local session; rollback is `{"sandbox": {"enabled": false}}` in `.claude/settings.local.json` |
| A tool needs a cache path not in `allowWrite` | Command fails inside the sandbox, falls back to a prompt; add the path |
| Vendor dispatch from the lead session prompts | Accepted until ri-03/ri-05; stated in the guide |
| Overlap with `add-isolation-posture-detection`, which changes `environment_profile` | This change only calls `detect()` and reads `isolation_provided`/`source` |

## Verification on the operator's hosts

Not executable in CI. The guide lists: run the probe via the Bash tool; run
`uv run --project skills pytest -q` and `git status` and confirm no prompt;
run `alembic --help` and confirm a prompt; ask for `git push origin main`
and confirm a prompt.
