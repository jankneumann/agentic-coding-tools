# Strengthen `/simplify` Behavior Preservation

## Why

`skills/simplify/` already encodes Chesterton's Fence, the Rule of 500, and a local clarity pattern catalog. What it does **not** deterministically require is a **coverage gate + characterization tests + dual-run proof** before structural edits. Agents can "run the suite," pass because the surface was never pinned, and ship isomorphic-looking refactors that change behavior.

External references (`addyosmani/agent-skills` code-simplification; isomorphic DRY refactor skills) share the preserve-behavior goal but still under-specify the *missing-coverage* case. Our own `test-driven-development` skill already teaches the Beyoncé Rule and state-based tests; `simplify` must compose with that contract rather than hope the suite is sufficient.

This change upgrades the single `/simplify` skill (no second skill name), adds optional mechanical scripts for scope / assertion-contract / dual-run checks, and documents remediation routing from tech-debt plus optional polish hooks after implement/iterate. Invocation stays **manual** — not default-on in autopilot.

## What Changes

### Phase A — Skill contract

Expand `skills/simplify/SKILL.md`:

1. **Coverage gate** before production edits — if behavioral tests do not pin the surface, write characterization tests first (green on baseline).
2. **Dual-run verification** as a workflow step (suite green on pre-simplify tip and final tip), not only a tail-bullet.
3. **Assertion gate** — test expectation bodies must not change to make a simplify pass.
4. **Expanded pattern catalog** — isomorphic extract, dead-code removal, redundant intermediate (alongside existing six clarity patterns).
5. **When / when-not** and explicit handoffs to `performance-optimization`, `deprecation-and-migration`, `plan-feature`.
6. **Frontmatter** — `related:` to TDD / tech-debt / deprecation / iterate-on-implementation; extra trigger aliases (`code-simplify`, `isomorphic refactor`) while keeping primary invoke `/simplify`.
7. Content invariants in `skills/tests/simplify/`.

### Phase B — Deterministic helpers

Add portable scripts under `skills/simplify/scripts/`:

| Script | Role |
|---|---|
| `check_scope.py` | Enforce Rule of 500 / 5-file limit (or require `--allow-codemod`) |
| `check_test_contract.py` | Fail if assertion/expect bodies in test paths changed |
| `verify_behavior_preservation.py` | Dual-run tests at baseline SHA vs HEAD; emit `simplify-report.json` |

Scripts are optional (skill remains usable as pure markdown) but recommended in Verification.

### Phase C — Ecosystem hooks

1. `tech-debt-analysis` — remediation routing: local clarity/dup → `/simplify`; hubs → `/plan-feature`; dead APIs → `/deprecation-and-migration`.
2. `implement-feature` / `iterate-on-implementation` — optional Next Step: pure `refactor` polish via `/simplify` (never mixed into feat commits).
3. `docs/skills-catalogue.md` + `docs/skill-flow/README.md` — behavior-preservation contract + manual polish edge.

### Spec delta

Adds requirements to `skill-workflow` for the strengthened simplify contract (characterization gate, dual-run, scripts, manual invocation, remediation routing). See `specs/skill-workflow/spec.md`.

## Non-goals

- A second skill (`code-simplification`, `isomorphic-refactor`).
- Auto-running simplify inside implement work packages or autopilot by default.
- Full codemod infrastructure (recommend external tools when Rule of 500 trips).
- Importing paywalled third-party skill text; only the isomorphic *idea* is adopted.

## Success Criteria

1. Agent following `/simplify` refuses production edits on an unpinned surface and writes characterization tests first.
2. Landed simplifications prove: characterization green on baseline + suite green after + no assertion-body edits.
3. Pattern catalog covers clarity **and** isomorphic DRY.
4. Scripts mechanically fail Rule of 500 violations and test-expectation mutations.
5. Catalogue/skill-flow/tech-debt/implement/iterate docs describe the handoffs; autopilot remains manual-only.
6. Content tests fail if Chesterton, Rule of 500, or the coverage-gate language regresses.

## Decisions (operator-approved)

| # | Decision |
|---|---|
| 1 | Ship Phase **A + B + C** |
| 2 | Leave invocation **manual** (no autopilot default-on) |
| 3 | Track as this **OpenSpec** change |
| 4 | Keep primary command **`/simplify`** |
