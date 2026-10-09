## ADDED Requirements

### Requirement: Oracle-Source Vocabulary and Label Ledger

The system SHALL define a closed oracle-source vocabulary of exactly seven values (`spec`, `property`,
`reference_impl`, `external_contract`, `characterization`, `current_impl_output`, `none`), with a
fixed binary partition into intent-derived (`spec`, `property`, `reference_impl`,
`external_contract`) and not-intent-derived (`characterization`, `current_impl_output`, `none`).
The system SHALL record human oracle-source labels in a sidecar label ledger keyed by pytest node id
and a normalized content hash of the test function. It SHALL NOT edit test files or register pytest
markers.

#### Scenario: Label is recorded with the test's content hash

- **WHEN** an operator labels test `tests/test_x.py::test_y` as `spec`
- **THEN** the ledger entry contains the node id, the sha256 of the `ast.unparse`-normalized test function source, the label, the labeller and a timestamp
- **AND** the ledger validates against `label-ledger.schema.json`

#### Scenario: Label goes stale when the test changes

- **WHEN** a labelled test function's logic is edited after labelling
- **THEN** loading the ledger reports that entry as `stale`
- **AND** the analysis excludes it

#### Scenario: Whitespace-only edits do not invalidate a label

- **WHEN** a labelled test function changes only in whitespace or comments
- **THEN** its content hash is unchanged and the label remains current

#### Scenario: Unknown label value is rejected

- **WHEN** a label outside the seven-value vocabulary is submitted
- **THEN** the ledger rejects it with an error naming the allowed values

#### Scenario: Audit leaves test files and pytest configuration untouched

- **WHEN** the full pipeline, including labelling, runs over a suite
- **THEN** no test file, `conftest.py`, or `pyproject.toml` in the audited project is modified

### Requirement: Read-Only Audit Execution

The audit SHALL NOT modify any file under the audited source or test directories. Stages that change
code (mutation, rename survival) MUST operate only on an isolated copy that is removed when the stage
exits. The audit SHALL write only to its `--out` directory and the label ledger path.

#### Scenario: Full pipeline leaves the working tree clean

- **WHEN** every stage runs in dry-run mode against the fixture repository
- **THEN** `git status --porcelain` over the fixture's source and test directories is empty afterwards

#### Scenario: Isolated copy is removed after a failing stage

- **WHEN** a mutation or rename stage raises midway
- **THEN** its isolated copy directory no longer exists after the stage returns

### Requirement: Test Inventory

The system SHALL enumerate the tests of a named suite as entries carrying the pytest node id, content
hash, file path, line range, the fixtures the test uses, and the source modules the test reaches by
import. The ordering SHALL be deterministic for identical inputs.

#### Scenario: Inventory is deterministic

- **WHEN** the inventory is built twice over an unchanged suite
- **THEN** both runs produce byte-identical `inventory.jsonl`

#### Scenario: Parametrized tests are distinct entries sharing one content hash

- **WHEN** a test is parametrized with three cases
- **THEN** the inventory has three node ids that all carry the same content hash

### Requirement: Deterministic Static Test Checks

The system SHALL run AST-only checks per test and record each fired rule by stable rule id:
`assertion_free`, `mock_assertion_dominant`, `private_attribute_assert`, `private_import`,
`mirrored_test_file`, `unscoped_patch`. Static checks SHALL NOT execute test code.

#### Scenario: Assertion-free test is flagged

- **WHEN** a test function contains no `assert` statement, no `pytest.raises`/`pytest.warns` context, and no call to an `assert*` method
- **THEN** its static record contains rule `assertion_free`

#### Scenario: Mock-dominant test is flagged

- **WHEN** a test's mock interaction assertions (`assert_called*`, `call_count`, `call_args`) outnumber its other assertions
- **THEN** its static record contains rule `mock_assertion_dominant`

#### Scenario: Assertion on a private attribute is flagged

