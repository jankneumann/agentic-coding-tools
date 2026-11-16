# Implementation Findings: pilot-test-quality-audit

## Iteration 1 (2026-11-15, after rebase onto origin/main)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | resilience | medium | `cli.CommandBackend.run` piped the prompt to `--explain-command` with no timeout, so one hung backend call (for example `claude -p` waiting on auth) blocked the explain stage forever instead of producing a per-test `error` record. | Fixed: `CommandBackend(timeout=300.0)`; `subprocess.TimeoutExpired` is recorded by `run_explain` as `backend_error`. Test: `tests/test_cli.py::test_command_backend_times_out_instead_of_hanging`. |
| 2 | bug | medium | Inventory runs `pytest --collect-only` in the audited tree itself and only disabled the cache provider when the suite config happened to pass `-p no:cacheprovider`. A collection error then wrote `.pytest_cache/` into the audited repo, breaking D3 ("the package writes only to `--out`"). | Fixed: the collect command always passes `-p no:cacheprovider`, as `run_suite`/`can_collect` already did. Test: `tests/test_inventory.py::test_collection_leaves_no_pytest_cache_in_the_audited_tree`. |
| 3 | edge-case | low | `history._resolve_source_paths` falls back to the first tracked file whose path ends with `/<module>.py`, so a single-segment module name can resolve to an unrelated same-named file elsewhere in the repo. | Deferred (low): only reached when the inventory did not supply `source_paths`. |
| 4 | edge-case | low | `history._changed_assertion_in_span` treats removed/added lines whose content starts with `--`/`++` as diff headers. | Deferred (low): such lines are not assertion lines in Python test code. |
| 5 | workflow | low | `mypy src` reports 13 errors (mostly missing third-party stubs); CI does not run mypy for this package. | Deferred (low): not a CI gate for this package. |
