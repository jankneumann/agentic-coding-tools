# Design: Publish the supervisor-worker dispatch contract

## Context

The supervisor (`skills/supervise/scripts/execution.py`, `gate_router.py`) prepares
delegated attempts through the roadmap orchestrator
(`skills/autopilot-roadmap/scripts/orchestrator.py`), persists them in the roadmap
`checkpoint.json` (`skills/roadmap-runtime/scripts/models.py`, `checkpoint.py`), and a
child `/autopilot` run in an isolated worktree drives `loop-state.json` through
`skills/autopilot/scripts/runner.py`. The request/result shape is defined three times
by hand and the child-to-result mapping is composed by the worker. This design fixes
one definition, one mapping, and one answer path per parked shape, and makes the
persisted state safe to commit to a shared ref.

Existing behaviour this design builds on, not replaces:

- The supervisor side already re-evaluates a `posture_block` record when the
  posture's *disposition* for that gate changes (`gate_router._apply_prior_record`).
  The child side does not: `runner.py gate-check` prints an existing `pending_gate`
  without re-evaluating it.
- `ExecutionAdapter.resume` already requires an `approval_ref` of the form
  `gate-decision:<decision_id>` resolving to a `proceed` record.
- `ExecutionAdapter.prepare` already requires a `roadmap_approval_ref` whose
  fingerprint matches the current roadmap (`gate_router.require_approval_ref`).

## Decisions

### D1. Schema versioning: v2 writers, v1-tolerant readers

Both schemas are published at `schema_version` 2. Writers (`orchestrator.py`,
`execution.py`, `emit-result`) emit only v2. Readers accept v1 requests and results by
upgrading them in memory through `dispatch_contract.upgrade_v1()`; the existing v1
fixtures stay byte-unchanged and must pass this way (acceptance outcome 1). A v1
request gains an empty `execution_profile`/`review_requirements` (which the child
treats as standalone for D10 purposes). A v1 result gains
`degradations: []`, its absolute `worktree_path` is converted to `worktree_ref`
against the current host's managed worktree root or repo root, its absolute
`evidence.loop_state_path` is rewritten relative to that worktree, and `host_id` is
set to the current host. A v1 result whose paths cannot be made relative is rejected
with a named error. `upgrade_v1(doc, *, repo_root, managed_root, host_id)` takes the
host context explicitly; schema validation of a v1 document (against the frozen v1
reader schemas, D2) is host-independent, so the existing fixtures validate on any
host and only the upgrade step is host-bound.

- *Alternative:* bump in place with no v1 support. Rejected: workers already running on
  `multiplayer-collaboration` return v1 results, and refusing them would strand those
  attempts.
- *Alternative:* indefinite dual support. Rejected: v1 reading is removed by a later
  change once no unresolved v1 attempt exists; the closure test covers v2 only.

### D2. One definition, loaded at runtime

`skills/shared/dispatch_contract.py` locates the schemas the same way
`review_findings_schema.find_schema_path` does (repo `openspec/schemas/` first, then
`skills/roadmap-runtime/install_assets/openspec/schemas/`), validates with
`jsonschema.Draft202012Validator`, and adds only the cross-field checks a schema
cannot express: result identity matches the attempt, evidence commit and digest match
the worktree, size of canonical JSON is at most 16 KiB. `_RESULT_REQUIRED`,
`_RESULT_ALLOWED` and `_validate_result` in `execution.py`, and
`_validate_dispatch_result` in `orchestrator.py`, are deleted. The inline result
object in `checkpoint.schema.json` becomes a `$ref` to
`dispatch-result.schema.json`, resolved through a `referencing.Registry` built from
the schema directory.

