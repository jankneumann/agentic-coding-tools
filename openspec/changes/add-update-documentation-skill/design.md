# Design: `/update-documentation`

## Context

Three sources of truth (README.md, CLAUDE.md, docs/skills-catalogue.md) drift because no skill owns the sync. The audit on `claude/update-readme-docs-9cpTs` found 42 of 52 skills missing from the README and 18 of 30 docs missing from CLAUDE.md's index. Pass A hand-fixes the visible drift; this skill prevents recurrence.

The closest existing pattern is `coordinator-task-status-renderer` (CLAUDE.md:37): it renders a coordinator-owned status block between `<!-- GENERATED: begin ... -->` / `end` markers inside `openspec/changes/<id>/tasks.md`, wired into `.githooks/pre-commit` and `.githooks/post-merge`. This skill mirrors that pattern at the repo-doc level rather than the per-change level.

## Key Design Decisions

### D1: Generator with markers, not full file regeneration

**Decision**: Insert generated content between `<!-- GENERATED: begin docs:<block-id> -->` and `<!-- GENERATED: end docs:<block-id> -->` HTML comment markers. Hand-authored prose outside markers is preserved verbatim.

**Why**: Full-file regeneration would erase narrative voice (the README's "bottleneck is human attention" opener, CLAUDE.md's worktree contract, the catalogue's "How to find what you need" tail). Hand-authored prose has *intent* the generator cannot reproduce. Markers let the generator own the mechanical bits and humans own the prose.

**Alternative considered**: Jinja2 templates with the README as a template file. Rejected because it forces every contributor who edits prose to also understand the templating language, and because narrative changes would all become PRs against the template, hiding the actual prose diffs.

**Trade-off**: Contributors must edit prose *outside* the markers. The skill rejects edits that move marker positions in a way that would orphan content.

### D2: Filesystem is the source of truth

**Decision**: All generated content is derived from filesystem state at sync time. No separate manifest file is maintained.

**Why**: A manifest would itself drift. Filesystem state is what `install.sh` reads, what skill discovery enumerates, and what `git diff` shows; deriving from it means the documentation can't be wrong without the codebase also being wrong.

**Trade-off**: Skill description quality depends on `SKILL.md` frontmatter `description` field quality. Skills with poor descriptions produce poor catalogue entries. Mitigation: the skill warns when frontmatter is missing or too short (< 20 chars).

### D3: Two-tier `--check` mode

**Decision**: Default invocation writes changes to disk. `--check` mode (used by pre-commit) computes the diff in memory and exits non-zero if changes would be made, without writing anything.

**Why**: Pre-commit hooks must not modify files mid-commit (it confuses git and the user). Hooks need a pure "would this be clean?" signal. The CLI invocation needs to actually fix things.

**Trade-off**: Two code paths to maintain. Mitigated by sharing the rendering function and only branching at the write step.

### D4: Three-target sync vs single-file generator

**Decision**: One skill writes to all three targets (README.md, CLAUDE.md, docs/skills-catalogue.md). Each target gets its own block IDs.

**Why**: Splitting into three skills (`update-readme`, `update-claude-md`, `update-catalogue`) would triple the orchestration cost and create ordering questions (does CLAUDE.md depend on the catalogue?). One skill, one scan, multiple writes is simpler.

**Trade-off**: Single skill must understand three different file structures. Mitigated by per-target renderer functions and per-block tests.

### D5: Exit-code semantics for hook integration

**Decision**:
- `0` — no changes needed OR changes applied successfully (write mode)
- `0` — no drift detected (check mode)
- `1` — internal error (filesystem, parsing, I/O)
- `2` — drift detected in `--check` mode (advisory: "run /update-documentation")

**Why**: Standard convention is `0` success, non-zero error. Splitting "drift detected" into its own exit code (2) lets the pre-commit hook distinguish "documentation is out of sync, please fix" from "the tool itself broke" — both are non-zero but require different user actions.

### D6: Storage location for the sync report

**Decision**: JSON report at `docs/architecture-analysis/documentation-sync-report.json`; Markdown report printed to stdout (and captured by the hook if it ran).

**Why**: `docs/architecture-analysis/` is already the home for auto-generated artifacts (`refresh-architecture` writes there). The JSON report can be consumed by `bug-scrub` or dashboards. The Markdown stdout report is for humans reading hook output.

### D7: Python implementation, shared with `coordinator-task-status-renderer`

**Decision**: Python script at `skills/update-documentation/scripts/sync_docs.py`, depending on `skills/shared/` and `skills/.venv/`.

**Why**: Matches the existing pattern (the renderer skill, `worktree.py`, `merge_worktrees.py`). Reuses the existing `skills/.venv/` so no new dependency surface. The marker-insertion logic can be factored into a shared utility used by both renderers.

**Alternative considered**: Pure shell + `awk`/`sed`. Rejected because the scan-and-categorise logic across 50+ skills is materially harder to express correctly without proper data structures.

## Open Questions

- **Q1**: Should the skill auto-commit when invoked by `post-merge`, or just leave the working tree dirty and let the next manual commit pick it up?
  - **Proposed answer**: Auto-commit with message `chore(docs): sync generated blocks after merge`. Matches the `coordinator-task-status-renderer` convention.

- **Q2**: How aggressive should the cross-link check be — should it follow links into `docs/architecture-analysis/` (auto-generated) and `openspec/changes/` (transient)?
  - **Proposed answer**: No. Check links only within README, CLAUDE.md, skills-workflow.md, and skills-catalogue.md. Avoid noise from transient artifacts.

- **Q3**: What happens if a generated block is missing entirely from a target file?
  - **Proposed answer**: Skill inserts the marker pair at a deterministic location (end of the target section, identified by heading anchor) and emits a warning. Subsequent runs render normally.

## Risks

- **Marker drift**: If a contributor edits markers manually (e.g., deletes a `begin` marker), the generator could overwrite content. Mitigation: skill refuses to write if markers are unbalanced and reports the problem.
- **Performance**: Scanning 50+ `SKILL.md` files on every commit is non-trivial. Mitigation: hook short-circuits if no staged file is under `skills/`, `openspec/specs/`, or `docs/`.
- **Frontmatter parse errors**: A malformed `SKILL.md` could break the scan. Mitigation: skill emits a per-file warning and skips the bad file rather than aborting the whole sync.
