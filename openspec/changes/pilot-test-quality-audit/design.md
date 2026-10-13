# Design: pilot-test-quality-audit

## Context

The proposal sets the goal: measure, before formalizing, whether candidate test-linter rules
predict weak tests. A weak test is one whose expected values restate the implementation instead of
the intent. This design fixes the package shape, the vocabulary, how each of the four approaches
produces evidence, how ground truth is formed, and how the approaches are compared.

The discovery answers that constrain it are recorded under "Selected Approach" in the proposal:

- reusable modules for ri-07 and ri-08;
- the pilot slice `test_evaluation` plus `skills/tests/parallel-infrastructure`;
- a sidecar ledger, with no edits to test files;
- proxies plus about 40 human labels as ground truth.

Two facts about the environment shape it as well. The planning clone is shallow (255 commits), and
neither `TYPESAFE_API_KEY` nor an LLM API key is present in the planning session.

## Goals / Non-Goals

**Goals**

- One runnable, read-only pipeline that produces, per test: static flags, judged answers,
  execution evidence and history signals, joined on a stable test identity.
- Ground truth that does not come from any of the approaches being measured.
- Agreement and predictive metrics that report n and confidence intervals, and say "insufficient"
  instead of producing a number from too little data.
- Public modules that ri-07 (mutation) and ri-08 (labels, kappa) can import unchanged.

**Non-Goals**

- A CI linter, or any blocking gate.
- Editing or deleting tests, or registering pytest markers.
- Promoting any judgment to an acting decision. That is owned by
  `promote-shadow-judgments-to-acting-decisions`.
- Changing the coverage-ratchet policy. It is recorded as an open decision (D13).

## Decisions

### D1: Package layout and the record join

`packages/test-oracle-audit/src/test_oracle_audit/` has one module per stage:

| Module | Stage | Public entry point |
|---|---|---|
| `records.py` | identity + envelopes | `TestId(node_id, content_hash)`, `StageRecord`, `read_records`, `write_records` |
| `vocabulary.py` | oracle-source vocabulary | `ORACLE_SOURCES`, `INTENT_DERIVED`, `IMPL_DERIVED` |
| `thresholds.py` | config + shared cut-points (owned by wp-contracts) | `load_thresholds()`, `tercile_cutpoints(values) -> (t1, t2)`, `tercile_of(value, cuts)` |
| `schemas/*.schema.json` | runtime copies of `contracts/schemas/` | loaded by `records.py` validation and `cli.py report --validate` |
| `inventory.py` | inventory | `build_inventory(suite: SuiteSpec) -> list[TestEntry]`; `SuiteSpec(name, project_root, test_paths, source_roots, pytest_args)` from `config/suites.json` |
| `static_checks.py` | static | `run_static(entries) -> list[StageRecord]`; the six rules are defined normatively in the spec's "Deterministic Static Test Checks" requirement |
| `judged.py` | Jev | `run_judged(entries, *, dry_run) -> list[StageRecord]` |
| `isolation.py` | sandbox copy | `isolated_copy(repo_root, paths) -> ContextManager[Path]` |
| `mutation.py` | mutation | `MutationRunner` protocol, `MutmutRunner`, `AstMutantRunner`, `run_mutation(...)` |
| `refactor.py` | rename survival | `run_rename_survival(entries, suite) -> list[StageRecord]` |
| `history.py` | git signals | `run_history(entries, repo_root) -> list[StageRecord]` |
| `explain.py` | LLM prose | `ExplainBackend` protocol, `run_explain(flagged, backend)` |
| `ledger.py` | label ledger (shared contract, owned by wp-contracts) | `LabelLedger.load/add/save`, `LabelState{current, stale}` |
| `labelling.py` | sampling + cards | `stratified_sample`, `render_card` |
| `analysis.py` | metrics | `cohen_kappa`, `brier`, `bootstrap_ci`, `cliffs_delta`, `analyze(...)` |
| `disagreement.py` | disagreement classes (D11) | `classify_disagreements(joined) -> dict[str, list[str]]` |
| `report.py` | report | `render_report(analysis, disagreements) -> str` |
| `cli.py` | CLI | `test-oracle-audit <stage> --suite <name> --out <dir> [--dry-run]` |

