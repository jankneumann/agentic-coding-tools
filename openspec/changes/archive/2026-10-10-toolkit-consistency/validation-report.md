# Validation Report: toolkit-consistency

**Date**: 2026-10-10
**Commit**: e4d0b25da37427fb3851ac276115b7cbb9460615 (branch `openspec/toolkit-consistency-closeout--validate`)
**Reviewed at**: 44f696041ab8b60c668c162561c34fc7232c38a5 (VAL_REVIEW post-merge, branch
`openspec/toolkit-consistency-closeout--val-review`). `git diff e4d0b25 44f6960 -- skills docs`
and `git diff origin/openspec/roadmap-multiplayer-collaboration 44f6960 -- skills docs` are both
empty: every section below ran against the merged code byte for byte, and the review round
re-ran the live flows at 44f6960 (see Validation Review).
**Scope**: Re-validation of the MERGED toolkit-consistency code (PR #671, rebase-merged into
`openspec/roadmap-multiplayer-collaboration`). All evidence below was re-run on this commit in
this container; nothing was copied from the earlier report except the scenario-to-test mapping.
The earlier report used `Result:` lines, which `gate_logic.check_phase_status()` does not parse;
every section below uses the documented `**Status**:` form.
**Overall**: PASS (all five goal-gate sections; the Validation Review section was written after
its round ran, not before)

## Phase Summary

| Phase | Status |
|-------|--------|
| Deploy | not applicable (no service: shell installer and Python scripts) |
| Spec Compliance | pass |
| Smoke Tests | pass |
| Security | pass |
| E2E Tests | pass |
| Test suites | pass (255 passed, 1 skipped, 0 failed) |
| Validation Review | pass (VAL_REVIEW post-merge, claude_code single vendor, 0 blocking; ledger 76-81) |

This table summarises for readers. `gate_logic.check_phase_status()` parses each section's
`**Status**:` line (`pass`, `fail`, `skipped`, `degraded`, `not applicable`), not this table, so
the `Test suites` row, which has no section of its own, is informational. Deploy is not one of
the goal gate's five required sections (Spec Compliance, Smoke Tests, Security, E2E Tests,
Validation Review); its `not applicable` parses as `not_applicable`.

## Deploy

**Status**: not applicable

Reason: the change ships a shell installer (`skills/install.sh`) and Python scripts; there is no
service to deploy, so the container phases do not apply.

## Spec Compliance

**Status**: pass

`openspec validate toolkit-consistency --strict` -> "Change 'toolkit-consistency' is valid".
`specs/toolkit-distribution/spec.md` declares 29 scenarios (`grep -c '^#### Scenario'` = 29).

Scenario mapping. Tests are in `skills/tests/install_sh/` (I) and
`skills/tests/improve-harness/` (H); "live" means exercised in the Smoke and E2E sections below.

