# Change: pilot-test-quality-audit

## Why

This repo's skills tell agents how to test: `test-driven-development` prescribes red→green,
`simplify` writes characterization tests, and `coverage-baseline.json` ratchets line coverage
upward. These rules come from human practice. Nobody has measured whether the tests they produce
check what the code is *supposed* to do or just restate what it currently does.

The concern is concrete. If one agent, in one context, writes both a function and its test, both
come from the same mental model. When that model is wrong, the test passes anyway. Line coverage
cannot see this. A coverage ratchet makes it worse, because deleting a worthless test lowers
coverage and is penalized.

We want a **test linter** that flags these tests. But its rules are hypotheses right now. They
include: mock assertions outnumbering behavior assertions; asserting on private attributes; an
expected value that matches whatever the code currently outputs; and a test that breaks when a
private name is renamed. Turning them into a linter before measuring them would just swap one
unvalidated metric (coverage) for another.

This change is the measurement. It runs a pilot audit over two test suites and compares four
independent approaches:

- deterministic static checks;
- calibrated System One (Jev) judgments;
- execution evidence: mutation kill rate, survival of a private-name rename, and git-history
  signals;
- a frontier LLM, used only to explain flagged tests.

All four are compared against about 40 human labels of where each test's expected values come
from (its "oracle source"). The output says which rules and which Jev questions actually predict
weak tests, sets thresholds from our own labelled data, and leaves the linter to a follow-up
change.

The pilot also deliberately builds pieces that two unstarted `skill-rightsizing` roadmap items
need. Its mutation runner is the runner `add-mutation-score-guardrail` (ri-07) needs. Its label
ledger and agreement metrics use the method `calibrate-llm-judge-against-human-labels` (ri-08)
specifies: Cohen's kappa, a 0.7 exclusion floor, and a blind judge. So this change avoids building
a second calibration method.

## What Changes

- **New package `packages/test-oracle-audit`** (its own `uv` project and CI job). It is read-only
  over the code and tests it audits, and has these stages:
  - **Inventory.** Enumerates test node ids and the source modules each test reaches. Reuses the
    test-to-module mapping from `refresh-architecture/.../test_linker.py`.
  - **Static checks (AST).** Flags tests with no assertions, tests where mock assertions dominate,
    assertions on private attributes, imports of `_private` names, test files that mirror source
    files one-to-one, and unscoped `patch` targets.
  - **Judged stage.** Runs through `system_one_decisions.decide()` in shadow/advisory mode with
    batched questions:
    - `Choice(oracle_source)`
    - `Noul(survives_behaviour_preserving_refactor)`
    - `Choice(boundary_level)`

    Every answer is `evidence_class: judgment`. It never blocks anything and never enters
    `context_eval.verdict`. It falls back to no answer when `TYPESAFE_API_KEY` is absent or
    `--dry-run` is set.
  - **Mutation runner.** A `MutationRunner` interface with a mutmut backend. It runs on a sampled
    set of source modules, reports kill rate per test, and is reusable by ri-07.
  - **Refactor survival.** An automated, provably behaviour-preserving refactor: renaming private
    symbols in the module under test. A test that fails afterwards is coupled to implementation
    details.
  - **History signals.** From git: (a) the co-change ratio, meaning how often a test's assertions
    were rewritten in the same commit as the code it tests; (b) whether the test was added
    alongside a `fix:` commit, i.e. as a regression pin.
  - **Explanation stage.** A frontier LLM writes prose only for tests that some approach flagged.
    It reuses the two-stage pattern from `gen_eval.semantic_judge`.
  - **Analysis.**
    - Compares each approach to the ground truth. Static flags are compared to mutation kill
      rate. Jev's oracle-source label is compared to the human labels using Cohen's kappa.
      Jev's refactor-survival probability is compared to the rename result using a Brier score.
    - Sets thresholds from our own labelled data.
    - Produces a **disagreement report** listing tests where the approaches disagree.
