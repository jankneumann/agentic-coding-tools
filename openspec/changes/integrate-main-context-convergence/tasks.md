# Tasks — integrate-main-context-convergence (ri-11)

Each task is sized to one commit. Group numbers map to work packages in
`work-packages.yaml`.

## 1. Convergence record contract (wp-contracts)

**Files**: `openspec/changes/integrate-main-context-convergence/contracts/`,
`openspec/contracts/project-context-refresh/schemas/`,
`skills/project-context-refresh/install_assets/openspec/schemas/`,
`skills/tests/project-context-runtime/`
**Dependencies**: none

- [x] 1.1 Write a failing test asserting `context-convergence-record.schema.json` is
      present in the promoted-contract byte-compare set. It must fail before 1.2.
- [x] 1.2 Author `context-convergence-record.schema.json`: closed object with
      `operation_id`, `merged_revision`, `refresh_revision`, `convergence_commit`,
      `manifest_path`, `manifest_sha256`, `refresh_status`, `producers[]`
      (`producer_id` / `status` / `owner`), `semantic_index` (`status`,
      `requested_revision`, `operation_id`), and `merged_pull_requests[]`. `$ref`
      `GitRevision` from `context-refresh-types.schema.json` rather than restating it.
- [x] 1.3 Install the schema under
      `skills/project-context-refresh/install_assets/openspec/schemas/` and declare it
      in `skills/install-manifest.json`; verify with `bash skills/install.sh --check`.
- [x] 1.4 Copy the schema to
      `openspec/contracts/project-context-refresh/schemas/` and make 1.1 pass.

## 2. Sync-point authorization and deferred semantic index (wp-sync-point)

**Files**: `skills/project-context-refresh/scripts/cli.py`,
`skills/project-context-refresh/scripts/orchestrator.py`,
`skills/tests/project-context-refresh/`
**Dependencies**: none

- [x] 2.1 Write a failing test proving `refresh` is refused from a shared checkout
      today and permitted with sync-point authorization (design D5). Assert against
      `checkout_policy.classify_checkout` reasons, not message strings.
- [x] 2.2 Add `--sync-point` to the `refresh` subparser and thread `sync_point=True`
      through `_require_mutation` into `require_mutation_allowed`. Default stays
      `False`; no environment inference (D5).
- [x] 2.3 Write a failing test that a deferred-index refresh records a `pending`
      `SemanticIndexReference` with an `exact-search` fallback and produces
      byte-identical deterministic results to a non-deferred run (D7).
- [x] 2.4 Add a `defer_semantic_index` keyword to `orchestrator.generate` that skips
      the inline attempt and records the pending reference. Do not change
      `decide_outcome`; a pending index degrades through the existing rule.
- [x] 2.5 Add `--defer-semantic-index` to the CLI and surface both new flags in the
      skill's docstring and `SKILL.md`.
- [x] 2.6 Verify by mutation that 2.1 and 2.3 fail against the pre-change modules.
      Clear `__pycache__` between mutation cycles.

## 3. Convergence driver (wp-convergence)

**Files**: `skills/merge-pull-requests/scripts/main_convergence.py`,
`skills/tests/merge-pull-requests/`
**Dependencies**: wp-contracts, wp-sync-point

- [x] 3.1 Write failing tests for operation identity: the id derives from
      `(repository_id, merged_main_sha)`, is stable across retries, and differs when
      the SHA differs (D4).
- [x] 3.2 Implement identity resolution plus the two-source idempotence check —
      terminal ri-06 record **or** `Context-Refresh-Operation:` commit trailer
      discoverable via `git log --grep` (D4). Either alone is sufficient to skip.
- [x] 3.3 Write failing tests for the three-layer guard: active-agent check,
      coordinator lock when available, and the pre-push compare-and-swap against
      `origin/main` (D5).
- [x] 3.4 Implement the guards. Coordinator unavailability degrades with a recorded
      warning; a losing push race aborts and never force-pushes.
- [x] 3.5 Implement the phase sequence: staged cleanup output → `make
      architecture-refresh` → `cli.py refresh --sync-point --defer-semantic-index` →
      one commit → one push (D2, D3, D10).