| Scenario | Evidence |
|----------|----------|
| Consumer install writes the stamp | I test_install_stamp::test_consumer_install_writes_stamp; live install wrote stamp.json |
| Self-install writes no stamp | I test_self_install_writes_no_stamp |
| Aborted install leaves previous stamp intact | I test_aborted_install_leaves_previous_stamp_intact |
| Check mode does not stamp | I test_check_mode_does_not_stamp; live `--check` with stamp removed left it absent |
| Source and mirror hash identically | I test_payload_hash::test_source_and_mirror_hash_identically (copy and rsync; rsync present) |
| Content change changes the hash | I test_content_change_changes_hash |
| Excluded directories do not affect the hash | I test_excluded_directories_do_not_affect_hash |
| Helper passes the portability gate | `skills/install-manifest.json` `smoke_entrypoints` lists `shared/payload_hash.py`; I test_consumer_portability::test_manifest_entry_points_run_without_source_checkout iterates that list and runs each entry from the installed closure (not skipped: rsync present); live gate pass on both installs |
| Pinned payload matches | I test_pinned_payload_matches; live `--check` exit 0 "Pinned toolkit matches" |
| Checkout drift | I test_checkout_drift (+ changed-skill-set variant) |
| Runtime drift | I test_runtime_drift_names_the_agent; live edit -> exit 1 "Runtime drift" |
| Unpinned repository | I test_unpinned_repository_is_advisory; live exit 0 "Unpinned" |
| Invalid stamp fails loud | I test_invalid_stamp_fails_loud_and_is_not_rewritten; live exit 1 "Invalid toolkit stamp" |
| Self-install skips the stamp comparison | I test_self_install_skips_stamp_comparison |
| Export refused without opt-in | H test_export_refused_without_opt_in (incl. wrong-schema), test_cli_refuses_without_config; live exit 2 (absent config and schema_version 2) |
| Export with opt-in | H test_export_with_opt_in_writes_one_object_per_line; live stubbed export |
| Installer never touches the config | I test_installer_never_touches_config; live re-install with `--force` left config.json and learnings.jsonl intact |
| Transcript-mined entries are excluded | H test_transcript_mined_entries_are_excluded (+ variants fail closed, producer tag test); live |
| Private fields are dropped | H test_private_fields_are_dropped; live |
| Identity-bearing tags are dropped | H test_identity_bearing_tags_are_dropped; live |
| Secrets are redacted | H test_secrets_are_redacted; live (GitHub token and AWS key redacted) |
| Deterministic output | H test_output_is_deterministic_sorted_and_deduplicated; live second run byte-identical |
| Exporter passes the portability gate | `smoke_entrypoints` lists `improve-harness/scripts/export_shared_learnings.py`; I test_consumer_portability::test_manifest_entry_points_run_without_source_checkout runs it from the installed closure; installer "portability validation passed" |
| Shared records merged and attributed | H test_shared_learnings_merge::test_shared_record_is_merged_and_attributed |
| Duplicate shared record appears once | H test_duplicate_shared_record_appears_once_from_custom_path |
| Disabled sharing ignores the file | H test_disabled_sharing_ignores_the_file |
| No write-back | H test_module_has_no_memory_write_path, test_cli_merges_and_never_stores_to_memory |
| Registration rows present | I test_state_artifacts_registration::test_artifact_row_names_writer_and_missing_behavior |
| Projection never feeds canonical state | I test_learnings_projection_never_feeds_canonical_state |

All 29 scenarios covered.

## Smoke Tests

**Status**: pass

Fresh `mktemp -d` git repo under the session scratchpad (`consumer.W04v`); real consumer install,
`install.sh --target <tmp> --mode copy --deps none --python-tools none`:

- Install exit 0; "Skill install portability validation passed"; 75 skill directories x 2
  agents copied; stamp written: `toolkit_version 0.2.0`, `source_commit e4d0b25...`,
  `payload_hash sha256:fcd299a0afd2...`, agents `agents`+`claude`, mode `copy`.
- `--check` immediately after: exit 0, "Installed skill mirrors match canonical payload",
  "Pinned toolkit matches: 0.2.0 (sha256:fcd299a0afd2)".
- rsync is present here (`/usr/bin/rsync`), so rsync-gated tests ran; the smoke install itself
  was copy mode as specified.

## Security

**Status**: pass

- Portability gate: `skills/shared/validate_install_manifest.py --skills-root skills` ->
  "Skill install portability validation passed"; also run by both live installs.
  `test_consumer_portability.py` passes in the suite run (not skipped: rsync present).
- Exporter privacy rules, verified live with a stubbed `query_memory` (installed copy of the
  exporter, 3 stub entries): allowlisted fields only (`details`, `agent_id`, `session_id`
  dropped); only the five tag namespaces survive (`agent:` and `session:` tags dropped); the
  `source:transcript-mined` entry was excluded (2 of 3 exported); the GitHub token and AWS
  key were redacted (`[REDACTED:github-token]`, `[REDACTED:aws-access-key]`); output sorted
  keys, one object per line.
- Secret scan (`secret_scan_substitute`, operator-accepted; gitleaks unavailable and NOT
  downloaded): regex scan with `git grep` over `skills/shared`, `skills/improve-harness`,
  `skills/install.sh`, the install_sh/improve-harness/shared/_shared test trees, `docs`, and
  `openspec/changes/toolkit-consistency` for `AKIA[0-9A-Z]{16}`, `ghp_`, `gho_`,
  `github_pat_`, `xox?-`, `sk-`, private-key headers, and quoted
  `key|secret|token|password` literals. One token-shaped hit only: the synthetic AWS key
  fixture at `skills/tests/improve-harness/test_export_shared_learnings.py:266`, used by
  `test_secrets_are_redacted`. The literal substring `github_pat_` also matches twice in prose
  in `docs/kanban-viz/README.md` (error-code names `github_pat_denied`, `github_pat_missing`;
  pre-existing, outside this change, not tokens). This status rests on that substitute, not on
  gitleaks. (The sentence on the prose matches was added by VAL_REVIEW, VAL_FIX 9; the status
  is unchanged.)

