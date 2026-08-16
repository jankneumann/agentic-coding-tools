# Design — Phase-Scoped Worktree Lifecycle

## Context

The worktree registry currently gives one Boolean, `pinned`, two incompatible
meanings: preserve this checkout from garbage collection and treat this checkout
as an active writer. Planning pins its worktree after pushing, while merge-time
sync points treat every pin as active forever. The resulting idle-worktree
deadlock is amplified by workflows whose cleanup is tier-specific, by
interrupted Markdown-driven runs, and by merge handling that assumes every
OpenSpec PR contains a completed implementation.

This change makes the repository-owned registry the local lifecycle authority.
Activity becomes a bounded, owner-scoped lease; retention remains a separate GC
policy. A pushed branch and PR become the durable boundary between standalone
phases. Autopilot is the explicit continuous-mode exception. Merge triage also
gains a deterministic delivery-stage classifier so proposal-only merges do not
archive the proposal they are meant to hand off.

The design must compose with two active changes. `add-merge-plan-orchestration`
owns the durable merge-plan envelope and its file/coordinator storage tiers;
this change extends each node with delivery evidence rather than creating a
second plan. `validate-feature-findings-gate` owns validation findings and its
ephemeral validation mode; this change supplies the phase lifecycle around that
worktree rather than adding another validation checkout implementation.

## Goals and non-goals

Goals are to make activity ownership expiring and observable, make every direct
write-capable phase release its own activity, preserve a continuous autopilot
run across nested skills, classify OpenSpec PR delivery independently from
origin and author, and keep local and coordinator projections consistent.

This change does not auto-merge PRs, make the coordinator authoritative for
local worktree safety, delete dirty worktrees on expiry, replace merge-review
consensus, or change vendor dispatch isolation posture. In particular, an
activity lease is coordination metadata, not permission to bypass the checkout
mutation policy.

## Decisions

### D1 — One shared schema-v2 interpreter is the lifecycle authority

`.git-worktrees/.registry.json` remains authoritative in local execution. A
stdlib-only `skills/shared/worktree_lifecycle.py` module will own parsing, v1
normalization, lease state calculation, and locked read-modify-write
transactions. `worktree.py`, `active_agents.py`, coordinator sync-point checks,
and worktree projections will consume this interpreter instead of independently
restating `pinned` and heartbeat rules. `skills/install.sh` ships it with the
portable shared payload, and the coordinator runtime image copies the same file
under `SKILLS_ROOT`; source and container import-contract tests prevent either
consumer from silently falling back to a duplicated parser.

Missing registries mean no local worktrees. A malformed registry is not silently
rewritten: inspection reports the parse error, mutating lifecycle commands
refuse to overwrite it, and sync-point checks report an indeterminate blocker
that requires the existing explicit operator override. This distinguishes
"nothing registered" from "ownership cannot be proven" without inventing a
remote authority.

Cloud/harness short-circuit behavior remains intact. When
`EnvironmentProfile.isolation_provided` is true, lifecycle mutation commands do
not create or update the local registry; the harness owns disposal.

### D2 — Schema v2 separates retention from one current activity lease

Canonical writes use the following shape (timestamps are UTC RFC 3339 values):

```json
{
  "schema_version": 2,
  "entries": [
    {
      "change_id": "add-user-export",
      "agent_id": null,
      "branch": "openspec/add-user-export",
      "worktree_path": "/repo/.git-worktrees/add-user-export",
      "created_at": "2026-08-15T12:00:00Z",
      "entry_generation": "01K2ENTRY",
      "setup_id": "01K2SETUP",
      "durability_target": {
        "remote_name": "origin",
        "remote_url_hash_algorithm": "git-remote-url-v1",
        "canonical_remote_url_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "ref_name": "refs/remotes/origin/openspec/add-user-export"
      },
      "retained": false,
      "retention_reason": null,
      "recovery_required": false,
      "recovery_reason": null,
      "recovery_context": null,
      "activity_lease": {
        "owner": "autopilot:01K2RUN",
        "lease_id": "01K2LEASE",
        "controller_instance_id": "01K2CONTROLLER",
        "session_id": null,
        "phase": "IMPLEMENT",
        "lifecycle_mode": "continuous",
        "reason": "autopilot-run",
        "acquired_at": "2026-08-15T12:00:00Z",
        "last_heartbeat": "2026-08-15T12:05:00Z",
        "expires_at": "2026-08-15T12:35:00Z",
        "ttl_seconds": 1800
      }
    }
  ],
  "setup_reservations": [],
  "recovery_audit": []
}
```

