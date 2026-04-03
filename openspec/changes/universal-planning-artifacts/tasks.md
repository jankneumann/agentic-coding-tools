# Tasks: universal-planning-artifacts

## Phase 1: Spec Tests and Core Skill Changes

- [ ] 1.1 Write tests for plan-feature universal artifact generation
  **Spec scenarios**: skill-workflow.1 (sequential contracts), skill-workflow.2 (sequential work-packages), skill-workflow.3 (commit message)
  **Design decisions**: N/A
  **Dependencies**: None

- [ ] 1.2 Update plan-feature SKILL.md — remove tier gates on Steps 7-8
  Remove `[local-parallel+]` annotation from Steps 7 and 8 headers. Remove "Skip this step if TIER is sequential" lines. Change to `[all tiers]`. Add guidance for sequential tier: generate a single `wp-main` package with `write_allow: ["**"]`. Update the commit message template to always include "contracts, work-packages".
  **Dependencies**: 1.1

- [ ] 1.3 Write tests for parallel-review-implementation whole-branch fallback
  **Spec scenarios**: skill-workflow.4 (whole-branch fallback), skill-workflow.5 (existing behavior preserved)
  **Design decisions**: N/A
  **Dependencies**: None

- [ ] 1.4 Update parallel-review-implementation SKILL.md — add whole-branch fallback
  Add a new section before Step 1 or within Step 1: "If `work-packages.yaml` is missing, enter whole-branch review mode." In this mode: skip scope verification (Step 2), skip per-package contract compliance where no contracts exist, use full `git diff <base>...<head>` as the review unit. Add a `package_id` of `whole-branch` for findings output.
  **Dependencies**: 1.3

- [ ] 1.5 Write tests for implement-feature contract consumption at all tiers
  **Spec scenarios**: skill-workflow.6 (sequential uses contracts), skill-workflow.7 (legacy without contracts)
  **Design decisions**: N/A
  **Dependencies**: None

- [ ] 1.6 Update implement-feature SKILL.md — always consume contracts
  Modify Step 3a to always read contracts (not just at parallel+ tiers). Add fallback: if `contracts/` directory doesn't exist, log a warning and proceed without contract validation. Update the RTM template to always include "Contract Ref" column mapping.
  **Dependencies**: 1.5

## Phase 2: Review and Documentation Updates

- [ ] 2.1 Update merge-pull-requests SKILL.md — document review resilience
  Update Step 9 documentation to clarify that vendor review works with or without planning artifacts. When artifacts exist, include them in the review prompt for richer context. When missing, proceed with PR diff only.
  **Dependencies**: 1.2, 1.4

- [ ] 2.2 Update CLAUDE.md tier table
  Change sequential tier "Planning Artifacts" column from "Tasks.md only" to "Tasks.md + contracts + work-packages (single package)". Keep coordinated and local-parallel descriptions unchanged.
  **Dependencies**: 1.2

- [ ] 2.3 Create spec delta for skill-workflow
  Write spec amendments to `openspec/specs/skill-workflow/spec.md` capturing all new requirements from this change.
  **Dependencies**: 1.2, 1.4, 1.6
  **Note**: The delta spec at `openspec/changes/universal-planning-artifacts/specs/skill-workflow/spec.md` is already drafted — this task syncs it to the main spec after implementation.

- [ ] 2.4 Create spec delta for merge-pull-requests
  Write spec amendments to `openspec/specs/merge-pull-requests/spec.md` capturing the review resilience requirement.
  **Dependencies**: 2.1

## Phase 3: Validation and Sync

- [ ] 3.1 Run openspec validate
  Validate all spec deltas pass strict validation.
  **Dependencies**: 2.3, 2.4

- [ ] 3.2 Run skills/install.sh to sync runtime copies
  Sync canonical `skills/` to all runtime directories (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`, `.agents/skills/`).
  **Dependencies**: 1.2, 1.4, 1.6, 2.1

- [ ] 3.3 Verify work-packages.yaml validates against schema
  Run `validate_work_packages.py` against the change's own work-packages.yaml to ensure the single-package pattern conforms.
  **Dependencies**: 3.1
