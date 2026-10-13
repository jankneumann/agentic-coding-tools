# Tasks: Pilot multi-approach test-quality audit

> Change ID: `pilot-test-quality-audit`
> Tier: coordinated (work packages in `work-packages.yaml`)
>
> **Scenario IDs.** `test-oracle-audit.1`–`.55` are the scenarios of `specs/test-oracle-audit/spec.md`, in
> document order (adding a scenario renumbers everything after it; re-derive this table from the spec):
>
> | Requirement | Scenarios |
> |---|---|
> | Ledger | .1–.5 |
> | Read-only | .6–.7 |
> | Inventory | .8–.10 |
> | Static | .11–.18 |
> | Judged | .19–.23 |
> | Mutation | .24–.28 |
> | Rename | .29–.32 |
> | History | .33–.35 |
> | Explain | .36–.38 |
> | Labelling | .39–.41 |
> | Analysis | .42–.46 |
> | Disagreement | .47–.48 |
> | Lens | .49–.52 |
> | Report | .53–.55 |
>
> **Test-authoring rule (design D14).**
> - Every *"Write failing tests"* task is done by a sub-agent whose context holds only the spec
>   deltas, `contracts/`, and the cited design decisions. It holds no implementation files. Tests
>   cite their scenario IDs in docstrings.
> - Each implementation task runs in a separate context afterwards.
> - If a test task needs an unspecified detail, it records a `skill-procedure-deviation` decision
>   instead of reading code.
> - `tests/conftest.py` is owned by wp-contracts and holds only the shared fixtures listed in task
>   1.2. Stage packages keep stage-specific helpers inside their own `test_<stage>*.py` modules and
>   `tests/fixtures/<stage>/` trees; they never edit `conftest.py`.
>
> **Sizes.** XS ≤ 30 min, S ≤ 2 h, M ≤ 1 day. There are no L or XL tasks.

## 1. Contracts and package skeleton (wp-contracts)

- [x] 1.1 Write failing contract tests. [S]
  - Records serialize to JSON that validates against each `contracts/schemas/*.schema.json`.
  - The vocabulary has exactly seven values with the D2 binary partition.
  - The ledger records content hashes, marks stale entries, ignores whitespace-only edits, and
    rejects unknown labels.
  - The runtime schema copies under `src/test_oracle_audit/schemas/` are byte-identical to
    `contracts/schemas/` (D1 "Schema runtime copy").
  - `thresholds.py` loads `config/thresholds.json`, rejects a missing key, and `tercile_cutpoints`
    splits a known list into thirds.
  - Resolve contract paths with `change_dir()` from `tests/_shared/openspec_paths.py` (copied from
    `skills/tests/_shared/openspec_paths.py`, per the OpenSpec path-stability guide).

  **Spec scenarios**: test-oracle-audit.1, test-oracle-audit.2, test-oracle-audit.3, test-oracle-audit.4
  **Contracts**: contracts/schemas/stage-record.schema.json, contracts/schemas/label-ledger.schema.json, contracts/schemas/mutation-result.schema.json, contracts/schemas/analysis-report.schema.json
  **Design decisions**: D1, D2, D9
  **Dependencies**: None
- [x] 1.2 Scaffold `packages/test-oracle-audit`. [S]
  - `pyproject.toml`: depends on `libcst` and `system-one-decisions` (path dependency); extras
    `mutation` (`mutmut>=3.8,<4`, `pytest-cov`) and `dev`.
  - `records.py`, `vocabulary.py`, `thresholds.py` (config loader, tercile cut-points).
  - `src/test_oracle_audit/schemas/`: runtime copies of the five contract schemas.
  - `config/thresholds.json` with display thresholds only; `config/suites.json` with the two pilot
    `SuiteSpec`s (project root, test paths, source roots, pytest args).
  - `tests/conftest.py` with the shared fixtures only: `schema_validator(stage)` and
    `fixture_project(name)` (copies `tests/fixtures/<name>` to a temp dir and runs `git init` +
    one commit).
  - `tests/_shared/openspec_paths.py`.

  **Dependencies**: 1.1
