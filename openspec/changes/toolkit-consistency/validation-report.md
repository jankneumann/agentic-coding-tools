# Validation Report: toolkit-consistency

**Date**: 2026-10-10
**Commit**: cce5f3662b1c0588290e2b4a56d191b41f817c9a (branch `openspec/toolkit-consistency--validate`)
**VAL_FIX commit**: b7f8168 (branch `openspec/toolkit-consistency--val-review-2`, from bdfeefe).
`skills/` and `docs/` are byte-identical between cce5f36 and bdfeefe (`git diff --stat cce5f36
bdfeefe -- skills/ docs/` is empty), so the Deploy, Spec Compliance, Smoke, Security and E2E
sections below describe the code at bdfeefe unchanged; the post-VAL_FIX re-run is in the
Validation Review section.
**Overall**: PASS

## Phase Summary

| Phase | Result |
|-------|--------|
| Deploy | skip (no service: shell installer + Python scripts) |
| Spec Compliance | pass |
| Smoke Tests | pass |
| Security | pass |
| E2E Tests | pass |
| Test suites | pass (168 passed, 16 skipped) |
| Validation Review | pass (single-vendor converge, 0 blocking; VAL_FIX 1-6; see section) |

## Deploy

Result: skip. The change ships a shell installer and Python scripts; there is no
service to deploy.

## Spec Compliance

Result: pass

`openspec validate toolkit-consistency --strict` -> "Change 'toolkit-consistency' is valid".

Scenario mapping (spec `toolkit-distribution/spec.md`, 29 scenarios). Tests are in
`skills/tests/install_sh/` (I) and `skills/tests/improve-harness/` (H).

| Scenario | Evidence |
|----------|----------|
| Consumer install writes the stamp | I test_install_stamp::test_consumer_install_writes_stamp; live install wrote stamp.json |
| Self-install writes no stamp | I test_self_install_writes_no_stamp |
| Aborted install leaves previous stamp intact | I test_aborted_install_leaves_previous_stamp_intact |
| Check mode does not stamp | I test_check_mode_does_not_stamp; live `--check` with stamp removed left it absent |
| Source and mirror hash identically | I test_payload_hash::test_source_and_mirror_hash_identically |
| Content change changes the hash | I test_content_change_changes_hash |
| Excluded directories do not affect the hash | I test_excluded_directories_do_not_affect_hash |
| Helper passes the portability gate | I test_consumer_portability (passed) |
| Pinned payload matches | I test_pinned_payload_matches; live `--check` exit 0 "Pinned toolkit matches" |
| Checkout drift | I test_checkout_drift (+ changed-skill-set variant) |
| Runtime drift | I test_runtime_drift_names_the_agent; live edit -> exit 1 "Runtime drift" |
| Unpinned repository | I test_unpinned_repository_is_advisory; live: exit 0 "Unpinned" |
| Invalid stamp fails loud | I test_invalid_stamp_fails_loud_and_is_not_rewritten; live: exit 1 "Invalid toolkit stamp" |
| Self-install skips the stamp comparison | I test_self_install_skips_stamp_comparison |
| Export refused without opt-in | H test_export_refused_without_opt_in, test_cli_refuses_without_config; live exit 2 |
| Export with opt-in | H test_export_with_opt_in_writes_one_object_per_line; live stubbed export |
| Installer never touches the config | live re-install with --force left config.json and learnings.jsonl intact |
| Transcript-mined entries are excluded | H test_transcript_mined_entries_are_excluded (+ variants fail closed); live |
| Private fields are dropped | H test_private_fields_are_dropped; live |
| Identity-bearing tags are dropped | H test_identity_bearing_tags_are_dropped; live |
| Secrets are redacted | H test_secrets_are_redacted; live (GitHub and AWS tokens redacted) |
| Deterministic output | H test_output_is_deterministic_sorted_and_deduplicated; live second run |
| Exporter passes the portability gate | I test_consumer_portability; installer "portability validation passed" |
| Shared records merged and attributed | H test_shared_learnings_merge::test_shared_record_is_merged_and_attributed |
| Duplicate shared record appears once | H test_duplicate_shared_record_appears_once_from_custom_path |
| Disabled sharing ignores the file | H test_disabled_sharing_ignores_the_file |
| No write-back | H test_module_has_no_memory_write_path, test_cli_merges_and_never_stores_to_memory |
| Registration rows present | I test_state_artifacts_registration::test_artifact_row_names_writer_and_missing_behavior |
| Projection never feeds canonical state | I test_learnings_projection_never_feeds_canonical_state |

