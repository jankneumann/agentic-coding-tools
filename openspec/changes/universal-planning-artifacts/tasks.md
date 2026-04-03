# Tasks: universal-planning-artifacts

**Parallel execution note**: Phase 1 contains three independent chains that can run concurrently:
- Track A: 1.1 → 1.2 (plan-feature)
- Track B: 1.3 → 1.4 (parallel-review-implementation)
- Track C: 1.5 → 1.6 (implement-feature)
Max parallel width: 3 tasks. Total sequential depth: 2 levels per track.

## Phase 1: Verification Criteria and Core Skill Changes

- [ ] 1.1 Define acceptance criteria for plan-feature universal artifact generation
  Verify that after task 1.2, plan-feature SKILL.md: (a) Steps 7 and 8 are annotated `[all tiers]`, (b) no "Skip this step if TIER is sequential" lines remain, (c) sequential tier guidance specifies single `wp-main` package with `write_allow: ["**"]`, (d) guidance for no-interface features specifies `contracts/README.md` stub, (e) commit message template unconditionally includes "contracts, work-packages", (f) context slicing table includes sequential tier entry.
  **Scenarios verified**: Sequential-tier contracts, sequential-tier work-packages, no applicable contract sub-types, commit message
  **Dependencies**: None

- [ ] 1.2 Update plan-feature SKILL.md — remove tier gates on Steps 7-8
  Remove `[local-parallel+]` annotation from Steps 7 and 8 headers. Remove "Skip this step if TIER is sequential" lines. Change to `[all tiers]`. Add guidance for sequential tier: generate a single `wp-main` package with `write_allow: ["**"]`. Add guidance for features with no applicable interfaces: create `contracts/README.md` stub documenting which sub-types were evaluated and why none apply. Update the commit message template to always include "contracts, work-packages". Update the context slicing table to include sequential tier.
  **Dependencies**: 1.1

- [ ] 1.3 Define acceptance criteria for parallel-review-implementation whole-branch fallback
  Verify that after task 1.4, parallel-review-implementation SKILL.md: (a) detects missing `work-packages.yaml` before attempting per-package review, (b) in whole-branch mode: uses full `git diff` as review unit, skips scope verification, skips contract compliance when `contracts/` is missing or contains only `README.md`, uses `package_id: "whole-branch"` in findings, (c) performs contract compliance when `contracts/` has machine-readable artifacts even without work-packages, (d) falls back to whole-branch mode on malformed `work-packages.yaml`, (e) existing per-package review behavior is unchanged when work-packages present.
  **Scenarios verified**: Whole-branch fallback, whole-branch with contracts, existing behavior preserved, malformed work-packages
  **Dependencies**: None

- [ ] 1.4 Update parallel-review-implementation SKILL.md — add whole-branch fallback
  Add a conditional at the start of Step 1: "If `work-packages.yaml` is missing or cannot be parsed, enter whole-branch review mode." In whole-branch mode: skip scope verification (Step 2), skip contract compliance review when `contracts/` is missing or contains only README.md (but perform it when machine-readable contracts exist), use full `git diff <base>...<head>` as the review unit, use `package_id: "whole-branch"` for findings output. Ensure per-package mode is unchanged when work-packages exist.
  **Dependencies**: 1.3

- [ ] 1.5 Define acceptance criteria for implement-feature contract consumption at all tiers
  Verify that after task 1.6, implement-feature SKILL.md: (a) Step 3a reads contracts regardless of tier, (b) partial contracts are handled gracefully (validate present sub-types, skip absent), (c) missing `contracts/` directory logs warning and proceeds, (d) malformed contract files log error and skip that sub-type without blocking, (e) RTM uses `---` for contract refs where no applicable contract exists.
  **Scenarios verified**: Sequential uses contracts, partial contracts, legacy without contracts, malformed contract file
  **Dependencies**: None

- [ ] 1.6 Update implement-feature SKILL.md — always consume contracts
  Modify Step 3a to always read contracts (not just at parallel+ tiers). Add fallback: if `contracts/` directory doesn't exist, log a warning and proceed without contract validation. If `contracts/` exists with partial sub-types, validate only present sub-types. If a contract file is malformed (invalid YAML/JSON), log error for that file and skip its validation without blocking. Update the RTM template to always include "Contract Ref" column, using `---` where no applicable contract exists.
  **Dependencies**: 1.5

## Phase 2: Documentation Updates

- [ ] 2.1 Update merge-pull-requests SKILL.md — document review resilience
  Update Step 9 documentation to clarify that vendor review works with or without planning artifacts. When artifacts exist, include contract and scope information in the review prompt. When missing, proceed with PR diff only. No script changes needed — `vendor_review.py` already works on PR diffs.
  **Dependencies**: 1.2, 1.4

- [ ] 2.2 Update CLAUDE.md tier table
  Change sequential tier "Planning Artifacts" column from "Tasks.md only" to "Tasks.md + contracts + work-packages (single package)". Keep coordinated and local-parallel descriptions unchanged.
  **Dependencies**: 1.2

## Phase 3: Validation and Sync

- [ ] 3.1 Run openspec validate
  Validate all spec deltas pass strict validation: `openspec validate universal-planning-artifacts --strict`.
  **Dependencies**: 1.2, 1.4, 1.6, 2.1, 2.2

- [ ] 3.2 Run skills/install.sh to sync runtime copies
  Sync canonical `skills/` to all runtime directories: `bash skills/install.sh --mode rsync --deps none --python-tools none`.
  **Dependencies**: 1.2, 1.4, 1.6, 2.1

**Note**: Syncing delta specs to main specs (`openspec/specs/`) is handled by `/cleanup-feature` after the PR is merged, not during implementation.
