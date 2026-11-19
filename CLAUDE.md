# Claude Code Instructions

Project guidelines live in `AGENTS.md` and are imported below. Edit **`AGENTS.md`**
for anything general; this file is only for guidance specific to Claude Code.

Until 2026-09-08 `AGENTS.md` was a symlink *to* this file, which meant anything
written here also appeared as project-wide guidance to every other agent. The
direction is now inverted so that Claude-specific notes can exist without leaking
into the shared instructions.

@AGENTS.md

## Claude-Code-Specific Notes

Add an item only when it is genuinely Claude-Code-specific: harness behaviour,
tool affordances, slash commands. Anything that would also apply to another
agent belongs in `AGENTS.md`.

### Write Bash commands that permission rules can match

`.claude/settings.json` turns on the Bash sandbox with auto-allow. On a host
where the sandbox is active, sandboxed commands need no allow rule: they run
without a prompt inside the checkout, with credential directories and sibling
checkouts unreadable and the network limited to the package registries and the
coordinator. Setup, verification and rollback are in
[docs/guides/lead-session-sandbox.md](docs/guides/lead-session-sandbox.md).

Three kinds of command still go through the permission rules:

- **Excluded commands** run outside the sandbox because they need credentials
  or a host the sandbox cannot reach: `git push`, `git fetch`, `git pull`,
  `gh`, `railway`, `docker`. The `git push`, `git fetch` and `git pull` allow
  rules decide whether they prompt. Do not wrap them (`bash -c 'git push …'`):
  the wrapped form runs sandboxed and cannot connect.
- **Ask and deny rules apply even to sandboxed commands.** `Bash(env *)`,
  `Bash(alembic *)`, `Bash(psql *)` and the gate-recording rules prompt; the
  deny rules refuse.
- **Everything, when the sandbox is not active** (no `bubblewrap`/`socat`, or
  switched off locally). The allow list no longer holds readers, interpreters
  or test runners, so those commands prompt there. Cloud sessions are
  unaffected.

Rules match on how each `;`/`&&`/`|` segment starts, so keep the start
predictable:

- **No `env` prefix.** Not `env -u VIRTUAL_ENV …`, not `env FOO=bar …`; it
  matches the ask rule and prompts every time. The harness shell often inherits
  `VIRTUAL_ENV=agent-coordinator/.venv`; let uv handle it instead.
  `uv run --project <dir> <cmd>` ignores the stale value and passes the project
  venv's `VIRTUAL_ENV`/`PATH` to the child process. `uv sync --project <dir>`
  needs nothing extra.
- **A venv interpreter called by path needs no unset.**
  `skills/.venv/bin/python -m pytest …` picks its interpreter from the path, not
  from `VIRTUAL_ENV`.
- **No interpreter aliases.** `PY=…; $PY -m pytest` starts with an unexpanded
  variable, so no excluded-command or allow rule can match it. Write the path
  out in every segment.
- **No `cd` partway through a chain.** Run from the checkout or worktree root
  with root-relative paths.
- **Use the worktree's own venv** (`uv sync --project skills` once), not
  `../../../skills/.venv` from the main checkout: it may import the main
  checkout's code, and the sandbox cannot read a sibling checkout.
