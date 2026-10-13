# Plan Findings: pilot-test-quality-audit

> Structured quality findings from `/iterate-on-plan` cycles. Threshold: medium. Max iterations: 3.
> Analysis ran inline (the autopilot sub-agent harness exposes no `Agent`/`Task` tool); vendor
> review dispatch found no non-Claude CLI installed.

## Iteration 1 (2026-10-13)

Baseline: `openspec validate --strict` passes; 14 requirements, 48 scenarios; 9 work packages.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency / feasibility | high | Contract schemas live only under `openspec/changes/<id>/contracts/`, which moves on archive, yet `report --validate` (pilot-run gate) and ri-07/ri-08 need them at runtime. | D1 "Schema runtime copy": byte-identical copies under `src/test_oracle_audit/schemas/`, parity contract test via `change_dir()`, `tests/_shared/openspec_paths.py`; wp-contracts scope and task 1.1/1.2 updated. |
| 2 | clarity / testability | high | Three of six static rule ids (`private_import`, `mirrored_test_file`, `unscoped_patch`) had no definition and no scenario; `private_attribute_assert` relied on unresolvable "object from the code under test". | Spec requirement now defines all six rules syntactically; four scenarios added (three rules + "never imports test modules"); task 2.3 cites them. |
| 3 | parallelizability / feasibility | high | `wp-pilot-run` depended on `wp-skill-audit-lens`, which was gated on archiving `add-skill-audit` (human-cadence `/cleanup-feature`), so the pilot deliverable waited on an unrelated archive. | Lens run (old 9.7) moved into `wp-skill-audit-lens` as 7.6 with `docs/reports/skill-audit/**` in its scope; `wp-pilot-run` no longer depends on the lens; 7.1 precondition relaxed to "merged to main" (D12 explains why archive is not required). |
| 4 | clarity / consistency | high | Explain-stage flagging, labelling strata, analysis and disagreement classes all need kill-rate terciles, but no module owned the computation and explain.py runs before analysis. | `thresholds.py` (wp-contracts) owns `load_thresholds` and `tercile_cutpoints`; D1/D8 state cut-points are per suite, written into `analysis.json`; task 5.3 tests the source. |
| 5 | consistency | medium | NFR "static+inventory+history ≤ 2 min for both suites, verified by CI job" but CI only runs the fixture dry-run. | NFR verified by pilot-run task 9.2 (timed); CI times the fixture only. |
| 6 | testability | medium | Cost NFR "≤ $1.00 via event_sink" but `decide()` emits `usage_input_tokens`, not dollars. | NFR and task 9.4 measure summed input tokens × recorded price; D15 states the method. |
| 7 | clarity | medium | `SuiteSpec` undefined; inventory collection and mutation/rename execution of `skills/` tests need the suite's own interpreter and `--import-mode=importlib`. | D1 "Suite interpreter": `SuiteSpec(name, root, test_paths, python, pytest_args)` in `config/suites.json`; spec Inventory requirement states collection runs in the suite interpreter. |
| 8 | completeness | medium | Inventory had no failure path (uncollectable file). | Spec: `error` record with `collection_error`, stage continues; scenario .10; task 2.1. |
| 9 | completeness | medium | D5 risk "module >50% unrenamable is low-confidence" had no spec scenario or schema field. | Spec sentence + scenario .32; `RenamePayload.low_confidence` (optional) added to stage-record schema; task 3.7. |
| 10 | clarity | medium | `added_with_fix` left "the commit that introduced the test function" undefined; co-change line mapping across commits was underspecified. | Spec and D6 define introduction (oldest commit, `--follow`, `def` line present, `git log -S`) and per-commit function location via `git show` + `ast`; task 4.1. |
| 11 | clarity | medium | Labelling CLI interaction model undefined (interactive TTY vs agent-driven); dry-run behaviour of `label` unstated although scenario .5 runs "the full pipeline, including labelling". | Spec: non-interactive `label next` / `label record`, `--dry-run` never writes the ledger; scenario .41; D9 CLI contract; task 6.1. |
| 12 | completeness / scope | medium | `boundary` judged question collected but consumed nowhere in D10/D11. | Spec and D7: descriptive only; disagreement report carries it; `mock_assertion_dominant` vs kill rate split by boundary, subject to n<20 rule. |
| 13 | security / feasibility | medium | Audited tests executed inside the isolated copy can write outside it (home, temp, caches). | D3: `HOME`/`TMPDIR`/`XDG_*`/`--basetemp` redirected, `-p no:cacheprovider`, `git worktree prune`; risk recorded; task 3.2. |
| 14 | parallelizability | medium | `tests/conftest.py` owned by wp-contracts only; five parallel stage packages had no stated way to add fixtures. | D1 "Test tree ownership" + tasks header: shared conftest holds `schema_validator`, `fixture_project`, `stub_decide` only; stage helpers stay in `test_<stage>*.py`. |
| 15 | assumptions | medium | Single labeller assumed; no inter-rater check although ri-08's blind-judge rule may need one. Could not be surfaced via AskUserQuestion (non-interactive sub-agent). | Documented in D9 as an explicit assumption with the multi-labeller rule; added to open questions. |
| 16 | consistency | low | Contracts README named `labels.py`; design has `ledger.py`/`labelling.py`. | README fixed; runtime-copy section added. |
| 17 | consistency | low | Pilot-run verify step read `docs/reports/test-oracle-audit/latest/analysis.json`; task 9.6 writes `<date>/`. | Verify step resolves the newest dated directory; task 9.6 states no `latest` symlink. |
| 18 | clarity | low | Scenario-ID table in tasks.md is positional and silently drifts when scenarios are added. | Table regenerated and annotated; renumbering done by title-matching script. |

Parallelizability after iteration 1: wp-contracts (root) → {wp-inventory-static, wp-execution, wp-history, wp-judged-explain, wp-labels-analysis} ∥ wp-skill-audit-lens → wp-integration → wp-pilot-run. Independent: 1 root + 1 (lens) | Sequential chains: 3 (contracts→stages→integration→pilot; lens standalone) | Max parallel width: 6. File overlap: none between parallel packages (session-log.md and design.md are written only by wp-execution among the parallel set).

Deferred / out of scope: a second labeller (open question, ri-08); moving a private helper between modules as a second refactor (open question).
