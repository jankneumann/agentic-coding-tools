# Design — integrate-main-context-convergence (ri-11)

Every decision below was taken against measured state at `1cf51386`. Where a
decision resolves a tension between the roadmap's wording and a contract that
ri-07 already shipped, that is said explicitly rather than papered over.

---

## D1. The convergence hook fires once per invocation pass, as Step 11.6

**Decision.** Add a new `merge-pull-requests` step **11.6 — Main Context
Convergence**, immediately after Step 11.5 (post-merge OpenSpec cleanup approval,
`SKILL.md:536-578`) and immediately before Step 12 (Summary). It runs once, after
the per-PR loop has fully drained, and only when at least one PR was merged during
the pass.

**Rejected: the existing per-merge post-merge pipeline**
(`scripts/post_merge_pipeline.py:21-94`, invoked per merge). Its three hooks are
deliberately per-PR and failure-isolated. Putting convergence there produces N
convergences, N commits, and N index requests for N merged PRs — a direct
violation of roadmap acceptance outcome 2 and 4.

**Rejected: inside the per-PR merge loop, right after `git pull origin main`**
(`SKILL.md:472-477`). Same N-times problem, and it would run *before* the
post-merge cleanup approval gate, so an OpenSpec change would be converged against
an un-archived tree.

**Rejected: a separate operator-invoked `/project-context-refresh` afterwards.**
Not enforceable, and it contradicts the roadmap's premise that
`merge-pull-requests` is the authoritative main-synchronization point. Convergence
that depends on remembering to run it is exactly the failure mode that let
`docs/decisions/` drift.

**Consequence.** Step 11.6 must handle the multi-PR case in one shot, which is
what D2 and D8 specify.

---

## D2. OpenSpec cleanup runs first, for every merged OpenSpec change, before any refresh

**Decision.** Step 11.6 is a fixed three-phase sequence:

1. For each OpenSpec change merged during this pass, run
   `/cleanup-feature <change-id> --post-merge --pr <n>` (merge-driven mode, D3),
   in the operator-approved order Step 11.5 already establishes.
2. Run **one** deterministic refresh over the resulting tree.
3. Commit, push, enqueue the index.

**Rationale.** `cleanup-feature` owns task migration, `openspec archive`, the
spec-delta merge into `openspec/specs/`, and `make decisions`. Those mutate the
exact inputs the deterministic producers read: `openspec.projection` reads
`openspec/changes/*/specs/**` and `openspec/specs/*` and `decisions.timeline`
reads `openspec/changes/**/session-log.md` (measured via `cli.py list`). A refresh
that ran first would be stale the instant the archive moved.

**Rejected: convergence per change, interleaved with each cleanup.** N
convergences again, and each intermediate tree is a state main never actually had.

**Rejected: moving convergence into `cleanup-feature`.** Non-OpenSpec merges
(dependabot, sentinel, manual) would then never converge, and acceptance outcome 2
requires both paths to converge. It would also break the ownership split the
roadmap rationale states outright.

**Rejected: teaching `merge-pull-requests` to archive directly.** Duplicates
archive logic in two skills; the first divergence between them is silent spec
corruption.

---

## D3. Merge-driven cleanup stages its output; the sync point owns the single commit

**Decision.** `cleanup-feature --post-merge` gains a merge-driven mode (invoked
with an explicit flag, e.g. `--defer-commit`) in which it:

- operates directly in the sync-point checkout on `main` rather than setting up
  its own `--cleanup` worktree (`SKILL.md:81-100`);
- performs archive, spec-delta merge, `make decisions`, and `openspec validate
  --strict` exactly as today;
- **stages** its output with `git add` and **returns**, committing nothing and
  pushing nothing.

The sync point then produces one commit (D9) containing every change's staged
cleanup output plus the refresh output.

**Rejected: cleanup commits and pushes per change, convergence appends a second
commit.** Produces N+1 commits for N changes; acceptance outcome 3 asks for one
follow-up convergence commit.