- **Test identity.** Every stage emits `StageRecord(test_id, stage, status, payload)` to
  `<out>/<stage>.jsonl`. `test_id` is the pytest node id plus `content_hash`, a sha256 of the
  test function's source after `ast.unparse` normalization. Normalizing makes the hash ignore
  whitespace and comments but change with any edit to the test's logic.
- **Status.** `status ∈ {ok, degraded, skipped, error}`. A `degraded` record carries a `reason`.
  No stage raises on unavailable dependencies.
- **Joining.** Stages are independent and can be re-run. `analysis.py` joins the stage records on
  `test_id`.
- **Suite environment.** Collection (inventory) and every test execution (mutation, rename) run
  as a subprocess `uv run --project <SuiteSpec.project_root> --with pytest-cov --with
  "mutmut>=3.8,<4" pytest <SuiteSpec.pytest_args> ...` (for the `skills/` suite:
  `--import-mode=importlib`). `--with` overlays the audit's tools on the suite's own environment
  without editing its `pyproject.toml` or lockfile, which neither suite declares `pytest-cov`,
  `mutmut` or `libcst` in. Inside an isolated copy, `project_root` is the copy's project. The
  package's own interpreter never imports audited test modules. `config/suites.json` holds the
  two pilot `SuiteSpec`s (`test_evaluation`: project `agent-coordinator`, source root
  `agent-coordinator/evaluation`; `parallel_infrastructure`: project `skills`, source root
  `skills/parallel-infrastructure/scripts`); the CLI's `--suite <name>` selects one.
- **Schema runtime copy.** `contracts/schemas/*.schema.json` is the source of truth while the
  change is active, but it moves on archive and is not importable by ri-07 or ri-08. The package
  therefore ships byte-identical copies under `src/test_oracle_audit/schemas/`, and a contract test
  (task 1.1) asserts the parity, resolving the change directory with `change_dir()` so the test
  survives archival. `report --validate` and `records.py` read only the runtime copies.
- **Shared cut-points.** Explain (D8), labelling strata (D9), analysis (D10) and the disagreement
  classes (D11) all need the same kill-rate terciles. `thresholds.tercile_cutpoints` computes them
  once, per suite, over tests with a numeric kill rate (33.3rd and 66.7th percentiles, linear
  interpolation); the cut-points are written into `analysis.json`. Display thresholds
  (`judged_impl_derived_p`, `co_change_high`) come from `config/thresholds.json` through
  `load_thresholds()`; no module holds a threshold literal.
- **Test tree ownership.** `tests/conftest.py` belongs to wp-contracts and holds only
  `schema_validator` and `fixture_project` (judged tests import
  `system_one_decisions.testing.stub_decide` directly). Stage packages keep their
  helpers inside their own `test_<stage>*.py` modules, so the five parallel packages never touch a
  shared test file.
- **Reused code.** Inventory reuses the import-based test-to-module mapping from
  `skills/refresh-architecture/scripts/insights/test_linker.py`. History reuses the assertion-line
  diff scanner from `skills/simplify/scripts/check_test_contract.py`. Both are **vendored as small
  adapted functions with a provenance comment**, not imported across trees. That keeps the
  package's import graph self-contained, the same constraint that makes `system-one-decisions`
  dependency-free.

### D2: Oracle-source vocabulary

The vocabulary answers: *where do this test's expected values come from?*

| Value | Meaning | Class |
|---|---|---|
| `spec` | A stated requirement, scenario or documented contract of the unit under test | intent-derived |
| `property` | An invariant or relation that must hold for all inputs (round-trip, idempotence, ordering) | intent-derived |
| `reference_impl` | An independent computation of the same answer (oracle function, known-good table) | intent-derived |
| `external_contract` | A schema, protocol or third-party format the code must conform to | intent-derived |
| `characterization` | Today's behaviour, **deliberately** frozen to guard a refactor (`simplify`'s pattern) | impl-derived, declared |
| `current_impl_output` | Today's output copied into the assertion **without** a stated reason | impl-derived, undeclared |
| `none` | The test asserts nothing about outputs (smoke, no-crash, or only mock interactions) | no oracle |

