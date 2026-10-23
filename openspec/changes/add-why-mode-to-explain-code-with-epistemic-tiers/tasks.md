# Tasks: Add why mode to explain-code with epistemic tiers

> Change ID: `add-why-mode-to-explain-code-with-epistemic-tiers`
> Roadmap item: `ri-09` (`verification-enforcement-discipline`)

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## 1. why_trace script (wp-why-mode)

- [ ] 1.1 Write failing fixture tests in `skills/tests/explain-code/test_why_trace.py` (M)
  - A temp git repository built with `git -c user.name=… -c user.email=… -c commit.gpgsign=false`. It holds `openspec/changes/archive/2026-01-01-demo-change/session-log.md` with an `architectural: demo-cap` Decision bullet, plus `openspec/specs/demo-cap/`.
  - Cases: traced (with `(#N)` subject), `no_change_id`, `no_decision_record`, `uncommitted`, exit 2 (malformed target, untracked path, line out of range), supersession, `mentions_target` true and false, no side effects (`git status --porcelain` and refs unchanged).
  - Fixture change ids are synthetic, so the OpenSpec path-stability guard does not apply.
  **Spec scenarios**: skill-workflow.why-trace-full-chain, .why-trace-no-change-id, .why-trace-no-decision-record, .why-trace-uncommitted, .why-trace-invalid-input, .why-trace-superseded, .why-trace-mentions-target, .why-trace-no-side-effects
  **Design decisions**: D2, D3, D4
  **Dependencies**: None
- [ ] 1.2 Implement `skills/explain-code/scripts/why_trace.py` (M)
  - Set `sys.dont_write_bytecode = True`, put `parents[2]/"explore-feature"/"scripts"` on `sys.path`, and import `extract_decisions` and `_build_supersession_map` from `decision_index` (D7). Do not write a second parser.
  - Name `<skill-base-dir>/../explore-feature/scripts` in the module docstring so the manifest validator detects the sibling reference.
  - Match archive dirs exactly (`<YYYY-MM-DD>-<id>`), and look up supersession under both the extracted dir-name id and the canonical id (D3).
  - Resolve the chain in the order of the D3 table, emit the D4 JSON with sorted keys, and use exit codes 0, 1 and 2.
  **Dependencies**: 1.1
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Why mode in explain-code (wp-why-mode)

- [ ] 2.1 Write failing contract tests (S)
  - `test_skill_md.py` covers: a "Why chain" catalogue row linking `references/why.md`; all five tiers and both rules named; still at most 150 lines; `why.md` links no further reference file.
  - New vocabulary test: the `why.md` tier list, lowercased, equals the schema `evidence_level` enum.
  **Spec scenarios**: skill-workflow.why-chain-tagged, .why-null-result, .why-embedded-hypothesis, .why-vocabulary-single-source, .explainer-progressive-disclosure
  **Design decisions**: D5, D6
  **Dependencies**: None
- [ ] 2.2 Write `skills/explain-code/references/why.md` (S)
  - Tier table, tag format, the null-result and embedded-hypothesis rules, a worked example, and the grounding closing line.
  **Dependencies**: 2.1
- [ ] 2.3 Update `skills/explain-code/SKILL.md` (S)
  - Add the catalogue row and a short "Why mode" section with the tier list, both rules and the `why_trace.py` invocation. Add `explore-feature` to frontmatter `related`. Keep it at most 150 lines.
  **Dependencies**: 2.2, 1.2
- [ ] Checkpoint: run tests, review diff, verify scope

## 3. evidence_level schema field (wp-why-mode)

- [ ] 3.1 Write failing tests (S)
  - `prompt_contract()` enums include `evidence_level`, and `prompt_contract_block()` names it OPTIONAL.
  - A finding with `inferred` validates; one with `certain` fails.
  - Emitter regression: for each committed `openspec/changes/**/findings-*.json`, the errors under the current schema are a subset of the errors under the schema without `evidence_level`.
  - The existing `test_enum_values_match_the_schema` covers the vendor prompt.
  **Spec scenarios**: skill-workflow.evidence-level-prompt-contract, .evidence-level-vendor-prompt, .evidence-level-existing-documents, .evidence-level-validates
  **Design decisions**: D6
  **Dependencies**: None
- [ ] 3.2 Add the `evidence_level` property to both schema copies (XS)
  - The copies are `openspec/schemas/review-findings.schema.json` and `skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`. They must stay byte-identical, and the diff must be that one property only.
  **Dependencies**: 3.1
- [ ] 3.3 Add the OPTIONAL `evidence_level` line to `prompt_contract_block()` and `vendor_review.build_review_prompt()`, and add the `evidence_level` tuple to `vendor_review._FALLBACK_ENUMS` (XS)
  **Dependencies**: 3.2
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. Distribution and verification (wp-why-mode)

- [ ] 4.1 Add `explore-feature` to `cross_skill_dependencies["explain-code"]` in `skills/install-manifest.json` (XS)
  **Spec scenarios**: skill-workflow.explainer-manifest-dependencies, .explainer-manifest-validation
  **Design decisions**: D7
  **Dependencies**: 1.2
- [ ] 4.2 Re-sync the runtime mirrors with `skills/install.sh` (they are gitignored), then run `skills/install.sh --check` (XS)
  **Dependencies**: 4.1, 2.3, 3.3
- [ ] 4.3 Run the affected suites (XS)
  - `skills/tests/explain-code`
  - `skills/tests/parallel-infrastructure/test_review_findings_schema*.py`
  - `skills/tests/merge-pull-requests/test_vendor_review_prompt.py`
  - `skills/tests/openspec_paths`
  **Dependencies**: 4.2
- [ ] 4.4 Run `openspec validate add-why-mode-to-explain-code-with-epistemic-tiers --strict` (XS)
  **Dependencies**: 4.3