**Rejected: cleanup commits locally without pushing; convergence amends.**
Amending a commit that another process may already have observed is a footgun,
and `git commit --amend` after a partial failure silently rewrites cleanup work
that succeeded.

**Failure containment.** If phase 1 fails partway (change 2 of 3), the staged
output of changes 1-2 is committed as a *cleanup-only* convergence commit with the
refresh recorded as not-run, and the pass stops. Nothing staged is ever discarded;
the operator resumes from a clean, pushed state. This mirrors the existing rule at
`SKILL.md:578` ("stop the cleanup pass, preserve the error output").

**Assumption flagged.** The current skill text says post-merge cleanup should
"Archive the OpenSpec change, sync specs, validate, commit, and push"
(`SKILL.md:572`) without naming the branch it pushes to, while Step 1 sets up a
scratch `--cleanup` worktree. That is genuinely ambiguous today. This design reads
the intent as "land the archive on main" and makes the sync point the thing that
does it. If the intent was a separate archive PR, D3 is the decision to revisit.

---

## D4. The durable operation identity is keyed on the merged main SHA

**Decision.** The convergence operation is the ri-06 record derived by
`derive_operation_id(repository_id, merged_main_sha)`
(`skills/project-context-runtime/scripts/models.py:191-203`), where
`merged_main_sha` is `main`'s HEAD **after every merge in the pass and after phase
1 staging is committed** — i.e. the exact revision the deterministic producers
read. `repository_id` follows `PROJECT_CONTEXT_REPO_ID` or the repo directory name,
identical to ri-07's `resolve_repository_identity` (`orchestrator.py:128-161`).

Idempotence rests on two independent checks, because each has a hole the other
covers:

| Check | Where it lives | Hole |
|---|---|---|
| terminal ri-06 operation record for the SHA | `.git/` common dir (`store.py:76-90`) | lost on a fresh clone |
| `Context-Refresh-Operation: pcr-<id>` commit trailer on main | git history | absent until the commit lands |

A retry consults both. A terminal record *or* a discoverable trailer means the
convergence for that SHA already happened; the pass reports the existing identity
and does nothing.

**Rejected: keying on the set of merged PR numbers.** Not stable — a retry after a
partial pass merges a different set and would mint a new identity for the same
tree.

**Rejected: a per-invocation UUID.** Defeats resume entirely; every retry is a new
operation, which is exactly the duplicate-commit/duplicate-index failure acceptance
outcome 4 forbids.

**Rejected: keying on the post-convergence SHA.** Not knowable before the work is
done. It is, however, the right key for the *index* (D7).

---

## D5. Sync-point authorization is granted explicitly, and locking is three-layered

**Decision.** Add `--sync-point` to the refresh CLI's mutating path, threading
`sync_point=True` into `require_mutation_allowed` (`cli.py:109-128`). The
`approved_sync_point` branch already exists at `checkout_policy.py:109-121` and is
currently unreachable — this change is the caller it was written for.

Because that branch's own message says *"Caller must still enforce clean-tree and
active-agent guards"*, Step 11.6 enforces three layers before writing:

1. **Active-agent guard** — the existing `shared/active_agents.py` check
   (`SKILL.md:39-50`) already runs at skill start; Step 11.6 re-runs it, because
   an agent may have started a worktree during the merge loop.
2. **Coordinator lock** — when `CAN_LOCK`, `acquire_lock` on the key
   `sync-point:main-convergence` for the duration of Step 11.6. Coordinator
   unavailability degrades to layers 1 and 3 with a recorded warning; it never
   blocks the pass.
3. **Git-level compare-and-swap** — immediately before `git push`, re-verify that
   `origin/main` still equals the SHA the operation is keyed on. On rejection:
   **never** force. Abort, leave the operation resumable, report.

**Rejected: coordinator lock only.** This repository runs solo without a
coordinator often enough that a coordinator-only guard would be absent exactly when
it matters. Layer 3 is the only one that cannot be bypassed by a process that
never asked.

**Rejected: `git push --force-with-lease`.** A lease that succeeds still rewrites
another writer's commit. At a sync point, losing the race is information, not an
obstacle.

---