- The binary split used throughout the analysis is **intent-derived** (the first four values)
  vs **not intent-derived** (the last three).
- `characterization` is separate from `current_impl_output` because the first is a legitimate
  declared practice and the second is the failure mode. A future linter must be able to tell them
  apart, so the labels must too.

### D3: Read-only by construction

- Mutation and rename-survival only ever run inside an `isolated_copy`. That is a
  `git worktree add --detach` of HEAD into a scratch directory when available, falling back to
  `shutil.copytree` of the suite's source and test roots. The copy is removed on exit.
- The package writes only to `--out` and to the label ledger path.
- Audited tests may have side effects of their own (temp files, caches, `~/.config`). Every test
  run inside the copy sets `HOME`, `TMPDIR`, `XDG_CACHE_HOME` and `XDG_CONFIG_HOME` to a scratch
  directory beside the copy, passes `--basetemp` under it and `-p no:cacheprovider`, and runs
  with `cwd` set to the copy. The copy is a `git worktree` of HEAD, so uncommitted edits in the
  real tree are not audited; the pilot run therefore starts from a clean, committed tree. On exit
  the stage removes the worktree and runs `git worktree prune`.
- An end-to-end test runs the full dry-run pipeline against a fixture repo and asserts
  `git status --porcelain` is empty over the fixture's source and test directories.

### D4: Mutation: mutmut generates mutants, our runner attributes kills to tests

- **Why we run the mutants ourselves.** Per-test kill attribution is the measurement we need.
  mutmut's own result is per mutant ("killed" or "survived") and doesn't say which tests killed it.
- **`MutmutRunner`.**
  - Inside the isolated copy, it writes a `[tool.mutmut]` section into the copy's
    `pyproject.toml`, never the real one.
  - It uses mutmut 3.x to generate mutants and trampolines for the sampled source modules.
  - For each sampled mutant, it runs the tests that cover the mutated function with
    `MUTANT_UNDER_TEST=<id>` and reads per-test outcomes from JUnit XML.
  - Covering tests come from one coverage run with dynamic contexts (`--cov-context=test`),
    executed in the suite environment (D1) so the coverage plugin and the trampolines resolve
    there. The spike (3.1) confirms both resolve under `uv run --with`.
- **Mutant record.** Each mutant becomes
  `MutantResult(mutant_id, module, function, operator, covered_by[], killed_by[], status)`.
- **Per-test kill rate.**
  `killed_by-count / covered_by-count` over the mutants in functions the test covers. It is
  undefined (`insufficient`) below 5 covering mutants.
- **`AstMutantRunner`.** A fallback with no third-party dependencies. It applies four operators:
  comparison flip, boolean negate, constant perturbation, and `return` → `return None`. It runs
  covering tests the same way.
  - It is chosen automatically when the spike (task 3.1) or a runtime probe shows mutmut cannot
    handle the suite layout. The `skills/` tests use `--import-mode=importlib` and `sys.path`
    inserts, which are the likely problem.
  - The backend used is recorded in every record.
- **Bounds.** `--max-mutants N` (default 400) and `--seed`. Sampling is stratified by source
  module, so one large module (e.g. the 3.6k-line `review_dispatcher.py`) cannot take the budget.
- **Reuse by ri-07.** ri-07 imports `MutationRunner` and `run_mutation` and aggregates per-suite
  scores. The public signatures are a contract (`contracts/schemas/mutation-result.schema.json`).

### D5: Refactor survival means renaming private symbols

- **The refactor.** Inside an isolated copy, `libcst` renames every eligible private symbol in
  the source modules under test, consistently across the **source** tree and never in tests:
  `_name` → `_name__r`. Eligible symbols are module-level and class-level `def`, `class` and
  assignment names matching `^_[^_]`.
- **Why this one.** The rename is provably behaviour-preserving for every caller that uses public
  names. So a test that passes before and fails after is coupled to implementation details, by
  definition.
