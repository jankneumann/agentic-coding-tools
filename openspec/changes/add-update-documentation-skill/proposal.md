# Add `/update-documentation` Skill

## Why

Documentation in this repo lives in three hand-maintained sources of truth that drift independently:

1. **`README.md`** — public face, written for newcomers
2. **`CLAUDE.md`** — canonical workflow/conventions for contributors and agents
3. **`docs/skills-catalogue.md`** — discoverable skill index, hand-maintained (it says so at line 158)

An audit conducted on branch `claude/update-readme-docs-9cpTs` found severe drift:

- README's "Project Structure" tree listed **10 of 57 actual skill directories**
- README's specs table listed **4 of 21 specs**
- README still described skills as "Claude Code slash commands" even though `skills/install.sh` syncs to `.claude/`, `.agents/` (Codex), `.codex/`, and `.gemini/`
- README's Agent Coordinator section omitted worktree isolation entirely — the central mechanism that makes parallel multi-agent work safe
- CLAUDE.md's "Documentation" section listed **7 of 30+ docs**, omitting foundational references like `docs/parallel-agentic-development.md` (44KB) and `docs/mental-models.md` (40KB)
- `docs/skills-catalogue.md` listed `openspec-coordinator-worktree` (renamed from `openspec-beads-worktree`) but neither the directory nor the README had caught up — eventually removed entirely once Beads was dropped from the project

Pass A (companion commit on this branch) hand-fixes the visible drift. But hand-fixing doesn't solve the underlying problem: there's no skill that owns documentation sync, so every new skill, spec, or doc file adds drift unless a contributor remembers to update three Markdown files in three places.

This proposal adds `/update-documentation` — a skill that mechanically syncs the inventories (skills table, specs table, docs index, project tree) from filesystem reality into generated blocks within `README.md`, `CLAUDE.md`, and `docs/skills-catalogue.md`. Hand-authored prose (intro, "Three Roles", "Getting Started", "Contributing") stays untouched. The skill is wired as a pre-merge gate in `/cleanup-feature` and `/merge-pull-requests`, plus a `.githooks/pre-commit` advisory check, so documentation drift becomes a merge-blocking condition rather than a chore.

## What Changes

### New skill (1)

**`skills/update-documentation/SKILL.md`** — `user_invocable: true`. Operator can invoke `/update-documentation` directly to refresh generated blocks; orchestrators call it as a pre-merge gate.

Behaviour:
1. **Scan `skills/*/SKILL.md`** — extract `name`, `description`, `user_invocable`, `triggers`, `related`, and group/category metadata. Build the master inventory.
2. **Scan `openspec/specs/*/spec.md`** — count `### Requirement:` headers; capture spec title from frontmatter or first H1.
3. **Scan `docs/*.md` and `docs/*/`** — list files and subdirectories with a one-line summary (frontmatter `description:` if present, else first paragraph).
4. **Scan repo root (`ls -d */ .*/`)** — refresh the project-structure tree, filtering by `.gitignore` and a small built-in exclude list.
5. **Render generated blocks** into the three target files between `<!-- GENERATED: begin docs:<block-id> -->` and `<!-- GENERATED: end docs:<block-id> -->` markers. Re-runs are idempotent.
6. **Cross-check** — verify every `/skill-name` mention in `README.md`, `CLAUDE.md`, and `docs/skills-workflow.md` resolves to an actual `skills/<name>/SKILL.md`. Verify every `docs/*.md` link in those files resolves.
7. **Emit a report** — Markdown summary of what changed plus a JSON summary at `docs/architecture-analysis/documentation-sync-report.json` for machine consumption.
8. **Exit-code contract** — `0` if nothing changed; `0` if changes were applied successfully; `2` if `--check` was passed and drift was detected (pre-commit hook mode); `1` on filesystem or parsing errors.

### Generated blocks (introduced in this change)

| Target file | Block ID | Contents |
|---|---|---|
| `README.md` | `docs:project-tree` | Top-level directory tree |
| `README.md` | `docs:specs-table` | Headline specs table |
| `README.md` | `docs:skill-summary` | One-line count + link to skills-catalogue.md (the README does NOT list every skill — that's the catalogue's job) |
| `CLAUDE.md` | `docs:documentation-index` | The "Documentation" section's bullet lists |
| `docs/skills-catalogue.md` | `docs:quick-map-counts` | The "Quick map" group counts |
| `docs/skills-catalogue.md` | `docs:skill-tables` | Per-group skill tables (Feature workflow lifecycle, Roadmap, Quality, Methodology, etc.) |

Hand-authored prose outside the markers is preserved verbatim across re-runs.

### Integration points

- **`.githooks/pre-commit`** — runs `/update-documentation --check` if any file under `skills/`, `openspec/specs/`, or `docs/` was staged. Fails the commit if drift is detected, with a one-line fix instruction (`run /update-documentation`).
- **`.githooks/post-merge`** — runs `/update-documentation` after merges that touched skill/spec/doc files, auto-committing a follow-up sync commit if needed.
- **`/cleanup-feature`** — adds a pre-merge phase that calls `/update-documentation --check`. Drift blocks merge; this is the durable safeguard.
- **`/validate-feature --phase docs`** — new validation phase exposing the same check for manual invocation.
- **`skills-catalogue.md` line 165** — the "future enhancement" note about auto-rendering from `related:` graph is fulfilled by this skill; update the note accordingly.

### Spec delta

Adds a new requirement to `skill-workflow` spec: **Documentation Sync Skill**. The skill must scan the three filesystem sources, render generated blocks idempotently, preserve hand-authored prose, and gate merges via `--check` mode. See `specs/skill-workflow/spec.md` for the full requirement and scenarios.

### Out of scope

- Rewriting hand-authored prose (introductions, "Three Roles", "Getting Started", workflow narrative, conventions in CLAUDE.md). Those stay human-owned.
- Auto-rendering the `related:` skill graph as a visualisation (deferred from D4 of `add-engineering-methodology-skills`).
- Multi-language documentation (English only for now).
- Sync of skill READMEs inside individual `skills/<name>/` directories — that's per-skill maintenance.
- Re-introduction of the `openspec-beads-worktree` / `openspec-coordinator-worktree` skill (removed 2026-05-18, see `docs/decisions/agent-coordinator.md`). The skill stays gone; its functionality lives in `/plan-feature`, `/implement-feature`, and `parallel-infrastructure`.

## Success Criteria

- After running `/update-documentation` once, all three target files contain accurate generated blocks reflecting filesystem reality.
- Running `/update-documentation` a second time with no filesystem changes produces a zero-diff result (idempotency).
- Adding a new skill at `skills/<new-name>/SKILL.md` and committing it without running `/update-documentation` causes the pre-commit hook to block the commit with an actionable message.
- A merge that introduces a new spec under `openspec/specs/` cannot reach main via `/cleanup-feature` until the docs are synced.
- All existing hand-authored prose in README.md and CLAUDE.md is preserved byte-for-byte after the first sync.