## D6. A refresh failure never un-merges and never blocks the merge

**Decision.** Merges are terminal. Step 11.6 cannot revert, close, or re-open a PR
under any convergence outcome. Outcomes map as follows:

| Refresh outcome | Exit | Convergence commit | Pass result |
|---|---|---|---|
| succeeded | 0 | yes | ok |
| degraded — drift regenerated, or optional owner absent | 2 | yes, carrying whatever deterministic output was produced | ok, with a recorded warning |
| failed — a producer raised | 1 | cleanup-only commit; refresh artifacts omitted | **warning**, operation left resumable |
| apparatus could not run (lock, dirty tree, push race) | — | none | **warning**, nothing staged is lost |

In every row, Step 12's summary still runs and still reports the merges. A
convergence problem is reported *alongside* the merge result, never in place of it.

**Rejected: reverting the merge on convergence failure.** Trades reviewed,
CI-green product code for a derived-artifact problem. The auto-rollback hook that
already exists (`post_merge_pipeline.py:76-92`) is scoped to *CI failures on the
merged code*, which is a different and legitimate trigger.

**Rejected: blocking Step 12 / the merge log on convergence failure.** The merge
log is the decision record (`SKILL.md:610-665`); suppressing it because a derived
artifact failed loses the more valuable of the two.

**Rejected: exit 2 aborting the commit.** `degraded` is the *normal* outcome
whenever the semantic index is deferred (D7) or an optional owner is absent.
Treating it as failure would mean convergence never commits on a machine without
the semantic stack.

---

## D7. Semantic indexing is enqueued for the final pushed SHA, never awaited

**Decision.** Add `--defer-semantic-index` to the refresh mutating path. In that
mode `orchestrator.generate` skips the inline attempt at `orchestrator.py:699-708`
and records a `SemanticIndexReference` with `status=pending` and the canonical
`exact-search` fallback. `SemanticIndexStatus.PENDING` already exists
(`models.py:108`), and a non-succeeded reference is valid as long as it carries a
fallback (`models.py:473-477`), so this needs no schema change.

After the convergence commit is pushed, Step 11.6 enqueues **exactly one**
indexing request for the **final pushed SHA** — a different revision from the
operation key (D4), and therefore a separate ri-06 operation of its own. The
handoff reports its status; the pass does not wait for it.

**Rejected: running the index inline at the merged SHA.** It would index a SHA that
is never main's final state, and the convergence commit would immediately stale it —
so a correct system would then index a second time. That is the duplicate indexing
acceptance outcome 4 forbids.

**Rejected: awaiting the index.** `semantic_adapter.py:86` defaults to a
1800-second ceiling for one run. Blocking a sync point on a 30-minute rebuild makes
the semantic index a hard dependency of merging, which the roadmap explicitly
rules out.

**Rejected: recording nothing.** `decide_outcome` treats `semantic_index=None` as
"not part of this run" (`orchestrator.py:429-449`), which would report a clean
`succeeded` while silently making no currency claim. Acceptance outcome 5 requires
a reported semantic status; `pending` with a fallback is the honest value.

---

## D8. "Exactly one convergence per merged main state" is defined per pass, not per PR

**Decision.** One `merge-pull-requests` invocation that merges *k ≥ 1* PRs produces
exactly one convergence for the single main state those merges produced. Concretely:

- k = 0 merged PRs → no convergence, no commit, no index request. The pass is a
  read of main, not a write.
- k ≥ 1 via direct merge → one convergence at the final main HEAD.
- k ≥ 1 landed as one batch by the GitHub merge queue or a coordinator train
  (`SKILL.md:52-62`) → still one main state, therefore still one convergence.
- A PR merged by *someone else* between the pass's merges → detected by the D5
  layer-3 compare-and-swap, which aborts rather than converging a state this pass
  did not produce.

**Rejected: "one convergence per merged PR".** Reads acceptance outcome 2's "each
run exactly one convergence operation" as per-PR. The sentence says *"for the
resulting main state"*, and k merges produce one resulting state.

