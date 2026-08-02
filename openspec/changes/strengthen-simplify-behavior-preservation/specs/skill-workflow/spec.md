## ADDED Requirements

### Requirement: Simplify Skill Behavior-Preservation Contract

The `simplify` skill SHALL preserve observable behavior of the code under edit. Before modifying production source, the skill SHALL apply a **coverage gate**:

1. Identify the behavioral surface (public inputs, outputs, errors, and side-effect ordering relevant to the candidate change).
2. Determine whether existing **state-based** tests pin that surface.
3. If the surface is not pinned, the skill SHALL write **characterization tests** that pass against the **current** code (green-on-baseline), commit them separately (conventional `test` type), and only then apply simplifications.

Simplification commits SHALL NOT modify test expectation bodies (`assert` / `expect` arguments or equivalent) to make the suite pass. If expectations must change for the suite to pass, the simplification SHALL be reverted and re-evaluated — the change is treated as a behavior change outside this skill's scope.

The skill SHALL perform **dual-run verification**: the selected test suite SHALL pass on the pre-simplify baseline tip and on the post-simplify tip. Primary invoke remains `/simplify`; invocation SHALL remain operator-manual (not default-enabled in autopilot).

#### Scenario: Unpinned surface blocks production edits

- **GIVEN** a module with no tests covering the function under consideration
- **WHEN** an agent runs `/simplify` on that module
- **THEN** the agent SHALL write characterization tests that pass on the baseline code before editing production source
- **AND** the characterization tests SHALL be committed separately from refactor commits

#### Scenario: Assertion mutation is rejected

- **GIVEN** a simplification that changes return values or error messages
- **WHEN** existing tests fail unless their expectations are edited
- **THEN** the agent SHALL revert the simplification
- **AND** SHALL NOT land expectation-body edits as part of the simplify workflow

#### Scenario: Dual-run proves preservation

- **GIVEN** characterization coverage (existing or newly added) for the surface
- **WHEN** simplifications are complete
- **THEN** the test suite SHALL pass on the commit immediately before the first simplify production edit
- **AND** the test suite SHALL pass on HEAD after all simplify commits

#### Scenario: Manual invocation only

- **GIVEN** an autopilot or implement-feature run
- **WHEN** no operator explicitly requests `/simplify`
- **THEN** the orchestrator SHALL NOT automatically run a simplify phase by default

---

### Requirement: Simplify Pattern Catalog Includes Isomorphic DRY

The `simplify` skill's pattern catalog SHALL include, in addition to local clarity patterns (guard clauses, extract helpers from long functions, nested ternaries, boolean flag splits, domain naming, premature-abstraction inline):

- **Isomorphic extract** — structural duplication across call sites collapsed into a shared helper without changing observable behavior, only when characterization tests pin all rewritten sites
- **Dead code removal** — unreachable or unreferenced code removed only after Chesterton's Fence and call-graph/test evidence
- **Redundant intermediate** — pure-forwarding wrappers inlined when they add no policy and are not a public or documented extension point

Large structural changes remain subject to the Rule of 500 (≤500 lines and ≤5 files by hand, else automate or split, else escalate to `/plan-feature`).

#### Scenario: Isomorphic extract requires pinned sites

- **GIVEN** the same multi-line structural block in two modules
- **WHEN** the agent extracts a shared helper
- **THEN** characterization or existing behavioral tests SHALL cover both call sites before the extract lands
- **AND** the suite SHALL remain green without expectation edits

---

### Requirement: Simplify Mechanical Helper Scripts

The `simplify` skill SHALL ship optional helper scripts under `skills/simplify/scripts/`:

| Script | Behavior |
|---|---|
| `check_scope.py` | Compares a git diff range to the Rule of 500 / 5-file limit; exits non-zero when exceeded unless `--allow-codemod` is set |
| `check_test_contract.py` | Examines a git diff for changes to assertion/expect bodies in test paths; exits non-zero when expectation bodies change |
| `verify_behavior_preservation.py` | Runs a configured test command at a baseline ref and at HEAD (or records dual-run results); writes a machine-readable report |

Scripts SHALL be invocable via `<skill-base-dir>/scripts/...` and MUST NOT require agent-coordinator. The skill remains valid when scripts are unavailable; Verification SHOULD recommend running them when git history is present.

#### Scenario: Scope check fails oversized manual diff

- **GIVEN** a diff touching more than 5 files or more than 500 lines
- **WHEN** `check_scope.py` runs without `--allow-codemod`
- **THEN** the process exits non-zero
- **AND** the message references Rule of 500

#### Scenario: Test contract check fails expectation edits

- **GIVEN** a diff that changes `assert result == 1` to `assert result == 2` in a test file
- **WHEN** `check_test_contract.py` runs on that diff
- **THEN** the process exits non-zero

---

### Requirement: Tech-Debt Remediation Routing to Simplify

The `tech-debt-analysis` skill SHALL document remediation routing for findings:

- Local complexity / nesting / naming / local duplication → recommend `/simplify`
- Hub nodes, high coupling, large extract-class work → recommend `/plan-feature`
- Zombie or unused public surfaces → recommend `/deprecation-and-migration`
- Measured performance hotspots → recommend `/performance-optimization`

#### Scenario: Quick-win finding routes to simplify

- **GIVEN** a tech-debt report finding for deep nesting in a single file under 500 lines
- **WHEN** the operator follows remediation routing
- **THEN** the recommended next skill SHALL be `/simplify` rather than a full OpenSpec feature plan

---

### Requirement: Optional Post-Implementation Simplify Polish

The `implement-feature` and `iterate-on-implementation` skills SHALL document an **optional** next step to invoke `/simplify` for behavior-preserving polish after the suite is green. Any such polish SHALL land as separate `refactor` commits and SHALL NOT mix with `feat` / `fix` commits from the feature work.

#### Scenario: Optional polish is not required for implement completion

- **GIVEN** implement-feature has created a PR with a green suite
- **WHEN** the operator does not request simplify
- **THEN** implement-feature completion remains valid without a simplify pass