- [x] 3.6 Implement the outcome mapping from design D6 (succeeded / degraded /
      failed / apparatus-failure) and assert with tests that no branch can revert,
      close, or reopen a pull request.
- [x] 3.7 Emit the convergence record as one JSONL line to
      `docs/merge-logs/context-convergence.jsonl` and validate it against the
      wp-contracts schema in a test (D9).
- [x] 3.8 Implement post-push semantic enqueue for the final pushed SHA, fire-and-
      report, with a test that an unavailable service still lets the pass complete (D7).
- [x] 3.9 Add a `--dry-run` path that derives and reports the identity, checks for an
      existing convergence, and runs `make context-drift-gate` read-only (D12).

## 4. Merge-driven cleanup mode (wp-cleanup)

**Files**: `skills/cleanup-feature/SKILL.md`, `skills/tests/cleanup-feature/`
**Dependencies**: wp-sync-point

- [ ] 4.1 Write a failing `test_skill_md.py` assertion that `cleanup-feature`
      documents a merge-driven deferred-commit mode and names the sync point as the
      committer.
- [ ] 4.2 Document `--defer-commit` in the Arguments section and in the post-merge
      mode section: operate in the sync-point checkout on main, stage with `git add`,
      commit nothing, push nothing (D3).
- [ ] 4.3 Replace `make architecture` with `make architecture-refresh` in the
      post-merge step and state why (provenance is written only by the staged target,
      D10). Add a failing assertion for this first.
- [ ] 4.4 Document the partial-failure rule: staged output from changes that already
      succeeded is committed by the sync point, never discarded (D3).
- [ ] 4.5 Update the Verification and Red Flags sections for the new mode.

## 5. Merge skill integration (wp-skill)

**Files**: `skills/merge-pull-requests/SKILL.md`,
`skills/tests/merge-pull-requests/`
**Dependencies**: wp-convergence, wp-cleanup

- [ ] 5.1 Write failing `test_skill_md.py` assertions that Step 11.6 exists, sits
      between Steps 11.5 and 12, and names `cleanup-feature --post-merge` before the
      refresh.
- [ ] 5.2 Author Step 11.6 with the three-phase sequence, the guard order, and the
      exact commands.
- [ ] 5.3 Extend the Step 12 summary template with merged SHA, context-refresh SHA,
      convergence commit SHA, and semantic-index status (acceptance outcome 5).
- [ ] 5.4 Extend the merge-log template (Step 13) with a Context Convergence section.
- [ ] 5.5 Add Error Handling rows for lock contention, push race, producer failure,
      and unavailable index; add Common Rationalizations and Red Flags entries for
      skipping convergence or forcing a losing push.
- [ ] 5.6 Update the Dry-Run Mode section per D12.

## 6. Integration and proof (wp-integration)

**Files**: repository-wide
**Dependencies**: all packages

- [ ] 6.1 Merge every package worktree and run the full affected test suites.
- [ ] 6.2 Demonstrate the guard fails before it passes: on an unmodified tree, show
      that `refresh` is refused from the shared checkout, then show it permitted with
      `--sync-point`. Capture both outputs as evidence.
- [ ] 6.3 Rehearse one full convergence end to end against a scratch clone with a
      single merged PR; capture the convergence record, the commit trailer, and the
      handoff report.
- [ ] 6.4 Prove idempotence: re-run the rehearsal at the same merged SHA and show no
      second commit, no second archive, and no second index request.
- [ ] 6.5 Run `make context-drift-gate` on the post-convergence tree and confirm
      exit 0.
- [ ] 6.6 Run `openspec validate integrate-main-context-convergence --strict`,
      `bash skills/install.sh --check`, and the skills lint gate at the locked
      version.
- [ ] 6.7 Sync skills to runtimes with
      `bash skills/install.sh --mode rsync --force --deps none --python-tools none`.
- [ ] 6.8 Confirm the contract is promoted to
      `openspec/contracts/project-context-refresh/schemas/` and byte-identical to the
      change-local and install-asset copies.
