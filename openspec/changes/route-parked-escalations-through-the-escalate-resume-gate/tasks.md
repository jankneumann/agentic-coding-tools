# Tasks — Route parked escalations through the escalate-resume gate

## 1. Specify and prove the post-persist routing boundary

- [ ] 1.1 Add failing tests showing a durably applied `policy_pause` evaluates `escalate_resume` only after the attempt is parked and its lease released.
- [ ] 1.2 Add failing auto-posture coverage proving the same dispatch resumes with generation increment and preserved attempt/token/isolation identity.
- [ ] 1.3 Add failing `notify_with_timeout` coverage proving one notification, a still-parked attempt, and a pending supervisor gate with the configured deadline.
- [ ] 1.4 Add idempotency and exclusion tests for prior-record reuse, ordinary `pending_gate`, failure, and quarantine paths.
- [ ] 1.5 Add a timeout-guarded concurrency test proving two routing calls yield one generation-scoped gate record/notification and one non-deadlocking resume.
- [ ] 1.6 Add an end-to-end park -> route -> resume -> child-start/acknowledge/enter -> apply test proving the old application journal cannot bind the resumed generation.
- [ ] 1.7 Add a second-exhaustion test proving an old proceed decision is not reused across lease generations while a same-generation retry is idempotent.
- [ ] 1.8 Add failure-path tests proving routing retry never replays `apply`/`dispatch_fn`, including an earlier pause persisted before a later batch-member failure.

## 2. Implement immediate escalation routing

- [ ] 2.1 Add `ExecutionAdapter.route_parked_escalations` with an injectable evaluator and a scan limited to the named batch's persisted `policy_pause` attempts.
- [ ] 2.2 Delegate every matched attempt to `gate_router.resolve_parked`; do not import or duplicate approval-service policy.
- [ ] 2.3 Hold one workspace serialization boundary and route in stable dispatch-ID order; split public resume into lock-taking and private already-locked paths so routing cannot nested-lock, and never save the scan-time checkpoint.
- [ ] 2.4 Make `escalate_resume` prior-record correlation include `lease_generation` without changing other gate subject keys, and clear the old `application_journal` on authorized resume.
- [ ] 2.5 Return only the exact bounded response keys in `contracts/README.md`, using fixed policy-pause reason text for gate notification, while preserving `ExecutionAdapter.apply` and all existing apply result keys.
- [ ] 2.6 Ensure per-attempt routing errors fail closed after durable parking and are retried by rerunning only the routing method, never the already-applied batch or `dispatch_fn` effects; report already committed proceeds as `already_routed` on retry.

## 3. Document and integrate

- [ ] 3.1 Update `skills/supervise/SKILL.md` collect/apply instructions to call the retryable routing method after apply and from partial-apply error cleanup, retry only routing, report its synchronous timeout cost/degradations, and retain blocked gates through mirror-first rehydrate into the next cycle handoff. Keep literal gate names inside the existing recognized protocol blocks.
- [ ] 3.2 Sync canonical skill runtime mirrors with `skills/install.sh` and verify byte identity.
- [ ] 3.3 Record implementation and review decisions in `session-log.md`.
- [ ] 3.4 Add executable documentation guards for apply-before-route ordering, no apply retry after routing failure, mirror-first rehydrate, and the prose-free gate-name invariant.

## 4. Validate

- [ ] 4.1 Run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`.
- [ ] 4.2 Run the affected autopilot-roadmap and phase-record recovery suites.
- [ ] 4.3 Run Ruff on changed Python and tests.
- [ ] 4.4 Run `openspec validate route-parked-escalations-through-the-escalate-resume-gate --strict` and repo-wide strict validation.
- [ ] 4.5 Run the deterministic context-drift gate against the roadmap base and record any inherited-only drift separately.
- [ ] 4.6 Run scope checking after skill mirror synchronization and confirm only allowlisted supervise mirrors changed.