## E2E Tests

**Status**: pass

Drift, opt-in and determinism flows on the consumer repo above:

- Runtime drift: appended a line to installed `.claude/skills/shared/payload_hash.py` ->
  `--check` exit 1, "Runtime drift: installed claude copies are not the pinned payload
  (pinned 0.2.0 @ e4d0b25..., sha256:fcd299a0...; installed sha256:bd2404c1...)"; reverted ->
  exit 0 "Pinned toolkit matches".
- Invalid stamp (`{not json`) -> exit 1, "Invalid toolkit stamp".
- Unpinned (stamp removed) -> exit 0, "Unpinned: no .../stamp.json ... Run install.sh"; no
  stamp was written by `--check`.
- Exporter, no config -> exit 2 "refusing to export: ... config.json is absent", nothing written.
- Exporter, config `schema_version: 2` -> exit 2 "unsupported schema_version 2 (expected 1)".
- Exporter, valid opt-in config + stubbed memory -> exit 0, 2 of 3 entries; second run
  byte-identical (`cmp`).
- Re-install with `--force` preserved `config.json` and `learnings.jsonl` (byte-identical).

Pytest (`skills/.venv`, created by `uv sync --all-extras --directory skills`;
`skills/tests/install_sh`, `improve-harness`, `_shared`, `shared`):
**255 passed, 1 skipped, 0 failed** (344.5s). The one skip is
`skills/tests/shared/test_validate_install_manifest_excludes.py:101` "node_modules not present
in this checkout"; rsync is installed here, so the 15 rsync-gated tests all executed. (Two
pre-merge runs are referred to below: the first pre-merge VALIDATE run, with rsync absent,
skipped those 15; the pre-merge VAL_REVIEW run on 80747aa, with rsync installed by VAL_FIX 1,
executed them.) No test was skipped or weakened by the validator.

Baseline for the count (256 collected): this change's six test files (`test_payload_hash`,
`test_install_stamp`, `test_install_check_drift`, `test_state_artifacts_registration`,
`test_export_shared_learnings`, `test_shared_learnings_merge`) hold 67 tests, unchanged since
the PR tip 80747aa because `skills/` is unchanged; the other 189 are pre-existing suites. The
pre-merge VAL_REVIEW run on 80747aa (rsync installed, so the same 15 tests executed; the only
skip was the same `node_modules` one) counted 189 passed + 1 skipped = 190 collected because
those pre-existing suites then held 123 tests: `skills/tests/shared/` gained 66 from other changes merged into the roadmap branch
between the PR base and the rebase merge (`test_dispatch_contract.py` 44,
`test_trust_posture_scope.py` 12, `test_approval_gate_provenance.py` 5,
`test_environment_profile_host_id.py` 5; `git diff --stat 80747aa HEAD -- skills/tests`).

## Validation Review

**Status**: pass

Post-merge round (this container, branch `openspec/toolkit-consistency-closeout--val-review`,
HEAD 44f6960, 2026-10-10). The code was reviewed and merged before this round (PR #671;
IMPL_REVIEW and the pre-merge VAL_REVIEW rounds, ledger 1-75); this round critiques the
validation evidence above: does it, re-run on the merged code, prove the four ri-20 acceptance
outcomes and the 29 scenarios?

