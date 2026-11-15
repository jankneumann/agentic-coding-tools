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

`.claude/settings.json` puts `Bash(env *)` under `ask`. Ask beats allow
regardless of how specific the allow rule is. Allow rules match on how each
`;`/`&&`/`|` segment starts, so write commands whose start is predictable:

- **No `env` prefix.** Not `env -u VIRTUAL_ENV …`, not `env FOO=bar …`. The
  harness shell often inherits `VIRTUAL_ENV=agent-coordinator/.venv`; let uv
  handle it instead. `uv run --project <dir> <cmd>` ignores the stale value and
  passes the project venv's `VIRTUAL_ENV`/`PATH` to the child process.
  `uv sync --project <dir>` needs nothing extra.
- **A venv interpreter called by path needs no unset.**
  `skills/.venv/bin/python -m pytest …` picks its interpreter from the path, not
  from `VIRTUAL_ENV`.
- **No interpreter aliases.** `PY=…; $PY -m pytest` starts with an unexpanded
  variable and cannot match any rule. Write the path out in every segment.
- **No `cd` partway through a chain.** Run from the checkout or worktree root
  with root-relative paths.
- **Use the worktree's own venv** (`uv sync --project skills` once), not
  `../../../skills/.venv` from the main checkout, which may import the main
  checkout's code.
