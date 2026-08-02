# Design: Strengthen `/simplify` Behavior Preservation

## Context

`/simplify` is a Quality skill that already teaches behavior-preserving local clarity. Agents still skip pinning untested surfaces. This design makes tests the isomorphism proof and adds optional mechanical gates.

## Decisions

### D1 — Single skill, expanded contract

Keep `skills/simplify/` and `/simplify`. Do not create parallel skill names. Add trigger aliases only.

**Rationale:** Competing skills dilute ownership and drift.

### D2 — Characterization-first coverage gate

Before editing production code:

1. Identify the behavioral surface (inputs/outputs/side effects).
2. Search for existing state-based tests that pin that surface.
3. If insufficient → write characterization tests that pass on **current** code (green-on-baseline), commit as `test(...): pin behavior for <surface>`, then simplify.

**Rationale:** Existing suite green is not proof when coverage is missing (Beyoncé Rule).

### D3 — Dual-run + assertion contract

- Dual-run: targeted or full suite must pass on the pre-simplify tip **and** the final tip.
- Assertion contract: simplify commits MUST NOT change test expectation bodies (`assert` / `expect` arguments). Renames of helpers and import path updates are allowed only when expectations are unchanged in meaning; prefer zero test-file diffs beyond characterization commits.

### D4 — Pattern catalog expansion

Add: isomorphic extract, dead-code removal, redundant intermediate. Keep existing six patterns. Prefer state-based tests so structure can move without test rewrites.

### D5 — Scripts optional but verified

Scripts under `skills/simplify/scripts/` implement mechanical checks. Skill remains valid without running them in environments where git/history is unavailable; Verification recommends them.

### D6 — Manual invocation only

No autopilot default phase. Document optional polish after implement/iterate as operator-invoked pure `refactor` commits.

### D7 — Remediation routing from tech-debt

| Finding class | Route |
|---|---|
| Long method, deep nesting, local duplication, generic names | `/simplify` |
| Hub / high coupling / large extract class | `/plan-feature` |
| Unused public API / zombie surface | `/deprecation-and-migration` |
| Perf hotspots with measured budgets | `/performance-optimization` |

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| New `code-simplification` skill | Duplicates triggers and ownership |
| Auto-simplify in implement-feature | Violates Rule 0.5; mixed feat+refactor PRs |
| Require scripts always | Breaks thin/portable environments |
| Characterization as separate skill | Fragmentation; belongs in simplify + TDD |

## Consequences

- Agents spend more tokens on tests before polish — intentional.
- Simplify PRs may include a leading `test:` commit; reviewers should treat that as safety net, not scope creep.
- Tech-debt reports gain an explicit action path for quick wins.
