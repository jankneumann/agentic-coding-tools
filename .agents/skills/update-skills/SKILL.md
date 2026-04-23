---
name: update-skills
description: "Sync canonical skills/ into .claude/skills/ and .agents/skills/, regenerate AGENTS.md from CLAUDE.md, commit the regenerated files, and push with rebase-retry."
category: Infrastructure
tags: [skills, sync, install, agents-md, pre-commit, infrastructure]
triggers:
  - "update skills"
  - "update-skills"
  - "sync skills"
  - "sync runtime skills"
  - "regenerate agents.md"
---

# Update Skills

Orchestrates the four-step sync loop that keeps the runtime skill copies and `AGENTS.md` in lockstep with the canonical sources.

## What this skill does

1. **Propagates** canonical `skills/<name>/` edits into `.claude/skills/<name>/` (for Claude Code) and `.agents/skills/<name>/` (for Codex) via `skills/install.sh`.
2. **Regenerates** `AGENTS.md` as a byte-identical copy of `CLAUDE.md` so Codex gets the same project context Claude Code does.
3. **Commits** the regenerated files with `chore(skills): sync runtime copies` — unless the staged diff is empty, in which case nothing is committed (no empty commits).
4. **Pushes** to `origin <current-branch>`, doing `git pull --rebase --autostash` on rejection and retrying up to 3 total attempts.

The invariant `CLAUDE.md ≡ AGENTS.md` is additionally enforced by a pre-commit hook (install via `./install-hooks.sh` once per clone) so the rule holds even when this skill is forgotten.

## When to run

- After editing any file under `skills/` (canonical source).
- After editing `CLAUDE.md` (which must propagate to `AGENTS.md`).
- Before opening a PR that modifies either, to ensure runtime directories and `AGENTS.md` are up to date on the remote.

## Usage

```bash
python3 skills/update-skills/scripts/update_skills.py
```

Or invoke via the skill trigger: "update skills" / "sync skills".

## Scripts

- `scripts/sync_agents_md.py` — Regenerates `AGENTS.md` from `CLAUDE.md`. Standalone tool; used by this skill and by the pre-commit hook in `--check` mode. Exit codes: 0 success, 1 missing `CLAUDE.md`, 2 drift (`--check` only).
- `scripts/update_skills.py` — The four-step orchestrator. Exit codes: 0 success (including no-op), 1 any step failed or push retry exhausted. On retry exhaustion, emits `UNPUSHED_COMMIT=<sha>` to stdout for automation.

## Related

- **`.pre-commit-config.yaml`** at repo root declares the `agents-md-sync` hook that runs `sync_agents_md.py --check`.
- **`install-hooks.sh`** at repo root installs pre-commit into `skills/.venv/` and wires the git hook.
- **`skills/session-bootstrap/scripts/hooks/auto_pull.py`** is the opt-in SessionStart auto-pull helper (`AGENTIC_AUTO_PULL=1`).

## Tests

```bash
skills/.venv/bin/python -m pytest skills/tests/update-skills/ -v
```