- [x] 1.3 Implement `ledger.py`: load, add, save, and the content-hash staleness check. [S]
  **Dependencies**: 1.2
- [x] Checkpoint: run the package tests, review the diff, verify the write scope is limited to wp-contracts.

## 2. Inventory and static checks (wp-inventory-static)

- [ ] 2.1 Write failing inventory tests over a fixture mini-project: deterministic output,
  parametrized cases sharing one content hash, resolved fixtures, covered modules, and an
  uncollectable file yielding an `error` record without aborting. [S]
  **Spec scenarios**: test-oracle-audit.8, test-oracle-audit.9, test-oracle-audit.10
  **Contracts**: contracts/schemas/stage-record.schema.json (InventoryPayload)
  **Design decisions**: D1
  **Dependencies**: 1.2
- [ ] 2.2 Implement `inventory.py`. Vendor the test-to-module mapping from `test_linker` with a
  provenance comment, and resolve fixtures through pytest's fixture manager. [M]
  **Dependencies**: 2.1
- [ ] 2.3 Write failing static-check tests: one positive and one negative fixture per rule id, a
  behaviour-only test that fires no rule, and a module that raises at import time and is still
  analysed. [S]
  **Spec scenarios**: test-oracle-audit.11, test-oracle-audit.12, test-oracle-audit.13, test-oracle-audit.14, test-oracle-audit.15, test-oracle-audit.16, test-oracle-audit.17, test-oracle-audit.18
  **Contracts**: contracts/schemas/stage-record.schema.json (StaticPayload)
  **Design decisions**: D1
  **Dependencies**: 1.2
- [ ] 2.4 Implement `static_checks.py`. It is AST-only and never imports test modules. [M]
  **Dependencies**: 2.3
- [ ] Checkpoint: run the package tests, review the diff, verify scope.

## 3. Execution evidence (wp-execution)

- [ ] 3.1 Spike: run mutmut 3.x mutant generation and one `MUTANT_UNDER_TEST` execution on an
  isolated copy of each pilot suite through `uv run --project <copy> --with pytest-cov --with
  mutmut pytest` (D1), confirming the trampolines and `--cov-context=test` resolve there. Record
  the verdict (works / needs AST fallback) as a session-log decision and in a design D4 note. [S]
  **Design decisions**: D4
  **Dependencies**: 1.2
- [ ] 3.2 Write failing isolation tests: the copy is removed after a stage raises, the original
  tree is untouched, and a test run inside the copy sees `HOME`, `TMPDIR` and pytest `--basetemp`
  under the scratch directory (D3). [XS]
  **Spec scenarios**: test-oracle-audit.7
  **Design decisions**: D3
  **Dependencies**: 1.2
- [ ] 3.3 Implement `isolation.py`: a `git worktree add --detach` copy, with a `copytree` fallback. [S]
  **Dependencies**: 3.2
- [ ] 3.4 Write failing mutation tests over a fixture mini-project. [M]
  - Attribution goes only to the failing test.
  - Seeded sampling is reproducible and spread across modules.
  - The AST fallback is used when the probe fails, and the backend is recorded.
  - Fewer than 5 covering mutants gives `insufficient`.

  **Spec scenarios**: test-oracle-audit.24, test-oracle-audit.25, test-oracle-audit.26, test-oracle-audit.27, test-oracle-audit.28
  **Contracts**: contracts/schemas/mutation-result.schema.json, contracts/schemas/stage-record.schema.json (MutationPayload)
  **Design decisions**: D4
  **Dependencies**: 3.3
- [ ] 3.5 Implement `mutation.py`: the `MutationRunner` protocol, `AstMutantRunner`, and
  `run_mutation` with stratified seeded sampling and coverage-context attribution. [M]
  **Dependencies**: 3.4
- [ ] 3.6 Implement the `MutmutRunner` backend with its probe, following the 3.1 verdict. [M]
  **Dependencies**: 3.1, 3.5