- **WHEN** a test asserts on an attribute whose name matches `^_[^_]` of an object from the code under test
- **THEN** its static record contains rule `private_attribute_assert`

#### Scenario: Behaviour-only test fires no rule

- **WHEN** a test calls only public functions and asserts on their return values
- **THEN** its static record has an empty rule list and status `ok`

### Requirement: Judged Oracle Assessment in Shadow Mode

The system SHALL ask, per test, an `oracle_source` choice over the vocabulary, a
`survives_refactor` noul, and a `boundary` choice, through `system_one_decisions.decide()` with site
`test-oracle-audit.judge`. Judged answers SHALL be stored as probabilities with
`evidence_class: judgment` and SHALL NOT affect any exit code or gate. The judged state MUST NOT
include static, mutation, rename, history or human-label outputs. Display thresholds SHALL be read
from the package configuration file, not from literals.

#### Scenario: Judged answers are recorded as judgment evidence

- **WHEN** `decide()` returns answers for a batch of tests
- **THEN** each test's judged record stores the full probability distributions and `evidence_class: judgment`

#### Scenario: Missing key degrades without failing

- **WHEN** `TYPESAFE_API_KEY` is unset or `--dry-run` is given
- **THEN** every judged record has status `degraded` with a reason
- **AND** the command exits 0

#### Scenario: Judged state is blind to other approaches

- **WHEN** a judged call is constructed for a test that has static flags, mutation results and a human label
- **THEN** the `state` passed to `decide()` contains none of those values

#### Scenario: Over-budget state is recorded, not truncated silently

- **WHEN** a test's state exceeds the 32K-token budget
- **THEN** its judged record has status `degraded` with reason `over_budget`

#### Scenario: Judged findings never change the exit code

- **WHEN** every judged answer assigns probability above 0.9 to `current_impl_output`
- **THEN** the judge command still exits 0

### Requirement: Mutation Runner With Per-Test Kill Attribution

The system SHALL provide a public `MutationRunner` interface whose results attribute each mutant to
the tests that cover it and the tests that kill it. It SHALL bound runs by a maximum mutant count
with seeded sampling stratified by source module. It SHALL record which backend produced each
result. The per-test kill rate SHALL be reported as `insufficient` when fewer than five mutants fall
in functions the test covers.

#### Scenario: Kill is attributed to the failing test only

- **WHEN** a mutant in function `f` is covered by tests A and B and only A fails
- **THEN** the mutant result lists A and B in `covered_by` and only A in `killed_by`

#### Scenario: Seeded sampling is reproducible

- **WHEN** the runner is invoked twice with the same `--seed` and `--max-mutants`
- **THEN** the same mutant ids are selected

#### Scenario: Sampling is spread across modules

- **WHEN** one module has ten times more candidate mutants than another
- **THEN** both modules are represented in a sample smaller than the total candidate count

#### Scenario: Fallback backend is used when mutmut cannot run

- **WHEN** the mutmut backend's probe fails for a suite
- **THEN** the AST mutant backend runs instead
- **AND** every result records `backend: ast`

#### Scenario: Low-coverage test is insufficient

- **WHEN** a test covers functions containing four sampled mutants
- **THEN** its kill rate is reported as `insufficient`

### Requirement: Refactor Survival via Private-Symbol Rename

The system SHALL apply a behaviour-preserving rename of eligible private symbols (`^_[^_]`) across the
source tree of an isolated copy, never in tests, and record per test whether it still passes. Names
listed in `__all__`, appearing as string literals in the source tree, or re-exported by a public
module SHALL be excluded and counted as `unrenamable`.

#### Scenario: Test reaching a private helper breaks

- **WHEN** a test imports or patches `module._helper`
- **THEN** after the rename its record has `survives: false`

#### Scenario: Public-only test survives

- **WHEN** a test uses only public names of the module under test
- **THEN** after the rename its record has `survives: true`