`owner` is an opaque, namespaced identity; `lease_id` is a client-generated,
single-acquisition fencing token; `controller_instance_id` binds that token to
one live controller process; and `session_id` is independently matchable by
session-end cleanup. Automatic ownership is the exact
`(owner, lease_id, controller_instance_id)` triple. `entry_generation` fences
observations made outside the registry lock. Automatic workflows use one
setup-and-acquire operation to create the checkout entry, process evidence,
and first lease without exposing intermediate unleased state. Because Git
worktree creation, evidence creation, and registry publication cannot be one
filesystem transaction, the operation first publishes a generation-fenced,
non-authoritative `setup_reservation` whose timestamp-free `lease_intent`
contains the requested initial ownership. It advances that reservation through
`reserved`, `checkout-created`, and `evidence-created`, then atomically replaces
it with the active entry and derives the lease timestamps from that final
publication time. Each reservation has a fixed 30-minute `ttl_seconds` and
`expires_at` bounding the original controller's exact-retry window. Every
unfinished reservation blocks sync points as indeterminate provisioning, but
only an unexpired exact retry may advance it. Expiry never silently clears the
blocker or side effects: explicit, generation-fenced setup reconciliation
either removes a reservation proven to have no side effects or publishes its
attributable checkout and evidence as an unleased, `recovery_required` entry.
The completed entry retains nullable `setup_id` provenance, so an exact setup
id, generation, target, and ownership-triple retry after response loss returns
the original success while an unrelated existing entry still refuses. Retry may complete or clean up only side effects proven
to belong to that exact reservation and generation; conflicting or unprovable
state is quarantined. Reservations never count as activity or satisfy an
ownership assertion.
`durability_target` stores the exact remote/ref that must
contain the checkout HEAD (the parent feature ref for package worktrees). A
worktree has at most one current lease. `retained=true` prevents ordinary GC
but never makes an entry active. `recovery_required=true` quarantines preserved
dirty or non-durable state from automatic adoption without making it a sync-point
activity blocker. `recovery_context` retains prior controller/process evidence
whenever ownership is cleared into quarantine. `activity_lease` may remain present after expiry for
inspection, but an expired lease is not active and may be replaced only by an
acquire carrying a new lease id. Explicit release sets it to `null`; GC may
compact expired lease details when it otherwise updates an entry.

Successful force-adoption, expired-setup reconciliation, and lease-free
recovery teardown append typed top-level `recovery_audit` events in the same
registry transaction that clears active `recovery_context` and issues the new
manual lease. The event records its unique id, actor, rationale, termination
confirmation, entry generation, prior identity, new identity, timestamp, and
the newly established durability target or null when the target pre-existed.
That append-only safety history survives both quarantine clearing and later
entry teardown.

The registry is state, not a general event log. The narrow exception is the
append-only operator-recovery safety audit. Operator-visible command results and
coordinator status events carry acquire/renew/release/conflict outcomes; durable
workflow history remains in the owning workflow's state and handoff artifacts.

### D3 — Every registry mutation is a locked, atomic transaction

All setup, teardown, retain, lease, migration, and GC mutations take an advisory
exclusive lock on `.git-worktrees/.registry.lock`, reload under that lock,
validate and normalize, apply exactly one transaction, write a uniquely named
temporary file, flush it, and atomically replace the registry. Read paths that
make a safety decision take a shared lock. Lock acquisition has a bounded
timeout and fails visibly; it never falls back to an unlocked write.

Reservation stage changes/reconciliation, active-entry publication, quarantine, teardown
removal, and recovery-audit append are atomic registry replacements. Git and
process-evidence side effects occur between those checkpoints and are reconciled
by exact reservation id, entry generation, and ownership triple. Fault tests
cover crashes after reservation, checkout creation, evidence creation,
publication, and response loss.

This removes the current lost-update window between `load_registry()` and
`save_registry()` and the collision risk of a single fixed `.tmp` name. File
locking and replacement live in the shared interpreter, so setup and lease
commands cannot accidentally use different transaction disciplines.

### D4 — Leases last 30 minutes and renew every 5 minutes

The default TTL is 30 minutes and the default renewal interval is 5 minutes.
Both are constants in the shared lifecycle module and may be overridden by
explicit CLI arguments for tests and exceptional operators; normal skills do
not select their own values. Time-dependent code accepts an injected clock.

The executable phase lifecycle wrapper starts renewal after acquire and stops
it in `finally`. The owning controller also renews at write-capable phase
transitions, before dispatch, after dispatch, and on resume. Renewal sets
`last_heartbeat=now` and `expires_at=now+ttl`; it does not extend from a possibly
stale prior expiry. The five-minute cadence leaves six missed-renewal windows
before a healthy lease expires.

A live lease blocks sync-point writers and GC regardless of retention. Expiry
only changes the activity calculation: it never tears down a checkout, drops a
branch, resets files, or clears retention.

### D5 — Acquire, renew, release, and teardown are owner checked

The lifecycle CLI exposes owner-, lease-, and controller-scoped `lease acquire`,
`lease resume`, `lease renew`, `lease release`, `lease status`, `lease release-owner`, and
`lease release-session` operations in addition to setup/teardown and retention
commands. Acquire accepts an optional non-empty session id and stores it as a
nullable, explicit lease field; release-session never treats null or empty as a
wildcard.

- Initial acquisition uses a non-active reservation with a timestamp-free lease
  intent. Git checkout and process-evidence checkpoints are reconciled outside
  that final transaction; one locked publication derives all initial lease
  timestamps from publication time, creates the fresh entry, and removes the
  reservation. Every separately observed unleased or
  legacy entry is unknown state and receives the same assessment as an expired
  entry. Takeover first refreshes the stored durability target outside the
  global lock, then under the lock revalidates entry generation and target
  before inspecting worktree/submodule cleanliness, exact HEAD reachability,
  and local process evidence from a digest of the canonical entry identity plus
  lease id. The record
  contains PID, platform process-start token, host/boot id, controller-instance
  id, entry identity, owner/lease id, and timestamps. Exact same-host PID/start matches are
  live; absent PIDs and start-token mismatches are stale; missing, unreadable,
  cross-host, and unsupported checks are indeterminate. Dirty, non-durable,
  live-writer, or indeterminate state is atomically marked `recovery_required`
  and ordinary acquisition fails. Only a checkout proven clean and durable with
  stale same-host process evidence may replace the expired lease, and
  replacement uses a caller-generated lease and controller id not equal to the expired identity.
- Reacquiring a live lease with the same owner, lease id, and controller id is idempotent,
  preserves `acquired_at`, and may update phase/reason before renewing expiry.
  The same token from a different controller conflicts. `lease resume` rotates
  lease/controller identities only after stale same-host evidence and safe,
  durable checkout state are proven; live or indeterminate evidence refuses or
  quarantines the transition even when the TTL expired.
