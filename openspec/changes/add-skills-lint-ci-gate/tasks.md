# Tasks — add-skills-lint-ci-gate

Executed in the order below, with the full skill test suite re-run after every step. The
suite reported **1143 passed, 55 skipped** at the baseline and at every checkpoint after,
which is the evidence that a 140-file mechanical sweep changed no behaviour.

## Phase 1 — Mechanical cleanup

- [x] 1.1 Establish the baseline: 415 ruff findings, test suite at 1143 passed / 55 skipped.
      **Size**: XS
- [x] 1.2 Apply `ruff check --fix` (safe fixes only, no `--unsafe-fixes`): 235 fixes across
      135 files. Confirm zero `F401` sites were in `__init__.py`, so no re-export was
      removed — that is the main hazard of a mass unused-import fix.
      **Size**: S
- [x] 1.3 Checkpoint: re-run the suite, confirm 1143/55 unchanged.
      **Size**: XS

## Phase 2 — Undefined names, including real bugs

- [x] 2.1 Fix `enable-pg-stats.py`: import `run_railway_command` from `dal`. Verify by
      importing the module, not just by re-running the linter.
      **Spec scenarios**: harness-engineering "An undefined name in a skill script fails CI"
      **Size**: XS
- [x] 2.2 Fix `test_pipeline_integration.py`: import `pytest`, used by `pytest.skip()`.
      **Size**: XS
- [x] 2.3 Add `TYPE_CHECKING` bindings to the five `collect-transcripts` adapter tests so
      forward-reference annotations resolve. Runtime behaviour is unchanged: the adapter
      import stays inside each test, where it must follow the `sys.path` insert.
      **Size**: S
- [x] 2.4 Add the missing `typing.Any` import to `test_check_compact.py`.
      **Size**: XS
- [x] 2.5 Checkpoint: re-run the suite, confirm 1143/55 unchanged.
      **Size**: XS

## Phase 3 — Remaining findings

- [x] 3.1 Underscore-prefix 19 benign unused variables. Preserve every call kept for its
      side effect (`subparsers.add_parser`, worktree setup) — drop only the binding.
      **Size**: S
- [x] 3.2 Mark, do not delete, the `analyze_failures.py` unused-result defect. Deleting it
      would erase the evidence and cascade two further findings, which is itself proof the
      block is orphaned.
      **Size**: XS
- [x] 3.3 Rename ambiguous `l` variables. Re-run lint immediately: one rename exposed a
      second undefined name in a multi-line comprehension whose `if` clause still used the
      old name.
      **Size**: S
- [x] 3.4 Rename the `info` loop variable in `pg-extensions.py` that shadowed the imported
      logger.
      **Size**: XS
- [x] 3.5 Checkpoint: re-run the suite, confirm 1143/55 unchanged.
      **Size**: XS

## Phase 4 — Configuration and gate

- [x] 4.1 Add `ruff` to `skills/pyproject.toml` and regenerate `uv.lock`.
      **Size**: XS
- [x] 4.2 Declare `[tool.ruff.lint] select` explicitly and ignore `E402` with a comment
      explaining why it is convention rather than debt.
      **Spec scenarios**: harness-engineering "The enforced rule set does not change with
      the linter version", harness-engineering "A skill importing a sibling after a path
      insert passes lint"
      **Size**: S
- [x] 4.3 Verify the gate is version-stable: clean under both the locally installed 0.15.22
      and the locked 0.16.0, whose default rule set differs by ~1500 findings.
      **Size**: S
- [x] 4.4 Add the blocking `Lint (ruff)` step to `test-infra-skills`, before the
      install/test steps.
      **Spec scenarios**: harness-engineering "A clean tree passes the lint check",
      harness-engineering "Lint failure is reported before slower checks"
      **Size**: XS
- [x] 4.5 Prove the gate can fail: a probe file with an unused import, an unused variable
      and an undefined name produces 3 errors on an otherwise clean tree. A gate that
      cannot fail is decoration.
      **Spec scenarios**: harness-engineering "An undefined name in a skill script fails CI"
      **Size**: XS
- [x] 4.6 Checkpoint: re-run the suite, confirm 1143/55 unchanged.
      **Size**: XS
