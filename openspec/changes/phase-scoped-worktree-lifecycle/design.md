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
stdlib-only shared registry module will own parsing, v1 normalization, lease
state calculation, and locked read-modify-write transactions. `worktree.py`,
`active_agents.py`, coordinator sync-point checks, and worktree projections will
consume this interpreter instead of independently restating `pinned` and
heartbeat rules.

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
      "retained": false,
      "retention_reason": null,
      "activity_lease": {
        "owner": "autopilot:01K2RUN",
        "session_id": "session-123",
        "phase": "IMPLEMENT",
        "mode": "continuous",
        "reason": "autopilot-run",
        "acquired_at": "2026-08-15T12:00:00Z",
        "last_heartbeat": "2026-08-15T12:05:00Z",
        "expires_at": "2026-08-15T12:35:00Z"
      }
    }
  ]
}
```

`owner` is an opaque, namespaced identity; `session_id` is independently
matchable by session-end cleanup. A worktree has at most one current lease, so
ownership arbitration remains simple and auditable. `retained=true` prevents
ordinary GC but never makes an entry active. `activity_lease` may remain present
after expiry for inspection, but an expired lease is not active and may be
replaced by a later acquire. Explicit release sets it to `null`; GC may compact
expired lease details when it otherwise updates an entry.

The registry is state, not an event log. Operator-visible command results and
coordinator status events carry acquire/renew/release/conflict outcomes; durable
workflow history remains in the owning workflow's state and handoff artifacts.

### D3 — Every registry mutation is a locked, atomic transaction

All setup, teardown, retain, lease, migration, and GC mutations take an advisory
exclusive lock on `.git-worktrees/.registry.lock`, reload under that lock,
validate and normalize, apply exactly one transaction, write a uniquely named
temporary file, flush it, and atomically replace the registry. Read paths that
make a safety decision take a shared lock. Lock acquisition has a bounded
timeout and fails visibly; it never falls back to an unlocked write.

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
it in `finally`. Long-running orchestrators also renew at write-capable phase
transitions, before dispatch, after dispatch, and on resume. Renewal sets
`last_heartbeat=now` and `expires_at=now+ttl`; it does not extend from a possibly
stale prior expiry. The five-minute cadence leaves six missed-renewal windows
before a healthy lease expires.

A live lease blocks sync-point writers and GC regardless of retention. Expiry
only changes the activity calculation: it never tears down a checkout, drops a
branch, resets files, or clears retention.

### D5 — Acquire, renew, release, and teardown are owner checked

The lifecycle CLI exposes owner-scoped `lease-acquire`, `lease-renew`,
`lease-release`, `lease-status`, `release-owner`, and `release-session`
operations in addition to setup/teardown and retention commands.

- Acquiring an unleased or expired entry succeeds.
- Reacquiring with the same owner is idempotent, preserves `acquired_at`, and
  may update phase/reason before renewing the expiry.
- Acquiring an entry held by a different live owner fails with both owner,
  phase, and expiry evidence; it never steals the lease.
- Renewing or releasing with the wrong owner is a non-mutating conflict.
- Releasing an already absent lease for the same requested owner is idempotent.
- `release-session` clears only leases whose stored `session_id` exactly
  matches; an empty or missing session id is not a wildcard.
- Normal teardown refuses to remove a worktree with another owner's live lease.
  Expired leases do not authorize deletion, and dirty/unmerged safety checks
  still apply.

Owner strings use stable namespaces: `phase:<phase>:<run-id>` for a direct
phase, `autopilot:<run-id>` for continuous mode, and existing package/agent
identities for child worktrees. Security does not depend on the string format;
the full string equality check is the ownership boundary.

### D6 — V1 reads are compatible; v2 migration changes meaning deliberately

Readers accept both the existing top-level `version: 1` registry and canonical
`schema_version: 2`. V1 entries normalize as follows:

- `pinned=true` becomes `retained=true` with reason `legacy-pin`.
- A parseable legacy `last_heartbeat` within the existing one-hour activity
  window becomes a synthetic `legacy:<change-id>:<agent-id-or-parent>` lease
  expiring at `last_heartbeat + 1 hour`.
- A stale or invalid heartbeat does not create live activity.
- Branch, path, agent, and creation fields are preserved byte-for-value where
  the v2 schema permits them.

Read-only `inspect --migration-report` shows the exact normalization and any
invalid entries without writing. The first successful mutating transaction
prints the same migration summary before atomically writing canonical v2; reads
alone never rewrite state. Unknown top-level or entry fields are preserved in a
compatibility extension map during conversion rather than silently discarded.

`pin` and `unpin` remain migration aliases for setting and clearing retention.
They do not acquire, renew, or release activity. The legacy `heartbeat` command
continues to support v1 entries during the transition, but a v2 lease can only
be renewed with its owner identity. Help and status output label these
compatibility semantics explicitly.

### D7 — Lifecycle context is explicit and reports who must release

Write-capable skills receive a lifecycle context with `mode`, `owner`,
`session_id`, worktree identity, and `release_responsibility`. The executable
setup/acquire helper returns `acquired_here=true|false`; only a caller that
acquired a standalone lease releases it. A nested caller presented with a live,
same-owner continuous lease may update its phase and renew it, but receives
`acquired_here=false` and must not release or tear down the parent's worktree.

The context is passed as explicit command arguments/environment for subprocesses
and as dispatch context for agents. Ambient process state is not the sole source
of truth: continuous orchestrators also persist it in their resumable state.
Missing or contradictory context fails before mutation rather than guessing
standalone versus continuous ownership.

### D8 — Standalone phases push, release, and dispose independently

Direct `plan-feature` uses branch `openspec/<change-id>--proposal`, acquires a
PLAN lease, validates all plan artifacts, commits and pushes them, opens a PR
whose body contains `OpenSpec-Delivery: proposal`, and then releases in
`finally`. Its local worktree is torn down after the remote branch and PR are
durable. If push or PR creation fails, it still releases activity and performs
only safe teardown; dirty or otherwise unsafe leftovers are reported as idle
recovery state rather than force-deleted.

Direct `iterate-on-plan` recreates or adopts the proposal branch/worktree and
owns only that invocation's lease. Direct `implement-feature`,
`iterate-on-implementation`, and `validate-feature` similarly recreate or adopt
the implementation branch `openspec/<change-id>` from the reviewed proposal on
`main` or its remote implementation branch, own a phase lease, push durable
output, and finalize independently. This rule applies to sequential,
local-parallel, and coordinated tiers. Package worktrees have their own leases
and are released/removed after integration or on failure.

Every phase uses the same executable `try/finally` lifecycle wrapper. The
Markdown skill specifies what runs inside the wrapper; it is not itself the
only guarantee that finalization occurs. Release is unconditional. Teardown is
idempotent and conditional on the existing clean/merged safety checks.

### D9 — Autopilot persists and owns one continuous lease

Autopilot creates `autopilot:<run-id>` once before PLAN, stores the owner,
session, mode, worktree identity, and lease phase in `loop-state.json`, and
passes that context into PLAN, PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT,
IMPL_ITERATE, IMPL_REVIEW, VALIDATE, optional VAL_REVIEW, and SUBMIT_PR.
Nested skills and review/fix callbacks renew the same lease; they do not create
or release phase owners.

On resume, autopilot reloads the persisted owner before dispatching. It renews
if the matching lease is live, reacquires if that lease expired and no other
owner has acquired the worktree, and escalates on a different live owner or a
worktree/branch identity mismatch. Resume never steals ownership based only on
the change id.

After SUBMIT_PR has persisted the PR/evidence checkpoint, autopilot stops the
renewer, owner-checks release, safely tears down, records final lifecycle state,
and only then enters DONE and presents the human merge gate. On exception,
failed outcome, or ESCALATE, its outermost `finally` first flushes the latest
loop state and handoff, then attempts release and safe teardown. A checkpoint
write failure is reported as a hard recovery error, but does not justify an
indefinite blocker: release is still attempted and bounded expiry remains the
last backstop.

### D10 — Session end performs local, best-effort owner-scoped release first

The session-end hook resolves the repository from the hook project directory,
reads the terminating `SESSION_ID`, and invokes the stdlib lifecycle helper's
`release-session` operation before optional coordinator handoff/status calls.
This path works with no coordinator URL or network. It never uses a blank id,
never releases another session's lease, and never deletes a worktree.

Hook failures are logged but cannot block process shutdown. The lease TTL is
still authoritative when a process is killed too abruptly for hooks. Explicit
workflow finalization remains the primary mechanism; session release is a
backstop, not a substitute for it.

### D11 — Delivery stage is a pure classifier over diff, base state, and marker

Origin classification remains in the portable GitHub classifier. A separate
pure delivery classifier consumes the resolved change id, the complete changed
file set, the PR base/head OpenSpec state, and the optional PR-body trailer
`OpenSpec-Delivery: proposal|implementation|mixed`. It returns `stage`, a
structured evidence list, marker status, and warnings.

Planning files are files under `openspec/changes/<change-id>/` that define the
proposal, design, delta specs, tasks, contracts, work packages, or workflow
metadata. Any substantive changed path outside that planning set is
implementation evidence. The deterministic ladder is:

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

Discovery records four independent fields: `origin`, `change_id`, raw
`github_author`, and `author_vendor`. `author_vendor` is computed by one shared
classifier using, in order, configured exact GitHub identity mappings and a
standard `OpenSpec-Author-Vendor` trailer written by agent workflows. Known
branch prefixes and generator trailers may corroborate but cannot override a
conflicting exact identity. Conflicting evidence yields `unknown` plus its
evidence; it never silently attributes work to a convenient reviewer vendor.

The allowed vendor values are the configured dispatch vendors plus `human` and
`unknown`; they are not folded into OpenSpec origin. Existing PRs without the
new trailer remain classifiable when their GitHub identity is known. Agent
workflow PR creation writes both delivery and author-vendor trailers so a PR
opened through a human GitHub account still preserves the producing agent.

### D13 — Claude-authored OpenSpec PRs require independent Codex/Grok/Pi review

For `origin=openspec` and `author_vendor=claude`, review dispatch attempts each
configured Codex, Grok, and Pi adapter. It never substitutes Claude for an
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

The `add-merge-plan-orchestration` node definition is extended in place with
`change_id`, `delivery_stage`, `delivery_evidence`, `delivery_marker_status`,
`github_author`, and `author_vendor`. `ambiguous` adds a human-decision gate and
sets `auto_executable=false`. File-tier and coordinator-tier plans persist the
same fields; coordinator work-queue metadata must not drop them. Execution
reclassifies live state and writes any changed evidence back before merge.

The coordinator's worktree projection uses the shared schema interpreter.
Sync-point blockers and `/worktrees/active` include only unexpired activity
leases and expose owner, phase, heartbeat, and expiry. Retained-idle worktrees
remain visible in inventory/status projections with `retained=true` and
`activity_state=idle`, but are absent from the active blocker list. UI labels
and tests stop deriving activity from `pinned`.

This change serializes its merge-plan schema edits with
`add-merge-plan-orchestration`; it does not fork the schema or add a sidecar.
It likewise reuses the validation worktree selected by
`validate-feature-findings-gate` and wraps that run in the phase lease contract.

### D16 — Canonical skills are edited first and mirrors are generated

Lifecycle code and workflow text are changed only under canonical `skills/`
and shared libraries. `skills/install.sh` regenerates `.agents/skills/`,
`.claude/skills/`, and other supported runtime copies. Drift checks are part of
validation; runtime copies are not hand-patched to make tests pass.

Operator documentation covers lease inspection, owner/session release,
retention, expired-state recovery, classifier evidence, and ambiguous PR
resolution. Command output has a stable machine-readable mode so hooks and
coordinator consumers do not scrape prose.

### D17 — Roll out through dual-read/single-write, then remove legacy writes

Rollout has three compatibility steps:

1. Ship the shared dual reader, inspection report, v2 writer, lease commands,
   and updated local/coordinator projections while retaining `pin`/`unpin`
   aliases.
2. Move phase workflows, autopilot, hooks, PR creation/classification, merge
   routing, and merge-plan fields to the new contract; exercise direct,
   continuous, crash, legacy, and proposal-merge scenarios.
3. After installed-mirror and consumer compatibility is established, stop
   ordinary workflows from writing v1 heartbeat/pin semantics. Alias removal is
   a later deprecation, not part of this change.

Rollback keeps the dual reader and never down-migrates destructively. Older
readers may ignore v2 extension fields, while rollback tooling can render a v1
compatibility view without replacing the v2 source. Disabling new workflow
routing makes an uncertain delivery stage `ambiguous`, never
`implementation`. No rollback command deletes a dirty worktree, steals a live
lease, or archives a proposal-only change.

## State transitions

For a registry entry, the relevant transitions are:

```text
idle --acquire(owner)--> active(owner, expires_at)
active(same owner) --renew/reacquire--> active(same owner, new expires_at)
active(other owner) --acquire--> conflict (no mutation)
active --time passes expiry--> expired/idle (files untouched)
active(same owner) --release--> idle
idle --retain/unretain--> idle + GC policy change
```

For standalone workflows, `push/PR durable` precedes release and teardown. For
continuous autopilot, every nested phase returns to the same active owner;
SUBMIT_PR checkpoint precedes release, and release precedes DONE.

## Verification strategy

Tests use temporary repositories, injected clocks, and concurrent processes.
The minimum matrix covers:

- v1 pinned/unpinned migration reports and canonical v2 writes;
- concurrent setup/acquire/renew/release without lost entries;
- same-owner idempotency, wrong-owner conflicts, expiry, session release, and
  retained-idle GC behavior;
- corrupt-registry preservation and sync-point indeterminate handling;
- direct proposal/implementation/iteration/validation success and failure
  finalizers in every execution tier;
- one stable autopilot owner across dispatch, resume, exception, ESCALATE,
  SUBMIT_PR, and DONE;
- every delivery-stage rule, missing/matching/conflicting markers, legacy PRs,
  proposal-branch change-id parsing, and author-evidence conflicts;
- Claude proposal versus implementation prompt contents, Codex/Grok/Pi
  attempts, unavailable-vendor reporting, and quorum loss;
- proposal merge skip versus implementation/mixed archival, once-per-pass
  convergence, merge-plan persistence, and coordinator/UI projections;
- canonical-to-runtime mirror drift.

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
  sessions but cannot prove process death. A writer that discovers lease loss
  must stop before its next mutation/push; acquire conflicts and sync-point git
  freshness checks remain mandatory.
- **Session hooks release the wrong run.** Release matches a non-empty stored
  session id and remains non-destructive; explicit workflow release uses the
  stronger full owner identity.
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
- **Teardown loses recoverable work.** Release and teardown are separate;
  teardown retains existing dirty/unmerged refusal, and expiry never calls it.
