# Implementation Findings: pilot-test-quality-audit

## Iteration 1 (2026-11-15, after rebase onto origin/main)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | resilience | medium | `cli.CommandBackend.run` piped the prompt to `--explain-command` with no timeout, so one hung backend call (for example `claude -p` waiting on auth) blocked the explain stage forever instead of producing a per-test `error` record. | Fixed: `CommandBackend(timeout=300.0)`; `subprocess.TimeoutExpired` is recorded by `run_explain` as `backend_error`. Test: `tests/test_cli.py::test_command_backend_times_out_instead_of_hanging`. |
| 2 | bug | medium | Inventory runs `pytest --collect-only` in the audited tree itself and only disabled the cache provider when the suite config happened to pass `-p no:cacheprovider`. A collection error then wrote `.pytest_cache/` into the audited repo, breaking D3 ("the package writes only to `--out`"). | Fixed: the collect command always passes `-p no:cacheprovider`, as `run_suite`/`can_collect` already did. Test: `tests/test_inventory.py::test_collection_leaves_no_pytest_cache_in_the_audited_tree`. |
| 3 | edge-case | low | `history._resolve_source_paths` falls back to the first tracked file whose path ends with `/<module>.py`, so a single-segment module name can resolve to an unrelated same-named file elsewhere in the repo. | Deferred (low): only reached when the inventory did not supply `source_paths`. |
| 4 | edge-case | low | `history._changed_assertion_in_span` treats removed/added lines whose content starts with `--`/`++` as diff headers. | Deferred (low): such lines are not assertion lines in Python test code. |
| 5 | workflow | low | `mypy src` reports 13 errors (mostly missing third-party stubs); CI does not run mypy for this package. | Deferred (low): not a CI gate for this package. |

## Iteration 2 (2026-11-15, vendor review)

Vendor dispatch (`review_dispatcher.py --mode review`, 500s timeout): codex succeeded with 6 findings
(`reviews/findings-codex-impl.json`). antigravity needed interactive auth, grok timed out at 500s, and pi
returned output that was not valid findings JSON. Quorum is DEGRADED (1 of 2), so every codex finding was
checked against the code by the orchestrator before it was accepted.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 6 | security | high | Suite specs accepted absolute or `..` paths. Mutation and rename write under `copy.root / <source root>`, and `Path("/copy") / "/etc"` is `/etc`, so a bad suites file pointed the writing stages outside the isolated copy (D3). | Fixed: `SuiteSpec.__post_init__` rejects absolute or escaping `project_root`/`test_paths`/`source_roots`. Test: `tests/test_contracts.py::test_suite_paths_must_stay_inside_the_repository`. |
| 7 | bug | medium | Inventory collection runs `uv run --project <audited project>` in the audited tree, and uv could re-lock and rewrite that project's `uv.lock`. | Fixed: collection passes `--frozen`. Test: `tests/test_inventory.py::test_default_python_runs_collection_through_uv_project`. uv may still create the project's `.venv`, which is an environment, not tracked content; this is accepted. |
| 8 | bug | medium | The rename transformer renamed matching attribute names off external modules (`import vendor; vendor._helper()`), so a working test could fail in the renamed copy and be misreported as `survives_refactor: false`. | Fixed: `_Renamer` tracks names bound by non-source `import`/`from ... import` and leaves attributes on them unchanged. Tests: `tests/test_refactor.py::test_private_attribute_of_an_external_module_is_not_renamed`, `..._of_a_source_module_or_self_is_renamed`. |
| 9 | bug | medium | `label next` treated any ledger entry as labelled, so a test edited after labelling kept only a stale label and was never served again; analysis then dropped it silently. | Fixed: `label_next` counts only labels whose stored hash matches the test's current hash. Test: `tests/test_labelling.py::test_label_next_re_serves_a_test_whose_label_went_stale`. |
| 10 | gap | medium | `MutmutRunner.run` is not implemented; only the probe exists, so the AST backend always runs. | Deferred (known limitation): design D4 records the spike 3.1 verdict, "AST runner is primary; mutmut stays as a probed" backend. The spec's fallback scenario holds, and every result records `backend: ast`. |
| 11 | spec-conformance | low | The label card includes function bodies (up to 40 lines), while the spec mentions only signatures and docstrings. | Rejected: design D9 says "signatures and docstrings, but not their bodies beyond 40 lines", and the test `test_card_cuts_function_bodies_at_forty_lines` pins this. The card still shows no other approach's output (scenario .40). |
