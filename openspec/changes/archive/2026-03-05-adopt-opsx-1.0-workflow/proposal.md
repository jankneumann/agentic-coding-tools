# Change: Adopt OpenSpec 1.0 OPSX Workflow

## Why

OpenSpec 1.0 introduces generated, agent-native command/skill artifacts for Claude/Codex/Gemini (`.claude/commands/opsx/*.md`, `.claude/skills/openspec-*/SKILL.md`, `.codex/skills/openspec-*/SKILL.md`, `.gemini/commands/opsx/*.toml`, `.gemini/skills/openspec-*/SKILL.md`) plus a command-driven CLI fallback (`openspec instructions`, `openspec new change`, `openspec status`, `openspec archive`). Our current skills/docs still assume older conventions. This proposal aligns workflow internals to prefer agent-native OpenSpec artifacts first, with direct CLI as deterministic fallback, while preserving the existing 5-skill approval-gated workflow.

## What Changes

### Configuration Layer
- Keep `openspec/config.yaml` as the canonical schema/rules source and align rule language with the OpenSpec 1.0 command model
- Keep custom schema `feature-workflow` at `openspec/schemas/feature-workflow/` and validate it with `openspec schema validate`
- Keep artifact templates for `exploration`, `plan-findings`, `impl-findings`, `architecture-impact`, `validation-report`, and `deferred-tasks`

### Skills Layer — Agent-Native OpenSpec First, CLI Fallback
- **`/explore-feature`** (new supporting skill): Analyze architecture and code signals to recommend highest-value next features; use weighted scoring + quick-win/big-bet buckets + dependency blockers, persist machine-readable opportunities/history artifacts, and feed outputs into `/plan-feature`
- **`/plan-feature`**: Prefer agent-native OpenSpec planning artifacts/commands for the current agent; fallback to `openspec new change` + `openspec instructions <artifact> --change <id>`
- **`/iterate-on-plan`**: Prefer agent-native `plan-findings` generation; fallback to `openspec instructions plan-findings --change <id>` and `openspec status --change <id>`
- **`/implement-feature`**: Prefer agent-native apply guidance; fallback to `openspec instructions apply --change <id>`
- **`/iterate-on-implementation`**: Prefer agent-native `impl-findings` generation; fallback to `openspec instructions impl-findings --change <id>`
- **`/validate-feature`**: Prefer agent-native validation/verification artifacts; fallback to `openspec instructions` + existing deployment checks, with `openspec validate <change-id> --strict` as gate
- **`/cleanup-feature`**: Prefer agent-native archive flow; fallback to `openspec archive <change-id> --yes`; produce `deferred-tasks` artifact before archive when needed

### Architecture Integration
- **`/refresh-architecture`** remains a standalone skill (project-global, not per-change) but is called at specific workflow touchpoints:
  - **Before `/plan-feature`** (exploration phase): Ensure `docs/architecture-analysis/` is current so proposal/spec/task instructions use accurate cross-layer flow and parallel zone data
  - **During `/validate-feature`**: Run `make architecture-diff` and `make architecture-validate` scoped to changed files, producing the per-change `architecture-impact` artifact
  - **After `/cleanup-feature`** (post-merge): Refresh `docs/architecture-analysis/` on main so it reflects the merged change for future planning
- Keep `architecture-impact` as a per-change OpenSpec artifact in the schema (depends on `tasks`, produced alongside `validation-report`)

### Skills Layer — Cleanup
- Remove stale references to retired wrapper skills (`/openspec-proposal`, `/openspec-apply`, `/openspec-archive`) from skill docs and workflow docs
- Define precedence explicitly: agent-native OpenSpec skill/command artifacts first, direct OpenSpec CLI fallback second

### Documentation
- Update `AGENTS.md` to reference OpenSpec 1.0 precedence rules and `feature-workflow` schema usage
- Update `docs/skills-workflow.md` and `CLAUDE.md` with agent-native-first + CLI-fallback behavior and parity expectations across Claude/Codex/Gemini

## Impact

- Affected specs: `skill-workflow`
- Affected code/docs: 6 core skills (`plan-feature`, `iterate-on-plan`, `implement-feature`, `iterate-on-implementation`, `validate-feature`, `cleanup-feature`), new supporting skill (`explore-feature`), `refresh-architecture` touchpoints, `AGENTS.md`, `docs/skills-workflow.md`, `docs/feature-discovery/`, `CLAUDE.md`, `openspec/config.yaml`, `openspec/schemas/feature-workflow/`
- No breaking changes to the external workflow; skill names and approval gates remain identical
- Assumes OpenSpec CLI is already upgraded to 1.0+