- Acquiring an entry held by a different live owner fails with both owner,
  phase, and expiry evidence; it never steals the lease.
- Renewing, releasing, or disposing with the wrong owner, lease id, or controller id is a
  non-mutating conflict.
- Releasing an already absent lease is an idempotent no-op. Because a null lease
  retains no prior owner, lease id, or controller id, this result makes no claim that the
  caller formerly owned it; a live lease still requires exact ownership-triple
  equality.
- `release-session` clears only leases whose stored `session_id` exactly
  matches; an empty or missing session id is not a wildcard. As a crash
  backstop it never makes a preserved checkout automatically adoptable: while
  holding the lifecycle lock it marks each matching, still-present checkout
  `recovery_required` with session-termination evidence before clearing the
  lease. It preserves the prior evidence and identity in `recovery_context`. A
  checkout already removed by its explicit finalizer is a no-op.
- `release-owner` applies the same quarantine-before-clear rule to every
  still-present exact-owner checkout and reports per-entry outcomes; bulk
  recovery never makes preserved state ordinarily adoptable.
- Normal `recovery adopt` requires the former controller evidence to be stale
  on the same host. Live or indeterminate evidence refuses adoption. A separate
  audited `recovery force-adopt` requires actor, rationale, and explicit process
  termination confirmation for missing/cross-host evidence and is never used by
  automatic workflows. It appends the durable audit event in the same
  transaction that rotates ownership, so clearing quarantine cannot erase the
  authorization.
- `setup reconcile` accepts only an expired exact setup id and entry
  generation plus actor, rationale, and termination confirmation. It removes a
  side-effect-free reservation or converts attributable side effects to an
  unleased quarantine entry and audits that outcome; it never deletes
  unproven work.
- `recovery teardown` is the safe disposal route for an entry with no lease.
  It requires the exact entry generation and operator attribution, revalidates
  cleanliness and durability, and removes a missing checkout or clean durable
  checkout. Dirty, null-target, or non-durable state refuses.
- `recovery force-teardown` is a separately named, audited compatibility path.
  It requires exact stored lease identity when a lease remains, explicit
  process-termination and data-loss confirmation, and preserves the entry if
  Git removal fails. Automatic workflows never invoke it; legacy
  `teardown --force` fails with migration guidance to this command.
- When a recovery entry has a null durability target (including normalized v1
  and compatibility setup), force-adopt may issue a manual recovery lease
  without pretending durability. Automatic mutation and safe teardown remain
  forbidden until `recovery bind-target`, under that exact manual lease and
  generation, validates and establishes one complete remote/ref tuple.
  Existing non-null targets cannot be replaced.
- Normal teardown refuses to remove a worktree with another owner's live lease.
  Expired leases do not authorize deletion, and dirty/non-durable safety checks
  still apply.
- The durability target is one bound tuple. The remote component in
  `refs/remotes/<remote>/...` must equal `remote_name`. `git-remote-url-v1`
  requires exactly one configured fetch URL; for URI syntax it removes the
  complete userinfo component, for scp syntax it removes the prefix through
  `@`, and otherwise preserves every remaining UTF-8 byte without case,
  percent, path, slash, port, or `.git` normalization before SHA-256.
  Before a proof, the current configured URL digest must match and the exact ref
  is fetched outside the lock. The observed tip OID is bound to the revalidated
  generation and target; mismatch never falls back to another ref.

An automatic acquire refuses `recovery_required=true`. Only an explicit
operator adoption command may clear that state after inspection. This prevents
a later phase from silently building on dirty or unpushed files preserved by a
failed phase.

Owner strings use stable namespaces: `phase:<phase>:<run-id>` for a direct
phase, `autopilot:<run-id>` for continuous mode, and existing package/agent
identities for child worktrees. Security does not depend on the string format;
the full string equality check is the ownership boundary.

### D6 — V1 reads are compatible; v2 migration changes meaning deliberately

Readers accept both the existing top-level `version: 1` registry and canonical
`schema_version: 2`. V1 entries normalize as follows:

- `pinned=true` becomes `retained=true` with reason `legacy-pin`.
- A parseable legacy `last_heartbeat` within the existing one-hour activity
  window becomes a complete synthetic lease: owner
  `legacy:<change-id>:<agent-id-or-parent>`, deterministic lease id
  `legacy-v1:<sha256(change-id|agent-id-or-parent|created-at)>`, null session,
  phase `LEGACY`, reason `legacy-heartbeat-migration`, lifecycle mode `manual`,
  `acquired_at=min(created_at,last_heartbeat)`, the original heartbeat,
  `expires_at=last_heartbeat + 1 hour`, and `ttl_seconds=3600`.
- A stale or invalid heartbeat does not create live activity.
- Branch, path, agent, and creation fields are preserved byte-for-value where
  the v2 schema permits them.
- V1 entries normalize with a deterministic, inspection-visible
  `entry_generation`, null `setup_id`, null `durability_target`, and null
  automatic controller identity. Ordinary
  acquisition cannot silently adopt that unknown state; recovery must establish
  a trusted durability target and prior-process termination evidence.

Read-only `inspect --migration-report` shows the exact normalization and any
invalid entries without writing. The first successful mutating transaction
prints the same migration summary before atomically writing canonical v2; reads
alone never rewrite state. Unknown top-level or entry fields are preserved under
an explicit `extensions` object during conversion rather than silently
discarded. Canonical v2 writers never emit unknown fields beside the
schema-defined properties.

