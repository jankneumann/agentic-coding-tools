# Tasks: Add dispatch sandbox enforcement

## 1. Freeze contracts and ownership

- [ ] 1.1 Add versioned execution-context, network-policy-export, and sandbox-event schemas.
- [ ] 1.2 Reconcile proposal, design, specs, downstream ownership, and current SRT sources.
- [ ] 1.3 Converge the implementation plan across all configured vendor-panel harnesses.

## 2. Coordinator policy export and durable audit (TDD)

- [ ] 2.1 Add failing service/API tests for exact-agent global+profile export, ordering,
  disabled-rule exclusion, grammar validation, atomic revision, and deterministic digest.
- [ ] 2.2 Implement the default-deny export and authenticated API/bridge client.
- [ ] 2.3 Add failing tests for narrow durable sandbox events, secret exclusion, auth actor
  binding, event-id replay, local locked JSONL outbox fallback, and acknowledged drain.
- [ ] 2.4 Add migration 044 and implement synchronous idempotent coordinator audit plus secure
  outbox fallback outside all checkout roots.

## 3. Pure renderer and prepared command lifecycle (TDD)

- [ ] 3.1 Add failing tests for deterministic SRT rendering, deny-first conservative policy,
  read-only project roots, per-launch vendor state, confined write modes, unsafe/symlink roots,
  explicit credential reads, and denied `.git` metadata writes.
- [ ] 3.2 Add the pinned SRT package/lock and implement runtime discovery and capability preflight.
- [ ] 3.3 Implement pure rendering plus mode-0600 materialization, sanitized environment, absolute
  binaries, `--` argv boundary, structured metadata, and cleanup.
- [ ] 3.4 Add failing timeout/concurrency tests and implement the single
  `local_process_backend.py` with process-group TERM/KILL ownership.

## 4. Route every vendor CLI through the backend (TDD)

- [ ] 4.1 Test and fix config projection so effective mode isolation is mode override then entry,
  and preserve per-vendor credential/state configuration.
- [ ] 4.2 Add RED/GREEN coverage for review-dispatch sync, async submit, poll, repair, and snapshot
  fallback with an explicit execution-context parameter and retryable pre-launch poll denial.
- [ ] 4.3 Version `PhaseDispatchPayload`, embed `DispatchExecutionContext`, and add RED/GREEN coverage
  for `phase_agent.py`/roadmap-host construction and autopilot local-provider passthrough without
  cwd inference.
- [ ] 4.4 Add an AST guard rejecting subprocess calls whose argv derives from vendor command
  templates/binaries outside the shared backend, with explicit Git/coordinator-helper allowlists.
- [ ] 4.5 Extend result/ledger metadata with requested/applied isolation and policy/runtime identity.
- [ ] 4.6 Add a sandbox host-commit signal, update mutating skill prompts/commit steps so sandboxed
  workers edit only, and make the host validate and create save-point commits after collection.

## 5. Behavioral evidence and documentation

- [ ] 5.1 Add a controlled vendor fixture under the runtime package proving review project writes
  fail, write-mode edits remain under root, credential fixtures cannot be read, allowed egress
  succeeds, denied egress fails, and one configured real vendor executable enters the backend.
- [ ] 5.2 Run the real SRT probe on a capable Linux or macOS host and persist evidence; incapable
  hosts must report exact missing prerequisites rather than silently skip. The canonical job is a
  manual `macos-14` workflow that uploads and records `sandbox-runtime-evidence.json`.
- [ ] 5.3 Document installation, policy authoring/endpoint inventory, rollout, degradation outbox,
  threat boundary, and recovery.
- [ ] 5.4 Run focused/full tests, Ruff, strict OpenSpec validation, and multi-vendor implementation
  review to convergence.

<!-- CHECKPOINT: plan-review-pending -->

## 6. Landing

- [ ] 6.1 Record evidence, push, merge, and advance the roadmap checkpoint.