- **An oracle-source vocabulary and label ledger.**
  - Seven values: `spec`, `property`, `reference_impl`, `external_contract`, `characterization`,
    `current_impl_output`, `none`.
  - The ledger is a sidecar file keyed by test node id plus a hash of the test's content, so a
    label goes stale when the test changes.
  - No test files or pytest marker registrations are edited. That avoids conflicts with the paused
    `parallel-infrastructure` changes and with ri-20's `skills/pyproject.toml` edit. In-file
    markers are a decision for the linter follow-up.
- **A human labelling flow for about 40 tests**, stratified across static flags and mutation-score
  buckets. Modeled on `cite-requirements`, it shows one card per test and the operator makes the
  call. The judge stages never see these labels.
- **A test-policy lens in `skill-audit`.** It classifies each test-prescribing instruction in
  `test-driven-development`, `simplify`, `implement-feature`, `validate-feature` and
  `iterate-on-implementation` on two axes:
  - *oracle source*: spec-derived vs implementation-derived;
  - *authorship*: written in a separate context vs by the same agent.

  This needs new finding `KINDS` and a schema enum extension that stays backward-compatible.
- **The pilot run itself.** Audited suites:
  - `agent-coordinator/tests/test_evaluation/` (91 tests);
  - `skills/tests/parallel-infrastructure/` (271 tests).

  Mutation runs on a sampled subset of the modules these tests cover. The run produces a stamped
  report under `docs/reports/test-oracle-audit/`.
- **Recorded open decisions for the follow-up.**
  - The coverage-ratchet policy in `fitness-functions` "Coverage Signal With No-Decrease Ratchet",
    `coverage-baseline.json`, and the TDD skill's "coverage hasn't decreased" step. These are
    flagged, not changed.
  - Whether oracle-source labels become in-file pytest markers.

**Out of scope:** the CI test linter, rewriting any skill, deleting or editing any test, and
promoting any judgment to an acting decision. The last belongs to `promote-shadow-judgments-to-acting-decisions`.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Read-only | `git diff` over audited test and source dirs after a full pilot run | empty | validate-feature (pilot-run task) |
| Degradation | Full pipeline with no `TYPESAFE_API_KEY` and no LLM backend | completes; judged/explain stages report `degraded`, never crash | package CI job |
| Cost | Jev spend for the full pilot (≈362 tests, batched) | ≤ $1.00 (est. ≈ $0.10) | pilot-run telemetry via `event_sink` |
| Runtime | Static + inventory + history stages for both suites | ≤ 2 min | package CI job (timed) |
| Runtime | Mutation sample run | ≤ 60 min wall-clock, bounded by `--max-mutants` | pilot-run task |
| Statistical honesty | Every reported agreement or predictive metric | carries n and a 95% CI; metrics with n < 20 are marked "insufficient" | analysis-stage tests |

## Approaches Considered

### Approach 1: New standalone package `packages/test-oracle-audit` (Recommended)

**Description:** A dedicated `uv` package with one module per stage and one CLI
(`test-oracle-audit inventory|static|judge|mutate|refactor|history|label|analyze|report`).
The skill-audit lens is a small `conventions.py`-style plug-in in `skills/skill-audit` that
imports the shared vocabulary.

**Pros:**
- One home that ri-07 (mutation runner) and ri-08 (label ledger, kappa) can import without
  `sys.path` workarounds. The repo already uses this pattern for `system-one-decisions`,
  `context-eval` and `gen-eval`.
- Stages are separate modules with non-overlapping write scopes, so they can be built in parallel
  work packages.
- The package's own tests run as their own CI job. They don't hit the module-name collisions that
  force `skills/` suites into separate processes.
- Read-only by construction: the package writes only to `docs/reports/test-oracle-audit/` and the
  label ledger.

**Cons:**
- A new package means more CI configuration and one more venv.
- Reusing `test_linker` and `check_test_contract` from `skills/` means either importing across
  trees or vendoring small pieces.

**Effort:** L