The complete legacy `setup` signature remains valid, including explicit branch,
environment override and computed-default precedence, isolation short-circuit,
bootstrap behavior, package/path layout, and existing shell output. This is a
compatibility/manual setup path, not the first half of automatic acquisition.
Without an optional complete durability pair it records a null target; either
way, later automatic acquire assesses it as unknown state. Automatic workflows
use setup-and-acquire with an explicit bound target.

`pin` and `unpin` remain migration aliases for setting and clearing retention.
They do not acquire, renew, or release activity. For a v1 entry only, the legacy
`heartbeat CHANGE_ID [--agent-id ID]` command atomically canonicalizes the entry
using the deterministic mapping above, sets `last_heartbeat=now` and
`expires_at=now+3600`, and reports the synthetic owner and lease id. Once an
entry is v2, the alias requires explicit `--owner` and `--lease-id`. A separate
compatibility handler may omit controller identity only when the stored lease
is that manual `LEGACY` null-controller lease; every other v2 lease requires a
controller and delegates to `lease renew`. Help and status output label these
compatibility semantics explicitly.
The same exact synthetic identity permits controller omission for `lease
release` only on a manual `LEGACY` lease whose stored controller is null; every
other release requires a non-empty controller identity.

### D7 — Lifecycle context is explicit and reports who must release

Write-capable skills receive a lifecycle context with `lifecycle_mode`, `owner`,
`session_id`, worktree identity, `controller_instance_id`, and
`release_responsibility=caller|parent`.
Release responsibility is explicit input, not inferred from whether an
idempotent acquire happened to create a new lease record. A standalone caller
uses a unique phase owner and has `release_responsibility=caller`; a nested
caller presented with a live continuous lease may assert the exact inherited
triple, but only the parent controller updates phase or renews it. The child has
`release_responsibility=parent` and must not release or
tear down the parent's worktree. This avoids leaking a standalone lease when an
acquire response is retried after its original output was lost.

The context is passed as explicit command arguments/environment for subprocesses
and as dispatch context for agents. Ambient process state is not the sole source
of truth: continuous orchestrators also persist it in their resumable state.
Missing or contradictory context fails before mutation rather than guessing
standalone versus continuous ownership.

The concrete `skills/shared/phase_lifecycle.py` controller starts and monitors
the renewer, persists non-authoritative process context, and provides idempotent
`begin`, `assert-owned`, and `finalize` operations for all Markdown-driven
skills. It latches renewal failures and verifies the matching ownership triple
before each subsequent repository mutation boundary, integration, commit, and
push. An expired lease, fencing mismatch, or failed renew aborts the phase
instead of allowing an unfenced writer to publish. A tool already in flight may
finish, but its caller must not start another mutation after lease loss. Session
hooks never invoke the phase finalizer or teardown. They invoke only
`release-session` as a non-destructive crash backstop; explicit workflow
finalization alone performs durability checks and removal. Registry state
remains the only ownership authority.

The controller also owns process evidence. It derives the process-start token
and host/boot id, atomically creates the schema-valid evidence file before
publishing an automatic lease and refreshes it with renewal. Clean disposal
deletes matching evidence; quarantine release archives or preserves it and
binds the key into `recovery_context` until safe adoption or teardown. Evidence
keys hash a versioned length-prefix encoding of `(change_id,
agent_id-or-null, entry_generation, lease_id)`, and every operation validates
entry, generation, owner, lease, and controller fields before use. Stale orphan
records are GC-eligible. Evidence can veto automatic expired
takeover but can never grant ownership or replace exact ownership-triple assertions.

### D8 — Standalone phases push and finalize through teardown-or-quarantine

Direct `plan-feature` uses branch `openspec/<change-id>--proposal`, acquires a
PLAN lease, validates all plan artifacts, commits and pushes them, opens a PR
whose body contains `OpenSpec-Delivery: proposal`, and then finalizes. While the
lease is still live, finalization takes the exclusive lifecycle lock, verifies
owner, lease id, and controller instance, checks dirtiness (including submodules) before any
destructive submodule operation, proves `HEAD` is reachable from the entry's
stored durability target, removes the worktree, and deletes its registry entry. Being
unmerged into `main` is not unsafe once the commit is durable on that remote
branch. If disposal refuses dirty or non-durable state, teardown atomically
marks the entry `recovery_required` and clears the matching lease with
operator-visible recovery evidence; it never force-deletes it.
Automatic teardown has no force mode. Compatibility callers and coordinator
kick operations inspect state and choose expired-setup reconciliation, safe
lease-free recovery teardown, or the separately confirmed and audited force
path.
The controller invokes disposal from the resolved main-repository directory,
not with its current working directory inside the worktree being removed.

Direct `iterate-on-plan` recreates or adopts the proposal branch/worktree and
owns only that invocation's lease. Direct `implement-feature`,
`iterate-on-implementation`, and `validate-feature` similarly recreate or adopt
the implementation branch `openspec/<change-id>` from the reviewed proposal on
`main` or its remote implementation branch, own a phase lease, push durable
output, and finalize independently. This rule applies to sequential,
local-parallel, and coordinated tiers. Package worktrees have their own leases
and are torn down after successful integration or quarantined-and-cleared on failure. Successful package
integration first pushes the parent feature ref, then proves the exact package
HEAD is reachable from its stored parent-feature durability target; the child branch need
not be pushed under its own name. Only then may exact-triple-and-generation-fenced
disposal remove the package checkout.

Every phase uses the same executable lifecycle controller. The Markdown skill
specifies the guarded mutation boundaries; it is not itself the only mechanism
for renewal and finalization. Clean durable disposal happens while the lease and
registry lock still fence acquisition, eliminating a release-then-remove race.
If disposal cannot proceed, quarantine-plus-clear is idempotent and the caller
does not issue a second release. Session hooks and bounded expiry remain crash
backstops.
If a process crashes after Git removal but before registry replacement, a
repeated teardown with the still-present exact entry generation and ownership
triple reconciles the
missing checkout by removing the entry and matching process evidence. A wrong
owner, token, controller instance, or entry generation cannot perform this
reconciliation.