The v1 boundary is also published, but unused at runtime, as JSON Schemas under
`openspec/contracts/roadmap-orchestration/schemas/` (`supervised-dispatch-request`,
`supervised-dispatch-result`, `delegated-dispatch-attempt`, `bounded-dispatch-context`,
each with an `https://agentic-coding-tools.dev/contracts/...` `$id`). They are
validated today only by tests (`skills/tests/supervise/test_execution_contract.py`,
`test_execution.py`, `roadmap-runtime/test_dispatch_scheduler.py`,
`autopilot-roadmap/test_supervised_dispatch_e2e.py`). To end with one definition per
shape:

- `supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json`
  are frozen as the **v1 reader schemas**: `upgrade_v1()` validates a v1 document
  against them before upgrading it, and nothing writes v1. They are deleted with v1
  reading (Open questions).
- `delegated-dispatch-attempt.schema.json` becomes the **single attempt definition**:
  it gains `launch_digest`, `roadmap_approval_ref` and portable isolation, and
  `checkpoint.schema.json`'s `dispatch_attempts.items` becomes a `$ref` to it (its
  `result` in turn `$ref`s `dispatch-result.schema.json`).
- `bounded-dispatch-context.schema.json` is kept and `$ref`'d by the v2 request.
- The v2 request/result live only at `openspec/schemas/dispatch-*.schema.json`.
  `dispatch_contract`'s registry loads every schema in `openspec/schemas/` and
  `openspec/contracts/roadmap-orchestration/schemas/` by `$id`; the four contract
  files are mirrored under `skills/roadmap-runtime/install_assets/openspec/` at the
  same relative paths, and the locator's install_assets fallback covers both
  directories.
- The four tests above validate through `dispatch_contract` instead of building their
  own validators.

- *Alternative:* generate Python validators from the schema at build time. Rejected:
  adds a build step that installed copies in consumer repos would not run.
- *Alternative:* keep the hand validators and add a parity test. Rejected: two
  definitions are the root cause this item exists to remove.

### D3. Gate field is a closed enum

The v2 result's `parked.gate` is the `Gate` enum (nine values) or `null`, not a free
string of up to 128 characters. A closure property is only checkable over a finite
set. Allowed combinations are constrained per kind with `oneOf`:

| `parked.kind` | `parked.gate` | Supervisor answer path |
|---|---|---|
| `pending_gate` | any `Gate` except `roadmap_approval` | `resolve_parked` evaluates `Gate(parked.gate)`; `escalate_resume` included via the merged narrow fix |
| `policy_pause` | `null` or `escalate_resume` | `resolve_parked` evaluates `escalate_resume` for the generation |
| `permission_blocked` | `null` | escalation subject keyed by rule fingerprint (D9), answered by `escalate_resume` |
| `capability_unavailable` | `null` | escalation subject keyed by missing-lane set (D9), answered by `escalate_resume` |

`roadmap_approval` is excluded from child parks because a child never evaluates it.

Non-parked outcomes close as today: `success` completes the item, `failed:<reason>`
goes through `orchestrator._handle_failure`, and `vendor_limit:<vendor>:<reason>` goes
through `_handle_vendor_limit`. `vendor_limit` is written by the host when the child
session hits a provider limit, not by `emit-result`. The closure test enumerates
these outcome classes alongside the parked table.

### D4. Normative loop-state -> result mapping, in code

`skills/shared/dispatch_contract.py` owns `result_from_loop_state(state, attempt_ctx)`;
`runner.py emit-result` is its only CLI. Precedence, first match wins:

| Loop-state condition | Result |
|---|---|
| `park` set (v6) | `parked/<park.kind>` with its payload |
| `pending_gate` set | `parked/pending_gate`, `gate = pending_gate.gate` |
| `current_phase == "ESCALATE"` | `parked/policy_pause`, `resume_hint` carries `previous_phase` |
| `current_phase == "DONE"` and `goal_gate.verdict == "abandoned"` | `failed:abandoned` |
| `current_phase == "DONE"` and `goal_gate.verdict == "passed"` and `last_handoff_id` set | `success` with `handoff_id = last_handoff_id` |
| `current_phase == "DONE"` otherwise (verdict missing/refused, or no handoff) | `failed:goal_gate_unverified` |
| any other phase | no result; exit 5 (`EXIT_NOT_TERMINAL`), nothing written |