- `converge(review_type=implementation, min_quorum=1, fix_mode=targeted)` ran as the whole
  phase with a real VAL_FIX applicator wired (claude_code write-capable mode, scoped to this
  change directory). Packet: `git diff origin/openspec/roadmap-multiplayer-collaboration...HEAD`
  (5 files: this report, two `dispatch-results/` records, and `skills/autopilot/scripts/goal_gate.py`
  plus its test: the merge base predates the goal-gate author-date fix and both branches carry
  it as separate commits (94bf202 here, d1f65b25 on the roadmap tip), so the three-dot diff
  shows it although the tips are identical; `loop-state.json`, `.review-ledger/**` and
  `.review-cache/**` excluded) plus a
  45,181-char addendum: review focus, code-identity facts, the four acceptance outcomes, this
  report, the pre-merge Validation Review section from git history, proposal.md and the full
  spec. 103,051 of 320,000 chars, nothing truncated. Dispatch: claude_code CLI (`claude-local`,
  model fable, 120 s); 6 findings (1 high, 1 medium, 4 low), fact-check kept all 6; 0 blocking
  under D3 (single vendor: every finding is `unconfirmed` judgment). Ledger 76 (high judgment)
  made the loop return `adjudication_required`; the conductor adjudicated it (below).
  Evidence: `.review-cache/round-1-val-postmerge-initial/`; ledger 76-81.
- Degradation `single_vendor_review` (phase VAL_REVIEW post-merge, vendor claude_code, policy
  TRUST_POSTURE.md 479dcd9): per the operator policy only the claude_code local CLI adapter
  was dispatchable; no other lane or credential was probed (`report_degraded`: "only 1 of 2
  required vendors dispatchable"). Compensating control, as in the earlier rounds: the
  findings were read as conductor and the real ones fixed (VAL_FIX 8), and the live flows
  below were re-run independently of the dispatched reviewer.
- `secret_scan_substitute` (operator-accepted 2026-10-10): gitleaks is not installed and was
  not downloaded. The regex scan re-ran at 44f6960 over the paths the Security section lists:
  token-shaped patterns hit only the synthetic AWS key fixture at
  `skills/tests/improve-harness/test_export_shared_learnings.py:266`; the literal substring
  `github_pat_` also appears twice in prose in `docs/kanban-viz/README.md` (error-code names
  `github_pat_denied`, `github_pat_missing`, pre-existing and outside this change), which the
  Security section's "one hit" count, being a count of token-shaped matches, does not list.
  The Security `**Status**` stands on that substitute, not on gitleaks.

Evidence re-run at 44f6960 by the review round (in addition to the VALIDATE evidence above):

- `openspec validate toolkit-consistency --strict` valid; `grep -c '^#### Scenario'` = 29; all
  35 `test_*` names cited in the Spec Compliance table resolve to a test function or module
  under `skills/tests/install_sh` or `skills/tests/improve-harness`; pytest collects 256 tests
  in the four suites (= 255 passed + 1 skipped), and a fresh run with the goal-gate tests
  added gave **285 passed, 1 skipped, 0 failed** (255 + 30; 347.8s).
- Fresh scratch consumer, `install.sh --target <tmp> --mode copy --deps none
  --openspec-assets none --openspec-cli none --python-tools none`: exit 0, portability gate
  passed, 75 skill directories x 2 agents; stamp `schema_version 1`, `toolkit_version 0.2.0`,
  `source_commit 44f6960...`, `payload_hash sha256:fcd299a0afd2...` (identical to the e4d0b25
  smoke hash: the payload is byte-identical), `agents ["agents","claude"]`, `mode copy`.
  `--check`: exit 0, "Pinned toolkit matches: 0.2.0 (sha256:fcd299a0afd2)".
- Runtime drift (one line appended to the installed `shared/payload_hash.py`): exit 1,
  "Runtime drift: installed claude copies are not the pinned payload (pinned 0.2.0 @
  44f6960..., sha256:fcd299a0...; installed sha256:bd2404c1...)"; file restored, `--check`
  exit 0 again. Invalid stamp (`{not json`): exit 1 "Invalid toolkit stamp: .../stamp.json",
  file content unchanged afterwards. Stamp removed: exit 0 "Unpinned: no .../stamp.json",
  `.agentic-toolkit/` still empty afterwards (nothing written by `--check`).
- Exporter from the source checkout against an empty scratch repo: absent config -> exit 2
  "refusing to export: .../config.json is absent"; `schema_version: 2` -> exit 2 "unsupported
  schema_version 2 ... (expected 1)"; `.agentic-toolkit/` holds only the config afterwards.
- Loose grep `agent-coordinator|coordination_mcp|coordination_api` over the installed
  `.claude/skills` mirror: 61 files, none of them `shared/payload_hash.py`,
  `improve-harness/scripts/export_shared_learnings.py`, `analyze_failures.py` or the
  improve-harness SKILL.md; no `from|import src|agent_coordinator|coordination_*` statement
  anywhere in the mirror. The authoritative gate (`validate_install_manifest.py`) passed on
  the live install and in `test_consumer_portability`.