### D9 — Autopilot persists and owns one continuous lease

Before PLAN mutates, autopilot resolves and persists the change id using the
same deterministic normalization as `plan-feature` (or asks the operator when a
description cannot resolve uniquely), creates the continuous implementation
branch/worktree `openspec/<change-id>`, then creates `autopilot:<run-id>` plus a
new lease and ephemeral controller id. The canonical state-machine
`openspec/changes/<change-id>/loop-state.json` remains in the feature branch for
existing phase, audit, and coordinator consumers. The canonical convergence
schema is the autopilot install asset; revision 5 accepts all current persisted
fields/phases and adds nullable evidence-only lifecycle context. The root
`openspec/schemas/` copy is generated byte-for-byte from that source, and a
persisted old controller identity never grants resume authority. A minimal schema-validated
recovery envelope lives outside the disposable checkout at
`.git-worktrees/.autopilot-runs/<run-id>/recovery.json`. It includes owner,
lease id, branch, durability target, durable HEAD, path and SHA-256 of the
committed canonical loop state, checkout state, and finalization intent, but
never duplicates phase authority or treats the prior controller id as reusable identity. The
envelope is lifecycle recovery metadata, not a second workflow-state authority.
Before constructing the path, autopilot validates safe run/change identifiers,
derives the path, branch, canonical loop-state path, and
`owner=autopilot:<run-id>`, and rejects every cross-field mismatch. The envelope
is written under a per-run lock with monotonic generation/CAS, a same-directory
unique temporary file, file flush/fsync, atomic replace, and parent-directory
fsync. Invalid existing bytes are preserved and fail closed. The loop-state
digest covers exact committed Git blob bytes before JSON parsing or migration;
the continuation phase is derived only from that validated canonical state.
Every `present` or `teardown_pending` envelope mutation also proves the exact
live registry owner/lease/controller triple plus entry generation before CAS; a
stale controller cannot gain authority by reloading the latest envelope
generation. After registry deletion, only the expected
`teardown_pending -> removed` CAS is allowed, bound to unchanged envelope
generation, lease id, entry generation, and finalization intent.
After unsafe teardown has atomically cleared the lease, a second narrow
exception permits `teardown_pending -> quarantined` only when the expected
envelope generation and prior fence match immutable registry recovery context
for the same entry generation and `unsafe-finalization` event, the entry has no
replacement lease, and finalization intent is unchanged. A stale controller,
adoption, generation change, or missing evidence is a non-mutating conflict.
Autopilot passes
the current exact lease triple into PLAN, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT,
IMPL_ITERATE, IMPL_REVIEW, VALIDATE, optional VAL_REVIEW, and SUBMIT_PR. Nested
skills and review/fix callbacks assert that inherited triple; only the parent
continuous controller renews it. Children do not create, rotate, or release
phase owners.

On resume, autopilot loads the external checkpoint. A still-running same
controller may idempotently continue its exact triple. A replacement controller
uses `lease resume`, which rejects live/indeterminate old evidence and rotates
the lease/controller only after stale evidence and safety checks. If the
checkout and registry were cleanly removed after ESCALATE or exception,
resume verifies the currently configured remote URL digest, fetches the stored
ref, and requires its tip to equal `durable_head` exactly. Mere reachability is
insufficient; an advanced, rewound, deleted, or mismatched ref remains
escalated. Before worktree creation it reads and hashes the loop-state blob from
that exact OID, schema-validates it, and checks its change id. It then recreates
the worktree and registry entry, verifies the restored canonical loop-state
digest against the envelope, atomically acquires a new lease/controller under
the stable owner, checkpoints the new identity in both views, and only then dispatches.
Partial presence, `teardown_pending`, quarantine, missing/non-durable refs, or
identity mismatch remains escalated until reconciliation proves one safe state.
An exact `removed` envelope with `finalization_intent=done` and canonical
`current_phase=DONE` is a terminal tombstone: resume returns the stored result
and never recreates a checkout or dispatches a phase. Inconsistent removed/done
evidence fails closed; further work requires a new run id.

Continuous autopilot always stores `session_id=null`; session hooks therefore
cannot clear its lease. The parent controller's `finally`, TTL fencing, and
explicit envelope recovery remain its cleanup authorities.

After SUBMIT_PR has persisted the PR/evidence checkpoint, autopilot writes the
canonical `current_phase=DONE` result, commits and pushes it, and records its
exact durable HEAD and blob digest in the still-present envelope. It then CASes
`finalization_intent=done` plus `checkout_state=teardown_pending`, stops
renewal, and uses the still-live exact triple plus entry generation for fenced
teardown. Successful teardown removes the entry and evidence before autopilot
CASes `checkout_state=removed`, and only then presents the human merge gate. A
crash after DONE resumes finalization only, never a workflow phase. Exception,
failed-outcome, and ESCALATE checkpoints follow the same durable-checkpoint,
pending, teardown, and removed ordering with their respective intents. Unsafe
teardown atomically quarantines and clears the exact
lease, then CASes the envelope to `quarantined`; it does not perform a second
release. A crash after Git/registry removal but before the removed CAS is
reconciled from unchanged pending generation and identity. A checkpoint write
failure is a hard recovery error and never authorizes deletion; quarantine and
bounded expiry remain the backstops.

