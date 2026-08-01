# Tasks — gate-semantic-context-default-enablement (ri-13)

Seven phases, one per work package. Test tasks precede the implementation they
verify (TDD RED → GREEN). `depends_on` in `work-packages.yaml` is the
authoritative execution order, not file position.

Capability short names used in scenario references: `sce` =
`semantic-context-evaluation`, `cs` = `code-search`, `sw` = `skill-workflow`.

**Phase 6 may legitimately end in a FAIL verdict.** No task in this file
requires `report.verdict == "pass"`. See design D11.

---

## Phase 1 — wp-contracts: the evaluation contracts

- [x] 1.1 Extend the promoted-contract byte-compare test to cover the three new
      schemas, and assert the closed verdict enum has exactly two members
      **Spec scenarios**: `sce` — Fail-closed evaluation verdict / A verdict enum with no escape value
      **Contracts**: all three
      **Design decisions**: D3
      **Dependencies**: None
      **Size**: S
      **Note**: Must fail before 1.2 lands — the schemas do not exist yet.

- [x] 1.2 Author `context-eval-report.schema.json`
      **Spec scenarios**: `sce` — Fail-closed evaluation verdict / A verdict enum with no escape value; `sce` — Evaluation report record / The report identifies its index and configuration
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D6, D9, D15
      **Dependencies**: 1.1
      **Size**: M
      **Note**: `verdict` is `enum: ["pass","fail"]`. No `waived`, `blocked`,
      `skip`, `unmeasured`, or `partial`. `gates[].required` is `const: true`.
      No waiver field anywhere.

- [x] 1.3 Author `context-eval-corpus.schema.json` and
      `context-eval-case.schema.json`
      **Spec scenarios**: `sce` — Declared evaluation corpus / Thresholds are corpus data
      **Contracts**: both
      **Design decisions**: D6, D7, D8
      **Dependencies**: 1.1
      **Size**: M
      **Note**: thresholds live in the manifest, never in Python. Every consumer
      slice carries an explicit `utility_applicable` boolean.

- [x] 1.4 Promote all three to
      `openspec/contracts/semantic-context-evaluation/schemas/`, byte-identical,
      and add the row to `openspec/contracts/README.md`
      **Spec scenarios**: none
      **Contracts**: all three
      **Design decisions**: none
      **Dependencies**: 1.2, 1.3
      **Size**: XS
      **Note**: promote-before-archive is a hard repo rule
      (`openspec/contracts/README.md`), not bookkeeping. `$id` must name the
      promoted location so relative `$ref`s resolve after archival.

- [x] 1.5 Checkpoint: run tests, review diff, verify scope

---

## Phase 2 — wp-corpus: rescue the ten tasks, add the labels the gates need

- [x] 2.1 Write the corpus integrity test: every declared consumer has a slice
      with an explicit `utility_applicable`; every labeled path exists; every
      case validates; the digest is stable across two loads
      **Spec scenarios**: `sce` — Declared evaluation corpus / An unlabeled consumer is a corpus error
      **Contracts**: `contracts/schemas/context-eval-case.schema.json`
      **Design decisions**: D3, D7
      **Dependencies**: 1.3
      **Size**: M
      **Note**: fails on the empty corpus — zero of ri-12's six consumers are
      covered by anything today.

- [x] 2.2 Rescue T1-T10 into `packages/context-eval/corpus/cases/`, preserving
      `case_id`, `query`, `expected_files`, `category`, `rationale`, and the
      original `ripgrep_baseline` string, with a `provenance` block naming the
      archived origin
      **Spec scenarios**: `sce` — Declared evaluation corpus / Rescued cases keep their identity
      **Contracts**: `contracts/schemas/context-eval-case.schema.json`
      **Design decisions**: D10
      **Dependencies**: 2.1
      **Size**: M
      **Note**: all 13 expected files verified present at `748af34c`.

- [x] 2.3 Label the rescued cases with `must_touch`, `evidence_spans`, a
      declared `read_allow`/`deny` scope, and an owning `consumer`
      **Spec scenarios**: `sce` — Coding-context utility measurement / Utility is measured against labeled evidence
      **Contracts**: `contracts/schemas/context-eval-case.schema.json`
      **Design decisions**: D7
      **Dependencies**: 2.2
      **Size**: L
      **Note**: the only L in the plan. Hand labeling is the irreducible cost of
      a quality evaluation; decomposing it would split one judgement across two
      agents and produce two labeling conventions.

- [x] 2.4 Add per-consumer cases covering all six ri-12 consumers, plus
      fail-closed regression cases (no index at revision, revision mismatch,
      scope rejected, unknown state) and adversarial out-of-scope responses
      **Spec scenarios**: `sce` — Scope compliance measurement / A leaked hit is caught client-side; `sce` — Fail-closed regression cases / An unavailable exact-revision index restores exact search
      **Contracts**: `contracts/schemas/context-eval-case.schema.json`
      **Design decisions**: D7, D8, D12
      **Dependencies**: 2.3
      **Size**: L
      **Note**: `quick-task` declares `utility_applicable: false` with
      fail-closed cases only — its SKILL.md documents that it has no declared
      scope and therefore always returns `out_of_scope`/`no_declared_scope`.

