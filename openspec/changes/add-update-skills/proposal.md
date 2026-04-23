# Proposal — add-update-skills

## Why

Today, edits to canonical `skills/` don't reach `.claude/skills/` or `.agents/skills/` until someone runs `bash skills/install.sh` manually. The runtime copies aren't automatically committed or pushed, so agent-discovery state can silently lag the source-of-truth. Compounding this, `AGENTS.md` at repo root is empty, which means Codex (which uses `AGENTS.md` as its canonical project-context file) has no project guidance — Claude Code reads `CLAUDE.md` and gets full guidance, Codex reads `AGENTS.md` and gets nothing.

This change closes both gaps with a single skill (`/update-skills`) and one supporting invariant (`CLAUDE.md ≡ AGENTS.md`). It is prerequisite plumbing for the follow-on `add-skillify-and-resolver-audit` change — without a reliable sync+commit+push loop, skillify-generated skills wouldn't reach the runtime directories.

Roadmap: `openspec/roadmaps/skillify-foundation/roadmap.yaml` item `ri-01`.

## What Changes

- **New skill** `skills/update-skills/SKILL.md` orchestrating the four-step sync loop:
  1. Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to refresh `.claude/skills/` and `.agents/skills/` from canonical `skills/`.
  2. Run `sync-agents-md.py` to regenerate `AGENTS.md` from `CLAUDE.md`.
  3. Stage regenerated runtime files + `AGENTS.md`. If staged diff is empty, skip commit (no empty commits). Otherwise commit with `chore(skills): sync runtime copies`.
  4. `git pull --rebase --autostash` then `git push` with bounded retry (max 3 attempts, exponential backoff) to handle concurrent updates.
- **New script** `skills/update-skills/scripts/sync_agents_md.py` — pure-stdlib Python that copies `CLAUDE.md` → `AGENTS.md`, exits `0` on success, `1` on missing source, `2` on byte-drift when run with `--check`.
- **New pre-commit hook** wired through the standard [pre-commit framework](https://pre-commit.com/) via a new `.pre-commit-config.yaml` at repo root. The hook is a `local` entry that runs `python3 skills/update-skills/scripts/sync_agents_md.py --check` on every commit and fails the commit if `CLAUDE.md` and `AGENTS.md` have drifted. Enforces the invariant independently of `/update-skills`.
- **New `install-hooks.sh`** at repo root that bootstraps the pre-commit framework (`uv pip install pre-commit` into the project venv, then `pre-commit install`). Separate from `skills/install.sh` so the hooks setup is invoked deliberately and doesn't surprise users who only want to install skills.
- **Optional SessionStart hook** wired in `.claude/settings.json` and the Codex equivalent: invokes `git pull --rebase --autostash` on the current branch when `AGENTIC_AUTO_PULL=1` is set, no-ops on dirty trees, silent on network failure (exit 0).
- **CLAUDE.md update**: add a "Generated AGENTS.md" subsection under "Skills" documenting the invariant and the pre-commit hook.
- **Initial generation**: run the new `sync_agents_md.py` once as part of this change to populate `AGENTS.md`.

## Impact

- **Affected specs**: new `skill-runtime-sync` capability (this change introduces it). No modifications to existing `skill-workflow` or `skill-consolidation` specs.
- **Affected code**:
  - new: `skills/update-skills/SKILL.md`, `skills/update-skills/scripts/sync_agents_md.py`, `skills/update-skills/scripts/update_skills.py`
  - new: `skills/tests/update-skills/` test files
  - new: `.pre-commit-config.yaml` (root) with the AGENTS.md sync check as a `local` hook
  - new: `install-hooks.sh` (root) that bootstraps pre-commit and runs `pre-commit install`
  - modified: `.claude/settings.json` (add SessionStart hook entry, gated by env)
  - modified: `CLAUDE.md` (add "Generated AGENTS.md" section, document `install-hooks.sh`)
  - generated: `AGENTS.md` (byte-identical to CLAUDE.md)
- **Operational risk**:
  - Auto-push could race with concurrent updates — mitigated by `git pull --rebase` immediately before push and bounded retry.
  - Auto-pull at SessionStart is opt-in only (`AGENTIC_AUTO_PULL=1`); default behavior is unchanged.
  - Pre-commit hook adds <50ms to commit time (single file copy + diff); negligible.

## Approaches Considered

### Approach 1 — Single skill that wraps install.sh + AGENTS.md generation + commit + push (Recommended)

**Description**: One skill (`/update-skills`) with a Python orchestrator that calls `install.sh`, runs the AGENTS.md generator, stages, commits if non-empty, and pushes with retry. Pre-commit hook enforces the AGENTS.md invariant independently. SessionStart auto-pull is a separate, opt-in hook.

**Pros**:
- Single entry point matches user's mental model ("run `/update-skills`").
- Pre-commit hook makes the invariant robust even if `/update-skills` is forgotten.
- Opt-in SessionStart pull respects user autonomy on dirty/feature-branch workflows.

**Cons**:
- Adds a new skill (one more thing to maintain).
- Auto-push race window is non-zero, even with rebase + retry.

**Effort**: S

### Approach 2 — Pre-commit hook only, no skill

**Description**: Just install a pre-commit hook that runs `install.sh` and `sync_agents_md.py` on every commit. No new skill.

**Pros**: No new skill; everything happens automatically on commit.

**Cons**:
- Pre-commit on every commit is heavy (`install.sh` rsync takes ~1s); rejected.
- Doesn't solve the "push after sync" gap — still requires manual push.
- Doesn't help skillify (Change B) which needs a programmatic way to trigger the full loop.

**Effort**: XS, but rejected on UX.

### Approach 3 — Make install.sh self-syncing (auto-commit + auto-push inside install.sh)

**Description**: Modify `skills/install.sh` directly to commit and push when changes are made.

**Pros**: No new skill, no new file.

**Cons**:
- Violates "no changes to existing install.sh behavior" non-goal.
- Couples installation (which may run on a fresh clone with no remote) to git operations.
- Hard to make conditional/opt-in; surprises users running install.sh in unusual contexts.

**Effort**: XS, but rejected on architectural grounds.

## Selected Approach

**Approach 1** — single `/update-skills` skill with separate pre-commit hook for the invariant and a separate opt-in SessionStart hook for auto-pull. This separates concerns cleanly: the skill is the user-facing operation, the pre-commit hook is the safety net, the SessionStart hook is freshness.