#### Scenario: String-referenced private name is not renamed

- **WHEN** a private name also appears as a string literal in the source tree
- **THEN** it is not renamed and is counted under `unrenamable` for its module

### Requirement: Git History Signals

The system SHALL compute, per test, a `co_change_ratio` (the fraction of commits changing a covered
source module that also changed the test's assertion lines) and `added_with_fix` (the commit adding
the test is a conventional `fix`). The history stage SHALL NOT fetch or unshallow. On a shallow
clone it SHALL record `degraded` with reason `shallow_history`.

#### Scenario: Shallow clone degrades

- **WHEN** the repository is shallow
- **THEN** every history record has status `degraded` and reason `shallow_history`
- **AND** no git network command is run

#### Scenario: Small denominator is insufficient

- **WHEN** fewer than three commits changed the test's covered source modules
- **THEN** the test's `co_change_ratio` is `insufficient`

#### Scenario: Regression pin is detected

- **WHEN** a test function was introduced in a commit whose subject begins `fix(`
- **THEN** its record has `added_with_fix: true`

### Requirement: Explanations for Flagged Tests Only

The system SHALL send to an explanation backend only tests flagged by at least one measured approach.
It SHALL record prose of at most 600 characters and one advisory action from `keep`,
`strengthen_assertions`, `rewrite_from_spec`, `declare_characterization`, or `delete_candidate`.
Explanation output MUST NOT be used as ground truth or as a measured approach.

#### Scenario: Unflagged tests are not sent

- **WHEN** a test fires no static rule, is judged intent-derived, has a mid or top kill-rate tercile, survives the rename, and has a low co-change ratio
- **THEN** no explanation request is made for it

#### Scenario: No backend degrades

- **WHEN** no explanation backend is available
- **THEN** each flagged test's explanation record has status `degraded` with reason `no_backend`

#### Scenario: Explanation never feeds analysis

- **WHEN** the analysis runs over records that include explanations
- **THEN** no agreement or predictive metric reads the explanation's action

### Requirement: Blind Stratified Human Labelling

The system SHALL draw a seeded labelling sample stratified by static-flag presence and mutation
kill-rate tercile (plus an `insufficient` stratum), render one card per test showing only the test,
the covered functions' signatures and docstrings, and any cited spec scenario, and record one
operator decision per card in the label ledger.

#### Scenario: Sample covers every non-empty stratum

- **WHEN** a sample of 40 is drawn from a suite in which all seven strata are non-empty
- **THEN** every stratum contributes at least one test

#### Scenario: Card hides other approaches' outputs

- **WHEN** a card is rendered for a test that has judged, static, mutation and history records
- **THEN** the card text contains none of those outputs

### Requirement: Agreement and Predictive Analysis

The system SHALL compute:

- Cohen's kappa, seven-class and binary, between judged `oracle_source` and human labels;
- the Brier score of judged `survives_refactor` against observed rename survival, compared to the
  base-rate Brier score;
- Cliff's delta of mutation kill rate between tests each static rule flags and tests it does not;
- AUC with a Youden's-J threshold for continuous predictors against the binary human label.

Every metric SHALL carry n and a seeded bootstrap 95% confidence interval. A metric with n < 20 SHALL
be reported `insufficient` with no point estimate. A judged question with binary kappa below 0.7, or
a Brier score not better than base rate, SHALL be excluded from linter candidates. A static rule
whose Cliff's delta interval includes zero SHALL be marked not predictive. Derived thresholds SHALL
be marked provisional.

#### Scenario: Perfect agreement yields kappa 1

- **WHEN** judged top labels equal human labels on 25 tests spanning at least two classes
- **THEN** kappa is 1.0

#### Scenario: Small n is insufficient

- **WHEN** only 12 tests have both a human label and a judged answer
- **THEN** the kappa cell is `insufficient` and has no point estimate

#### Scenario: Low-agreement question is excluded

