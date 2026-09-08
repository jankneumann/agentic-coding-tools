# Tasks — Route parked escalations through the escalate-resume gate

## 1. Specify the generation-safe boundary with failing tests

- [ ] 1.1 Prove routing starts only after every named-batch member is terminal `effects_applied`; partial apply replay does not re-run `dispatch_fn` and does not route/resume early.
- [ ] 1.2 Prove auto posture resumes the same identity at generation G+1 and clears G's application journal so a full new child result applies.
- [ ] 1.3 Prove notify-with-timeout emits one exact allowlisted request, leaves the attempt parked, and preserves the pending deadline through mirror, rehydrate, and next handoff.
- [ ] 1.4 Prove automatic/manual same-subject races yield one evaluation/notification/resume while unrelated workspace state operations remain available during coordinator wait.
- [ ] 1.5 Prove same-generation prior reuse, later-generation reevaluation, old approval-ref rejection, late-answer generation retention, and older mirror-entry retirement.
- [ ] 1.6 Prove backward-compatible gate-answer selects the newest blocked dispatch generation, optional explicit generation selects exactly, and the following route reuses the answer.
- [ ] 1.7 Prove routing failure after successful apply retries route only, and crash-after-resume reports `already_routed` without duplicate effects.
- [ ] 1.8 Guard exact result key sets/generation semantics, exact notification context/literal reason, prepared-continuation reporting, stable ordering, and exclusions.

## 2. Implement immediate escalation routing

- [ ] 2.1 Add `ExecutionAdapter.route_parked_escalations`, scanning named-batch parked policy pauses for routing and prepared policy-pause continuations for `already_routed` reporting only.
- [ ] 2.2 Keep partial-apply error cleanup non-routing; recover apply idempotently, then invoke route after complete success. Preserve `ExecutionAdapter.apply` exactly.
- [ ] 2.3 Add gate-router per-subject serialization with private already-locked evaluate/answer/resolve helpers; never hold the workspace state lock across approval I/O.
- [ ] 2.4 Include `lease_generation` in `escalate_resume` subject lookup, correlation, late-answer copy, and `require_approval_ref`; reject stale-generation proceed references without changing other gates.
- [ ] 2.5 Extend gate-answer with optional generation selection and backward-compatible newest-blocked-generation lookup from `--dispatch-id`.
- [ ] 2.6 Clear the old `application_journal` on authorized resume and return only the exact outcome/generation/pending-gate fields in `contracts/README.md`.
- [ ] 2.7 Send exactly the allowlisted approval context and literal fixed reason; retire older same-dispatch generation decision IDs from mirror projection.
- [ ] 2.8 Process fully applied candidates in stable dispatch-ID order and fail closed per attempt; retry only route after the complete-apply boundary.

## 3. Document and integrate

- [ ] 3.1 Update `skills/supervise/SKILL.md` protocol blocks with complete-apply-before-route ordering, partial-apply replay, route-only failure retry, per-subject synchronous timeout cost, mirror-first rehydrate, and answer/resume generation rules.
- [ ] 3.2 Document optional `lease_generation` in the open gate-decision schema and exact Python/context contracts in the change contract note.
- [ ] 3.3 Sync canonical supervise runtime mirrors with `skills/install.sh` and verify byte identity without retaining unrelated mirror drift.
- [ ] 3.4 Add executable documentation guards for complete-apply-before-route, partial-apply no-route cleanup, no apply retry after route failure, mirror-first rehydrate, and prose-free gate naming.
- [ ] 3.5 Record implementation and review decisions in `session-log.md`.

## 4. Validate

- [ ] 4.1 Run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`.
- [ ] 4.2 Run affected autopilot-roadmap and phase-record recovery suites.
- [ ] 4.3 Run Ruff on changed Python and tests.
- [ ] 4.4 Run strict validation for the change and all OpenSpec changes.
- [ ] 4.5 Validate work packages and DAG resolution from the repo root.
- [ ] 4.6 Run `make context-drift-gate` and distinguish inherited drift from feature drift.
- [ ] 4.7 Run post-sync package scope checking and retain only allowlisted supervise/schema/change artifacts.