- [ ] Checkpoint: run the package tests, review the diff, verify scope.
- [ ] 3.7 Write failing rename-survival tests. [S]
  - A test that imports or patches a private name breaks.
  - A public-only test survives.
  - A string-referenced name, an `__all__` entry, or a re-export is `unrenamable`.
  - A module with more than half of its eligible symbols `unrenamable` marks its tests
    `low_confidence`.

  **Spec scenarios**: test-oracle-audit.29, test-oracle-audit.30, test-oracle-audit.31, test-oracle-audit.32
  **Contracts**: contracts/schemas/stage-record.schema.json (RenamePayload)
  **Design decisions**: D5
  **Dependencies**: 3.3
- [ ] 3.8 Implement `refactor.py`: a libcst rename across the source tree only, run in an isolated copy. [M]
  **Dependencies**: 3.7
- [ ] Checkpoint: run the package tests, review the diff, verify scope.

## 4. History signals (wp-history)

- [x] 4.1 Write failing history tests against a synthetic git repository built in a temp dir. [S]
  - A shallow clone degrades, and no network command is run.
  - A denominator below 3 gives `insufficient`.
  - `fix:` and `fix(<scope>):` commits (with or without `!`) that introduce a test give `added_with_fix`; `fixup!` and `feat:` commits do not.
  - A test function added to an existing file in a later commit is attributed to that commit, not
    the file's first commit, and the attribution follows a file rename.
  - The co-change ratio is correct for a known commit sequence.

  **Spec scenarios**: test-oracle-audit.33, test-oracle-audit.34, test-oracle-audit.35
  **Contracts**: contracts/schemas/stage-record.schema.json (HistoryPayload)
  **Design decisions**: D6
  **Dependencies**: 1.2
- [x] 4.2 Implement `history.py`. Vendor the assertion-line diff scanner from
  `simplify/scripts/check_test_contract.py` with a provenance comment. [M]
  **Dependencies**: 4.1

## 5. Judged and explanation stages (wp-judged-explain)

- [ ] 5.1 Write failing judged-stage tests using `system_one_decisions.testing.stub_decide`. [S]
  - Distributions are stored with `evidence_class: judgment`.
  - A missing key or `--dry-run` gives `degraded` and exit 0.
  - The state passed to `decide()` excludes other approaches' outputs and human labels.
  - Over-budget state gives `degraded: over_budget`.
  - A confident `current_impl_output` still exits 0.

  **Spec scenarios**: test-oracle-audit.19, test-oracle-audit.20, test-oracle-audit.21, test-oracle-audit.22, test-oracle-audit.23
  **Contracts**: contracts/schemas/stage-record.schema.json (JudgedPayload)
  **Design decisions**: D7
  **Dependencies**: 1.2
- [ ] 5.2 Implement `judged.py`. It batches per file under budget, takes thresholds from config, and
  imports `system_one_decisions` as a module. [M]
  **Dependencies**: 5.1
- [ ] 5.3 Write failing explanation tests: only flagged tests are sent, no backend degrades,
  prose is capped at 600 chars with an action from the enum, and the kill-rate tercile used for
  flagging comes from `thresholds.tercile_cutpoints` over the mutation records, per suite. [S]
  **Spec scenarios**: test-oracle-audit.36, test-oracle-audit.37
  **Contracts**: contracts/schemas/stage-record.schema.json (ExplainPayload)
  **Design decisions**: D8
  **Dependencies**: 1.2
- [ ] 5.4 Implement `explain.py` with the `ExplainBackend` protocol and the flagging rule. [S]
  **Dependencies**: 5.3
- [ ] Checkpoint: run the package tests (including the system-one-decisions guard tests), review the diff, verify scope.

## 6. Labelling, analysis, report (wp-labels-analysis)