`park` precedes `pending_gate` because a park records why the child stopped *before*
reaching a gate. DONE via `abandoned` is separated because the transition table
routes `ESCALATE --abandoned--> DONE` (and `_check_done_evidence` stamps
`goal_gate.verdict = "abandoned"`); mapping every DONE to `success` would complete an
abandoned roadmap item. Evidence is `{loop_state_path, commit, loop_state_digest}`
computed from the committed file at `HEAD`, so `emit-result` refuses (exit 2) when
`loop-state.json` has uncommitted changes.

The result is written to
`openspec/changes/<id>/dispatch-results/<dispatch-slug>-g<N>.json`, where
`dispatch-slug` replaces every character outside `[A-Za-z0-9._-]` with `-` (dispatch
IDs contain `:`), and is also printed to stdout. The worker commits the file; the
cross-session message carries only its path and commit.

### D5. Gate provenance and the one-way answer

Every gate-decision record (child `loop-state.gate_decisions` and supervisor
`checkpoint.gate_decisions`) gains `provenance`:

- `{"source": "posture", "posture_digest": "<sha256>"}` for `auto`, `posture_block`
  and timeout-default resolutions;
- `{"source": "human", "approval_ref": "gate-decision:<id>" | null}` for
  console/coordinator approvals and rejections.

`posture_digest` is the SHA-256 of the canonical JSON of the *parsed* `gates` map
(`trust_posture.posture_digest()`), so prose edits to `TRUST_POSTURE.md` do not count
as a posture change, and an absent posture has the fixed digest of the all-`block`
default. `gate-request.schema.json` (`pending_gate.posture`) gains the same
`posture_digest`.

Authority rule (closes the "two state holders" gap): for a dispatched child the
supervisor's record is authoritative and its posture (at the roadmap workspace's repo
root) is the one evaluated. The child never re-evaluates a pending gate itself; it
applies only the `gate_answer` its marker carries. Because the child's worktree
posture can differ from the supervisor's (Issue 1 began exactly that way), the marker
carries the supervisor's `posture_digest`, and a dispatched child whose worktree
digest differs takes no `auto` disposition and parks `pending_gate` instead, so the
supervisor decides. Only a standalone run re-evaluates its own pending gate in
`gate-check`.

