# Tasks — add-update-skills

## Phase 1 — Sync script (foundation)

- [x] 1.1 Write tests for `sync_agents_md.py` covering regenerate mode, check mode (in-sync and drift), and missing-source error
  **Spec scenarios**: skill-runtime-sync.6 (regenerate), .7 (check drift), .8 (check in-sync), .9 (missing source)
  **Contracts**: contracts/README.md (no machine-readable contracts; pure-stdlib script)
  **Dependencies**: None
- [x] 1.2 Implement `skills/update-skills/scripts/sync_agents_md.py` (pure-stdlib Python; argparse for `--check` flag; exits 0/1/2 per spec)
  **Dependencies**: 1.1

## Phase 2 — Pre-commit hook for invariant (uses pre-commit framework)

- [x] 2.1 Write integration test that simulates a pre-commit context: stage a CLAUDE.md edit without AGENTS.md, invoke the hook entry, assert non-zero exit and instructive message
  **Spec scenarios**: skill-runtime-sync.4 (drift rejection), .5 (in-sync pass)
  **Dependencies**: 1.2
- [x] 2.2 Add `.pre-commit-config.yaml` at repo root with a single `local` hook that runs `python3 skills/update-skills/scripts/sync_agents_md.py --check` on every commit. Hook id: `agents-md-sync`. Files filter: `^(CLAUDE\.md|AGENTS\.md)$`
  **Dependencies**: 2.1
- [x] 2.3 Add `pre-commit` to `skills/pyproject.toml` under the `dev` optional-dependency group. Add `install-hooks.sh` at repo root that: (1) runs `cd skills && uv sync --all-extras` to install the now-pinned pre-commit into `skills/.venv/`, (2) runs `skills/.venv/bin/pre-commit install` to wire `.git/hooks/pre-commit`. Idempotent (safe to re-run — uv sync is a no-op when in-sync; pre-commit install overwrites harmlessly). Document invocation in CLAUDE.md "Skills" section.
  **Dependencies**: 2.2
  **Spec scenarios**: skill-runtime-sync.g (install-hooks idempotent), .h (install-hooks missing uv)

## Phase 3 — `/update-skills` orchestrator

- [ ] 3.1 Write tests for `update_skills.py` covering: install.sh invocation, sync_agents_md.py invocation, no-op when nothing changed (no commit), commit message format, push retry on rejection (mock git), retry exhaustion failure
  **Spec scenarios**: skill-runtime-sync.1 (propagation), .2 (no-op), .3 (commit message), .a (push success), .b (push retry), .c (retry exhausted)
  **Dependencies**: 1.2
- [ ] 3.2 Implement `skills/update-skills/scripts/update_skills.py` orchestrator (calls install.sh via subprocess, calls sync_agents_md.py, stages files, checks empty diff, commits with conventional message, pushes with rebase + bounded retry)
  **Dependencies**: 3.1
- [ ] 3.3 Write `skills/update-skills/SKILL.md` (frontmatter with `name`, `description`, `category: Infrastructure`, `tags`, `triggers: ["update skills", "sync skills", "update-skills"]`; usage section; pointer to scripts)
  **Dependencies**: 3.2

## Phase 4 — Opt-in SessionStart auto-pull hook

- [ ] 4.1 Write tests for the SessionStart hook script covering: disabled (env unset), enabled + clean tree (pull invoked), enabled + dirty tree (pull skipped), enabled + network failure (silent exit 0)
  **Spec scenarios**: skill-runtime-sync.d (auto-pull clean), .e (auto-pull dirty), .f (auto-pull disabled)
  **Dependencies**: None (parallel with Phase 3)
- [ ] 4.2 Implement `skills/session-bootstrap/scripts/hooks/auto_pull.py` (gated by `AGENTIC_AUTO_PULL=1`, dirty-tree check via `git status --porcelain`, subprocess `git pull --rebase --autostash`, exit 0 on any failure)
  **Dependencies**: 4.1
- [ ] 4.3 Wire the auto-pull hook for both runtimes. (a) Add an entry to `.claude/settings.json` SessionStart hooks block (after existing `bootstrap-cloud.sh`, `print_coordinator_env.py`, `register_agent.py` entries) invoking `python3 "$CLAUDE_PROJECT_DIR/.claude/skills/session-bootstrap/scripts/hooks/auto_pull.py"`. (b) Add an invocation of the same `auto_pull.py` to `skills/session-bootstrap/scripts/bootstrap-cloud.sh` (the Codex Maintenance Script entry point), placed after the existing verify/repair logic so a broken repo doesn't block auto-pull diagnostics. Both invocations are gated by `AGENTIC_AUTO_PULL=1` inside `auto_pull.py` itself, so the wiring is unconditional but the behavior is opt-in.
  **Dependencies**: 4.2
  **Spec scenarios**: skill-runtime-sync.d (auto-pull clean), .e (auto-pull dirty), .f (auto-pull disabled), .i (both runtimes covered)

## Phase 5 — Documentation and initial generation

- [ ] 5.1 Update `CLAUDE.md` with a "Generated AGENTS.md" subsection under "Skills" documenting the invariant, the pre-commit hook, and the opt-in `AGENTIC_AUTO_PULL` env var
  **Dependencies**: 3.3, 4.3
- [ ] 5.2 Run `python3 skills/update-skills/scripts/sync_agents_md.py` to generate the initial `AGENTS.md` (will be byte-identical to the updated CLAUDE.md)
  **Dependencies**: 5.1
- [ ] 5.3 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to propagate the new `update-skills` skill into `.claude/skills/` and `.agents/skills/`
  **Dependencies**: 3.3
- [ ] 5.4 Smoke test: run `/update-skills` end-to-end on the feature branch — expect a no-op exit (everything already committed and pushed during normal workflow)
  **Dependencies**: 5.2, 5.3

## Phase 6 — Verification

- [ ] 6.1 Run full skill test suite: `skills/.venv/bin/python -m pytest skills/tests/update-skills/ -v`
  **Dependencies**: All phases
- [ ] 6.2 Run `openspec validate add-update-skills --strict`
  **Dependencies**: All phases
