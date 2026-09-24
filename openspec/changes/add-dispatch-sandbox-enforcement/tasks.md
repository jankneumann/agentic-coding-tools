# Tasks: Add dispatch sandbox enforcement

## 1. Freeze contracts and ownership

- [ ] 1.1 Add versioned execution-context, network-policy-export, and sandbox-event schemas.
- [ ] 1.2 Reconcile proposal, design, specs, downstream ownership, and current SRT sources.
- [ ] 1.3 Converge the implementation plan across all configured vendor-panel harnesses.

## 2. Coordinator policy export and durable audit (TDD)

- [ ] 2.1 Add failing service/API tests for exact-agent global+profile export, ordering,
  disabled-rule exclusion, typed destination grammar, wildcard subset behavior, atomic revision,
  and canonical-JSON digest.
- [ ] 2.2 Implement the default-deny export and authenticated API/bridge client.
- [ ] 2.3 Add failing tests for narrow durable sandbox events, secret exclusion, auth actor
  binding, truthful cross-fields, event-id replay, secure state-root validation, locked JSONL
  append/compaction interruption, permanent-rejection dead-lettering, and acknowledged drain.
- [ ] 2.4 Add migration 044 and implement synchronous idempotent coordinator audit plus secure
  outbox fallback outside all checkout roots.

## 3. Pure renderer and prepared command lifecycle (TDD)

- [ ] 3.1 Add failing tests for deterministic SRT rendering, deny-first conservative policy,
  home/read confinement, read-only project roots, per-launch vendor state, confined write modes,
  unsafe/symlink roots, environment-only credentials, Git read/write behavior, and wildcard subset.
- [ ] 3.2 Add the pinned SRT package/lock and implement git-common-dir-aware runtime discovery and
  Linux/macOS capability preflight.
- [ ] 3.3 Implement pure rendering plus mode-0600 materialization, sanitized environment, absolute
  binaries, normative strip list/trusted PATH, `--` argv boundary, structured metadata, and cleanup.
- [ ] 3.4 Add failing timeout/concurrency tests and implement the single
  `local_process_backend.py` with process-group TERM/KILL ownership.

## 4. Route every vendor CLI through the backend (TDD)

- [ ] 4.1 Test and fix config projection so effective mode isolation is mode override then entry,
  only for standalone calls; preserve per-vendor state/env-auth/proxy-compatibility configuration.
- [ ] 4.2 Add RED/GREEN coverage for review-dispatch sync, async submit, poll, repair, and snapshot
  fallback with an explicit per-attempt context, read-only-only snapshots, typed enforcement
  failures, retryable poll collection, and `remote_state_unknown` deadline handling.
- [ ] 4.3 Version `PhaseDispatchPayload`, embed the full dg-06 enforcement projection/digest, remove
  the top-level v2 isolation authority, subordinate `phase_agent.py`'s worktree lifecycle default,
  and cover roadmap, smoke, and local-provider producers without cwd inference.
- [ ] 4.4 Add `test_no_vendor_subprocess_bypass.py` covering subprocess run/Popen/call/check APIs,
  asyncio subprocess APIs, and os.system/popen, exempting only the backend and an exact
  `(file,function)` Git/coordinator control-plane allowlist; run it in CI.
- [ ] 4.5 Extend result/ledger metadata with routing digest, requested/applied isolation,
  policy/runtime/settings identity, typed collection state, and cleanup status.
- [ ] 4.6 Add a sandbox host-commit signal, update mutating skill prompts/commit steps so sandboxed
  workers edit only, and make the host validate and create save-point commits after collection.

## 5. Behavioral evidence and documentation

- [ ] 5.1 In `wp-runtime`, add a controlled vendor fixture proving review project writes
  fail, write-mode edits remain under root, credential fixtures cannot be read, allowed egress
  succeeds, denied egress fails, linked-worktree runtime discovery works, and one configured real
  vendor executable plus its actual network client enters the backend.
- [ ] 5.2 Run the real SRT probe on capable Linux and macOS hosts and persist evidence; incapable
  hosts must report exact missing prerequisites rather than silently skip. A PR-triggered
  `ubuntu-24.04` + `macos-14` matrix must pass for the exact head SHA; download and verify the
  GitHub run/artifacts before recording evidence.
- [ ] 5.3 Document installation, policy authoring/endpoint inventory, rollout, degradation outbox,
  threat boundary, and recovery.
- [ ] 5.4 Run focused/full tests, coordinator mypy, Ruff, install-manifest check, dependency-
  direction lint, strict OpenSpec validation, and multi-vendor implementation review to convergence.

<!-- CHECKPOINT: plan-review-pending -->

## 6. Landing

- [ ] 6.1 Record evidence, push, merge, and advance the roadmap checkpoint.