- **Exclusions.** These are skipped and reported as `unrenamable`:
  - names listed in `__all__`;
  - names that appear as string literals anywhere in the source tree (`getattr`, `patch`
    targets in source, registries);
  - names re-exported by a public module.
- **Procedure.** One pass renames all eligible symbols, then the suite runs once. The result per
  test is `survives: bool`, plus `low_confidence: true` when more than half of the eligible
  symbols in any module the test covers were `unrenamable` (the risk noted below).
- **Why not more refactors.** Richer refactors (extract or inline function, reordering) were
  rejected: proving them behaviour-preserving would need a test oracle, which is what's being
  measured.

### D6: History signals need full history and never fetch

- `run_history` checks `git rev-parse --is-shallow-repository`. If the clone is shallow, every
  record is `degraded` with `reason: shallow_history` and the depth. The stage never unshallows,
  because that would be a network side effect in a read-only tool. The pilot-run task does
  `git fetch --unshallow` explicitly.
- **co_change_ratio.**
  - Look at commits that change any covered source module. Count those in which the same commit
    also changed this test function's assertion lines. The function's line range at a commit
    comes from parsing `git show <sha>:<path>` with `ast`; lines are mapped by diff hunks over
    that range, and assertion lines are detected with the vendored scanner. A commit in which the
    function cannot be found by name (not yet added, or renamed) is skipped for that test.
  - The ratio is that count divided by all such commits.
  - The denominator must be at least 3, otherwise the result is `insufficient`.
  - A high ratio means the test is routinely rewritten to match the code.
- **added_with_fix.** The commit that introduced the test function is the oldest commit, with
  `--follow` for file renames, in which `def <test_name>(` is present in the test file (found with
  `git log -S` and confirmed by parsing that revision). It has a conventional-commit type
  of `fix`, matched as `^fix(\([^)]*\))?!?:`. That covers unscoped `fix:` and scoped
  `fix(scope):`, with or without the `!` breaking marker, and excludes `fixup!` and every other
  type. This marks a regression test added with the fix (the Prove-It pattern), a positive
  signal.

### D7: The judged stage is batched, blind, shadow-only, and takes thresholds from config

- **Call.** Calls go through `system_one_decisions.decide(state, questions, site="test-oracle-audit.judge",
  dry_run=...)`. The module is imported as a module, never as a pre-bound name, per
  `system_one_decisions.testing`'s stubbing rule. The SDK is never imported directly, which keeps
  the repo-wide guard `test_no_sdk_import_outside_package.py` green.
- **Questions per test**, keyed `t<i>.<q>`:
  - `oracle_source`: a `choice` over the D2 vocabulary, with `none` as the no-match option.
  - `survives_refactor`: a `noul` question, "This test would still pass if every private helper in
    the code under test were renamed."
  - `boundary`: a `choice` over `{pure_function, module_api, service_api, ui, mixed}`. This answer
    is descriptive, never a decision input: the disagreement report (D11) prints each test's top
    boundary label, and the report splits the `mock_assertion_dominant` vs kill-rate comparison by
    boundary ∈ {`pure_function`, `module_api`} vs the rest, so a reviewer can tell mock-heavy
    tests at a service boundary from mock-heavy tests of a pure function. Both splits obey the
    n < 20 → `insufficient` rule.
- **State.** The state holds:
  - the test function plus the fixtures it uses;
  - the bodies of the covered source functions, truncated;
  - the test module docstring;
  - any spec scenario text the test cites, when a docstring names a `specs/<cap>` requirement.

  It never contains static flags, mutation or rename results, history signals or human labels.
  That keeps the approaches independent, so their disagreements mean something (blind, per
  ri-08).
- **Batching.** One `decide()` call per test file when its state fits the 32K-token budget,
  otherwise one call per test. `decide()` returns `None` over budget, and that test is recorded
  `degraded: over_budget`.
- **Shadow only.** Answers are stored as probabilities with `evidence_class: judgment`. Nothing in
  the package exits non-zero on a judged answer.
- **Thresholds.** Display thresholds, e.g. what counts as "judged impl-derived" in the
  disagreement report, come from `test_oracle_audit/config/thresholds.json`, never from literals.
  This mirrors the `system-one-decisions` threshold rule. Analysis (D10) replaces them with
  data-derived values.