External envelopes have a dedicated retention protocol. Generic worktree GC
never traverses `.git-worktrees/.autopilot-runs`. Only a schema-valid
`removed+done` tombstone receives `gc_eligible_at=removed_at+30 days`; all
active, resumable, quarantined, corrupt, or inconsistent records retain null
eligibility. Dedicated recovery GC takes the global-then-per-run lock order,
revalidates DONE/digest/ref plus absence of checkout, entry, and reservation,
then safely renames/removes and fsyncs. Corrupt records are preserved and
reported.

### D10 — Session end performs local, best-effort owner-scoped release first

The session-end hook resolves the repository from the hook project directory,
reads the terminating `SESSION_ID`, and invokes the stdlib lifecycle helper's
`release-session` operation before optional coordinator handoff/status calls.
This path works with no coordinator URL or network. It never uses a blank id,
never releases another session's lease, and never deletes a worktree. For every
matching lease whose explicit phase finalizer has not already removed the
checkout, the operation atomically records `recovery_required` with a
session-termination reason before clearing ownership. This conservative
backstop prevents a concurrent or abruptly terminated writer's checkout from
becoming ordinarily adoptable; explicit finalization remains the clean,
durable disposal path.

Hook failures are logged but cannot block process shutdown. The lease TTL is
still authoritative when a process is killed too abruptly for hooks. Explicit
workflow finalization remains the primary mechanism; session release is a
backstop, not a substitute for it.
`release-session` never reads or mutates an autopilot recovery envelope. If it
encounters continuous autopilot, its required null session is never a match and
the hook leaves both lease and envelope untouched.

### D11 — Delivery stage is a pure classifier over diff, base state, and marker

Origin classification remains in the portable GitHub classifier. A separate
pure delivery classifier consumes the resolved change id, immutable base/head
SHAs, the complete changed file set, the PR base/head OpenSpec state, and the
optional PR-body trailer `OpenSpec-Delivery: proposal|implementation|mixed`.
It returns `stage`, a structured evidence list, acquisition-completeness status,
marker status, and warnings. Truncated or failed diff acquisition and failed
base/head inspection are represented explicitly and always yield `ambiguous`.

Planning files are files under `openspec/changes/<change-id>/` that define the
proposal, design, delta specs, tasks, contracts, work packages, or workflow
metadata. Paths recognized outside that planning set are implementation
evidence; any path the versioned ruleset cannot partition is `other_files` and
makes the result ambiguous rather than being guessed into either class. The
deterministic ladder is:

1. Planning-only diff with a valid change directory at head is `proposal`,
   whether it introduces or revises the plan.
2. Implementation evidence with a governing active proposal present on the PR
   base is `implementation`; accompanying plan refinements do not make it mixed.
3. Implementation evidence plus a proposal introduced by the same PR because
   no governing active proposal exists on the base is `mixed`.
4. Missing diff/base data, multiple change ids, no valid governing plan,
   deleted/archived-only state, or otherwise contradictory evidence is
   `ambiguous`.

Branch naming may resolve a change id (`--proposal` is stripped) but cannot
decide stage. A matching marker corroborates the computed result. A conflicting,
duplicate, or invalid marker makes the result ambiguous. A missing marker emits
a warning but does not make deterministic legacy implementation PRs
unmergeable; all newly created OpenSpec PRs must write it. Classifier output is
recomputed from live GitHub/base data before execution rather than trusted from
a stale merge-plan snapshot.

### D12 — GitHub author and author vendor remain independent evidence

Discovery records independent `origin`, `change_id`, raw `github_author`,
`author_vendor`, and `author_vendor_evidence` fields. The evidence records exact
identity mapping, claimed trailer, corroborating generator/branch hints,
verification status, and conflicts. One shared classifier computes the result:
a configured exact GitHub identity is verified and authoritative; a standard
`OpenSpec-Author-Vendor` trailer written by agent workflows is a claim, not
authentication. Known branch prefixes and generator trailers may corroborate
but cannot override conflicting exact identity. Conflicting or unverified
evidence yields `unknown`; conservative routing attempts all configured
independent vendors and never uses the unverified claim to exclude a reviewer.

The allowed vendor values are the configured dispatch vendors plus `human` and
`unknown`; they are not folded into OpenSpec origin. Existing PRs without the
new trailer remain classifiable when their GitHub identity is known. Agent
workflow PR creation writes both delivery and author-vendor trailers so a PR
opened through a human GitHub account still records the producing-agent claim
without misrepresenting it as verified identity.

### D13 — Claude-authored OpenSpec PRs require independent Codex/Grok/Pi review

For `origin=openspec` and verified `author_vendor=claude`, review dispatch attempts each
configured Codex, Grok, and Pi adapter. Unknown or unverified provenance takes
the conservative route and attempts every configured independent vendor. It
never substitutes the claimed/same vendor for an
unavailable independent vendor. Availability and failure are recorded per
vendor, and the existing consensus/quorum policy decides whether the merge may
proceed; lost quorum is operator-visible and blocks unattended execution.

Prompts are stage aware:

- `proposal` supplies proposal, design, delta specs, contracts, tasks, and work
  packages and asks only for plan review.
- `implementation` supplies the governing plan from the base/head plus the
  complete implementation diff.
- `mixed` supplies the complete plan and implementation diff.
- `ambiguous` may be inspected, but cannot receive a merge-authorizing verdict
  until an operator resolves its stage.

The independent-review rule overrides the ordinary small-PR skip for a ready
Claude-authored OpenSpec PR. Draft PRs remain deferred. Other author vendors
retain existing eligibility and consensus behavior, with the author vendor
excluded where a configured independent-review policy requires it.

### D14 — Validation, cleanup, and convergence route by delivery stage