- [x] 2.5 Implement the corpus loader and the deterministic corpus digest
      **Spec scenarios**: `sce` — Declared evaluation corpus / Thresholds are corpus data
      **Contracts**: `contracts/schemas/context-eval-corpus.schema.json`
      **Design decisions**: D6, D12
      **Dependencies**: 2.4
      **Size**: M

- [x] 2.6 Checkpoint: run tests, review diff, verify scope

---

## Phase 3 — wp-scoring: baseline producer and the three scorers

- [x] 3.1 Write `test_repo_root_resolution.py` — the baseline producer's
      repository root is injected, contains `.git` and `openspec/`, and is never
      derived from `__file__`
      **Spec scenarios**: `sce` — Reproducible exact-search baseline / The baseline is reproducible from its published artifact
      **Contracts**: none
      **Design decisions**: D1, D10
      **Dependencies**: 2.5
      **Size**: S
      **Note**: this is the executable form of the `parents[3]` defect
      (`run_eval.py:31`, `index_and_query.py:31`), which resolves to
      `<repo>/openspec` from the archived path. Fails before 3.2.

- [x] 3.2 Implement `producers/exact_search.py` — the fair keyword ranker and
      the naive phrase baseline, budget-equalized per D5, root injected
      **Spec scenarios**: `sce` — Reproducible exact-search baseline / Both arms share one budget
      **Contracts**: none
      **Design decisions**: D5, D10
      **Dependencies**: 3.1
      **Size**: M

- [x] 3.3 Write `test_exact_search_algorithm.py` — the ranker over a tiny
      checked-in fixture tree with hand-computed expected output
      **Spec scenarios**: `sce` — Reproducible exact-search baseline / The ranking algorithm is pinned independently of the tree
      **Contracts**: none
      **Design decisions**: D10
      **Dependencies**: 3.2
      **Size**: M
      **Note**: the recorded `keyword hit@5 = 3/10` was measured on the tree of
      2026-07-19 and has NOT been re-verified at `748af34c`. Pin the algorithm,
      record the tree-dependent number.

- [x] 3.4 Implement the retrieval-relevance scorer (`hit_at_k`,
      `must_touch_coverage`, `wins_over_baseline`), thresholds from the manifest
      **Spec scenarios**: `sce` — Retrieval relevance measurement / Wins are measured, not labeled
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D6
      **Dependencies**: 3.2
      **Size**: M
      **Note**: `run_eval.py:161` computes wins as *measured* keyword misses
      while `eval-set.yaml`'s header describes them as the `semantic-win`
      *label*. The measured definition wins; the label is metadata.

- [x] 3.5 Implement the scope-compliance scorer — outbound fidelity, rendered
      violations (zero tolerance), deny precedence, rejection honored; record
      `scope_adapter: resolved|degraded`
      **Spec scenarios**: `sce` — Scope compliance measurement / A single violation fails the gate; `sce` — Scope compliance measurement / A degraded scope adapter is an apparatus failure
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D8
      **Dependencies**: 3.2
      **Size**: M
      **Note**: `_normalize_read_scope` (`semantic_context.py:919`) is NOT
      injectable and falls back to unnormalized globs at `:934-938`. A degraded
      adapter must be an `apparatus_failure`, never a silent pass.

- [x] 3.6 Implement the utility scorer — `answer_coverage`, `evidence_density`,
      `steps_to_evidence` (censored, never null), per consumer
      **Spec scenarios**: `sce` — Coding-context utility measurement / Missing evidence is censored, not null; `sce` — Coding-context utility measurement / No consumer may regress
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D7
      **Dependencies**: 3.2
      **Size**: L
      **Note**: no blended score. Three independent conditions, all of which
      must hold, plus an absolute do-no-harm clause per consumer.

- [x] 3.7 Write the determinism, no-wall-clock, no-random, and
      no-model-literal tests
      **Spec scenarios**: `sce` — Deterministic scoring / Reordered input produces identical output
      **Contracts**: none
      **Design decisions**: D16
      **Dependencies**: 3.4, 3.5, 3.6
      **Size**: M
      **Note**: hand-derived expected order over a tie-heavy fixture, then
      seeded shuffle — not "run it twice".

- [x] 3.8 Checkpoint: run tests, review diff, verify scope

---

## Phase 4 — wp-verdict: fail-closed composition, report, CLI

- [x] 4.1 Write the fail-closed composition tests: unscored case ⇒ fail;
      declared-vs-scored mismatch ⇒ `denominator_mismatch`; missing declared
      gate ⇒ `missing_required_gate`; `code_search_enabled: false` during a
      retrieval measurement ⇒ `service_disabled_during_measurement`; tier below
      declared ⇒ `index_tier_insufficient`
      **Spec scenarios**: `sce` — Fail-closed evaluation verdict / An unmeasured gate is a failing gate; `sce` — Fail-closed evaluation verdict / The denominator is declared
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D9, D17
      **Dependencies**: 3.7
      **Size**: M

