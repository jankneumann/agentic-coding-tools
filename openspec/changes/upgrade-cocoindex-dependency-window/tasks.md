# Tasks: upgrade-cocoindex-dependency-window

Sizes per plan-feature Task Sizing Reference. Tests precede the code they verify.
Run code-search commands with `uv run --project packages/code-search ...` from the worktree root.

## 1. Policy matcher (U3) — fix the fail-open deny before any pin moves

- [ ] 1.1 Write policy tests for control-character paths (S)
  Add to `packages/code-search/tests/test_indexing_policy.py`: deny `src/private/**` with include
  `**/*.py` rejects `src/private/x\ny.py`; include `src/**` admits `src/odd\tname.py` and
  `src/odd\nname.py`; no `DeprecationWarning` from the matcher. Must fail (RED) under pathspec
  0.12.1 (`uv run --project packages/code-search --with pathspec==0.12.1 pytest ...`).
  **Spec scenarios**: code-search / Matcher-Independent Path Policy Evaluation — "Deny rule covers a
  newline-named file", "Include rule covers tab- and newline-named files"
  **Design decisions**: U3
  **Dependencies**: None
- [ ] 1.2 Make `_compile_patterns` version-independent (S)
  Implement U3 option 1 (DOTALL-compiled gitwildmatch pattern class) in
  `packages/code-search/src/code_search_pkg/indexing_policy.py`. Green under pathspec 0.12.1 and
  1.0.4.
  **Dependencies**: 1.1
- [ ] 1.3 Checkpoint: run tests, review diff, verify scope

## 2. Dependency window tripwire (U1, U2, U4)

- [ ] 2.1 Rewrite `test_cocoindex_revision_compat.py` for the new window (S)
  - pin assertion: `cocoindex[sentence-transformers]>=1.0.17,<1.1.0`, `cocoindex-code==0.2.42`;
  - lock assertion (no extras): parse `packages/code-search/uv.lock`, locked cocoindex-code ==
    pin, locked cocoindex satisfies window (use `packaging.specifiers`);
  - coupling assertion: window upper bound ≤ `COCOINDEX_CODE_DECLARED_COCOINDEX = "<1.1.0,>=1.0.17"`
    (constant cites https://pypi.org/pypi/cocoindex-code/0.2.42/json), failure message names U2;
  - payload assertion: `cli_models._PIPELINE_PAYLOAD["cocoindex"]` / `["cocoindex_code"]` equal the
    pyproject values;
  - live (`requires_db`, `requires_embedder`) test: versions `(1, 0)` / `0.2.42`, installed
    `importlib.metadata.requires("cocoindex-code")` satisfies the coupling rule, the existing
    `App`/`ContextKey`/`fn`/`localfs.walk_dir` callables, plus `inspect.signature(build_matcher)`
    accepts the 3-positional call used by `indexer_pg`.
  Expected RED against current pins.
  **Spec scenarios**: code-search / Coupled Upstream Dependency Window — all four scenarios
  **Design decisions**: U1, U2, U4
  **Dependencies**: None
- [ ] 2.2 Move the pins in `packages/code-search/pyproject.toml` (XS)
  Update the `index` extra and the D8 comment (add one line referencing the U2 coupling rule).
  **Dependencies**: 2.1
- [ ] 2.3 Move the fingerprint payload in `cli_models.py` (XS)
  `_PIPELINE_PAYLOAD["cocoindex"] = ">=1.0.17,<1.1.0"`, `["cocoindex_code"] = "0.2.42"`; leave
  `policy.version` at 1 (U4). Check `tests/test_cli.py::test_pipeline_fingerprint_is_explicit_and_non_legacy`
  still holds.
  **Dependencies**: 2.1
- [ ] 2.4 Checkpoint: run tests, review diff, verify scope

## 3. Relock

- [ ] 3.1 Relock code-search (XS)
  `uv lock --project packages/code-search`; confirm cocoindex 1.0.26, cocoindex-code 0.2.42,
  pathspec 0.12.1; `uv lock --check --project packages/code-search` exits 0.
  **Dependencies**: 2.2
- [ ] 3.2 Relock agent-coordinator (XS)
  `uv lock --project agent-coordinator`; diff must be limited to the `code-search-pkg` specifier
  lines (coordinator keeps pathspec 1.x). Anything wider is a stop-and-report.
  **Dependencies**: 2.2
- [ ] 3.3 Run the full code-search suite on the new lock (S)
  `uv sync --project packages/code-search --extra dev && uv run --project packages/code-search pytest`;
  rerun `tests/test_indexing_policy.py` with `--with pathspec==1.0.4` (NFR: matcher agreement).
  **Spec scenarios**: code-search / Matcher-Independent Path Policy Evaluation — "Decisions agree
  across matcher library versions"
  **Dependencies**: 1.2, 2.3, 3.1
- [ ] 3.4 Checkpoint: run tests, review diff, verify scope

## 4. Live verification (operator environment)

- [ ] 4.1 Run resource-gated tests with the `index` extra (M)
  With ParadeDB (`POSTGRES_DSN`) and the local embedder: `uv sync --project packages/code-search
  --all-extras` then `pytest -m "requires_db or requires_embedder"` including
  `test_indexer_e2e.py` (two-revision incrementality). Record results in the validation report. If
  the environment is unavailable, record the skip explicitly — do not mark done.
  **Spec scenarios**: code-search / Coupled Upstream Dependency Window — "Live install exposes the
  frozen surface"
  **Dependencies**: 3.3

## 5. Repository hygiene (U6)

- [ ] 5.1 Add the dependabot ignore for cocoindex `>=1.1.0` (XS)
  `.github/dependabot.yml`, `/packages/code-search` uv entry; comment cites this change and U5.
  **Dependencies**: None
- [ ] 5.2 Open the implementing PR with `Supersedes #693, #730` in the body (XS)
  **Dependencies**: 3.3, 5.1
- [ ] 5.3 After merge, close #693 as superseded (XS)
  **Dependencies**: 5.2 merged
- [ ] 5.4 After merge, close #730 as superseded and unsatisfiable (XS)
  Comment links design.md U5.
  **Dependencies**: 5.2 merged
- [ ] 5.5 File the cocoindex 1.1 follow-up issue with the U5 trigger and checklist (XS)
  **Dependencies**: None