Re-evaluation rule (whoever is authoritative): on resume, a `posture`-provenance block
whose digest differs from the current posture digest is re-evaluated; a
`human`-provenance record is final for its subject. Comparing the digest instead of only the gate's disposition
(today's supervisor rule) also catches `notify_with_timeout` parameter changes.

Answer direction: supervisor -> child only. The resume request carries
`gate_answer: {gate, decision, approval_ref}`. The child applies it with
`runner.py gate-answer <change> --gate G --decision D --approval-ref R`, which records
a `human`-provenance (or, for a posture-derived proceed, `posture`-provenance) record
and clears `pending_gate`. `gate-answer` refuses a `--approval-ref` that does not
match the one in the current launch marker. The supervisor never writes a child
worktree file other than the launch marker.

- *Alternative:* the child re-reads the supervisor checkpoint to discover answers.
  Rejected: the child's worktree may be on another host and branch; the request is the
  only channel both sides share.

### D6. Launch token digest, minted per generation

`checkpoint.json` stores `launch_digest: "sha256:<64 hex>"` and never the raw token.
The raw token exists only in the request handed to the host. `child_start` verifies
`hmac.compare_digest(sha256(token), digest)`.

Because the supervisor cannot re-emit a token it no longer has, a token is minted per
*launch generation*: `resume` and a new `ExecutionAdapter.reissue(dispatch_id)` mint a
fresh token, store its digest under the same compare-and-swap that increments or
re-arms the generation, and return a request carrying it. `reissue` is allowed only
for `prepared` attempts and pre-go expired claims (the states where a takeover is
already permitted), so it cannot hand a second owner a post-go generation. The prior
"same token on resume" clause in Durable Delegated Attempt Ledger is modified
accordingly.

Field name and format are chosen against the default gitleaks `generic-api-key` rule:
the key contains none of its keywords (`token`, `key`, `secret`, `auth`, ...) and the
`sha256:` prefix breaks its value character class. A committed fixture checkpoint with
live attempts (`skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`) is
scanned by the existing CI gitleaks job with no allowlist entry; a unit test asserts
no serialized checkpoint field name matches the rule's keyword set.

Legacy reader: a stored `launch_token` is converted to `launch_digest` on load and the
raw value is dropped on the next save. The live roadmap checkpoint is not edited by
this change; it migrates the next time the supervisor saves it.

### D7. Host-portable isolation

Attempt isolation becomes `{mode, worktree_ref, branch, host_id}`:

- `worktree_ref`: the worktree path relative to the managed worktree root
  (`managed_worktree` mode) or to the repo root (`harness_provided` mode when it is
  inside the repo), else `null`.
- `host_id`: a stable, non-secret host identifier from
  `skills/shared/environment_profile.py` (cloud session environment ID when present,
  else a hash of the machine ID). Never a hostname or username.

On reconcile, an attempt whose `host_id` differs from the current host is:

- **rebound** when a worktree for `branch` exists under this host's managed root, its
  `HEAD` contains the attempt's last recorded evidence commit, and its
  `loop-state.json` digest matches; the attempt keeps its generation and records a
  `rebound` history entry with the new `host_id`;
- **reinitialized** when no such worktree exists and the attempt is `prepared`,
  `parked`, or pre-go: a managed worktree is created for `branch`, the generation is
  incremented, and a fresh token is minted (D6);
- otherwise (post-go with no positive liveness evidence) left in `quarantined`, as the
  existing liveness rules already require.

`resolve_worktree(attempt)` replaces every direct read of
`isolation["worktree_path"]` in `execution.py` and `orchestrator.py`; absolute paths
exist only in memory.

### D8. Roadmap-approval-scoped auto

`TRUST_POSTURE.md` gate configs for `proposal_approval` and `replan_required` gain an
optional `unscoped` sub-config (same shape as a gate config, `auto` disallowed),
defaulting to `{disposition: block}`. `approval_gate` resolves those two gates as
follows: `auto` applies only when the current launch marker (written by `child_start`
after the supervisor verified the ref with `require_approval_ref`) carries a
`roadmap_approval_ref`. `ApprovalGate` obtains the marker itself through an injected
`marker_reader` seam (default: a lazy import of
`dispatch_contract.read_launch_marker`); a `roadmap_approval_ref` supplied in the
evaluation context is ignored, so no caller can assert scope by passing a value.
Without a marker ref, the `unscoped` config applies and the decision's `reason` names
the fallback. The `scope` used is recorded in the gate-decision record. The seam lets
`wp-posture` land and test before `wp-contract-lib` exists.

`prepare` persists the verified `roadmap_approval_ref` on each attempt (it is a
`gate-decision:<uuid>` reference, not a secret) so that `child_start` can write it
into every generation's marker and so that the supervisor-side evaluation in
`gate_router.resolve_parked` can supply a `marker_reader` that returns the attempt's
own ref. Both sides therefore apply the same scope rule from the same recorded fact.

Trust boundary: the marker lives in the child's own worktree (gitignored
`.supervised-dispatch/`). Anything able to forge it can already act as the child, so
the marker is trusted to the same degree as the child process; it is not a defence
against a malicious child.

- *Alternative:* the child re-verifies the ref against the roadmap checkpoint.
  Rejected: the checkpoint lives on the roadmap branch, not the change branch; the
  marker is the authenticated channel (its generation and owner are already verified).
- *Alternative:* hard-code `block` as the fallback with no posture field. Rejected:
  the acceptance outcome speaks of the gate's "non-auto fallback", and operators may
  want `notify_with_timeout` for standalone runs.