- [x] 4.2 Implement `compose_verdict()` — signature takes scored cases and
      declared gates only, with **no judge parameter** — and compose **all four**
      gates the manifest declares required: `retrieval_quality`,
      `coding_context_utility`, `scope_compliance`, and `fail_closed_regression`
      **Spec scenarios**: `sce` — Advisory qualitative review / The judge cannot reach the verdict; `sce` — Fail-closed evaluation verdict / An unmeasured gate is a failing gate
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D15
      **Dependencies**: 4.1
      **Size**: M
      **Note**: `fail_closed_regression` was declared required in
      `corpus/manifest.yaml` by phase 2 but had **no task assigning its
      composition** — found by the phase 3 agent, corrected here. Phase 3 already
      implemented `expectation_honored()` in `scoring/scope.py` for task 3.5's
      "rejection honored" clause; compose the gate from it rather than writing a
      second predicate. The omission was fail-closed rather than fail-open — an
      uncomposed declared gate yields `missing_required_gate` and the verdict
      fails — which is precisely why it could have survived to phase 6 and been
      misread there as a measured failure.

- [x] 4.3 Implement the report emitter, schema-validated on write, with the
      optional judge block attached after composition
      **Spec scenarios**: `sce` — Evaluation report record / The report identifies its index and configuration
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D6, D15
      **Dependencies**: 4.2
      **Size**: M
      **Note**: embedder identity is read from the configured `EmbeddingContract`
      and from `CodeSearchResponse.index`. No model-id literal anywhere.

- [x] 4.4 Implement the CLI and its exit codes (0 pass / 1 apparatus / 2 gate
      fail / 3 report absent, stale, or schema-invalid) plus the live producer
      `producers/semantic_runtime.py` with an injected module path
      **Spec scenarios**: `sce` — Fail-closed evaluation verdict / Nothing exits zero without a passing report
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D4
      **Dependencies**: 4.3
      **Size**: M
      **Note**: `producers/semantic_runtime.py` is the ONLY module that knows
      about `skills/`. It loads `semantic_context.py` via
      `importlib.util.spec_from_file_location` with the path from configuration.

