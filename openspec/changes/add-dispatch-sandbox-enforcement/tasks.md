# Tasks: Add dispatch sandbox enforcement

## 1. Freeze contracts and ownership

- [x] 1.1 Add versioned execution-context, network-policy-export, and sandbox-event schemas.
- [x] 1.2 Reconcile proposal, design, specs, downstream ownership, and current SRT sources.
- [x] 1.3 Converge the implementation plan across all configured vendor-panel harnesses.

## 2. Coordinator policy export and durable audit (TDD)

- [x] 2.1 Add failing service/API tests for exact-agent global+profile export, ordering,
  unknown/disabled/unassigned rejection, disabled-rule exclusion, typed destination grammar,
  wildcard subset behavior (including multi-label wildcard suffixes), legacy ascending priority,
  atomic revision/zero-row sentinel, and canonical-JSON digest.
- [x] 2.2 Implement the default-deny export and authenticated API/bridge client.
- [x] 2.3 Add failing tests for narrow durable sandbox events, secret exclusion, auth actor
  binding, truthful cross-fields, endpoint-digest golden parity, event-id replay, secure state-root
  validation, per-record/file/count limits and backlog telemetry, locked JSONL
  append/compaction interruption, `${state_root}/dead-letter.jsonl` permanent-rejection handling,
  and acknowledged drain; expose the shared audit client/outbox port used by the process backend.
- [x] 2.4 Add migration 044 and implement synchronous idempotent coordinator audit plus secure
  outbox fallback outside all checkout roots.

## 3. Pure renderer and prepared command lifecycle (TDD)

- [x] 3.1 Add failing tests for deterministic SRT rendering, deny-first conservative policy,
  home/read confinement, read-only project roots, per-launch vendor state, confined write modes,
  unsafe/symlink roots and the exact posture-independent managed/snapshot-root predicate, positive
  child-environment allowlisting including backend-authored `GIT_OPTIONAL_LOCKS=0`, per-lane environment-only
  credentials, private-address/DNS denial, Git read/write behavior, and wildcard subset.
- [x] 3.2 Add the pinned SRT package/lock and implement git-common-dir-aware runtime discovery and
  Linux/macOS capability preflight.
- [x] 3.3 Implement pure rendering plus mode-0600 materialization, sanitized environment, absolute
  binaries, normative strip list/trusted PATH, `--` argv boundary, structured metadata, and cleanup.
- [x] 3.4 Add failing timeout/concurrency tests and implement the single
  `local_process_backend.py` with process-group TERM/KILL ownership.

## 4. Route every vendor CLI through the backend (TDD)

- [x] 4.1 Test and fix config projection so effective mode isolation is mode override then entry,
  only for standalone calls; require each mode's explicit enforcement scope/write capability and
  add and validate unique env-name `state_env_keys` in `CliConfig`/YAML (explicit empty list
  permitted), and preserve per-vendor `api_key_env`/proxy-compatibility configuration; sandbox
  lanes with missing environment-backed auth fail closed as rollout-ineligible.
- [x] 4.2 Add RED/GREEN coverage for review-dispatch sync, async submit, poll, repair, and snapshot
  fallback with an explicit per-attempt context, read-only-only snapshots, typed enforcement
  failures, retryable poll collection, `remote_state_unknown` deadline handling, and exact
  tracked/index/worktree/nonignored-untracked content-digest parity before snapshot launch.
- [x] 4.3 Version `PhaseDispatchPayload`, embed the full dg-06 enforcement projection/digest, remove
  the top-level v2 isolation authority, subordinate `phase_agent.py`'s worktree lifecycle default,
  define v1 sandbox `upgrade_required`, carry the lossless dg-06 digest source, reject projection or
  duplicate provider/model/agent/isolation mismatches and floats, and cover roadmap, smoke, and
  local-provider producers without cwd inference or model substitution.
- [x] 4.4 Add `test_no_vendor_subprocess_bypass.py` covering subprocess run/Popen/call/check APIs,
  asyncio subprocess APIs, and os.system/popen, exempting only the backend and an exact
  `(file,function)` Git/coordinator control-plane allowlist plus the exact inherited-SRT
  `(ocr_adapter.py, run_ocr)` descendant exemption; maintain a required production-surface
  registry covering review, fact-check, every registered evaluation backend, quick-task,
  phase-fixer, provider CLIs, and the explicitly inherited-sandbox OCR adapter;
  run it in CI.
- [x] 4.5 Extend result/ledger metadata with routing digest, requested/applied isolation,
  endpoint digest, policy/runtime/settings identity, snapshot content identity, typed collection
  state, and cleanup status.
- [x] 4.6 Add a sandbox host-commit signal, update mutating skill prompts/commit steps so sandboxed
  workers edit only, and make the host validate and create save-point commits after collection.

## 5. Behavioral evidence and documentation

- [x] 5.1 In `wp-runtime`, add a controlled vendor fixture proving review project writes
  leave no persistent host mutation, write-mode edits remain under root, credential fixtures cannot
  be read, allowed egress succeeds, denied/private/DNS-resolved egress fails, linked-worktree
  runtime discovery works, and one pinned configured vendor executable (`--version`) enters the
  backend. Authenticated per-lane client success remains a rollout precondition.
- [x] 5.2 Run the real SRT probe on capable Linux and macOS hosts and persist evidence; incapable
  hosts must report exact missing prerequisites rather than silently skip. A push/PR-triggered
  `ubuntu-24.04` + `macos-14` matrix must pass for the exact pushed head SHA; after push, download
  and verify the authoritative GitHub run/artifacts without checking in self-referential evidence.
- [x] 5.3 Document installation, policy authoring/endpoint inventory, rollout, degradation outbox,
  threat boundary, and recovery.
- [x] 5.4 Run focused/full tests, coordinator mypy, Ruff, install-manifest check, dependency-
  direction lint, strict OpenSpec validation, and multi-vendor implementation review to convergence.

<!-- CHECKPOINT: implementation-ready -->

## 6. Landing

- [x] 6.1 Record evidence, push, merge, and advance the roadmap checkpoint.
