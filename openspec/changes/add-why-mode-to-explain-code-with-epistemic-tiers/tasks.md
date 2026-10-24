# Tasks: Add why mode to explain-code with epistemic tiers

> Change ID: `add-why-mode-to-explain-code-with-epistemic-tiers`
> Roadmap item: `ri-09` (`verification-enforcement-discipline`)

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## 1. why_trace script (wp-why-mode)

- [x] 1.1 Write failing fixture tests in `skills/tests/explain-code/test_why_trace.py` (M)
  - A temp git repository built with `git -c user.name=… -c user.email=… -c commit.gpgsign=false`. It holds `openspec/changes/archive/2026-01-01-demo-change/session-log.md` with an `architectural: demo-cap` Decision bullet, plus `openspec/specs/demo-cap/`.
  - Cases: traced (with `(#N)` subject), `no_change_id`, `no_decision_record`, `uncommitted`, exit 2 (malformed target, untracked path, line out of range), supersession, `mentions_target` true and false, no side effects (`git status --porcelain` and refs unchanged).
  - Fixture change ids are synthetic, so the OpenSpec path-stability guard does not apply.
  **Spec scenarios**: skill-workflow.why-trace-full-chain, .why-trace-no-change-id, .why-trace-no-decision-record, .why-trace-uncommitted, .why-trace-invalid-input, .why-trace-superseded, .why-trace-mentions-target, .why-trace-no-side-effects
  **Design decisions**: D2, D3, D4
  **Dependencies**: None
- [x] 1.2 Implement `skills/explain-code/scripts/why_trace.py` (M)
  - Set `sys.dont_write_bytecode = True`, put `parents[2]/"explore-feature"/"scripts"` on `sys.path`, and import `extract_decisions` and `_build_supersession_map` from `decision_index` (D7). Do not write a second parser.
  - Name `<skill-base-dir>/../explore-feature/scripts` in the module docstring so the manifest validator detects the sibling reference.
  - Match archive dirs exactly (`<YYYY-MM-DD>-<id>`), and look up supersession under both the extracted dir-name id and the canonical id (D3).
  - Resolve the chain in the order of the D3 table, emit the D4 JSON with sorted keys, and use exit codes 0, 1 and 2.
  **Dependencies**: 1.1
- [x] Checkpoint: run tests, review diff, verify scope

## 2. Why mode in explain-code (wp-why-mode)

- [x] 2.1 Write failing contract tests (S)
  - `test_skill_md.py` covers: a "Why chain" catalogue row linking `references/why.md`; all five tiers and both rules named; still at most 150 lines; `why.md` links no further reference file.
  - New vocabulary test: the `why.md` tier list, lowercased, equals the schema `evidence_level` enum.
  **Spec scenarios**: skill-workflow.why-chain-tagged, .why-null-result, .why-embedded-hypothesis, .why-vocabulary-single-source, .explainer-progressive-disclosure
  **Design decisions**: D5, D6
  **Dependencies**: None
- [x] 2.2 Write `skills/explain-code/references/why.md` (S)
  - Tier table, tag format, the null-result and embedded-hypothesis rules, a worked example, and the grounding closing line.
  **Dependencies**: 2.1
- [x] 2.3 Update `skills/explain-code/SKILL.md` (S)
  - Add the catalogue row and a short "Why mode" section with the tier list, both rules and the `why_trace.py` invocation. Add `explore-feature` to frontmatter `related`. Keep it at most 150 lines.
  **Dependencies**: 2.2, 1.2
- [x] Checkpoint: run tests, review diff, verify scope

## 3. evidence_level schema field (wp-why-mode)

