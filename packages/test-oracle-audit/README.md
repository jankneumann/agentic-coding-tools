# test-oracle-audit

A read-only, multi-approach audit of test quality. For each test it asks: **do the expected values
come from intent (spec, property, reference, contract) or from restating the implementation?**
Four independent approaches answer, and their answers are compared against human labels.

Built for the pilot in OpenSpec change `pilot-test-quality-audit`. Everything it produces is
**advisory**: no exit code reflects a finding, and nothing here is a gate.

## Stages

| Subcommand | Module | Output | Evidence |
|---|---|---|---|
| `inventory` | `inventory.py` | `inventory.jsonl` | Test ids, content hashes, fixtures, covered modules (the join key) |
| `static` | `static_checks.py` | `static.jsonl` | Six AST rules: `assertion_free`, `mock_assertion_dominant`, `private_attribute_assert`, `private_import`, `mirrored_test_file`, `unscoped_patch` |
| `judge` | `judged.py` | `judged.jsonl` | Jev / System One `oracle_source`, `survives_refactor`, `boundary` via `system_one_decisions.decide()`: shadow-only judgment evidence, blind to every other stage |
| `mutate` | `mutation.py` | `mutation.jsonl`, `mutants.jsonl` | Per-test kill rate (AST mutant runner; mutmut probed first) |
| `refactor` | `refactor.py` | `rename.jsonl` | Survival of a behaviour-preserving private-symbol rename |
| `history` | `history.py` | `history.jsonl` | Co-change ratio and added-with-fix from git (never fetches) |
| `explain` | `explain.py` | `explain.jsonl` | LLM prose for flagged tests only (not a measured approach) |
| `label` | `labelling.py`, `ledger.py` | `cards/`, `label-cards.md`, ledger | Blind, stratified, seeded human oracle-source labels |
| `analyze` | `analysis.py`, `disagreement.py` | `analysis.json` | Kappa, Brier, Cliff's delta, AUC with n and 95% CIs; disagreement classes |
| `report` | `report.py` | `report.md` | Advisory report with linter candidates, exclusions and open decisions |
| `run-all` | `cli.py` | all of the above | Every stage, then `analyze` and `report` |

All stage output validates against the schemas in `src/test_oracle_audit/schemas/` (byte-identical
runtime copies of the change's `contracts/schemas/`).

## Running

```bash
cd packages/test-oracle-audit
uv sync --extra dev

# Whole pipeline over a pilot suite (suites are defined in src/test_oracle_audit/config/suites.json)
uv run test-oracle-audit --repo-root ../.. --suite test_evaluation \
    --out ../../docs/reports/test-oracle-audit/$(date +%F) run-all

# A single stage, or dry-run (no Jev or LLM calls; label writes no ledger)
uv run test-oracle-audit --repo-root ../.. --suite parallel_infrastructure static
uv run test-oracle-audit --repo-root ../.. --suite test_evaluation --dry-run run-all

# Labelling: render the next card, then record the operator's label
uv run test-oracle-audit --repo-root ../.. --suite test_evaluation label
uv run test-oracle-audit --repo-root ../.. --suite test_evaluation \
    label record 'agent-coordinator/tests/test_evaluation/test_x.py::test_y' spec --labeller jan

# Re-validate an analysis document
uv run test-oracle-audit --repo-root ../.. --suite test_evaluation --out <dir> report --validate
```

Audited suites run in **their own** project environment: `uv run --project <suite project>
--extra <suite extras> ...`. The audit's tooling is overlaid with `--with`, and the suite's
lockfile is never edited. `--python PATH` runs audited pytest with a given interpreter instead,
which is what the package's own tests and CI do.

## Environment prerequisites for a live pilot run (design D15)

| Stage | Needs | Without it |
|---|---|---|
| `judge` | `TYPESAFE_API_KEY` and `system-one-decisions[live]` | records `degraded` (`no_key` / `dry_run`; a missing live extra reports as `over_budget`) |
| `explain` | `--explain-command '<cmd>'`: any command reading the prompt on stdin and printing `{"action": ..., "prose": ...}` | records `degraded` (`no_backend`) |
| `history` | a full clone (`git fetch --unshallow`) | records `degraded` (`shallow_history`) |
| `mutate` / `refactor` | `uv` and network access for the suite's dependencies (or `--python`) | records `degraded` with the reason |

## Read-only guarantee (design D3)

Mutation and rename run only inside an `isolated_copy`: a detached `git worktree` of `HEAD`
(copytree fallback) with `HOME`, `TMPDIR`, XDG dirs and pytest `--basetemp` redirected. The copy is
always removed, including on errors. The audit writes only to `--out` and the label ledger.

## Reuse by other changes

- **ri-07 `add-mutation-score-guardrail`**: `test_oracle_audit.mutation.MutationRunner`,
  `run_mutation()` and `MutantResult` (contract `mutation-result.schema.json`). The task 3.1 spike
  (design D4) found that mutmut 3.8's relocated `mutants/` tree breaks tests that read
  repo-relative files, so `AstMutantRunner` is the working backend.
- **ri-08 `calibrate-llm-judge-against-human-labels`**: `test_oracle_audit.ledger.LabelLedger`
  (use `entry_type` for non-test entries), `labelling.stratified_sample` / `render_card`, and
  `analysis.cohen_kappa` / `bootstrap_ci` / `brier`, with the 0.7 binary-kappa floor.

## Development

```bash
uv run pytest -q          # the whole suite runs offline; audited runs use --python
uv run ruff check .       # tests/fixtures/ are deliberately imperfect audit inputs and excluded
```

The tests were written from the spec, contracts and design by a separate agent that never saw the
implementation (design D14).