- **WHEN** binary kappa for `oracle_source` is 0.55
- **THEN** the report lists `oracle_source` under excluded linter candidates, citing the 0.7 floor

#### Scenario: Non-predictive static rule is marked

- **WHEN** a static rule's Cliff's delta confidence interval spans zero
- **THEN** the report marks that rule `not_predictive`

#### Scenario: Bootstrap is reproducible

- **WHEN** the analysis runs twice with the same seed and inputs
- **THEN** every confidence interval is identical

### Requirement: Disagreement Report

The system SHALL produce a disagreement report listing, by named class, the tests where approaches
disagree:

- `weak_assertions`: intent-derived but kill rate in the bottom tercile;
- `static_blind_spot`: no static flag but `current_impl_output`;
- `coupled_spec_test`: intent-derived but broken by the rename;
- `judge_vs_human`: binary classes differ;
- `rubber_stamp`: co-change ratio above threshold while kill rate is not in the bottom tercile.

#### Scenario: Weak assertion is listed

- **WHEN** a test is human-labelled `spec` and its kill rate is in the bottom tercile
- **THEN** it appears under `weak_assertions`

#### Scenario: Static blind spot is listed

- **WHEN** a test fires no static rule and is human-labelled `current_impl_output`
- **THEN** it appears under `static_blind_spot`

### Requirement: Skill-Audit Test-Policy Lens

The skill-audit skill SHALL provide a `--lens test-policy` mode that extracts test-prescribing
instructions from a SKILL.md and classifies each on two axes:

- oracle source: `spec_derived`, `impl_derived` or `unspecified`;
- authorship: `separate_context`, `same_agent` or `unspecified`.

The mode SHALL emit findings of the kinds `test_oracle_impl_derived`,
`test_same_context_authorship` and `test_coverage_target`. The findings-schema `kind` enum SHALL be
extended append-only, so that every previously valid ledger remains valid. When neither a judge nor
a model backend is available, unresolved instructions SHALL be `unclassified`, never guessed. The
lens SHALL be read-only over the audited skill.

#### Scenario: Coverage gate instruction is found

- **WHEN** the lens audits a skill whose instruction requires that coverage not decrease
- **THEN** the ledger contains a `test_coverage_target` finding citing that section

#### Scenario: Same-agent authorship is found

- **WHEN** the lens audits a skill instructing one agent to write a failing test and then the implementation in the same context
- **THEN** the ledger contains a `test_same_context_authorship` finding

#### Scenario: Existing ledgers still validate

- **WHEN** the extended schema validates every committed ledger under `docs/reports/skill-audit/`
- **THEN** all of them pass

#### Scenario: No backend yields unclassified

- **WHEN** an instruction is not matched by the regex pre-pass and no judge or model backend is available
- **THEN** its classification is `unclassified` and no finding is emitted for it

### Requirement: Pilot Report With Open Decisions

The system SHALL render a stamped pilot report under `docs/reports/test-oracle-audit/` that states on
its first line that it is advisory. The report SHALL contain:

- per-approach coverage counts, including `degraded` and `insufficient` counts;
- the analysis tables;
- the linter-candidate and excluded lists;
- the disagreement report;
- an "Open decisions" section that records the coverage-ratchet options and the in-file-marker
  question.

Rendering the report SHALL NOT change the coverage-ratchet baseline, any spec, or any skill.

#### Scenario: Report states its advisory status

- **WHEN** a report is rendered
- **THEN** its first line declares it advisory and not a gate

#### Scenario: Degraded stages are visible

- **WHEN** the judged stage ran in dry-run
- **THEN** the report shows the judged approach as `not run` with its degraded count, rather than omitting it

#### Scenario: Open decisions are recorded

- **WHEN** a report is rendered
- **THEN** its "Open decisions" section lists the coverage-ratchet options (keep, deletion manifest, mutation-score ratchet) and the in-file-marker question