**Rejected: converging on a timer / in the background watcher**
(`merge_watcher.py`). The watcher ticks without an operator present; a background
process that commits and pushes to main is a different and larger authorization
question than this change is scoped to answer.

---

## D9. The gitignored manifest stays gitignored; a tracked convergence record is what lands

**Decision.** `.git-context/context-refresh-manifest.json`
(`orchestrator.py:70`, `.gitignore:277`) remains untracked. What the convergence
commit carries instead is a tracked, append-only **convergence record** at
`docs/merge-logs/context-convergence.jsonl`, one JSON object per line, validated
against a new `context-convergence-record.schema.json`. Each record carries the
operation id, the merged main SHA, the convergence commit SHA, the manifest path
and its `sha256`, per-producer outcome and owner, and the semantic-index enqueue
reference.

**Why this reading of acceptance outcome 3.** The roadmap says "…plus the manifest
are committed". Tracking `.git-context/` itself would break two things ri-07
deliberately built: D6's guarantee that a repeat refresh at the same revision
produces *no repository diff*, and the per-worktree, freely-cleanable nature of
that directory (`orchestrator.py:548-561` re-checks the digest precisely because
the file may be absent locally). The durable, reviewable, git-native form of "the
manifest is committed" is a record that pins the manifest by digest. That is what
lands.

**Rejected: tracking `.git-context/` directly.** Reintroduces the exact repository
diff ri-07 D6 exists to prevent, and makes a per-worktree cache a shared tracked
file.

**Rejected: one JSON file per SHA under `docs/`.** Unbounded file growth in a
directory the `documentation.inventory` producer reads.

**Rejected: recording only in the human merge log.** Not machine-checkable, so the
idempotence check in D4 would have nothing to read. JSONL follows the existing
`docs/merge-logs/metrics.jsonl` convention (`SKILL.md:68`).

---

## D10. Convergence uses the staged, provenance-writing architecture target

**Decision.** The convergence sequence invokes `make architecture-refresh`
(`Makefile:147`), not `make architecture` (`Makefile:138`), and
`cleanup-feature`'s post-merge step 4 switches to the same target.

**Measured basis.** `provenance.write_provenance` is called only from `run_staged`
(`skills/refresh-architecture/scripts/run_architecture.py:186`, inside lines
140-196). ri-10's architecture producer compares *committed* provenance and routes
missing or malformed provenance to drift rather than `not-configured`
(`orchestrator.py:212-334`, and the docstring says so explicitly). So the current
`make architecture` path can regenerate every artifact and still leave the ri-10
gate red.

`run_staged` requires a committed HEAD (`run_architecture.py:145-152`). At the sync
point on main after merges, that precondition holds.

**Rejected: leaving `make architecture` in place and adding provenance separately.**
Two writers for one artifact set; the first divergence is a provenance document
that does not describe the artifacts beside it.

---

## D11. Non-OpenSpec merges converge too, through the same single operation

**Decision.** The phase-1 cleanup loop is skipped when no OpenSpec change was
merged, but phases 2 and 3 run identically. A pass that merged only a dependabot
bump still converges.

**Rationale.** A dependency bump edits `**/*.py` lockfiles and `**/*.md`, which the
ri-08 rule table maps onto `semantic_code` and `documentation`
(`openspec/schemas/context-impact-rules.yaml:62-91`). Acceptance outcome 2 names
both paths.

**Rejected: converging only for OpenSpec merges.** Leaves the drift gate red after
a dependency-only pass, with no step in the workflow that would ever fix it.

---

## D12. Dry-run converges nothing and reports the identity it would have used

**Decision.** Under `--dry-run` (`SKILL.md:667-692`), Step 11.6 performs no merge,
so there is no merged SHA and no convergence. It reports: the operation id it would
derive from the current `main` HEAD, whether a terminal record or commit trailer
already exists for it, and a read-only drift assessment from `make
context-drift-gate` (`Makefile:471`) — which writes nothing by construction.

**Rejected: running the real refresh in dry-run "to show what would change".** The
mutating path writes producer outputs into the working tree. A dry run that dirties
main is not a dry run.