### D9. One escalation per capability park

`gate_router.resolve_parked` maps `permission_blocked` and `capability_unavailable` to
an `escalate_resume` subject keyed by a *dedupe fingerprint* instead of by dispatch:

- `permission_blocked`: `sha256(tool, rule, classifier_reason)` where `rule` is the
  matched permission rule (for example `Bash(env *)`), never the full command.
- `capability_unavailable`: `sha256(phase, sorted(missing_lanes))`.

N parked attempts with the same fingerprint produce one `pending_gates` entry listing
all their dispatch IDs, each with the `lease_generation` it had at projection. One
operator answer resumes every attempt in that entry, each through its own
generation-checked CAS.

Decision-record shape for the fan-out: answering a fingerprint entry writes **one
`escalate_resume` record per listed dispatch**, each with that dispatch's own
`dispatch_id` and projected `lease_generation`, plus the shared `dedupe_fingerprint`
and the answer's `provenance`. `gate_router.require_approval_ref` therefore keeps its
existing per-dispatch checks (`dispatch_id` equal, and for `escalate_resume`
`lease_generation` equal) unchanged; an attempt whose generation moved since
projection fails that check and is skipped and reported. `ExecutionAdapter.resume`
accepts parked kinds `permission_blocked` and `capability_unavailable` in addition to
`pending_gate` and `policy_pause`, with expected gate `escalate_resume`, and also
requires the record's `dedupe_fingerprint` to equal the fingerprint recomputed from
the attempt's parked payload.

The redacted command is stored only after passing through
`skills/session-log/scripts/sanitize_session_log.sanitize()` (secret-pattern and
high-entropy redaction; the stored value is the first element of its
`(content, redactions)` return value), truncated to 256 characters; it is redacted by
`runner.py park` in the child, and re-sanitized by the router.

### D10. Execution profile and honest quorum

