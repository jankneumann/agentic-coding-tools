# Tasks — Route parked escalations through the escalate-resume gate

## 1. Specify and prove the post-persist routing boundary

- [ ] 1.1 Add failing tests showing a durably applied `policy_pause` evaluates `escalate_resume` only after the attempt is parked and its lease released.
- [ ] 1.2 Add failing auto-posture coverage proving the same dispatch resumes with generation increment and preserved attempt/token/isolation identity.
- [ ] 1.3 Add failing `notify_with_timeout` coverage proving one notification, a still-parked attempt, and a pending supervisor gate with the configured deadline.
- [ ] 1.4 Add idempotency and exclusion tests for prior-record reuse, ordinary `pending_gate`, failure, and quarantine paths.

## 2. Implement immediate escalation routing

- [ ] 2.1 Extend `ExecutionAdapter.apply` with an injectable evaluator and a post-application scan limited to the current batch's persisted `policy_pause` attempts.
- [ ] 2.2 Delegate every matched attempt to `gate_router.resolve_parked`; do not import or duplicate approval-service policy.
- [ ] 2.3 Return bounded `escalation_resolutions` entries while preserving all existing apply result keys.
- [ ] 2.4 Ensure routing errors fail closed after durable parking and can be retried without replaying `dispatch_fn` effects.

## 3. Document and integrate

- [ ] 3.1 Update `skills/supervise/SKILL.md` collect/apply instructions to route newly parked policy pauses immediately and retain blocked pending gates in the supervisor record.
- [ ] 3.2 Sync canonical skill runtime mirrors with `skills/install.sh` and verify byte identity.
- [ ] 3.3 Record implementation and review decisions in `session-log.md`.

## 4. Validate

- [ ] 4.1 Run `skills/.venv/bin/python -m pytest skills/tests/supervise -q`.
- [ ] 4.2 Run the affected autopilot-roadmap and phase-record recovery suites.
- [ ] 4.3 Run Ruff on changed Python and tests.
- [ ] 4.4 Run `openspec validate route-parked-escalations-through-the-escalate-resume-gate --strict` and repo-wide strict validation.
- [ ] 4.5 Run the deterministic context-drift gate against the roadmap base and record any inherited-only drift separately.