- [ ] 6.1 Write failing labelling tests: every non-empty stratum is represented, the seed is
  reproducible, cards contain no judged, static, mutation or history output, `label next` /
  `label record` are non-interactive, and `--dry-run` renders cards without touching the ledger. [S]
  **Spec scenarios**: test-oracle-audit.39, test-oracle-audit.40, test-oracle-audit.41
  **Contracts**: contracts/schemas/label-ledger.schema.json
  **Design decisions**: D9
  **Dependencies**: 1.3
- [ ] 6.2 Implement `labelling.py`: `stratified_sample` and `render_card`. [S]
  **Dependencies**: 6.1
- [ ] 6.3 Write failing analysis tests. [M]
  - Kappa is 1 on perfect agreement.
  - n < 20 gives `insufficient` with no value.
  - Binary kappa below 0.7 excludes the question.
  - A Cliff's-delta CI spanning 0 gives `not_predictive`.
  - Bootstrap is reproducible.
  - Explanation actions are never read.
  - The output validates against `analysis-report.schema.json`.

  **Spec scenarios**: test-oracle-audit.38, test-oracle-audit.42, test-oracle-audit.43, test-oracle-audit.44, test-oracle-audit.45, test-oracle-audit.46
  **Contracts**: contracts/schemas/analysis-report.schema.json
  **Design decisions**: D10
  **Dependencies**: 1.3
- [ ] 6.4 Implement `analysis.py` with standard-library statistics only. [M]
  **Dependencies**: 6.3
- [ ] Checkpoint: run the package tests, review the diff, verify scope.
- [ ] 6.5 Write failing disagreement and report tests. [S]
  - `weak_assertions` and `static_blind_spot` are listed.
  - The first line says the report is advisory.
  - Degraded stages show as `not run` with counts.
  - The "Open decisions" section lists the coverage-ratchet options and the marker question.

  **Spec scenarios**: test-oracle-audit.47, test-oracle-audit.48, test-oracle-audit.53, test-oracle-audit.54, test-oracle-audit.55
  **Contracts**: contracts/schemas/analysis-report.schema.json
  **Design decisions**: D11, D13
  **Dependencies**: 6.4
- [ ] 6.6 Implement `disagreement.py`. [S]
  **Dependencies**: 6.5
- [ ] 6.7 Implement `report.py`. [S]
  **Dependencies**: 6.6

## 7. Skill-audit test-policy lens (wp-skill-audit-lens)

- [x] 7.1 Confirm that `add-skill-audit` is merged to `main` (it is, as of 2026-10-13: 31/31 tasks,
  validation pass). If it is not yet archived, archive it with `/cleanup-feature` when the operator
  allows; do not block on the archive, since the schema edit here is append-only over the merged
  file (D12). Record the outcome. [XS]
  **Design decisions**: D12
  **Dependencies**: None
- [x] 7.2 Write failing lens tests in `skills/tests/skill-audit/`. [S]
  - A coverage-gate instruction gives `test_coverage_target`.
  - Same-context red/green gives `test_same_context_authorship`.
  - Every committed ledger under `docs/reports/skill-audit/` validates against the extended schema.
  - No backend gives `unclassified` and no finding.

  **Spec scenarios**: test-oracle-audit.49, test-oracle-audit.50, test-oracle-audit.51, test-oracle-audit.52
  **Contracts**: contracts/schemas/skill-audit-kinds.delta.json
  **Design decisions**: D12
  **Dependencies**: 7.1
- [x] 7.3 Append the three kinds to `KINDS` and to the schema enum in both
  `skills/skill-audit/install_assets/...` and `openspec/schemas/...`. [XS]
  **Dependencies**: 7.2
- [x] 7.4 Implement `test_policy_lens.py` and the `--lens test-policy` flag in `skill_audit.py`,
  writing `<skill>-test-policy-findings.json` and `<skill>-test-policy-<date>.md` beside, never
  over, the rightsizing outputs (D12). [M]
  **Dependencies**: 7.3
- [x] 7.5 Document the lens in `skills/skill-audit/SKILL.md` (Arguments and Output only), then run
  `skills/install.sh` to sync the runtime copies. [XS]
  **Dependencies**: 7.4