All 29 scenarios covered.

## Smoke Tests

Result: pass

Fresh `mktemp -d` git repo under the session scratchpad; real consumer install
(`install.sh --target <tmp> --mode copy --deps none --python-tools none`):
- Install exit 0, "Skill install portability validation passed", stamp written
  (`toolkit_version 0.2.0`, `source_commit cce5f36...`, `payload_hash sha256:c3d2feb6...`,
  agents claude+agents, mode copy).
- `--check` immediately after: exit 0, "Installed skill mirrors match canonical payload",
  "Pinned toolkit matches: 0.2.0 (sha256:c3d2feb61ae2)".
- rsync is not installed in this environment; the installer used its cp fallback
  (copy mode, so rsync-only paths were not exercised here).

## Security

Result: pass

- Portability gate: installer's own portability validation and
  `test_consumer_portability.py` / `validate_install_manifest.py` tests pass. A loose
  grep for coordinator-source strings in the installed payload hit only pre-existing
  skill files that this change does not touch (none are in the diff); the
  authoritative gate passes.
- Exporter privacy rules verified live with stubbed memory: allowlisted fields only
  (`details`, `agent_id`, `session_id` dropped); only the five tag namespaces survive
  (`agent:`, `session:` dropped); `source:transcript-mined` entry excluded; GitHub
  token and AWS key redacted by the session-log sanitizer; output sorted and atomic.
- Secret scan: gitleaks is NOT available in this environment. Fallback regex scan
  of the diff (AKIA, ghp_, private-key headers, quoted key/secret/token literals) found
  only one hit: a synthetic AWS key fixture in
  `skills/tests/improve-harness/test_export_shared_learnings.py:196` used to test redaction.
- Advisory: 15 low-severity items remain open in `.review-ledger/ledger.json`.

## E2E Tests

Result: pass

Drift and opt-in flow on the consumer repo above:
- Edited installed `shared/payload_hash.py` -> `--check` exit 1, "Runtime drift: installed
  claude copies are not the pinned payload" naming pinned vs installed hash; reverted ->
  exit 0.
- Corrupt stamp -> exit 1 "Invalid toolkit stamp"; stamp removed -> exit 0 "Unpinned".
- Exporter with no config -> exit 2, nothing written. With opt-in config and stubbed
  memory -> exit 0, 2 of 3 entries exported; repeated run identical.
- Re-install with `--force` preserved `config.json` and `learnings.jsonl`.

Pytest (skills/.venv; `skills/tests/install_sh`, `improve-harness`, `_shared`, `shared`):
**168 passed, 16 skipped, 0 failed** (139.8s). Skips: 15 are rsync-unavailable
(test_consumer_portability, test_no_rsync_fallback, test_openspec_assets,
test_payload_hash, test_references_rsync, test_related_validation) and 1 is
"node_modules not present" (test_validate_install_manifest_excludes). No tests were
skipped or weakened by the validator.

## Validation Review

Result: pass

Round evidence (this container, branch `openspec/toolkit-consistency--val-review-2` from
bdfeefe, 2026-10-10):

- `converge(review_type=implementation, min_quorum=1, fix_mode=targeted)` ran as the whole
  phase. Packet: `git diff origin/openspec/roadmap-multiplayer-collaboration...HEAD` (23
  files, all from this change; `.review-cache/**`, `.review-ledger/**` and `loop-state.json`
  excluded; 212,124 of 320,000 chars, nothing truncated) plus a 9,811-char addendum
  reproducing this report and the four ri-20 acceptance outcomes. Dispatch: claude_code CLI
  (`claude-local`, model fable, 269 s); 13 findings (3 medium, 10 low), fact-check kept all
  13; 0 blocking under D3 (single vendor: every finding is `unconfirmed` judgment), so the
  loop converged in round 1. Evidence: `.review-cache/round-1-val-initial/`; ledger 53-65.
- Degradation `single_vendor_review` (phase VAL_REVIEW, vendor claude_code, policy
  TRUST_POSTURE.md 479dcd9): per the operator policy only claude_code was dispatched and no
  other lane or credential was probed. Compensating control, as in IMPL_REVIEW: the 13
  findings were read as conductor, 10 were fixed (VAL_FIX 2-6 below), 3 are left open
  advisory, and a verification round was run over the fix diff (below).
