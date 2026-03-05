# Implementation Findings

## Iteration 1

<!-- Date: 2026-02-17 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | workflow | high | Proposal/design/tasks/spec referenced incorrect runtime asset paths (`.claude/opsx`, `.codex/openspec-*.md`, `.gemini/commands/opsx/*.md`) that do not match generated assets. | Updated all affected OpenSpec docs to the actual generated locations: `.claude/commands/opsx/*.md`, `.claude/skills/openspec-*/SKILL.md`, `.codex/skills/openspec-*/SKILL.md`, `.gemini/commands/opsx/*.toml`, `.gemini/skills/openspec-*/SKILL.md`. |
| 2 | workflow | medium | Task `6.1` was marked complete without a full end-to-end `/plan-feature` execution test against a fresh test change in this session. | Re-opened task `6.1` in `tasks.md` to avoid over-claiming; keep completion pending full end-to-end run. |
| 3 | edge-case | medium | New OpenSpec command APIs reject change names with dots, and this change-id (`adopt-opsx-1.0-workflow`) includes a dot, which blocks `openspec status/instructions --change <id>`. | Treated as out-of-scope for this iteration; validated command-path behavior using a valid existing change-id. Recommend follow-up proposal to define migration/alias strategy for legacy dotted change-ids. |

### Quality Checks

- `openspec validate adopt-opsx-1.0-workflow --strict`: pass
- `openspec schema validate feature-workflow`: pass
- `openspec templates --schema feature-workflow --json`: pass
- Cross-agent parity mapping check (Claude/Codex/Gemini): pass after Codex `sync-specs` alias normalization

### Spec Drift

- Updated `openspec/changes/adopt-opsx-1.0-workflow/proposal.md` (runtime asset paths)
- Updated `openspec/changes/adopt-opsx-1.0-workflow/design.md` (runtime asset paths)
- Updated `openspec/changes/adopt-opsx-1.0-workflow/tasks.md` (runtime asset paths + reopened `6.1`)
- Updated `openspec/changes/adopt-opsx-1.0-workflow/specs/skill-workflow/spec.md` (runtime asset paths in parity scenario)