- [x] 7.6 Run the lens over `test-driven-development`, `simplify`, `implement-feature`,
  `validate-feature` and `iterate-on-implementation`. Commit the ledgers under
  `docs/reports/skill-audit/`. [S]
  **Design decisions**: D12
  **Dependencies**: 7.5
- [x] Checkpoint: run `skills/tests/skill-audit`, review the diff, verify scope.

## 8. Integration (wp-integration)

- [ ] 8.1 Write a failing end-to-end dry-run test. [S]
  - The CLI runs every stage over the committed fixture repo with no keys.
  - Afterwards, `git status --porcelain` over the fixture's source and test dirs is empty, and no
    test, conftest or pyproject file is modified.

  **Spec scenarios**: test-oracle-audit.5, test-oracle-audit.6
  **Design decisions**: D3, D15
  **Dependencies**: 2.2, 2.4, 3.5, 3.8, 4.2, 5.2, 5.4, 6.2, 6.7
- [ ] 8.2 Implement `cli.py` with the subcommands `inventory`, `static`, `judge`, `mutate`,
  `refactor`, `history`, `explain`, `label`, `analyze`, `report` and `run-all`. [S]
  **Dependencies**: 8.1
- [ ] 8.3 Add the `test-oracle-audit-tests` CI job, modeled on `system-one-decisions-tests`.
  Confirm `skills/tests/ci_coverage` still passes. [S]
  **Dependencies**: 8.2
- [ ] 8.4 Write the package `README.md`: stages, run commands, environment prerequisites (D15), and
  the reuse notes for ri-07 and ri-08. [XS]
  **Dependencies**: 8.2
- [ ] 8.5 Use `/refine-roadmap` to add notes to `skill-rightsizing` ri-07 and ri-08 that point to
  `MutationRunner` and `LabelLedger`. [XS]
  **Dependencies**: 8.2
- [ ] Checkpoint: run the package tests plus the CI-equivalent command, review the diff, verify scope.

## 9. Pilot run (wp-pilot-run)

- [ ] 9.1 Run `git fetch --unshallow` (operator environment). Record the resulting depth. [XS]
  **Design decisions**: D6, D15
  **Dependencies**: 8.2
- [ ] 9.2 Run the deterministic stages (inventory, static, mutation, rename, history) over both
  pilot suites. Verify the read-only NFR, the ≤ 2 min budget for inventory + static + history
  (timed), and the mutation wall-clock budget. [M]
  **Design decisions**: D3, D4, D5, D6
  **Dependencies**: 9.1
- [ ] 9.3 **[human]** Labelling session. Present the 40 seeded cards one at a time; the operator
  chooses each label. Commit the ledger. [M]
  **Design decisions**: D9
  **Dependencies**: 9.2
- [ ] 9.4 **[operator-env]** Live judged run with `TYPESAFE_API_KEY`. Record the summed
  `usage_input_tokens` from the `event_sink` telemetry and the input-token price in effect, and
  check the product against the ≤ $1.00 NFR. If no key is available, record `not run` and
  leave validation Gate 2 open (D15). [S]
  **Design decisions**: D7, D15
  **Dependencies**: 9.2
- [ ] 9.5 Run the explanation stage over flagged tests with an available LLM backend. [S]
  **Design decisions**: D8
  **Dependencies**: 9.4
- [ ] 9.6 Run the analysis, then render and commit the report and machine-readable analysis under
  `docs/reports/test-oracle-audit/<date>/` (the newest dated directory is the current report; no
  `latest` symlink). [S]
  **Design decisions**: D10, D11, D13
  **Dependencies**: 9.3, 9.5
- [ ] 9.7 Draft the follow-up linter proposal stub. List only the candidates that passed their
  decision rules, carry the open decisions forward, and cite the lens ledgers from 7.6 when they
  are committed (the stub does not wait for them). [S]
  **Design decisions**: D10, D13
  **Dependencies**: 9.6
- [ ] Checkpoint: confirm the report is committed, the NFR table is checked off with evidence, and every open decision is recorded.