### D8: The explanation stage

- **Input.** Only tests flagged by at least one approach are sent:
  - any static rule fired;
  - Jev's `P(intent-derived)` is below the display threshold;
  - kill rate is in the bottom tercile (cut-points from `thresholds.tercile_cutpoints` over the
    suite's `mutation.jsonl`; a test with `insufficient` kill rate is not flagged by this rule);
  - the rename broke the test;
  - `co_change_ratio` is above the display threshold.
- **Backend.** An `ExplainBackend` protocol with the shape of `gen_eval`'s backend (`run(prompt,
  system) -> str`). The CLI adapter uses `skills/quick-task`-style vendor discovery. With no
  backend, records are `degraded: no_backend`.
- **Output.**
  - Prose of at most 600 characters.
  - One advisory action from `{keep, strengthen_assertions, rewrite_from_spec,
    declare_characterization, delete_candidate}`.
- **Not measured.** The explainer sees all evidence, because explaining is its job. For the same
  reason it is **not** one of the measured approaches, and its action is never used as ground
  truth.

### D9: Human labelling is stratified, seeded and blind

- **Sample.** `stratified_sample(entries, n=40, seed)` draws across a 2×3 grid: any-static-flag
  (yes/no) × mutation kill-rate tercile. Tests with `insufficient` kill rate form a seventh
  stratum.
- **Cards.** `render_card` shows:
  - the test source;
  - the covered functions' signatures and docstrings, but not their bodies beyond 40 lines;
  - any cited spec scenario.

  It never shows judged, static, mutation or history outputs (no anchoring).
- **Recording.** The CLI is non-interactive, so an agent harness can drive it:
  `label next --out <dir> [--seed N --n 40]` draws (or reloads) the sample, writes every card to
  `<out>/cards/<index>-<slug>.md`, and prints the next unlabelled card; `label record <node_id>
  <label> [--note ...]` hashes the current test source and appends one ledger entry;
  `label --dry-run` renders cards and never writes the ledger. In an agent session the agent
  relays each card to the operator and records the answer, the way `cite-requirements` does.
- **One labeller.** The pilot assumes a single operator labels all 40 cards; the ledger's
  `labeller` field already distinguishes labellers, and the analysis uses the first entry per
  `test_id`. If a second labeller is added later, the analysis reports inter-rater kappa as one
  more `human_label` metric; nothing else changes. Recorded as an open question below.
- **Ledger.** `LabelLedger` (`ledger.py`) is a JSON file at
  `docs/reports/test-oracle-audit/labels.json` (`contracts/schemas/label-ledger.schema.json`). It
  stores `{test_id, label, labeller, labelled_at, note}`.
- **Staleness.** A label whose `content_hash` no longer matches the current test is reported as
  `stale` and excluded from the analysis.
- **Reuse by ri-08.** ri-08 can reuse the ledger and card renderer for replay outputs by supplying
  its own entry type.

### D10: Analysis metrics, written so a small n cannot overclaim

All statistics are implemented in the standard library only: kappa, Brier, bootstrap, Cliff's
delta and Youden's J are each a few lines. Seeded bootstrap with 2,000 resamples gives 95% CIs.

| Comparison | Metric | Decision rule |
|---|---|---|
| Jev `oracle_source` vs human label | Cohen's kappa, 7-class and binary (D2 split), with CI | binary kappa < 0.7 → Jev question **excluded** from linter candidates (ri-08 floor) |
| Jev `survives_refactor` vs observed rename survival | Brier score vs base-rate Brier; 5-bin reliability table | Brier not better than base rate → excluded |
| Each static rule vs mutation kill rate | Cliff's delta (flagged vs unflagged), CI | CI includes 0 → rule **not predictive** |
| Each static rule vs human binary label | precision / recall, CI | reported only |
| `co_change_ratio` vs human binary label | AUC, CI; threshold by Youden's J | threshold marked **provisional** |
| Jev `P(intent-derived)` vs human label | AUC; threshold by Youden's J | threshold marked **provisional** |

- Any cell with n < 20 is reported `insufficient` and given no point estimate.
- Rename records with `low_confidence: true` (D5) are excluded from the Brier comparison and from
  `coupled_spec_test` (D11); the excluded count is reported in the approach-coverage table.
- Per-suite kill-rate tercile cut-points (D1, `thresholds.tercile_cutpoints`) are written to
  `analysis.json` under `tercile_cutpoints` so the report and the explain stage cite the same
  numbers.
- The report's "linter candidates" list includes only rules and questions that pass their
  decision rule.

### D11: Disagreement report

The disagreement report lists named classes of disagreement, each with its tests:

| Class | Condition | What it suggests |
|---|---|---|
| `weak_assertions` | judged or human intent-derived **and** kill rate in bottom tercile | right oracle, assertions too loose |
| `static_blind_spot` | no static flag **and** judged or human `current_impl_output` | restatement that the AST rules can't see |
| `coupled_spec_test` | labelled intent-derived **and** rename broke it | spec test that reaches through private names |
| `judge_vs_human` | Jev top label's binary class ≠ human binary class | calibration evidence for ri-08 |
| `rubber_stamp` | `co_change_ratio` above threshold **and** kill rate not bottom tercile | rewritten with the code but still catches mutants; inspect |

### D12: Skill-audit test-policy lens

- **Location.** `skills/skill-audit/scripts/test_policy_lens.py`, invoked as
  `skill_audit.py --lens test-policy <skill>`.
- **Extraction.** A regex pre-pass, in the style of `classifier.prepass`, picks out
  test-prescribing instructions: sentences in sections that mention test, assert, coverage, TDD,
  mock, characteriz, red/green, or fixture.
- **Classification.** Each instruction is classified on two axes:
  - *oracle source*: `spec_derived | impl_derived | unspecified`;
  - *authorship*: `separate_context | same_agent | unspecified`.
- **Classifier order.** The regex pre-pass first. Then a `decide()` call with two `choice`
  questions. Then the existing `ModelBackend`. With no judge and no model, the result is
  `unclassified`, never a guess, which is skill-audit's existing rule.
- **New finding `KINDS`:**
  - `test_oracle_impl_derived`: prescribes tests whose expected values come from the
    implementation without declaring them as characterization.
  - `test_same_context_authorship`: has the same agent write both tests and implementation.
  - `test_coverage_target`: uses line coverage as a goal or gate.
- **Schema.** The kinds are appended to the enum in
  `skills/skill-audit/install_assets/openspec/schemas/skill-audit-findings.schema.json` and its
  synced copy `openspec/schemas/skill-audit-findings.schema.json`. The change is append-only, so
  every existing ledger still validates. A test re-validates the committed ledgers under
  `docs/reports/skill-audit/` to prove it.
- **Outputs.** The lens writes `docs/reports/skill-audit/<skill>-test-policy-findings.json` and
  `<skill>-test-policy-<date>.md`. It never overwrites the rightsizing audit's
  `<skill>-findings.json` or its dated report, and it does not count as that skill's freshness
  report, so the `skill-audit-freshness` CI job is unaffected. The ledger-validation test
  (scenario "Existing ledgers still validate") globs `*-findings.json`, which includes the lens
  ledgers.
- **Read-only** over audited skills, as before.
- **Precondition.** `add-skill-audit` is merged to `main` (true as of 2026-10-13: 31/31 tasks,
  validation pass). Archival is preferred but not required: its capabilities
  (`agent-archetypes`, `harness-engineering`, `skill-workflow`) do not overlap `test-oracle-audit`,
  and the schema edit here is append-only over the merged file, so the only race was with an
  unmerged branch. Task 7.1 records whether the archive has happened.

### D13: Coverage ratchet is an open decision, not an action

The pilot report includes a fixed "Open decisions" section. For the coverage ratchet, it records
the options with the pilot's evidence for each:

- **(a)** Keep the line-coverage ratchet.
- **(b)** Allow a coverage drop when it comes with a deletion manifest that cites audit evidence.
- **(c)** Replace it with a mutation-score ratchet, which is ri-07's territory.

The same section records whether oracle-source labels should become in-file pytest markers, plus
a `--strict-markers` note: no suite in the repo uses it today. No ratchet, spec or TDD skill text
changes in this change.

### D14: Dogfooding: this package's tests are written from spec only

The pilot exists to measure whether tests derived from intent beat tests that restate the code, so
the package follows that practice itself:

- **Separate context.** Every test task in `tasks.md` is done by a sub-agent dispatched with only
  the spec deltas, `contracts/`, and this design's decision tables. It has no implementation files
  in context and writes from the scenario IDs it cites. Implementation tasks run after, in a
  different context.
- **Recorded deviations.** A test task that needs an implementation detail the spec doesn't give
  records it as a `skill-procedure-deviation` session-log decision, rather than reading the code.

### D15: CI runs the dry-run; completion needs a live run

- **CI** (`test-oracle-audit-tests` job) runs the package tests and a dry-run pipeline over a
  committed fixture repo, with no keys and no network. Jev and explanation records are
  `degraded`.
- **Live pilot run.** It needs, as operator-environment prerequisites:
  - `TYPESAFE_API_KEY`;
  - an LLM backend;
  - an unshallowed clone.

  Jev spend is measured as the sum of `usage_input_tokens` from `decide()`'s `event_sink`
  telemetry, multiplied by the input-token price in effect in the operator environment, which the
  pilot run records beside the sum; the NFR holds at ≤ $1.00 of that product.

  The change is not complete until a live run's report is committed. If the key cannot be
  provided, the report is committed with the judged stage marked `not run`. Gate 2 of
  `validate-feature` then stays open, with the reason recorded, instead of reporting a pass.

## Risks / Trade-offs

- **mutmut may not handle the `skills/` suite layout** (importlib mode and `sys.path` inserts).
  *Mitigation:* the task 3.1 spike decides early, and `AstMutantRunner` is a fallback with no
  third-party dependencies. The backend is recorded on every result.
- **About 40 labels gives wide CIs.** *Mitigation:* D10 reports CIs and `insufficient`, and calls
  every threshold provisional. The pilot's value is in ruling rules **out**, which needs less data
  than ruling them in.
- **Over-eager exclusions in the rename.** Names in strings are skipped, which can make an
  implementation-coupled test look like it survives. *Mitigation:* `unrenamable` counts are
  reported per module, and a module with more than 50% unrenamable is marked low-confidence.
- **The judged state lacks context the test relies on**, such as fixtures defined in a distant
  `conftest.py`. *Mitigation:* fixture source is resolved through pytest's fixture manager during
  inventory and included until the budget runs out. Truncation is recorded per test.
- **Overlap with paused changes on `parallel-infrastructure` tests.** *Mitigation:* the pilot is
  read-only. A paused change that resumes and edits a test makes its label `stale` (content hash),
  so the result degrades instead of silently going wrong.
- **Audited tests have side effects.** `parallel-infrastructure` tests spawn subprocesses and
  write temp files; run inside the copy they could touch the real tree or the operator's home.
  *Mitigation:* D3's environment redirection, and the pilot-run read-only gate over the audited
  directories, which fails the package if anything escaped.
- **Pilot results get used as a gate before the linter change.** *Mitigation:* the package has no
  exit-code path tied to findings, and the report's first line says it is advisory.

## Migration Plan

There is no migration. This is a new package plus additive enum values in skill-audit. Rollback
means deleting the package, its CI job and the three enum values. Existing ledgers stay valid in
both directions.

## Open Questions

- Should rename survival also cover moving a private helper to another module? That changes
  `patch` target strings, a real-world refactor that couples tests. The current answer is no,
  because proving behaviour preservation is harder. Revisit if `coupled_spec_test` turns out
  empty.
- Should a second labeller label the same 40 cards so inter-rater kappa bounds what agreement
  with Jev can mean? The pilot runs with one labeller (D9); ri-08's blind-judge rule may require
  two.
- Should ri-08 adopt the D2 vocabulary for replay outputs, or define its own? To be decided by
  ri-08's owner. The ledger supports either through its entry type.
