# Tasks: harden-review-consensus-and-recovery

## 1. Consensus policy contract

- [x] 1.1 Write blocker-policy characterization tests [S]
  **Spec scenarios**: skill-workflow.1 (unmatched actionable blocker), skill-workflow.2 (matching failure false zero), skill-workflow.3 (explicit integration policy), compatibility aliases, false quorum rejection, skill-workflow.4 (source refutation), skill-workflow.5 (unsupported dismissal), skill-workflow.6 (deferred visibility)
  **Contracts**: `contracts/consensus-policy.schema.json`
  **Design decisions**: D1, D2
  **Dependencies**: None
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py`, `skills/parallel-infrastructure/scripts/tests/fixtures/review-hardening/consensus/**`

- [x] 1.2 Write deterministic-grouping characterization tests [S]
  **Spec scenarios**: skill-workflow.7 (same-location paraphrase), skill-workflow.8 (order invariance), skill-workflow.9 (ambiguous description)
  **Contracts**: `contracts/consensus-policy.schema.json`
  **Design decisions**: D3
  **Dependencies**: 1.1
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py`, `skills/parallel-infrastructure/scripts/tests/fixtures/review-hardening/consensus/**`

- [x] 1.3 Extend consensus report schemas for review hardening [S]
  **Spec scenarios**: skill-workflow.1 through skill-workflow.9, old/new reader compatibility, nested/flat quorum invariants
  **Contracts**: `contracts/consensus-policy.schema.json`
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.1
  **Files**: `openspec/schemas/consensus-report.schema.json`, `skills/parallel-infrastructure/install_assets/openspec/schemas/consensus-report.schema.json`

- [x] 1.4 Implement pure blocker evaluation plus adjudication validation [M]
  **Spec scenarios**: skill-workflow.1 through skill-workflow.6, compatibility alias and relational quorum validation
  **Contracts**: `contracts/consensus-policy.schema.json`
  **Design decisions**: D1, D2
  **Dependencies**: 1.1, 1.3, 2.3
  **Files**: `skills/parallel-infrastructure/scripts/consensus_policy.py`, `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`, `skills/parallel-infrastructure/scripts/tests/test_consensus_policy.py`

- [x] 1.5 Replace greedy lexical matching with deterministic structured grouping [M]
  **Spec scenarios**: skill-workflow.7 through skill-workflow.9
  **Contracts**: `contracts/consensus-policy.schema.json`
  **Design decisions**: D3
  **Dependencies**: 1.2, 1.3, 1.4
  **Files**: `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`

- [x] Checkpoint: consensus policy [XS]
  **Dependencies**: 1.4, 1.5
  **Files**: `openspec/changes/harden-review-consensus-and-recovery/tasks.md`

## 2. Vendor recovery path

- [x] 2.1 Write transport recovery characterization tests [M]
  **Spec scenarios**: skill-workflow.10 (corrective success), skill-workflow.11 (model fallback), skill-workflow.12 (exhaustion), replacement success/unavailable/no-double-vote, capacity fallback, auth terminal, transient exhaustion, configuration failure, whole-chain vendor timeout, invalid chain rejection, skill-workflow.13 (attempt provenance), skill-workflow.14 (secret redaction), skill-workflow.16 (malformed/unattributable quorum exclusion)
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D4, D5, D7
  **Dependencies**: None
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_attempts.py`, `skills/parallel-infrastructure/scripts/tests/fixtures/review-hardening/attempts/**`

- [x] 2.2 Write reviewer-routing characterization tests [S]
  **Spec scenarios**: agent-archetypes.1 (Pi premium), agent-archetypes.2 (resolved override), agent-archetypes.3 (resolution fallback), agent-archetypes.4 (model fallback provenance), agent-archetypes.5 (unsupported thinking)
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D6
  **Dependencies**: None
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_routing.py`, `agent-coordinator/tests/test_archetype_routing.py`, `agent-coordinator/tests/test_agents_config.py`

- [x] 2.3 Add shared attempt, diagnostics, and quorum-policy infrastructure [M]
  **Spec scenarios**: skill-workflow.13 through skill-workflow.16, valid empty checkpoint eligibility, attempt-chain application validation
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D5, D7
  **Dependencies**: 2.1
  **Files**: `skills/parallel-infrastructure/scripts/review_attempts.py`, `skills/parallel-infrastructure/scripts/review_result_policy.py`, `skills/parallel-infrastructure/scripts/checkpoint_findings.py`, `skills/parallel-infrastructure/scripts/tests/test_review_attempts.py`, `skills/parallel-infrastructure/scripts/tests/test_checkpoint_findings.py`

- [x] 2.4 Implement the transport-neutral bounded recovery engine [M]
  **Spec scenarios**: skill-workflow.10 through skill-workflow.12, replacement success/unavailable/no-double-vote, capacity fallback, auth terminal, transient exhaustion, configuration failure, whole-chain vendor timeout, attempt-chain validation, deadline and budget exhaustion
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D4
  **Dependencies**: 2.3
  **Files**: `skills/parallel-infrastructure/scripts/review_attempts.py`, `skills/parallel-infrastructure/scripts/review_result_policy.py`, `skills/parallel-infrastructure/scripts/tests/test_review_attempts.py`

- [x] 2.5 Add config-driven reviewer routing and thinking translation [M]
  **Spec scenarios**: agent-archetypes.2 (resolved override), agent-archetypes.5 (unsupported thinking)
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D6
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/agents.yaml`, `agent-coordinator/src/agents_config.py`, `skills/parallel-infrastructure/scripts/review_routing.py`, `skills/parallel-infrastructure/scripts/tests/test_review_routing.py`, `agent-coordinator/tests/test_archetype_routing.py`, `agent-coordinator/tests/test_agents_config.py`

- [x] 2.6 Wire recovery and reviewer routing into every transport and compatibility caller [M]
  **Spec scenarios**: skill-workflow.10 through skill-workflow.16, whole-chain vendor timeout with later-vendor continuation and progressive terminal persistence, agent-archetypes.1 through agent-archetypes.7
  **Contracts**: `contracts/review-attempt.schema.json`
  **Design decisions**: D6
  **Dependencies**: 2.3, 2.4, 2.5
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`, `skills/autopilot/scripts/convergence_loop.py`, `skills/merge-pull-requests/scripts/vendor_review.py`, `skills/merge-pull-requests/scripts/tests/test_vendor_review.py`, `skills/quick-task/scripts/quick_task.py`, `skills/quick-task/tests/test_quick_task.py`

- [x] Checkpoint: vendor recovery [XS]
  **Dependencies**: 2.6
  **Files**: `openspec/changes/harden-review-consensus-and-recovery/tasks.md`

## 3. Fail-closed convergence

- [x] 3.1 Write fail-closed convergence tests [M]
  **Spec scenarios**: skill-workflow.15 (valid empty quorum), skill-workflow.16 (malformed quorum exclusion), skill-workflow.17 (decreasing trend), skill-workflow.18 (flat trend), skill-workflow.19 (final-round actionable), skill-workflow.20 (disagreement)
  **Contracts**: `contracts/consensus-policy.schema.json`, `contracts/review-attempt.schema.json`
  **Design decisions**: D1, D7
  **Dependencies**: 1.3
  **Files**: `skills/autopilot/scripts/tests/test_convergence_loop.py`, `skills/tests/autopilot/test_convergence_checkpoint.py`

- [x] 3.2 Switch convergence to explicit policy counts; remove final-round relaxation [M]
  **Spec scenarios**: skill-workflow.15 through skill-workflow.20
  **Contracts**: `contracts/consensus-policy.schema.json`, `contracts/review-attempt.schema.json`
  **Design decisions**: D1, D7
  **Dependencies**: 1.4, 2.3, 2.6, 3.1
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/tests/autopilot/test_convergence_checkpoint.py`

- [x] 3.3 Update fail-closed recovery guidance [S]
  **Spec scenarios**: skill-workflow.4 (source refutation), skill-workflow.12 (recovery exhaustion), skill-workflow.19 (final-round actionable)
  **Contracts**: `contracts/consensus-policy.schema.json`, `contracts/review-attempt.schema.json`
  **Design decisions**: D2, D4, D5
  **Dependencies**: 3.2
  **Files**: `skills/autopilot/references/convergence-recovery.md`, `docs/parallel-agentic-development.md`

- [x] Checkpoint: fail-closed convergence [XS]
  **Dependencies**: 3.3
  **Files**: `openspec/changes/harden-review-consensus-and-recovery/tasks.md`

## 4. Integration evidence

- [x] 4.1 Add the end-to-end review-hardening golden regression [M]
  **Spec scenarios**: skill-workflow.2, skill-workflow.4, skill-workflow.12, old-producer/new-consumer and new-producer/old-consumer consensus fixtures, false quorum aliases, invalid attempt chains, agent-archetypes.1
  **Contracts**: `contracts/consensus-policy.schema.json`, `contracts/review-attempt.schema.json`
  **Design decisions**: D1 through D7
  **Dependencies**: 1.5, 2.6, 3.2
  **Files**: `skills/tests/autopilot/test_review_hardening_integration.py`, `skills/tests/autopilot/fixtures/review-hardening/**`

- [x] 4.2 Document typed-result channel compatibility [S]
  **Spec scenarios**: skill-workflow.13 (attempt provenance), agent-archetypes.4 (fallback provenance)
  **Contracts**: `contracts/README.md`
  **Design decisions**: D5, D6
  **Dependencies**: 4.1
  **Files**: `docs/script-skill-dependencies.md`, `docs/skills-workflow.md`, `skills/parallel-infrastructure/SKILL.md`

- [x] 4.3 Run final quality gates [S]
  **Spec scenarios**: all
  **Contracts**: all revision-2 contracts
  **Design decisions**: D1 through D7
  **Dependencies**: 4.2
  **Files**: `openspec/changes/harden-review-consensus-and-recovery/validation-report.md`, `openspec/changes/harden-review-consensus-and-recovery/tasks.md`