Acceptance outcomes (roadmap `multiplayer-collaboration`, item ri-20) and the evidence at
44f6960 that proves each:

| # | Outcome | Evidence |
|---|---------|----------|
| 1 | A consumer repository records the installed toolkit version and payload hash in a tracked file registered in `docs/guides/state-artifacts.md` | Live stamp above (`toolkit_version`, `payload_hash`, `source_commit`); `test_install_stamp` (consumer writes, self-install does not, aborted install leaves the prior stamp, `--check` does not stamp); `test_state_artifacts_registration::test_artifact_row_names_writer_and_missing_behavior[.agentic-toolkit/stamp.json]`. "Tracked" is the consumer's act: the installer writes the file and cannot commit it; the proposal and `docs/guides/skills.md` make committing it the declaration of the pin (ledger 75, open advisory) |
| 2 | `install.sh --check` reports drift between the pinned version and the local runtime copy | Live runtime-drift, invalid-stamp and unpinned flows above (messages name the pinned `0.2.0 @ 44f6960`); `test_runtime_drift_names_the_agent`, `test_checkout_drift`, `test_checkout_drift_with_changed_skill_set_is_not_runtime_drift`, `test_pinned_payload_matches`, `test_unpinned_repository_is_advisory`, `test_invalid_stamp_fails_loud_and_is_not_rewritten`, `test_self_install_skips_stamp_comparison`. Checkout drift is proven by test only in this round (the pre-merge round also saw it live at bdfeefe) |
| 3 | Repository-scoped learnings are opt-in and never include private transcript content | Opt-in: live exporter refusals above; `test_export_refused_without_opt_in[absent, disabled, string-true, bad-json, not-object, wrong-schema]`, `test_cli_refuses_without_config`, `test_refusal_does_not_overwrite_existing_learnings`, `test_installer_never_touches_config`, `test_disabled_sharing_ignores_the_file[...]`. Transcript content: `test_transcript_mined_entries_are_excluded`, `test_transcript_mined_variants_fail_closed`, `test_producer_transcript_tag_is_excluded` (tag built with collect-transcripts' own `TranscriptFinding.to_memory_tags()`), `test_private_fields_are_dropped`, `test_identity_bearing_tags_are_dropped`, `test_secrets_are_redacted`; the VALIDATE live stubbed export (2 of 3 entries, redaction markers, byte-identical second run). Known limit (design D8): self-reported `summary`/`lessons` are exported after the sanitizer; only secret patterns are redacted |
| 4 | Installed payloads contain no references to private coordinator source | Authoritative gate `skills/shared/validate_install_manifest.py` (rejects private coordinator `src` imports and `sys.path`/`parents[...]` injection of `agent-coordinator`): passed on the live install at 44f6960, on both VALIDATE live installs, and in `test_consumer_portability`, including `test_manifest_entry_points_run_without_source_checkout[.claude|.agents]`, which runs `shared/payload_hash.py --help` and `export_shared_learnings.py --help` from the installed closure (rsync present, not skipped). Loose grep re-run above: 61 pre-existing files (documentation strings, repo-root markers, opt-in integrations), none in this change, no source import |

Scenario evidence (29): the Spec Compliance table stands; this round added the
`smoke_entrypoints` citation to the two portability rows (ledger 80) and re-ran the live
flows behind 'Consumer install writes the stamp', 'Pinned payload matches', 'Runtime drift',
'Unpinned repository', 'Invalid stamp fails loud' and 'Export refused without opt-in' at
44f6960.

Findings (ledger id, criticality) and dispositions. Nothing blocked under D3, so the wired
applicator never fired; VAL_FIX 8 is a conductor sub-step (commit 0b945f5), report text only:

- 76 high, judgment (adjudication): the rewrite dropped the acceptance-outcome -> evidence
  mapping and its pre-merge evidence (bdfeefe/b7f8168/80747aa) could not be relied on from git
  history for a report that claims re-run evidence -> VAL_FIX 8: the table above, built from
  this run's evidence at 44f6960; trackedness caveat (75) and D8 limit carried over; the
  pre-merge 59-file loose grep re-run: 61 files. 56 of them are byte-identical to the
  pre-merge payload; the five that changed between the PR tip 80747aa and the merge
  (`autopilot/SKILL.md`, `supervise/SKILL.md`, `parallel-infrastructure/scripts/review_dispatcher.py`,
  `supervise/scripts/cycle_state.py`, `supervise/scripts/execution.py`, all pre-existing files
  edited by other merged changes) match only in documentation strings, comments and repo-root
  path markers (`agent-coordinator/agents.yaml`, `archetypes.yaml`, `routing.yaml`), so the
  +2 lies among them and none is a source import.
- 77 medium: `**Status**: not applicable` might not be a parser token and the Phase Summary
  has a row without a section -> evidence, not a fix: `gate_logic.check_phase_status()`
  recognises `pass|fail|skipped`, `degraded` and `not applicable` (`not_applicable`); Deploy
  is not a required section; the table is not parsed. At 44f6960 before VAL_FIX 8:
  Spec Compliance, Smoke Tests, Security, E2E Tests = `pass`, Deploy = `not_applicable`,
  Validation Review = `missing` (the `pending` placeholder, which only this section could
  close). The g8 refusal the finding cites predates the rewrite (be36e3a). Recorded in the
  Phase Summary note.
- 78 low: `Overall: PASS` and the Result section beside a `pending` section -> VAL_FIX 8:
  this section's `**Status**: pass`, the Phase Summary row, the header note and the Result
  section are written after the round.
- 79 low: 189 -> 255 tests unexplained; "first run" wording -> VAL_FIX 8: baseline paragraph
  in E2E Tests (67 tests from this change, 66 added to `skills/tests/shared/` by other merged
  changes), wording names the pre-merge run as a comparison.
- 80 low: portability rows silent on the `smoke_entrypoints` half of the THEN -> VAL_FIX 8:
  both rows cite the manifest entries and the test that iterates them.
- 81 low, `out_of_change` (`goal_gate.py` author-date caveat should also name
  `--reset-author-date`/`--ignore-date` rebases and squash merges): parked `out_of_scope`;
  orchestrator infrastructure, not this change's code, and no code is edited in this phase.
  Forwarded to the autopilot owners in the ledger resolution.
- No code defect was found; of the 18 pre-merge open advisory items (all low), 17 remain
  open and 75 closes below.

Verification round: a second `converge()` run over the VAL_FIX 8 diff only (packet base
44f6960, 1 file, 89,125 chars, same addendum plus a verification note) converged in round 1:
claude_code (fable, 103 s), 6 findings (1 medium, 5 low), fact-check kept all 6, 0 blocking,
no adjudication. Evidence `.review-cache/round-1-val-postmerge-verify/`; ledger 82-87.
Dispositions (VAL_FIX 9, conductor, record-only, this commit; no third round, the same
two-round pattern as IMPL_REVIEW and the pre-merge VAL_REVIEW, with `check_phase_status` and
the test counts as the check on record-only edits):

- 82 medium: the test-count baseline conflated two pre-merge runs -> E2E Tests names them
  (first VALIDATE run, rsync absent, skipped 15; VAL_REVIEW run on 80747aa, rsync installed,
  189 + 1 = 190).
- 83 low: the Security section's "one hit" stood beside a pattern list that matches prose ->
  the Security section itself now states one token-shaped hit plus the two prose matches.
  Text only; its `**Status**` is unchanged (stated explicitly per the phase policy).
- 84 low: the 59 -> 61 loose-grep delta unexplained -> named under 76 above.
- 85 low: no verification round recorded and VAL_FIX 8 unnamed -> this paragraph; VAL_FIX 8 is
  commit 0b945f5.
- 86 low: the goal_gate packet explanation read as a contradiction -> reworded above (merge
  base predates the fix; both branches carry it as separate commits).
- 87 low (re-verification of 75): the outcome-1 row satisfies ledger 75's first remedy -> 75
  and 87 closed as addressed by report text; the `git check-ignore` warning alternative
  remains a code change outside this phase.

## Result

PASS: spec, smoke, security and e2e pass on the merged code (e4d0b25 = 44f6960 for `skills/`
and `docs/`); the Validation Review round re-ran the live flows at 44f6960, found no code
defect, closed its report findings with VAL_FIX 8 (0b945f5), and its verification round
converged (VAL_FIX 9, record-only).