### Approach 2: New skill `skills/test-oracle-audit/` with scripts

**Description:** Package the audit as a skill (SKILL.md plus `scripts/`) like `bug-scrub` or
`skill-audit`, so agents can invoke it with `/test-oracle-audit`.

**Pros:**
- Agents can call it directly as a slash command.
- It sits next to `test_linker`, `simplify` and `skill-audit`, so those can be imported the way
  other skills already do.

**Cons:**
- ri-07 and ri-08 would have to import from skill scripts through `sys.path` insertion, which is
  the pattern this repo is moving away from.
- It lands in the shared `skills/` test tree, which the module-name collision constraint and ri-20
  (`collect-uncollected-skill-tests`) are both reworking right now.
- A skill implies a supported user workflow. This is a pilot whose tooling may be discarded.

**Effort:** M

### Approach 3: Distribute stages into existing tools

**Description:** Static checks go into `refresh-architecture`'s test linker. Mutation and the
private-name rename go into `simplify`'s `verify_behavior_preservation`. Jev questions go into
`skill-audit`. An analysis notebook joins them.

**Pros:**
- No new component.
- Each piece lands next to its closest relative.

**Cons:**
- There's no single place to run the audit, and joining four tools' outputs becomes the hard part.
- It changes active skills (`simplify`, `refresh-architecture`) for a pilot whose conclusions are
  unknown. If the pilot finds a rule useless, removing it means editing several skills.
- ri-07 and ri-08 still lack a shared runner or ledger to reuse.

**Effort:** M

**Recommended:** Approach 1. Shared tooling that ri-07 and ri-08 can reuse was the deciding
requirement from discovery, and only a package provides it cleanly. Effort is L, but the work
splits into M-sized packages with disjoint write scopes, one per stage, and the coordinated tier
can run those in parallel.

### Selected Approach

**Approach 1: standalone package `packages/test-oracle-audit`.** Selected at Gate 1
(2026-10-09) with no modifications. Discovery answers that shape it:

- **Relation to ri-07/ri-08:** build reusable modules and feed both items. The mutation runner
  and the label ledger are public package API that ri-07 and ri-08 can import. Agreement metrics
  follow ri-08's rules: Cohen's kappa, a 0.7 exclusion floor, and a blind judge.
- **Pilot slice:** `agent-coordinator/tests/test_evaluation/` plus
  `skills/tests/parallel-infrastructure/`, both read-only. Mutation runs on a sample.
- **Markers:** a sidecar label ledger only. No test files are edited and no pytest markers are
  registered.
- **Ground truth:** proxies (mutation, rename survival, history) for every sampled test, plus
  about 40 human oracle-source labels.

Approaches 2 (skill) and 3 (distribute into existing tools) were not selected. Approach 2 makes
reuse by ri-07 and ri-08 depend on `sys.path` imports and lands in the `skills/` test tree that is
being reworked. Approach 3 leaves no single runnable audit and changes active skills for a pilot
whose conclusions are unknown.

## Impact

- **New capability spec:** `test-oracle-audit`, which also holds the skill-audit lens requirement
  so the unarchived `add-skill-audit` deltas aren't touched.
- **New code:** `packages/test-oracle-audit/**`, plus a lens plug-in under
  `skills/skill-audit/scripts/`.
- **Modified:**
  - `skills/skill-audit`: new finding `KINDS` and a schema enum extension;
  - `.github/workflows/ci.yml`: a new package test job.
- **New report artifacts:** `docs/reports/test-oracle-audit/`.
- **Roadmap notes:** `skill-rightsizing` ri-07 and ri-08 get a note recording that the runner and
  the ledger now exist.
- **Dependencies:**
  - `add-skill-audit` must be archived before the lens work package merges.
  - History mining needs an unshallowed clone. This one is shallow: 255 commits, back to
    2026-08-31.
  - The live judged stage needs `TYPESAFE_API_KEY`, and the explanation stage needs an LLM
    backend. Neither is present in the planning session.
