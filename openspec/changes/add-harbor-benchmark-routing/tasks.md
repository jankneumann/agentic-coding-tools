# Tasks: add-harbor-benchmark-routing

Sizes per plan-feature sizing table. No XL tasks; former L items are pre-split (see
design.md "Task decomposition note").

## Phase 1 — Contracts, package scaffold, corpus manifest

- [ ] 1.1 Validate contract artifacts against their schemas (S)
  **Spec scenarios**: model-routing.1 (migration applies)
  **Contracts**: contracts/db/schema.sql, contracts/schemas/combo.schema.json,
  contracts/schemas/trial-record.schema.json, contracts/schemas/corpus-manifest.schema.json
  **Dependencies**: None
- [ ] 1.2 Scaffold packages/harbor-bench with uv project, pinned harbor dependency (S)
  **Design decisions**: D1
  **Dependencies**: None
- [ ] 1.3 Write tests for corpus manifest generation — split bias, checksum, tamper fail-closed (M)
  **Spec scenarios**: evaluation-framework.2 (manifest generation, tamper detection)
  **Contracts**: contracts/schemas/corpus-manifest.schema.json
  **Dependencies**: 1.2
- [ ] 1.4 Implement manifest generator over openspec/changes/archive (M)
  **Design decisions**: D5
  **Dependencies**: 1.3
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Converter

- [ ] 2.1 Write tests for instruction extraction — proposal-to-instruction, diff withholding (M)
  **Spec scenarios**: evaluation-framework.1 (convert an archived change)
  **Dependencies**: 1.2
- [ ] 2.2 Write tests for environment emission — pre-implementation commit pinning, reproducibility (S)
  **Spec scenarios**: evaluation-framework.1 (conversion is reproducible)
  **Design decisions**: D10 (OCI-compatible Dockerfile subset)
  **Dependencies**: 1.2
- [ ] 2.3 Implement converter core — instruction plus environment emission from an archive entry (M)
  **Design decisions**: D1, D10
  **Dependencies**: 2.1, 2.2
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.4 Write tests for verifier emission — scenario-test reward, repo-gate floor, exclusion path (M)
  **Spec scenarios**: evaluation-framework.1 (unconvertible excluded), evaluation-framework.5 (deterministic reward)
  **Dependencies**: 2.3
- [ ] 2.5 Implement verifier emitter with the deterministic-first ladder (M)
  **Design decisions**: D6, D7 (task_type stamping)
  **Dependencies**: 2.4
- [ ] 2.6 Implement blind judge scoring path behind per-task flag (S)
  **Spec scenarios**: evaluation-framework.5 (judge blinding)
  **Design decisions**: D6
  **Dependencies**: 2.5
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Adapters, sweep runner

- [ ] 3.1 Write adapter conformance tests shared by all custom adapters (M)
  **Spec scenarios**: evaluation-framework.3 (five-vendor coverage)
  **Contracts**: contracts/schemas/combo.schema.json
  **Dependencies**: 1.2
- [ ] 3.2 Implement grok BaseAgent adapter (M)
  **Dependencies**: 3.1
- [ ] 3.3 Implement antigravity BaseAgent adapter (M)
  **Dependencies**: 3.1
- [ ] 3.4 Implement pi/OpenRouter BaseAgent adapter with per-trial cost capture (M)
  **Design decisions**: D4
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.5 Write tests for sweep runner core — matrix expansion, attempt fan-out, trial records, holdout refusal (M)
  **Spec scenarios**: evaluation-framework.3 (sweep over configured combos), evaluation-framework.2 (holdout protection)
  **Contracts**: contracts/schemas/trial-record.schema.json
  **Dependencies**: 1.4, 2.5
- [ ] 3.6 Implement sweep runner core over harbor jobs (M)
  **Design decisions**: D2, D10 (podman socket wiring)
  **Dependencies**: 3.5
- [ ] 3.7 Write tests for budget policy — metered cap refusal, subscription window throttle (S)
  **Spec scenarios**: evaluation-framework.4 (metered cap reached, subscription throttle)
  **Dependencies**: 3.6
- [ ] 3.8 Implement budget policy module (S)
  **Design decisions**: D4
  **Dependencies**: 3.7
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Data plane, feedback keying, importer

- [ ] 4.1 Write migration tests — table shapes, thinking-distinct rows, provenance NOT NULL (S)
  **Spec scenarios**: model-routing.1 (migration applies, thinking-distinct candidates)
  **Contracts**: contracts/db/schema.sql
  **Dependencies**: 1.1
- [ ] 4.2 Create migration 035_model_routing.sql (S)
  **Design decisions**: D3
  **Dependencies**: 4.1
- [ ] 4.3 Write tests for feedback re-keying — thinking tiers separate, vendor-note resolution, compat shim (M)
  **Spec scenarios**: model-routing.3 (thinking tiers stay separate, vendor-note normalization)
  **Dependencies**: 1.2
- [ ] 4.4 Re-key feedback normalizers to composite (vendor, model, thinking) identity (M)
  **Design decisions**: D9
  **Dependencies**: 4.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 4.5 Write importer tests — aggregation keys, provenance stamping, judge-graded distinction, idempotent re-import (M)
  **Spec scenarios**: model-routing.2 (all four scenarios)
  **Contracts**: contracts/db/schema.sql, contracts/schemas/trial-record.schema.json
  **Dependencies**: 4.2, 4.4
- [ ] 4.6 Implement prior importer from sweep trial records (M)
  **Design decisions**: D3, D7
  **Dependencies**: 4.5
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Flagged read-path

- [ ] 5.1 Capture golden test of static resolve_for_phase outputs for all 15 phases (S)
  **Spec scenarios**: model-routing.4 (flag off is inert)
  **Dependencies**: None
- [ ] 5.2 Write tests for adaptive resolution — prior-ranked selection, constraint filtering, empty-catalog fallback (M)
  **Spec scenarios**: model-routing.4 (flag on ranks by priors, constraints filter, empty catalog falls back)
  **Dependencies**: 4.6, 5.1
- [ ] 5.3 Implement ROUTING_ADAPTIVE mode in resolve_for_phase (M)
  **Design decisions**: D8
  **Dependencies**: 5.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Scorecard, pilot integration

- [ ] 6.1 Write scorecard tests — per-cell aggregates, cost-unit split, low-confidence marking (S)
  **Spec scenarios**: evaluation-framework.6 (scorecard generation, small-sample marking)
  **Dependencies**: 3.8
- [ ] 6.2 Implement scorecard generator (M)
  **Design decisions**: D4
  **Dependencies**: 6.1
- [ ] 6.3 Run podman smoke trial — 1 task × 1 combo end-to-end (S, integration-marked)
  **Spec scenarios**: evaluation-framework.3 (podman execution)
  **Design decisions**: D10 acceptance check
  **Dependencies**: 3.6, 2.5
- [ ] 6.4 Run pilot sweep — 15–20 dev tasks × 5-vendor matrix under budget policy (M, integration-marked)
  **Design decisions**: D4
  **Dependencies**: 6.3, 3.8
- [ ] 6.5 Triage pilot failures for instruction-vs-capability causes; prune manifest (M)
  **Design decisions**: D5, Risks (instruction under-specification)
  **Dependencies**: 6.4
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 6.6 Import pilot priors; generate first scorecard report (S)
  **Dependencies**: 4.6, 6.2, 6.5
- [ ] 6.7 Annotate add-adaptive-model-router tasks.md; mark ri-05 superseded, ri-02 absorbed (S)
  **Design decisions**: D3, D5
  **Dependencies**: 6.6
- [ ] Checkpoint: run tests, review diff, verify scope