- `secret_scan_substitute` (operator-accepted 2026-10-10): gitleaks is not installed and,
  per the operator decision, was not downloaded. The regex scan (`AKIA...`, `ghp_`/`gho_`/
  `github_pat_`, `sk-`, `xox?-`, private-key headers, quoted `key|secret|token|password`
  literals) re-ran over the `skills/` + `docs/` diff at bdfeefe: one hit, the synthetic AWS
  key fixture at `skills/tests/improve-harness/test_export_shared_learnings.py:196` used by
  `test_secrets_are_redacted`. The Security section's `Result: pass` stands on that
  substitute, not on gitleaks.

Acceptance outcomes (roadmap `multiplayer-collaboration`, item ri-20) and the evidence that
proves each:

| # | Outcome | Evidence |
|---|---------|----------|
| 1 | A consumer repository records the installed toolkit version and payload hash in a tracked file registered in `docs/guides/state-artifacts.md` | `test_install_stamp` (fields incl. `toolkit_version`, `payload_hash`, `source_commit`); live rsync-mode scratch install at bdfeefe wrote `stamp.json` (`0.2.0`, `sha256:c3d2feb6...`, identical to the copy-mode Smoke hash, so rsync and copy mirrors hash alike); `test_state_artifacts_registration::test_artifact_row_names_writer_and_missing_behavior[.agentic-toolkit/stamp.json]` |
| 2 | `install.sh --check` reports drift between the pinned version and the local runtime copy | `test_runtime_drift_names_the_agent` (now also asserts the pinned version and commit), `test_checkout_drift`, `test_checkout_drift_with_changed_skill_set_is_not_runtime_drift`, `test_pinned_payload_matches`, `test_unpinned_*`, `test_invalid_stamp_fails_loud_and_is_not_rewritten[4]`; live: with the VAL_FIX edits in the checkout, the scratch consumer's `--check` reported `Checkout drift ... (pinned 0.2.0 @ bdfeefe..., sha256:c3d2feb6...; checkout sha256:f1b9e289...)` and exit 1; re-stamped from b7f8168 it reported `Pinned toolkit matches: 0.2.0 (sha256:f1b9e289f535)` and exit 0 |
| 3 | Repository-scoped learnings are opt-in and never include private transcript content | Opt-in: `test_export_refused_without_opt_in[absent, disabled, string-true, bad-json, not-object, wrong-schema]`, `test_cli_refuses_without_config`, `test_refusal_does_not_overwrite_existing_learnings`, `test_installer_never_touches_config`, `test_disabled_sharing_ignores_the_file`. Transcript content: `test_transcript_mined_entries_are_excluded`, `test_transcript_mined_variants_fail_closed`, `test_producer_transcript_tag_is_excluded` (builds the tag with collect-transcripts' own `TranscriptFinding.to_memory_tags()`), `test_private_fields_are_dropped` (`details`, `agent_id`, `session_id`), `test_identity_bearing_tags_are_dropped`, `test_secrets_are_redacted`. Known limit (design D8): self-reported entries' `summary`/`lessons` are exported after the sanitizer; only secret patterns are redacted |
| 4 | Installed payloads contain no references to private coordinator source | Authoritative gate `skills/shared/validate_install_manifest.py` (rejects private coordinator `src` imports and `sys.path`/`parents[...]` injection of `agent-coordinator`): "Skill install portability validation passed" on both live installs and in `test_consumer_portability`, incl. `test_manifest_entry_points_run_without_source_checkout[.claude|.agents]`, which runs `shared/payload_hash.py --help` and `improve-harness/scripts/export_shared_learnings.py --help` from the installed closure (rsync is present here, so not skipped). The loose grep `agent-coordinator|coordination_mcp|coordination_api` over the installed `.claude/skills` mirror hits 59 pre-existing files, none in this change's diff: documentation strings (SKILL.md files, `references/`), repo-root markers (`shared/archetype_roster.py`), session-bootstrap hooks that only run inside this repository, and lazily-imported opt-in integrations (`playwright-validator`, `coordination-bridge`). None is a source import, which is what the outcome and the gate forbid |

Scenario evidence (29): the Spec Compliance table stands. Changes from this phase:
'Installer never touches the config' is now proven by `test_installer_never_touches_config`
instead of only the live run; 'Runtime drift' test and scenario now cover the pinned
version and commit; the Drift check requirement and 'Invalid stamp fails loud' now list a
missing or non-`sha256:` `payload_hash` (already pinned by the `[no-hash]` case);
'Projection never feeds canonical state' gains
`test_learnings_projection_is_read_only_by_improve_harness` (only `analyze_failures.py`
and `export_shared_learnings.py` name `learnings.jsonl` under `skills/`); 'Export refused
without opt-in' gains `[wrong-schema]`.

Findings (ledger id, criticality) and VAL_FIX sub-steps:

- 53 medium, report header `Overall: PASS` beside an incomplete section, mixed commits ->
  VAL_FIX 2 (this commit): this section, the Phase Summary row and the header note that
  `skills/` and `docs/` are unchanged between cce5f36 and bdfeefe.
- 54 medium, outcome 4 not proven and no outcome-to-evidence mapping -> VAL_FIX 2: table above.
- 55 medium, exclusion tag never checked against the producer -> VAL_FIX 3 (b7f8168):
  `test_producer_transcript_tag_is_excluded`.
- 56 low, config scenario backed only by a live run -> VAL_FIX 3: `test_installer_never_touches_config`.
- 57 low, real `query_memory` signature never exercised -> VAL_FIX 3:
  `test_export_calls_the_real_query_memory_signature` (real `analyze_failures`, `urlopen` stubbed).
- 58 low, spec omits the `payload_hash` invalidity the code enforces -> VAL_FIX 4 (b7f8168):
  requirement and scenario text; `openspec validate toolkit-consistency --strict` passes.
- 59 low, config reader ignores `schema_version` -> VAL_FIX 5 (b7f8168): `sharing_enabled()`
  refuses `schema_version` other than `1` with a reason (same rule as the stamp reader);
  `[wrong-schema]` test; opt-in requirement and state-artifacts config row updated. The one
  real (low) defect of the round; minimal fix with a test.
- 60 low, runtime-drift test silent on version/commit -> VAL_FIX 4: assertions and scenario AND clause.
- 64 low (re-verification of 42), tasks.md Verification is a self-install -> VAL_FIX 6
  (b7f8168): scratch-consumer form added.
- 65 low (re-verification of 41), SKILL.md silent that `generate_report.py` does not merge
  -> VAL_FIX 6: one sentence under Consumption.
- 61, 62, 63 low: left open advisory (the aborted-install test's abort point, stale
  tasks.md Files lines, `json-canvas` coupling in a test oracle); reasons recorded in the ledger.

Tests after VAL_FIX (skills/.venv; `skills/tests/install_sh`, `improve-harness`, `_shared`,
`shared`; rsync present): **188 passed, 1 skipped, 0 failed** (342.7s) on b7f8168; the
five new tests and the new `[wrong-schema]` case all pass. Baseline on bdfeefe in this container:
183 passed, 1 skipped (`node_modules not present`). ruff clean on the edited Python;
`skills/install.sh` is unchanged this phase.

Verification round: VERIFY_ROUND_PLACEHOLDER

VAL_FIX 1 (first attempt, branch `openspec/toolkit-consistency--val-review` from 544fa99,
parked after a permission denial before `converge()` could run):

- rsync was installed (`apt-get install -y rsync`) and the suite from the Test suites
  section re-ran with it present (skills/.venv; `skills/tests/install_sh`,
  `improve-harness`, `_shared`, `shared`): **183 passed, 1 skipped, 0 failed** (311.8s).
  The 15 previously rsync-skipped tests all pass, including
  `test_consumer_portability::test_manifest_entry_points_run_without_source_checkout`
  for both `.claude` and `.agents`, which is the test the "Helper passes the portability
  gate" and "Exporter passes the portability gate" scenarios name and which the earlier
  run could not execute (it runs `shared/payload_hash.py --help` and
  `improve-harness/scripts/export_shared_learnings.py --help` from the installed closure
  only). `test_payload_hash::test_source_and_mirror_hash_identically[rsync]` also passed,
  so "Source and mirror hash identically" is now proven in rsync mode as well as copy
  mode. The one remaining skip is the pre-existing "node_modules not present".
- The Spec Compliance table above cited `test_consumer_portability (passed)` for the two
  portability scenarios while three of that module's tests were skipped; the rsync run
  above is the evidence that closes that gap. No other result line was changed.

The gitleaks download attempted in that first attempt (`curl -sSI ...
https://github.com/gitleaks/gitleaks/releases/latest`) was denied by the permission system
and not worked around; the operator then accepted the regex substitute recorded above.
