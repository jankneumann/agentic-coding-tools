# Validation Report: add-why-mode-to-explain-code-with-epistemic-tiers

## Spec Compliance
**Status**: pass
`openspec validate --strict add-why-mode-to-explain-code-with-epistemic-tiers` reports the change valid. Each scenario in `specs/skill-workflow/spec.md` maps to tests in `skills/tests/explain-code/` (`test_why_trace.py`, `test_skill_md.py`) and `skills/tests/parallel-infrastructure/test_review_findings_schema.py`:

| Requirement / Scenario | Covering test(s) |
|---|---|
| Why Trace Script: Full chain traced in a fixture repository | `test_why_trace.py::test_full_chain_traced`, `test_archive_match_is_exact`, `test_pr_and_change_id_from_merge_commit`, `test_index_path_reported_when_present` |
| Why Trace Script: No change id resolvable | `test_why_trace.py::test_no_change_id` |
| Why Trace Script: Change found but no decision record covers it | `test_why_trace.py::test_no_decision_record` |
| Why Trace Script: Uncommitted line | `test_why_trace.py::test_uncommitted_line`, `test_uncommitted_line_on_unborn_head` |
| Why Trace Script: Invalid input rejected | `test_why_trace.py::test_malformed_target_rejected`, `test_untracked_path_rejected`, `test_line_out_of_range_rejected`, `test_unreadable_target_is_an_input_error`; git failure exit 1 in `test_outside_a_repository_is_a_git_failure` |
| Why Trace Script: Superseded decision reported | `test_why_trace.py::test_superseded_decision_reported` |
| Why Trace Script: Target mention flag | `test_why_trace.py::test_mentions_target_flag` |
| Why Trace Script: No side effects | `test_why_trace.py::test_no_side_effects`; determinism in `test_output_is_deterministic`; reuse of `decision_index` in `test_reuses_decision_index_instead_of_parsing`; cwd-relative targets in `test_relative_to_cwd` |
| Why Chain Reply Contract: Why question answered with a tagged chain | `test_skill_md.py::test_why_chain_catalogue_row_links_reference`, `test_why_reference_documents_rules_and_disclosure`, `test_worked_example_tags_follow_the_tier_rules` |
| Why Chain Reply Contract: Null result reported as the finding | `test_skill_md.py::test_why_reference_documents_rules_and_disclosure`, `test_skill_md_names_tiers_rules_and_script` |
| Why Chain Reply Contract: Hypothesis in the question tested, not adopted | `test_skill_md.py::test_why_reference_documents_rules_and_disclosure`, `test_worked_example_tags_follow_the_tier_rules` (the untested verdict is tagged `[Unknown]`) |
| Why Chain Reply Contract: Tier vocabulary documented in one place | `test_skill_md.py::test_skill_md_names_tiers_rules_and_script`, `test_why_tier_vocabulary_matches_schema_enum` |
| Review Finding Evidence Level: Prompt contract includes the field | `test_review_findings_schema.py::test_prompt_contract_exposes_evidence_level_in_schema_order` |
| Review Finding Evidence Level: Vendor prompt names every enum value | `skills/tests/merge-pull-requests/test_vendor_review_prompt.py::test_enum_values_match_the_schema` and `test_fallback_matches_the_schema`, both now covering `evidence_level` |
| Review Finding Evidence Level: Existing findings documents still validate | `test_review_findings_schema.py::test_evidence_level_adds_no_error_to_committed_findings_documents` |
| Review Finding Evidence Level: Finding with an evidence level validates | `test_review_findings_schema.py::test_evidence_level_validates_known_value_and_rejects_unknown`, `test_evidence_level_is_optional_without_default`, `test_evidence_level_mirror_is_byte_identical` |
| MODIFIED Visual Code Explainer Skill (why chain in catalogue; only `why_trace.py` as code) | `test_skill_md.py::test_references_resolve`, `test_skill_md_line_budget`, `test_references_do_not_link_to_other_references`, `test_why_chain_catalogue_row_links_reference` |
| MODIFIED Explainer Distribution Wiring (`explore-feature` dependency) | `test_skill_md.py::test_related_includes_explore_feature`; `skills/tests/install_sh` (manifest validator and `install.sh --check`) |

The two regression tests added during implementation review (`test_uncommitted_line_on_unborn_head`, `test_unreadable_target_is_an_input_error`) were confirmed to fail against the pre-fix script.

**Schema diff scope.** `git diff origin/openspec/adopt-verification-enforcement-discipline -- openspec/schemas/review-findings.schema.json` shows one hunk of 11 added lines: the `evidence_level` property in `findings.items.properties` and nothing else. The install-assets mirror (`skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`) has the same 11-line diff, and `cmp` confirms the two copies are byte-identical.

## Evidence
**Status**: pass
- `skills/.venv/bin/python -m pytest -q skills/tests/explain-code skills/tests/parallel-infrastructure skills/tests/merge-pull-requests`: 588 passed, 2 skipped.
- Guard suites `skills/tests/install_sh` and `skills/tests/_shared`: 68 passed, 15 skipped.
- `ruff check` on the six changed Python files: all checks passed.
- `openspec validate --strict` passes.

## Deploy
**Status**: skipped
`work-packages.yaml` declares `deployable: false`. This change adds a read-only skill script, documentation and one optional schema property. There is no service.

## Smoke Tests
**Status**: skipped
Not applicable: there is no deployable surface (`deployable: false`).

## Security
**Status**: skipped
No network, auth or secrets surface. `why_trace.py` runs only read-only git subcommands, writes no file (it also suppresses bytecode writes), and makes no network calls.

## E2E Tests
**Status**: skipped
No UI or API surface. The script's CLI behaviour, including exit codes and stdout/stderr contracts, is exercised end to end against fixture git repositories in `test_why_trace.py`.

## Gatekeeper
**Status**: DEGRADED
The GATEKEEPER judge could not run because no sub-agent dispatch adapter was available. A permissive signal-only verdict stood in for the risk and verifiability judgment, so that judgment was not checked. This phase is not one of the required pre-merge phases. It is recorded here so that a gate that could not run is not read as a gate that passed.

## Overall
**Status**: pass

## Process Notes
**Status**: pass
The following degraded paths were recorded in `loop-state.json` and are disclosed here:
- **No sub-agent dispatch.** No dispatch adapter was available in this session (the Agent tool is unavailable). GATEKEEPER, PLAN, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW and VALIDATE therefore ran inline (`phase_fallback_inline`).
- **Single-vendor reviews.** Plan and implementation reviews each had one review lane, `claude_code` (`single_vendor_review`), under the dispatch's `min_quorum` of 1. The implementation review converged in round 2 with no blocking findings and one advisory.
- **Coordinator unavailable.** Coordinator state projection was forbidden (`coordinator_projection_forbidden`). Coordinator handoff writes failed with a session foreign-key violation, so every handoff was written locally (`handoff_local_fallback`). The audit sink failed during PLAN (`audit_sink_failed`).