- [x] 3.1 Write failing tests (S)
  - `prompt_contract()` enums include `evidence_level`, and `prompt_contract_block()` names it OPTIONAL.
  - A finding with `inferred` validates; one with `certain` fails.
  - Emitter regression: for each committed `openspec/changes/**/findings-*.json`, the errors under the current schema are a subset of the errors under the schema without `evidence_level`.
  - The existing `test_enum_values_match_the_schema` covers the vendor prompt.
  **Spec scenarios**: skill-workflow.evidence-level-prompt-contract, .evidence-level-vendor-prompt, .evidence-level-existing-documents, .evidence-level-validates
  **Design decisions**: D6
  **Dependencies**: None
- [x] 3.2 Add the `evidence_level` property to both schema copies (XS)
  - The copies are `openspec/schemas/review-findings.schema.json` and `skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`. They must stay byte-identical, and the diff must be that one property only.
  **Dependencies**: 3.1
- [x] 3.3 Add the OPTIONAL `evidence_level` line to `prompt_contract_block()` and `vendor_review.build_review_prompt()`, and add the `evidence_level` tuple to `vendor_review._FALLBACK_ENUMS` (XS)
  **Dependencies**: 3.2
- [x] Checkpoint: run tests, review diff, verify scope

## 4. Distribution and verification (wp-why-mode)

- [x] 4.1 Add `explore-feature` to `cross_skill_dependencies["explain-code"]` in `skills/install-manifest.json` (XS)
  **Spec scenarios**: skill-workflow.explainer-manifest-dependencies, .explainer-manifest-validation
  **Design decisions**: D7
  **Dependencies**: 1.2
- [x] 4.2 Re-sync the runtime mirrors with `skills/install.sh` (they are gitignored), then run `skills/install.sh --check` (XS)
  **Dependencies**: 4.1, 2.3, 3.3
- [x] 4.3 Run the affected suites (XS)
  - `skills/tests/explain-code`
  - `skills/tests/parallel-infrastructure/test_review_findings_schema*.py`
  - `skills/tests/merge-pull-requests/test_vendor_review_prompt.py`
  - `skills/tests/openspec_paths`
  **Dependencies**: 4.2
- [x] 4.4 Run `openspec validate add-why-mode-to-explain-code-with-epistemic-tiers --strict` (XS)
  **Dependencies**: 4.3

## 5. Independent review fixes (wp-why-mode)

- [x] 5.1 Report a shallow-clone boundary as `history_truncated` instead of tracing the graft commit (S)
  - Test: `test_shallow_clone_boundary_is_history_truncated` (a `--depth 1` `file://` clone of the fixture); guard `test_root_commit_in_full_history_is_still_traced`.
  **Spec scenarios**: skill-workflow.why-trace-history-truncated
  **Design decisions**: D3, D4
- [x] 5.2 Strip or normalise an invalid `evidence_level` at ingest and keep the finding (S)
  - Tests: `test_invalid_evidence_level_is_dropped_and_the_finding_kept`, `test_dispatch_keeps_every_finding_when_one_evidence_level_is_bogus`.
  **Spec scenarios**: skill-workflow.evidence-level-invalid-dropped
  **Design decisions**: D6
- [x] 5.3 Match `mentions_target` on whole tokens (XS)
  - Tests: `test_mentions_target_ignores_near_miss_names`, `test_mentions_target_symbol_is_whole_word`.
  **Spec scenarios**: skill-workflow.why-trace-mentions-target, .why-trace-near-miss-mention
- [x] 5.4 Count a text-tier change id only when it has a change directory (XS)
  - Test: `test_openspec_file_mention_is_not_a_change_id`.
  **Spec scenarios**: skill-workflow.why-trace-openspec-file-mention
- [x] 5.5 Say which record was missing in the `no_decision_record` message (XS)
  - Tests: `test_no_decision_record_message_names_the_missing_session_log`, `test_no_decision_record_message_names_a_missing_change_dir`.
- [x] 5.6 Cite the superseding reference, not D1's own pointer, in the `why.md` supersession example, and list `history_truncated` in the null-result rule (XS)
  - Tests: `test_worked_example_supersession_claim_cites_the_superseding_reference`, `test_null_result_rule_lists_every_trace_status`.