| Stage | Pre-merge review and validation | Post-merge behavior |
|---|---|---|
| `proposal` | Independent plan review, contract checks, and strict `openspec validate <change-id> --strict` against the PR head | Keep `openspec/changes/<change-id>/` active; skip deploy/smoke/security/e2e, implementation holdout/rework, cleanup, and archive; include the merge in the once-per-pass main-context convergence |
| `implementation` | Review governing plan plus code; run the full existing implementation validation and gates | Run cleanup/archive and normal branch/worktree cleanup, then main-context convergence |
| `mixed` | Review full plan plus code; run strict OpenSpec and full implementation validation | Run cleanup/archive and normal branch/worktree cleanup, then main-context convergence |
| `ambiguous` | Surface evidence and require an operator stage decision; no merge-authorizing automatic route | Do not merge, clean up, archive, or delete the active change |

Post-merge cleanup consumes the recorded/revalidated stage and explicitly
filters proposal nodes. It does not infer completion from `origin=openspec`.
Proposal merge cleanup may remove only its already-released disposable local
proposal branch/worktree when safe; it must not invoke `cleanup-feature` or
remove the active OpenSpec directory.

### D15 — Merge plans and coordinator/UI are projections of the same evidence

The `add-merge-plan-orchestration` node definition is extended in place with an
immutable discovery-time `delivery_classification`. Node state carries
`latest_delivery_classification` plus the effective routing decision. Both
classifications include base/head SHAs, changed-file acquisition status,
base/head proposal state, marker status, warnings, author, and author vendor.
`ambiguous` adds a human-decision gate and sets `auto_executable=false`.
The file tier persists both fields in this change. Coordinator APIs and UI
project that file-tier evidence without activating the deferred coordinator
system-of-record from `add-merge-plan-orchestration` Phase 2; when that tier is
implemented, its work-queue metadata must preserve the same contract. Execution
reclassifies live state
against current SHAs and writes the result to
`state.latest_delivery_classification` before merge without mutating the
definition snapshot.

An operator override is permitted only while the latest classification is
`ambiguous`; clear proposal, implementation, or mixed classifications require
classifier routing and reject an override. The override is bound to the
inspected `base_sha`, `head_sha`, `ruleset_version`, digest algorithm, and digest
of the canonical latest classification. Execution reclassifies and compares all
bindings before honoring it. A base/head update, ruleset change, or digest
mismatch discards the override: a newly clear classification uses classifier
routing, while a still-ambiguous result returns to blocked routing.
Before clearing the active override, execution atomically appends the complete
override, invalidation timestamp, mismatch reason, observed binding evidence,
and replacement classification to `operator_override_history`. Classifier
routing therefore resumes without erasing the safety-sensitive operator audit.

The digest algorithm identifier is `pr-delivery-v1+jcs-sha256`. The shared
helper schema-validates, projects every classification field except
`classified_at`, sorts all set-valued path/warning/reason/hint/conflict arrays
by strict UTF-8 byte order, performs no Unicode normalization, rejects invalid
Unicode scalar values, serializes with RFC 8785 JSON Canonicalization Scheme,
and returns lowercase SHA-256 hex. Disposition and execution use this one
helper; a checked-in Unicode-aware golden fixture fixes the expected hash.

The coordinator's worktree projection uses the shared schema interpreter.
`/worktrees/active` includes only unexpired activity leases and exposes owner,
phase, heartbeat, and expiry. Sync-point blockers include those leases plus
unfinished setup reservations labeled as indeterminate provisioning; a
reservation is never rendered as an active owner. Retained-idle worktrees
remain visible in inventory/status projections with `retained=true` and
`activity_state=idle`, but are absent from the active blocker list. UI labels
and tests stop deriving activity from `pinned`.

Implementation has one explicit preflight package and two enforced downstream
gates. `wp-baseline-preflight` resolves each named prerequisite PR through
authoritative repository metadata, requires merged state, records merge commit
and base ref in schema-valid evidence, fetches that configured ref, and proves
the merge commit is ancestral to both the fetched base and feature HEAD. The
preflight root package runs in the managed shared feature worktree, so its
verified commit is feature HEAD rather than an isolated result awaiting final
integration. The scheduler reads the feature-HEAD completion barrier from the
exact `contracts/prerequisites.yaml#execution_gate` declaration, re-verifies
that evidence under the branch lock, and records the resulting HEAD as the minimum base
for dependents, and only then marks the package complete or creates their
worktrees. Only after that barrier may `wp-pr-delivery` extend
`add-merge-plan-orchestration` or `wp-phase-lifecycle` wrap
`validate-feature-findings-gate`. A caller-supplied or unrelated ancestor SHA is
never sufficient, and dependent worktrees are not created before preflight.
For this bootstrap run, the shared root package first lands the generic barrier
implementation, reloads or reinstantiates the scheduler from that feature
commit, then produces and verifies the live evidence before releasing
dependents.

### D16 — Canonical skills are edited first and mirrors are generated

Lifecycle code and workflow text are changed only under canonical `skills/`
and shared libraries. `skills/install.sh` regenerates `.agents/skills/`,
`.claude/skills/`, and other supported runtime copies. Drift checks are part of
validation; runtime copies are not hand-patched to make tests pass.
The same source-first rule applies to the autopilot convergence-state install
asset and its generated root-schema mirror; real saved and migrated LoopState
instances validate against both byte-identical copies.

Operator documentation covers lease inspection, owner/session release,
retention, expired-state recovery, classifier evidence, and ambiguous PR
resolution. Command output has a stable machine-readable mode so hooks and
coordinator consumers do not scrape prose.

### D17 — Roll out through dual-read/single-write, then remove legacy writes

Rollout has three compatibility steps:

1. Ship the shared dual reader, inspection report, v2 writer, lease commands,
   and updated local/coordinator projections while retaining `pin`/`unpin`
   aliases.