The supervisor resolves `execution_profile` once per batch with
`review_dispatcher.py --check-vendors --json`, which reports, per mode, the lanes for
which a dry invocation (`<cli> --version`, or for SDK/API lanes the adapter's own
authenticated no-op, with a 10-second timeout) succeeded. Credentials are touched only
inside the adapter's existing credential path and never printed; workers never probe. The profile names
`probe_command`, the only probe a worker may re-run. `review_requirements` holds
`min_quorum` per review phase (`PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW`; default 2,
today's `--min-vendors` value, overridable by router context key `review_min_quorum`)
and `counting_lanes`: every lane the roster (`agents.yaml`) configures for mode
`review`, **verified or not**, ordered by the `cost_policy.tiers` ladder in
`agent-coordinator/routing.yaml` (subscription-local, subscription-cloud, metered-api).
`execution_profile.lanes.review` holds the verified subset, so a park's
`missing_lanes` is `counting_lanes` minus the verified lanes and is non-empty
whenever quorum is unmet by a configured-but-unverified lane; distinct gaps therefore
fingerprint differently (D9). The ladder orders lanes; it does not exclude any tier
from counting. `routing.yaml` itself is not edited.

In a dispatched child (launch marker present), a review phase whose verified lanes are
fewer than `review_requirements.min_quorum[phase]` records
`park(kind=capability_unavailable)` and stops; it never lowers the quorum. A
standalone run keeps today's behaviour (disable CLI review) but appends a
`single_vendor_review` or `review_skipped` degradation.

Where this happens: today the below-quorum decision is made in the worker protocol
(`skills/autopilot/SKILL.md` runs `--check-vendors` and sets
`CLI_REVIEW_ENABLED=false`, so the review phases are skipped and `converge()` never
runs). In a dispatched child the protocol instead keeps review enabled and, at
`PLAN_REVIEW` / `IMPL_REVIEW` entry, compares `execution_profile.lanes.review` with
`review_requirements.min_quorum[phase]` and runs `runner.py park --kind
capability_unavailable`. A standalone run below quorum runs `runner.py
record-degradation --code review_skipped` when it disables review.
`convergence_loop.converge()` gains a pre-dispatch guard that returns
`reason="capability_unavailable"` when handed fewer verified lanes than `min_quorum`;
it never writes loop state (`runner.py` stays the only writer of `park` and
`degradations`, D11).

Degradation codes (closed enum): `single_vendor_review`, `review_skipped`,
`coordinator_projection_forbidden`, `audit_sink_failed`, `phase_fallback_inline`,
`handoff_local_fallback`. Each entry is `{code, phase, detail<=512}`, at most 32 per
result.

### D10a. Launch marker v2 is the child's only view of the request

The child never sees the supervisor checkpoint. `child_start` writes the launch marker
(`<worktree>/.supervised-dispatch/<change-id>/<item-id>-attempt-<n>.marker`, path
unchanged) with the request fields the child needs: `dispatch_id`, `generation`,
`owner_nonce`, optional `continuation`, optional `gate_answer`,
`roadmap_approval_ref`, `posture_digest` (the supervisor's), `execution_profile`,
`review_requirements`. The marker carries
no token. `skills/shared/dispatch_contract.read_launch_marker(change_id)` returns the
highest-generation marker under `.supervised-dispatch/<change-id>/` whose identity
fields validate (or `None` for a standalone run); `runner.py` and `approval_gate` call only this function. "Dispatched
child" in the specs means this function returned a marker.

### D11. Loop state v6

`LoopState` advances to `schema_version` 6 with `park: dict | None` and
`degradations: list[dict]`. `_apply_transition` refuses while `park` is set (same
enforcement point as `pending_gate`). `runner.py park` and
`runner.py record-degradation` are the only writers. The resume continuation clears
`park` through `gate-answer --gate escalate_resume --approval-ref`.

## Package boundaries and ordering

See `work-packages.yaml`. The DAG is shaped by file ownership:

- Roots (parallel): `wp-merge-narrow-fix` (gate_router/execution/supervise SKILL),
  `wp-dispatch-schemas` (openspec/schemas dispatch + checkpoint), `wp-posture`
  (trust_posture, approval_gate, gate schemas).
- `wp-contract-lib` (shared/dispatch_contract.py) depends on schemas.
- `wp-runtime-ledger` (models/checkpoint/orchestrator) and `wp-autopilot-child`
  (runner/autopilot/autopilot SKILL) run in parallel after contract-lib and posture.
- `wp-review-honesty` (review_dispatcher, convergence_loop) after autopilot-child.
- `wp-supervisor` (execution/gate_router/supervise SKILL) after merge, runtime-ledger,
  posture.
- `wp-integration` (closure, e2e, cross-host, secret-scan fixture) last.

## Risks and trade-offs

- **Schema `$ref` resolution in installed copies.** Consumer repos may only have the
  `install_assets` mirror. Mitigation: the loader's fallback path and a parity test
  between the two schema copies.
- **Token rotation changes resume semantics.** A host still holding an old request
  after `reissue` gets `launch token mismatch`. Accepted: that is the intended
  revocation, and it only happens in states where a takeover is already allowed.
- **Dedupe merges distinct problems.** Two different commands under one permission rule
  share an escalation. Accepted: the operator fixes rules, not commands; the entry
  lists every dispatch and its redacted command.
- **v1 tolerance window.** Kept small and removed later; the closure test does not
  cover v1.
- **Scope.** L effort across four skills. Mitigated by eight packages with disjoint
  write scopes.

## Open questions

- History rewrite for PR #662: commits already on the roadmap branch contain raw
  tokens, so gitleaks over full history still fails until those commits are squashed
  or allowlisted by SHA. This change makes new state clean; the history decision is
  the operator's (not an edit this change may make).
- Removal of v1 reading (D1) is a follow-up; the trigger is "no unresolved attempt has
  a v1 result", which a small check in `/supervise` can report.
