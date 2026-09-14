# Change: Write a Durable State-Artifacts Guide

## Why

The orchestration stack persists related state in five different artifact classes, but their authority, writers, and replay order are explained repeatedly and inconsistently across skill documents. A rehydrated human or agent can therefore read a convenient handoff before the canonical loop or roadmap state, mistake a learning entry for resumable state, or miss the local fallback for a coordinator handoff.

Ri-07 established that durable files are authoritative and queue state is only a projection. This change applies that same one-source-of-truth discipline to session rehydration. The ri-09 failure also showed why the guide must define missing-artifact behavior: an implementation handoff could record ESCALATE while no canonical `loop-state.json` existed.

## What Changes

- Add `docs/guides/state-artifacts.md` as the canonical inventory for per-change `loop-state.json`, roadmap `checkpoint.json`, roadmap learnings, phase records, and coordinator/local handoff documents.
- For each class, document its path, authority, holder, canonical writer, consumers, and missing/stale behavior; document shared writer-ordering rules separately.
- Define one deterministic bootstrap and rehydration order that discovers work from the supervisor handoff, then verifies it against roadmap and per-change authoritative files before consuming advisory context.
- Replace duplicated state-artifact semantics in the six relevant workflow skills with short repository-relative references to the guide while preserving phase-specific commands and gate rules.
- Align `supervise` rehydration prose to the canonical order without changing its runtime or artifact formats.
- Add repository tests that enforce guide coverage, links, and order.

## Non-Goals

- No artifact schema, runtime state machine, coordinator API, or persistence behavior changes.
- No migration, deletion, or renaming of existing artifacts.
- No claim that handoffs, phase records, learnings, or queue rows outrank canonical loop or roadmap state.
- No broad rewrite of skill instructions unrelated to state ownership or rehydration.

## Approaches Considered

### 1. Canonical guide with thin skill references — Recommended

Create one durable guide and keep only phase-specific actions in each skill. Enforce the guide's inventory and reference set with focused tests.

- Pros: one source of truth; small review surface; references remain stable after change archival; testable drift boundary.
- Cons: readers follow one link for shared semantics.
- Effort: S

### 2. Preserve distributed explanations

Edit each skill's existing prose independently and rely on reviewers to keep copies aligned.

- Pros: each skill is self-contained.
- Cons: preserves the duplication that caused drift; rehydration order can diverge again.
- Effort: M

### 3. Generate the guide from runtime schemas

Introduce a producer that introspects Python models and schemas to render documentation.

- Pros: some structural fields could be generated.
- Cons: runtime schemas do not encode authority, missing-state behavior, or human replay order; adds tooling outside this documentation-only scope.
- Effort: L

### Selected Approach

Approach 1. The roadmap approval and acceptance outcomes already select a canonical guide plus linked skill docs; the implementation will keep normative ownership/replay rules in one human-readable document and use tests as the drift guard.

## Impact

- New guide: `docs/guides/state-artifacts.md`
- Documentation index: `docs/guides/documentation.md`
- Generated decision index: `docs/decisions/skill-workflow.md`
- Referencing skill sources: `skills/autopilot/`, `skills/autopilot-roadmap/`, `skills/session-log/`, `skills/supervise/`, `skills/implement-feature/`, and `skills/validate-feature/`
- Test collection configuration: `skills/pyproject.toml`
- Runtime mirrors for changed skills under `.agents/skills/` and `.claude/skills/`
- Focused tests under `skills/tests/state-artifacts/`
- Modified capability: `skill-workflow`

## Success Criteria

- The guide covers all five artifact classes with exact paths, holders, writers, authority, and missing/stale behavior.
- The guide defines an unambiguous supervisor bootstrap plus canonical rehydration sequence.
- The six relevant workflow skill docs reference the guide rather than restating shared ownership semantics.
- The supervise rehydration section follows the guide's order.
- Focused tests, mirror checks, strict OpenSpec validation, and context-drift validation pass.