2. Move every entry in the checked-in mutating-skill inventory to its declared
   standalone, continuous-parent, child-owner, sync-point, registry-reader, or
   inherited-only contract. This includes all phase launchers, roadmap and
   quick-task writers, prototype variants, autopilot/autopilot-roadmap,
   cleanup/update-specs/project-context-refresh/expedite consumers, hooks, and
   merge routing. Prototype retention stays independent from its writer lease.
3. After installed-mirror and consumer compatibility is established, stop
   ordinary workflows from writing v1 heartbeat/pin semantics. Alias removal is
   a later deprecation, not part of this change.

Rollback must keep the new dual reader and v2 writer in place; a pre-v2 reader
cannot safely interpret the disjoint registry shape. Higher-level phase and
merge routing may be disabled independently, while read-only tooling can render
a v1 compatibility view without replacing the v2 source. Disabling new workflow
routing makes an uncertain delivery stage `ambiguous`, never `implementation`.
No rollback command deletes a dirty worktree, steals a live lease, or archives a
proposal-only change.

## State transitions

For a registry entry, the relevant transitions are:

```text
fresh setup --reserve(setup-id, generation, target, exact triple)--> provisioning
provisioning --checkout/evidence/publish--> active(exact triple) | quarantine
provisioning --expires/reconcile--> removed(no side effects) | quarantine(no lease)
pre-existing idle --assess/adopt--> active(new exact triple) | quarantine
active(same triple) --renew/retry--> active(same triple, new expires_at)
active(different controller) --resume--> reject live | rotate after stale+safe
active(other owner) --acquire--> conflict (no mutation)
active --time passes expiry--> expired/idle (files untouched)
active(same triple) --abandon/release--> quarantine(no lease)
idle --retain/unretain--> idle + GC policy change
idle/quarantine --recovery teardown--> removed | explicit audited force teardown
```

For standalone workflows, `push/PR durable` precedes teardown. For
continuous autopilot, every nested phase returns to the same active controller;
an external durable checkpoint precedes teardown. A removed checkout is
recreated only from the recorded durable ref before a new controller resumes.

## Verification strategy

Tests use temporary repositories, injected clocks, and concurrent processes.
The minimum matrix covers:

- v1 pinned/unpinned migration reports and canonical v2 writes;
- reservation fault injection and concurrent setup/acquire/renew/release without
  lost entries or orphan adoption;
- same-owner idempotency, wrong-owner conflicts, expiry, session release, and
  retained-idle GC behavior;
- corrupt-registry preservation and sync-point indeterminate handling;
- direct proposal/implementation/iteration/validation success and failure
  finalizers in every execution tier;
- one stable autopilot owner across dispatch, resume, exception, ESCALATE,
  SUBMIT_PR, and DONE, including envelope CAS/fsync and exact-tip recreation;
- every delivery-stage rule, missing/matching/conflicting markers, legacy PRs,
  proposal-branch change-id parsing, and author-evidence conflicts;
- Claude proposal versus implementation prompt contents, Codex/Grok/Pi
  attempts, unavailable-vendor reporting, and quorum loss;
- proposal merge skip versus implementation/mixed archival, once-per-pass
  convergence, merge-plan persistence, and coordinator/UI projections;
- authoritative prerequisite preflight, complete lifecycle-consumer inventory,
  changed-Python Ruff routing, convergence-schema parity, and runtime mirror drift.

End-to-end fixtures assert both positive effects and absences: a proposal merge
leaves the active change on `main`, expiry leaves dirty files untouched,
retention does not create a blocker, and autopilot has no live lease before the
human merge question is rendered.

## Risks and mitigations

- **Concurrent registry corruption or lost updates.** One shared lock and
  atomic transaction implementation replaces independent load/save sequences;
  multiprocessing tests exercise contention.
- **A healthy phase loses its lease during a long tool call.** A five-minute
  executable renewer plus transition renewals provides margin inside the
  30-minute TTL; renewal failure is surfaced before further mutation.
- **An expired writer is still physically running.** Expiry unblocks dead
  sessions but cannot prove process death. Expired takeover runs a locked
  clean/durable/process-evidence assessment and quarantines unsafe or
  indeterminate state; every permitted replacement gets a new lease id, and
  mutation-boundary assertions fence the old id before its next mutation,
  integration, commit, or push.
- **Session hooks release the wrong run or expose half-finished state.** Release
  matches a non-empty stored session id and remains non-destructive; preserved
  checkouts are quarantined before ownership is cleared, while explicit
  workflow finalization uses the exact ownership triple plus entry generation
  for teardown-or-quarantine.
- **Classifier mistakes archive planning work.** Changed files and base state
  are primary, marker disagreement and incomplete evidence become ambiguous,
  and cleanup consumes the classified stage rather than OpenSpec origin.
- **Author spoofing causes same-vendor review.** Exact configured identities
  outrank body/branch metadata, conflicts become unknown, and evidence remains
  visible to the operator. The classifier is routing provenance, not an
  authentication mechanism.
- **Overlapping changes fork contracts.** Merge-plan fields are added to the
  existing schema and validation lifecycle wraps the existing ephemeral mode;
  package ordering and contract tests prevent parallel definitions.
- **Old consumers still treat retention as activity.** Dual-read projection
  tests cover `active_agents`, coordinator sync points, worktree inventory, and
  UI payloads before phase workflows start emitting v2 exclusively.
- **Teardown loses recoverable work.** Teardown-or-quarantine is one ordered
  transaction: finalization checks dirtiness and remote reachability while the
  live lease and registry lock still fence acquisition. Unsafe state enters
  explicit recovery quarantine as ownership is cleared, and expiry never calls
  teardown.
