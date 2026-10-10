# Validation Report: toolkit-consistency

**Date**: 2026-10-10
**Commit**: e4d0b25da37427fb3851ac276115b7cbb9460615 (branch `openspec/toolkit-consistency-closeout--validate`)
**Scope**: Re-validation of the MERGED toolkit-consistency code (PR #671, rebase-merged into
`openspec/roadmap-multiplayer-collaboration`). All evidence below was re-run on this commit in
this container; nothing was copied from the earlier report except the scenario-to-test mapping.
The earlier report used `Result:` lines, which `gate_logic.check_phase_status()` does not parse;
every section below uses the documented `**Status**:` form.
**Overall**: PASS

## Phase Summary

| Phase | Status |
|-------|--------|
| Deploy | not applicable (no service: shell installer and Python scripts) |
| Spec Compliance | pass |
| Smoke Tests | pass |
| Security | pass |
| E2E Tests | pass |
| Test suites | pass (255 passed, 1 skipped, 0 failed) |
| Validation Review | pending (filled by VAL_REVIEW) |

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
| Helper passes the portability gate | I test_consumer_portability (not skipped: rsync present); live gate pass |
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
| Exporter passes the portability gate | I test_consumer_portability::test_manifest_entry_points_run_without_source_checkout; installer "portability validation passed" |
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
  `key|secret|token|password` literals. One hit only: the synthetic AWS key fixture at
  `skills/tests/improve-harness/test_export_shared_learnings.py:266`, used by
  `test_secrets_are_redacted`. This status rests on that substitute, not on gitleaks.

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
in this checkout"; with rsync installed, the 15 rsync-gated tests that skipped in the first
run all executed. No test was skipped or weakened by the validator.

## Validation Review

**Status**: pending

Placeholder: VAL_REVIEW fills this section. The prior VAL_REVIEW round evidence (13 + 10
findings, VAL_FIX 1-7, ledger 53-75) is recorded in the earlier revisions of this file in git
history and in `.review-ledger/ledger.json`; it has not been re-run by this re-validation.

## Result

PASS: spec, smoke, security and e2e all pass on the merged code at e4d0b25; no defect found.
