# Validation Report: toolkit-consistency

**Date**: 2026-10-10
**Commit**: cce5f3662b1c0588290e2b4a56d191b41f817c9a (branch `openspec/toolkit-consistency--validate`)
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

_To be filled in by VAL_REVIEW._