- [x] 4.5 Add the `packages/context-eval` CI job (lint, mypy strict, pytest),
      pinning the version of every tool it installs
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: D2, D14
      **Dependencies**: 4.4
      **Size**: S
      **Note**: `packages/agent-scenarios` has NO CI job — verified by grep over
      `.github/workflows/*.yml` and `Makefile`. Omitting this is the default
      failure mode, not a hypothetical one. Pin tool versions: `ci.yml:92`
      installs `@fission-ai/openspec` unpinned (issue #318) and this job must
      not repeat that.

- [x] 4.6 Checkpoint: run tests, review diff, verify scope

---

## Phase 5 — wp-gate: enablement consistency, spec reconciliation, docs

- [x] 5.1 Write `test_spec_gate_artifact.py` — resolve the artifact the
      `code-search` Retrieval Quality Gate requirement names and assert it
      exists at a durable path and carries a verdict from the closed enum
      **Spec scenarios**: `cs` — Retrieval Quality Gate / A waived evaluation is not a pass
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D13
      **Dependencies**: 4.5
      **Size**: S
      **Note**: fails today — the requirement points at `eval/spike-report.md`
      "in the change directory", which archival moved, and whose verdict is
      `WAIVED`/`UNMEASURED`.

- [x] 5.2 Write `test_enablement_gate_mutation.py` — the gate exits non-zero for
      constant-`True` with (a) no report, (b) a stale report by each expiry
      condition of D12, (c) a failing report, (d) a schema-invalid report
      **Spec scenarios**: `sw` — Evidence-gated injection default / Enablement without evidence is rejected; `sw` — Evidence expiry / Stale evidence withdraws authorization
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D12, D14
      **Dependencies**: 4.5
      **Size**: M
      **Note**: the gate is correctly green on an unmodified tree — its job is to
      catch a flip nobody has made. This mutation test is the substitute for
      "fails today", and without it the gate is decoration.

- [x] 5.3 Extract `INJECTION_DEFAULT_ENABLED: bool = False` in
      `semantic_context.py` and have `injection_enabled()` fall back to it;
      assert byte-identical behaviour while it is `False`
      **Spec scenarios**: `sw` — Evidence-gated injection default / The default is one declaration
      **Contracts**: none
      **Design decisions**: D11
      **Dependencies**: 5.2
      **Size**: S
      **Note**: the ONLY edit to ri-12's runtime module in this change. Existing
      `skills/tests/context-engineering/` must pass unchanged.

- [x] 5.4 Implement the Enablement Consistency Gate and its
      `make semantic-enablement-gate` target, with all six D12 expiry conditions
      **Spec scenarios**: `sw` — Evidence expiry / Stale evidence withdraws authorization
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D12
      **Dependencies**: 5.3
      **Size**: M

- [x] 5.5 Add the blocking CI job for the enablement gate
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: D14
      **Dependencies**: 5.4
      **Size**: S
      **Note**: this is the one job in `ci.yml` that is GREEN on an unmodified
      tree by design, so "run it and watch it fail" is not available as proof.
      Two things were verified instead. Task 5.2's mutation suite proves the
      gate's *logic* discriminates; and the `make` wiring was proven separately
      by flipping `INJECTION_DEFAULT_ENABLED` to `True` on a scratch tree, where
      the gate exited 3, `make` reported `Error 3` and exited 2, and the step
      would therefore fail. Task 7.2 repeats that flip as a recorded artifact.

- [x] 5.6 Reconcile `openspec/specs/code-search/spec.md` via the MODIFIED delta,
      and update `docs/guides/code-search.md`'s `## Retrieval-quality gate`
      section and `docs/guides/semantic-context-injection.md` to the durable
      procedure
      **Spec scenarios**: `cs` — Retrieval Quality Gate / A waived evaluation is not a pass
      **Contracts**: none
      **Design decisions**: D13
      **Dependencies**: 5.1
      **Size**: M
      **Note**: this task originally also named `openspec/specs/code-search/spec.md`
      and `docs/decisions/code-search.md:232` as files to edit. **Neither is
      edited, and there will be no diff for either in this change.** The live
      spec is rewritten by `openspec archive` from the MODIFIED delta this
      change already carries, so hand-editing it now would conflict at archive
      time — which is why it sits in `wp-gate`'s `locks.files` but deliberately
      not in its `scope.write_allow`. `docs/decisions/code-search.md` is a
      derived artifact regenerated by `make decisions`; a direct edit is
      silently overwritten (issue #157). See design D13 for the full reasoning
      and for the separate defect that file carries.

- [x] 5.7 Create `docs/evaluation/semantic-context/README.md` — the durable
      report location, how to reproduce, and what each exit code means
      **Spec scenarios**: `sce` — Evaluation report record / The report has a durable home
      **Contracts**: none
      **Design decisions**: D1
      **Dependencies**: 5.4
      **Size**: S
      **Note**: `report.json` is deliberately ABSENT at this point. Absent is the
      fail-closed default state.

- [x] 5.8 Checkpoint: run tests, review diff, verify scope
      **Result**: `packages/context-eval` 306 passed, 0 skipped. The one
      previously-skipped test — ripgrep parity — executed for the first time on
      this machine (`rg` resolved at `/opt/homebrew/bin/rg`, absent earlier in
      the session) and passes: the ranking in `producers/exact_search.py` agrees
      with real ripgrep rather than only with our model of it. Both CI gates
      reproduce green (`ruff check src/ tests/`; `mypy src/context_eval/
      --strict`, 17 files). `openspec validate --strict` passes. The existing
      `skills/tests/context-engineering/` suite — 735 tests over the one runtime
      file this phase edited — passes unchanged, so the 5.3 refactor to a named
      constant altered no behavior.
      **Scope**: 11 files across the eight phase 5 commits; 9 fall inside
      `wp-gate`'s `write_allow`. The two that do not are both plan gaps rather
      than phase 5 overreach, and are filed at integration:
      (a) `tasks.md` appears in **no** package's `write_allow`, while
      `implement-feature` mandates flipping its checkbox in the same commit as
      the implementation — the plan and the skill contradict each other, and
      every package has to violate one of them;
      (b) `packages/context-eval/uv.lock` is unowned, though `wp-corpus` owns
      the `pyproject.toml` it is derived from.
      **Not checked by CI**: `ruff format --check` reports 20 files would be
      reformatted. No format gate exists in `ci.yml` for any package, so this is
      not a regression this change introduced; noted rather than fixed, since
      adding a repo-wide format gate is not in this change's scope.

---

## Phase 6 — wp-measure: attempt the measurement, record whatever it says

**A FAIL verdict is a successful completion of this phase.** Nothing here
requires a favourable number.

- [x] 6.1 Provision the measurement environment: install
      `packages/code-search[index]`, provision a **scratch** database applying
      migrations 028/029/030, and record the resolved embedding contract
      **Spec scenarios**: `sce` — Index tier declaration / A live retrieval measurement needs a real index
      **Contracts**: none
      **Design decisions**: D9
      **Dependencies**: 5.8
      **Size**: M
      **Note**: `sentence_transformers` and `cocoindex` are ABSENT from every
      active venv. The running `paradedb` container belongs to another project's
      test tiers and MUST NOT be mutated; `localhost:54322` is closed. Follow
      `packages/code-search/tests/conftest.py:132` (`index_e2e_case`), which
      provisions and migrates its own database. `huggingface.co` now returns 200
      (403 in July); `api.openai.com` returns 421, so prefer the `local`
      provider. `download.pytorch.org` is 403 but torch is on PyPI.
      **Result**: provisioned, and the provisioning itself is the first thing
      this phase measured.
      - **Install**: `packages/code-search[index]` installed into a venv OUTSIDE
        the repository (`**/.venv/**` is denied to `wp-measure`), resolving
        `cocoindex-code==0.2.37`, `sentence-transformers==5.6.1`,
        `torch==2.13.0`, `transformers==5.14.1`. `huggingface.co` served the
        model weights, so the July blocker (403 from every embedding backend)
        is genuinely gone. `api.openai.com` was never contacted; the `local`
        provider was used throughout.
      - **Database**: a NEW `paradedb/paradedb:0.22.2-pg17` container
        `ri13-measure-pg` on host port 55432, its own storage, migrations
        `028`/`029`/`030` applied to it and to nothing else. The other project's
        `real-ingestion-test-tiers-in-ci-postgres-1` on 5432 was never
        connected to, and was verified `Up (healthy)` before and after. Torn
        down at the end of the phase. `localhost:54322` is still closed.
      - **Clean tree**: `index_repo` requires a clean worktree and the shared
        checkout carries five untracked `openspec/schemas/context-*.json` files
        that belong to no change (issue #311). Rather than commit or delete
        them, a throwaway detached `git worktree` at the evaluated revision was
        used as the index source. First `index_repo` attempt, against the
        working tree, returned exit 1 / `source_dirty` and is recorded rather
        than discarded.
      - **Resolved embedding contract**: `provider_kind: local`,
        `model_id: sentence-transformers/all-MiniLM-L6-v2`, `dimension: 384`,
        `fingerprint:`
        `f5ae15d31080994823bfea9a455808c39f60e592977d74c034081db3506e388d`,
        read from `EmbeddingContract.fingerprint` / `provider.fingerprint` as
        the CLI constructs them — not asserted as a literal.

- [x] 6.2 Build a real index at the exact evaluated revision with `index_repo`
      and record its exit code and JSON result
      **Spec scenarios**: `sce` — Index tier declaration / A live retrieval measurement needs a real index
      **Contracts**: none
      **Design decisions**: D9
      **Dependencies**: 6.1
      **Size**: M
      **Note**: exit codes are `{ready:0, not_configured:2, conflict:3,
      failed:1}`. A non-zero exit is recorded as `unmeasured`, not retried into
      silence.
      **Result**: **no index was built. Every attempt exited 1 (`failed`).** The
      index tier for this measurement is therefore `none`, and the two gates
      that declare `min_index_tier: live` are `index_tier_insufficient`. Five
      attempts were made, each after a *documented change to the index scope or
      to the source tree* and never a bare repetition; all five are recorded
      here, including the ones that changed the error.
      Evaluated revision throughout: `184d132925215f03a84dd2867f15f9d5111a9902`.

      | # | Change from the previous attempt | Exit | `error.code` |
      |---|---|---|---|
      | 1 | working tree, `agent-coordinator/**` + `skills/**` | 1 | `source_dirty` |
      | 2 | clean detached worktree at the same revision | 1 | `secret_detected` |
      | 3 | + `--exclude` for the 7 secret-scan hits | 1 | `secret_scan_failed` |
      | 4 | scope narrowed to the corpus's own `read_allow` union (308 files) | 1 | `secret_scan_failed` |
      | 5 | scope narrowed to `skills/shared/**` (14 files) | 1 | `indexing_failed` |

      Attempt 1 verbatim:
      ```json
      {"counts":{"changed_files":0,"chunks":0,"copied_files":0,"eligible_files":0,"embedded_chunks":0,"removed_files":0,"skipped_files":0},"durable":false,"error":{"code":"source_dirty","message":"worktree has tracked or untracked changes"},"index_id":null,"namespace_key":"main","namespace_kind":"main","parent_index_id":null,"parent_revision":null,"promoted":false,"repo_slug":"ri13_measure","reused":false,"source_revision":"184d132925215f03a84dd2867f15f9d5111a9902","status":"failed","storage_key":null}
      ```
      Attempt 5 verbatim (the furthest any attempt reached):
      ```json
      {"counts":{"changed_files":0,"chunks":0,"copied_files":0,"eligible_files":0,"embedded_chunks":0,"removed_files":0,"skipped_files":0},"durable":true,"error":{"code":"indexing_failed","message":"semantic indexing failed; inspect sanitized operation logs"},"index_id":"7e6ee770-21da-412c-807c-7ee8be805c60","namespace_key":"main","namespace_kind":"main","parent_index_id":null,"parent_revision":null,"promoted":false,"repo_slug":"agentic_coding_tools","reused":false,"source_revision":"184d132925215f03a84dd2867f15f9d5111a9902","status":"failed","storage_key":"i_7e6ee77021da412c807c7ee8be805c60"}
      ```

      **Three independent defects in `packages/code-search` were found, none of
      them in `wp-measure`'s `write_allow` and none of them fixed here.** They
      are the substance of the follow-up in 6.4.
      1. **`.cocoindex_code/settings.yml` does not exist and is never created.**
         `indexer_pg.py:211` calls
         `cocoindex_code.settings.load_project_settings(project_root)`, which
         raises `FileNotFoundError: Project settings not found:
         <repo-root>/.cocoindex_code/settings.yml`. No such file is tracked
         anywhere in this repository, `index_repo` does not write one, and
         `docs/guides/code-search.md`'s indexing procedure — which attempt 5
         followed exactly — never mentions it. **This alone makes the documented
         indexing path unrunnable in this repository at any scale.**
      2. **The secret scanner's operation deadline is spent on work it does not
         do.** `cli_runtime.py:108` constructs `LocalSecretScanner()` with the
         default `operation_timeout_seconds=30.0`. `_operation_deadline` is set
         at the *first* `scan_bytes` and never reset, and the same instance is
         reused for both source-manifest planning *and* the per-chunk scan at
         `indexer_pg.py:205` — i.e. across model loading and embedding. The
         regex work itself is not the cost: scanning all 1367 eligible files
         directly takes **0.44 s**, while the real run raised `scanner_timeout`
         after 456 files and 46.1 s. The timeout is not reachable from the CLI,
         so there is no operator remedy.
      3. **`credential_assignment` false-positives on ordinary source.** The
         rule `(?i)\b(?:password|secret|api[_-]?key|token)\s*[:=]\s*["']?[A-Za-z0-9_./+=-]{20,}`
         matches `token = authorization.partition(" ")`
         (`agent-coordinator/src/coordination_api.py`) and
         `api_key = api_key_resolver.resolve(`
         (`skills/parallel-infrastructure/scripts/review_dispatcher.py`) —
         identifier text, not credentials. Seven tracked files trip it and are
         unindexable without an explicit `--exclude`. None of the seven is an
         `expected_files` or `must_touch` target of any corpus case, so
         excluding them changed no case's answer.

- [x] 6.3 Run the harness across all declared gates and consumers and commit the
      report to `docs/evaluation/semantic-context/`
      **Spec scenarios**: `sce` — Evaluation report record / The report has a durable home
      **Contracts**: `contracts/schemas/context-eval-report.schema.json`
      **Design decisions**: D3, D11
      **Dependencies**: 6.2
      **Size**: M
      **Note**: if any step of 6.1-6.2 failed, commit the report with
      `verdict: "fail"` and `fail_reasons: ["unmeasured", ...]`. That is the
      correct outcome, not a blocked task.
      **Result**: `docs/evaluation/semantic-context/report.json` committed.
      **`verdict: "fail"`**, `fail_reasons: ["unmeasured",
      "denominator_mismatch", "index_tier_insufficient"]`. CLI exit `2`.
      `cases_declared: 19`, `cases_scored: 7`, `index.tier: "none"`,
      `index.indexed_revision: null`, `environment.scope_adapter: "resolved"`,
      `judge.available: false`.

      | Gate | Min tier | Verdict | Measured vs threshold |
      |---|---|---|---|
      | `retrieval_quality` | `live` | fail | nothing measured — `unmeasured`, `index_tier_insufficient` |
      | `coding_context_utility` | `live` | fail | 0 cases scored over 5 utility-applicable consumers — `unmeasured`, `index_tier_insufficient` |
      | `scope_compliance` | `none` | pass | 0 rendered violations vs max 0; outbound fidelity 1.0 vs min 1.0 — **vacuous, see below** |
      | `fail_closed_regression` | `none` | fail | expectation match rate **0.571 (4/7)** vs min 1.0 |

      **Corrected 2026-08-01.** The two rows above describe an artifact HEAD no
      longer reproduces. `ddc30be2` fixed the fourth defect below, and the
      report was regenerated from its own recorded inputs at index tier `none`:
      `scope_compliance` still passes but now over two injected adversarial arms
      and one `all_hits_scope_filtered` fallback rather than three empty ones,
      so it is no longer vacuous, and `fail_closed_regression` measures
      **1.0 (7/7)** and passes. The verdict, its three `fail_reasons`,
      `cases_declared: 19`, `cases_scored: 7` and the index tier are unchanged,
      so the enablement decision is unaffected. Neither the corpus nor any
      threshold was touched. See design.md, *Amendment — 2026-08-01*.

      Two runs were made and both are reported. The first declared
      `--evaluated-revision 184d1329…` (the branch tip); every recorded response
      in the corpus is pinned to `748af34c`, so all three adversarial `ready`
      responses short-circuited at `mismatched`/`index_revision_differs` before
      the scope check. The committed run declares `748af34c` and reads a
      worktree at that revision, which is the only configuration under which the
      corpus's recorded responses describe the tree being searched. Both runs
      produce the same four gate verdicts and the same `fail_reasons`.

      **The `scope_compliance` pass is vacuous and must not be read as
      evidence.** Every case that reaches ri-12's `ready` path raises
      `AttributeError: '_ResolvedScope' object has no attribute 'allows'` at
      `semantic_context.py:454`: the harness's scope stand-in
      (`producers/semantic_runtime.py:117-123`) implements `read_allow` and
      `deny` but not `allows()`, and ri-12's never-raises guarantee
      (`semantic_context.py:1355-1356`) converts it to
      `unavailable`/`unknown_state`. The three adversarial responses therefore
      render nothing, and a gate counting rendered violations counts zero. This
      is a fourth defect, in `packages/context-eval` itself — phase 3's producer
      — and it is outside `wp-measure`'s `write_allow`. It is also what drags
      `fail_closed_regression` to 4/7: the four genuinely non-`ready` responses
      each produced exactly their declared trigger/reason pair, so ri-12's own
      fail-closed mapping is intact and measured; the three that failed are the
      `ready` adversarial cases that never got far enough to honour anything.

      A fifth defect, unrelated: `FC-QUICK-TASK-NO-DECLARED-SCOPE` and
      `FC-DEBUG-ADHOC-NO-SCOPE` declare an empty read scope and are designed to
      short-circuit inside ri-12 *before* the search seam, so they need no
      recorded response — but `SemanticRuntimeProducer.render` rejects any case
      with `response is None` outside `--live` before running ri-12 at all. Two
      cases that are structurally scorable at tier `none` are unscorable.

      `--live` was not used and could not have helped: it is a per-*producer*
      switch, not per-case, so it would have put the six fail-closed and
      adversarial cases — whose whole content is a recorded response — onto the
      wire as well. With no index and no `ready` path, it would have measured
      nothing while looking like a measured 0/10.

- [x] 6.4 Record the outcome in the design's decision log and, if the verdict is
      FAIL, write the specific follow-up (what was measured, what threshold was
      missed, what would have to change)
      **Spec scenarios**: none
      **Contracts**: none
      **Design decisions**: D11
      **Dependencies**: 6.3
      **Size**: S
      **Note**: do NOT open a follow-up that says "re-run until it passes".
      **Result**: `design.md` gains a `## Recorded outcome — phase 6,
      2026-07-31 (D11)` section. It answers D11's three questions with the
      measurement rather than with an expectation: question 1 ("can the gate be
      run at all?") is **no**, and for reasons that are five citable defects
      rather than an environment; question 2 ("does it pass?") is **fail**, with
      semantic hit@5 still never measured on this repository; question 3 ("does
      ri-13 flip the flag?") is unchanged at **no**.
      The follow-up is written per-defect — what was measured, what it would
      take — for all five: `.cocoindex_code/settings.yml` absent
      (`indexer_pg.py:211`); the secret scanner's 30 s operation deadline spent
      on model loading and embedding (`cli_runtime.py:108`); the
      `credential_assignment` rule matching identifier text; `_ResolvedScope`
      missing `allows()` (`producers/semantic_runtime.py:117-123` vs
      `semantic_context.py:454`), which is what makes the `scope_compliance`
      pass vacuous; and `render` refusing empty-scope cases that need no
      recorded response. Plus two ownerless observations: `--live` is
      per-producer rather than per-case, and every recorded response hard-codes
      `source_revision: 748af34c`.
      No follow-up says "re-run until it passes", and the section closes by
      stating what the outcome does **not** license: no repetition, no threshold
      relaxation (nothing was approached, let alone narrowly missed), and no
      enablement — D12 reads `verdict != "pass"` as an expiry condition, so this
      report withdraws authorization rather than granting it.

- [x] 6.5 Checkpoint: run tests, review diff, verify scope
      **Result**: `packages/context-eval` **306 passed, 0 skipped** — identical
      to the phase 5 baseline, so recording a report at the durable path changed
      no test outcome (notably `test_spec_gate_artifact.py`, which now resolves a
      real artifact instead of asserting the absent-is-fail-closed state).
      `ruff check src/ tests/` clean; `mypy src/context_eval/ --strict` clean
      over 17 files. All three `wp-measure` tier-B checks pass: the report
      validates against the promoted
      `context-eval-report.schema.json`; `-k provenance` in
      `test_report_emitter.py` is 5 passed; `make semantic-enablement-gate`
      exits `0` — correctly, because `INJECTION_DEFAULT_ENABLED` is still
      `False` and a default that claims nothing needs no evidence. The report's
      `verdict` is `"fail"`, a member of the two-member closed enum, and its
      three `fail_reasons` are all members of the closed 12-item vocabulary.
      **Scope**: four files, all inside `wp-measure`'s `write_allow` except
      `tasks.md`, which is in no package's `write_allow` — the same plan gap
      phase 5 recorded at 5.8(a).
      **Environment left as found**: the scratch `ri13-measure-pg` container and
      both throwaway git worktrees are torn down. The other project's
      `real-ingestion-test-tiers-in-ci-postgres-1` on port 5432 was never
      connected to and is `Up (healthy)`. The five untracked
      `openspec/schemas/context-*.schema.json` files (issue #311) are still
      untracked, verified before and after every commit in this phase.

---

## Phase 7 — wp-integration: integrate, promote, prove

- [x] 7.1 Merge every package; run the full `packages/context-eval` suite, the
      full `skills/tests/context-engineering/` suite, and
      `bash skills/install.sh --check`
      **Dependencies**: 6.5
      **Size**: M
      **Result**: nothing to merge — `git branch --list` shows no `--wp-*`
      siblings for this change; all seven packages executed sequentially on
      the single branch `openspec/gate-semantic-context-default-enablement`.
      Full suites reproduce the phase 5/6 baseline unchanged:
      `packages/context-eval` **306 passed, 0 skipped**;
      `skills/tests/context-engineering/` **735 passed**;
      `bash skills/install.sh --check` exits 0 ("Skill install portability
      validation passed").

- [x] 7.2 Prove the enablement gate by mutation on the integrated tree: flip
      `INJECTION_DEFAULT_ENABLED` to `True` in a scratch commit, run
      `make semantic-enablement-gate`, capture non-zero exit and the named
      reason, then revert
      **Spec scenarios**: `sw` — Evidence-gated injection default / Enablement without evidence is rejected
      **Design decisions**: D14
      **Dependencies**: 7.1
      **Size**: S
      **Note**: a gate that was never shown to fail is not evidence that it
      works. Capture the output as an artifact.
      **Result**: flipped in scratch commit `84120599a2d8e5f3c995d108e70e32d2e26b5a8d`,
      reverted in the next commit (byte-identical to pre-flip, verified via
      `git diff HEAD~1`). Raw module exit `3`; `make`'s collapsed exit `2`
      with `make: *** [semantic-enablement-gate] Error 3` naming the real
      code. All three unmet conditions (`embedder_fingerprint_current`,
      `indexed_revision_reachable`, `verdict_pass`) were named correctly.
      Full output recorded at
      `docs/evaluation/semantic-context/enablement-gate-mutation-proof.md`.
      The gate is green again post-revert with the unmodified baseline
      message.

- [x] 7.3 Confirm all three contracts are promoted and byte-identical, and that
      `openspec/contracts/README.md` lists them
      **Dependencies**: 7.1
      **Size**: XS
      **Result**: `diff` confirms all three schemas
      (`context-eval-case.schema.json`, `context-eval-corpus.schema.json`,
      `context-eval-report.schema.json`) are byte-identical between
      `openspec/changes/gate-semantic-context-default-enablement/contracts/schemas/`
      and `openspec/contracts/semantic-context-evaluation/schemas/`.
      `openspec/contracts/README.md:69` lists the `semantic-context-evaluation`
      row naming this change. `packages/context-eval/tests/test_promoted_contracts.py`
      (57 passed) reproduces the same check automatically.

- [x] 7.4 Run `make context-drift-gate` and regenerate any artifact the new
      package or docs directory made stale
      **Dependencies**: 7.1
      **Size**: S
      **Result**: `make context-drift-gate` reported exactly two blocking
      drifts, both owned by this change: `api.contracts` (stale
      `docs/architecture-analysis/contracts-inventory.md`, missing the three
      newly promoted `semantic-context-evaluation` schemas) and
      `context.impact` (`work-packages.yaml`'s `wp-contracts` and
      `wp-scoring` packages had `context_impact` blocks that omitted the
      `documentation` surface their diffs imply). Remediated with
      `skills/project-context-refresh/scripts/cli.py generate api.contracts`
      (regenerated only the inventory file, confirmed by `git status`) and by
      adding `documentation` to both packages' `context_impact.surfaces`.
      Reran `make context-drift-gate`: **exit 0**, only the pre-existing
      `openspec.projection` informational drift remains — owned by
      `cleanup-feature` / `openspec archive`, deliberately not remediated
      here (it rewrites `openspec/specs/` from every active change's delta,
      not just this one). `validate_context_impact.py --base main` now
      reports all seven packages `declared`; `validate_work_packages.py`
      confirms the edited file is still schema-valid.

- [x] 7.5 Run `openspec validate gate-semantic-context-default-enablement
      --strict` and fix everything it reports
      **Dependencies**: 7.1
      **Size**: S
      **Note**: **Record the openspec version used.** CI installs
      `@fission-ai/openspec` unpinned (`ci.yml:92`), so local and CI can run
      different software and disagree. Measured 2026-07-27 at `748af34c`:
      version 1.1.1 reports `61 passed, 1 failed` (exit 1) while version 1.6.0
      reports `62 passed, 0 failed` (exit 0). Main is green; the discrepancy is
      tooling drift, tracked as issue #318. Validate with the version CI
      installs — `npx -y @fission-ai/openspec@<ci-version>` — and validate **by
      change id**, so neither a tooling difference nor another change's state
      can mask a real failure in this change's own deltas.
      **Result**: `npm view @fission-ai/openspec version` resolved to
      **1.7.0** on 2026-08-01 (CI's unpinned install would fetch the same,
      issue #318 still open). `npx -y @fission-ai/openspec@1.7.0 validate
      gate-semantic-context-default-enablement --strict` reports "Change
      'gate-semantic-context-default-enablement' is valid" (exit 0). Nothing
      to fix.

- [x] 7.6 MANUAL: record the exact `gh api` call to add the two new jobs to
      branch protection's required contexts, and state that until it is applied
      they are "blocking jobs, not required contexts"
      **Design decisions**: D14
      **Dependencies**: 7.2
      **Size**: XS
      **Result**: NOT EXECUTED, per the task — this is a record for a human
      with admin rights on the repository. The two job ids this change adds to
      `.github/workflows/ci.yml` are `context-eval` (line 458) and
      `semantic-enablement-gate` (line 521). Current required contexts on
      `main` (queried read-only via `gh api
      repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks`):
      `test`, `test-infra-skills`, `test-skills`, `validate-specs`,
      `check-docker-imports`, `secret-scan` — neither new job is in that set.
      The call a repository admin must run to add them:

      ```bash
      gh api -X PATCH repos/jankneumann/agentic-coding-tools/branches/main/protection/required_status_checks \
        -f strict=false \
        -f 'contexts[]=test' \
        -f 'contexts[]=test-infra-skills' \
        -f 'contexts[]=test-skills' \
        -f 'contexts[]=validate-specs' \
        -f 'contexts[]=check-docker-imports' \
        -f 'contexts[]=secret-scan' \
        -f 'contexts[]=context-eval' \
        -f 'contexts[]=semantic-enablement-gate'
      ```

      **Until this is applied, `context-eval` and `semantic-enablement-gate`
      are blocking jobs, not required contexts**: they run on every PR and a
      failure shows red in the checks list (task 4.5, task 5.5), but GitHub
      does not refuse to merge on their failure the way it does for the six
      contexts already in the required set. A PR could be merged past a red
      `semantic-enablement-gate` — the one gate this whole change exists to
      make load-bearing — until a human runs the command above.
