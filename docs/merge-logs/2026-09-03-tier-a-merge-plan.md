# Tier A Merge Plan — 2026-09-03

Merge order and rationale for the five mergeable open PRs, derived from the
`/merge-pull-requests` dry-run analysis pass at `main@4e2eda94`.

Machine-readable companion: `2026-09-03-merge-plan.json` + its
`2026-09-03-merge-plan.md` projection, in this directory, built via
`skills/merge-pull-requests/scripts/build_plan.py` and amended through
`merge_plan.amend_plan()`. This document is the *rationale* record; the JSON
bundle is the executable one, and its `state.outcome` / `state.blocking_reason`
fields are the source of truth for what has and has not merged.

## Scope

The 11 open PRs split cleanly into two tiers by mergeability, and the split
tracks age exactly. Only Tier A is in scope for this pass.

| Tier | PRs | State |
|------|-----|-------|
| **A** | 468, 467, 465, 464, 463 | `MERGEABLE`, opened 2026-09-03, 4–11 commits behind |
| **B** | 422, 417, 411, 408, 363, 353 | `CONFLICTING` / `DIRTY`, 8–30 days old, 162–655 commits behind |

## Merge order

Order is not preference — step 0 gates everything, and steps 2–3 encode a hard
runtime dependency.

| Step | PR | Action | Gate before merge |
|------|----|--------|-------------------|
| **0** | **#472** | fix the Playwright probe guard | CI green — **blocks all of Tier A** |
| 1 | *(all Tier A)* | `refresh-branch` each node to pick up #472 | — |
| 2 | **#463** | merge | CI green |
| 3 | **#464** | fix 2×P1 ✅, `refresh-branch` (picks up #463), merge | CI green + P1s resolved |
| 4 | **#465** | fix 1×P1 ✅, merge | CI green + P1 resolved |
| 5 | **#468** | address 2×P1 + 4×P2 (plan-level), merge | plan review convergence |
| 6 | **#467** | address 3×P1 + 2×P2 + `context_impact` block, merge | plan review + drift gate green |
| — | #408 | close as superseded (see below) | after 463/464/465 land |

### Step 0 — why a sixth PR appeared

`test-infra-skills` is a **required** status check, and it was red on
`main@4e2eda94` *and* on every open PR. Cause:
`skills/tests/playwright-validator/test_e2e_sample.py` probes for Playwright
with `subprocess.run(["npx","playwright","--version"], timeout=30)` and skips
on a non-zero `returncode` — but an absent Playwright makes npx try to *fetch*
the package, so the probe hangs and raises `subprocess.TimeoutExpired`, which
escaped the guard and failed the test.

The test carries three separate "skip if Playwright is unavailable" guards and
a module docstring saying so; the timeout path was simply missed. PR #472 makes
every probe failure mode skip, and adds a parametrized regression test.

Nothing in Tier A can merge until #472 lands, because branch protection
requires that check. Note `"strict": false` in the protection config — branches
need not be current with `main` to merge — but each PR's check still runs
against a merge commit built when it was last pushed, so each Tier A branch
needs a `refresh-branch` after #472 lands to pick the fix up.

### Why #463 must precede #464

`#464`'s `test-integration` job fails with:

```
ERROR: column "delegated_from" of relation "audit_log" does not exist
```

This is **not** a defect in #464. Tracing it on `main`:

- `agent-coordinator/src/audit.py:119` writes `delegated_from` into `audit_log`.
- The only migration adding that column — `013_dynamic_authorization.sql` —
  adds it to **`agent_sessions`**, a different table.
- No migration on `main` has ever added `delegated_from` to `audit_log`.

That is defect #455, and `#463`'s new
`035_audit_log_delegated_from.sql` is its fix. #464 is failing on a
pre-existing `main` defect in files it does not modify — the textbook
stale-base signature.

**Consequence for tooling:** `rerun-checks` would be theatre here; it replays
the same merge commit. The correct sequence is merge #463, then
`refresh-branch 464` so the new merge commit contains migration 035.

**Consequence for the plan DAG:** #463 and #464 have *zero* file overlap, so
the file-overlap dependency deriver in `build_plan.py` produced no edge between
them. The edge was added manually to `merge-plan.json` with an
`inserted_reason`. A purely mechanical topology would have merged them in the
wrong order.

### Why #408 is closed rather than merged

#408 ("main cannot boot on PostgreSQL") is superseded by #463 + #464 + #465,
which carve up its file set exactly:

| #408 touches | Now owned by |
|---|---|
| `audit.py`, `0XX_audit_log_delegated_from.sql` | **#463** (renumbered 033 → 035) |
| `000_bootstrap.sql`, `config.py`, `db.py`, `migrations.py`, `policy_engine.py` | **#464** |
| `profiles.py`, `trust_resolution.py` | **#465** |

#408 is 276 commits behind, `CONFLICTING`, and shows zero checks — not because
CI never ran, but because GitHub cannot build a merge commit for a conflicting
branch, so no PR-triggered workflow can start.

Its 2 unresolved threads are reviewed before closing, in case the three-way
split dropped something.

## CI failure classification

Per the skill's Step 5b taxonomy:

| PR | Check | Class | Correct action |
|----|-------|-------|----------------|
| main, 463, 465, 467 | `test-infra-skills` | **latent defect, registry-triggered** | #472 |
| 463 | `test-integration` cancelled @ 1h16m | **transient** | `rerun-checks` |
| 464 | `test-integration` | **stale-base ×2** | merge #463; overload defect → issue #473 |
| 467 | `context-drift-gate` | **PR-specific** | fix `context_impact` block in PR |
| 411, 363 | 3 failures each | stale-base + conflicts | rebase required (Tier B) |

Note that `rerun-checks` did **not** fire on #463: the helper filters for
`conclusion == "failure"`, and #463's run was *cancelled*. Cancelled and failed
are distinct conclusions in the GitHub API, so the helper reported "no failed
workflow runs found" and did nothing. The run was re-triggered by id instead.
Worth fixing in `merge_pr.py`.

### #464 has two independent blockers, not one

Its `test-integration` job logs the `delegated_from` error, but the assertion
that actually fails is different:

```
asyncpg.exceptions.AmbiguousFunctionError:
  function coordinator_notify(unknown, text, text, text, text) is not unique
```

Migration `015` defines `coordinator_notify` with 5 params; `025` defines it
with 7 (last two defaulted) and never drops the old one. `CREATE OR REPLACE
FUNCTION` only replaces a *matching* signature — a different arity creates a
new overload — so both remain installed and a 5-argument call matches both.
`025`'s own header asserts the opposite, and that mistaken assumption is the
root cause.

This is pre-existing on `main`; #464 does not touch `coordinator_notify`.
`test-integration` is **not** a required check, so it does not block the merge.
Tracked as **issue #473**, to be fixed in its own PR after this pass.

`context-drift-gate` fails on #467, #411 and #363 — three unrelated PRs, which
normally implies a stale base. It does not here. The gate's own output does the
attribution:

```
[BLOCKING]      context.impact — introduced, attributed to HEAD
                openspec/changes/standardize-port-leases/work-packages.yaml
[informational] openspec.projection — inherited, attributed to main
                (~30 spec files)
```

Only #467's own `work-packages.yaml` blocks. Read the gate's verdict rather
than inferring from the failure count.

## Blocking review findings

All from `chatgpt-codex-connector`, all unresolved, none outdated.

### #463 — none

Zero unresolved threads. This is why it leads the order.

### #464 — 2×P1 — **fixed** (`fa3c66f1`)

- `src/config.py:139` — the new default selects PostgreSQL, but `asyncpg` is
  only in the optional `postgres` extra, so `create_db_client()` raises
  `ImportError`. The package's default configuration cannot start.
- `src/migrations.py:61` — SQLSTATE `42P16` is in the already-applied
  allowlist, but it means *invalid table definition*, not duplicate object. A
  malformed migration rolls back, has its checksum recorded, and is skipped
  permanently — reintroducing the exact silent schema-skew this PR exists to
  prevent.

Fixed by promoting `asyncpg` to a base dependency (the postgres default is
deliberate — docs, `coord-env`, and `migrations.py` all treat postgres as the
only supported backend — so the driver, not the default, was the thing out of
place), and by removing `42P16` from `_ALREADY_APPLIED_SQLSTATES`, keeping only
`42710`, `42P07`, `42723`, `42P06`, `42701`.

The `42P16` entry had been justified by a comment claiming
`ALTER PUBLICATION ... ADD TABLE` raises it for a table already in the
publication. That was checked against PostgreSQL's own `pg_publication.c` and
is wrong — it raises `ERRCODE_DUPLICATE_OBJECT` (`42710`), which was already in
the allowlist. The comment was corrected alongside the code.

The `postgres` extra was removed as now-empty. Every install path in the repo
uses `uv sync --all-extras`, so nothing referenced it by name; the one stale
mention, an error string in `db.py` suggesting
`pip install agent-coordinator[postgres]`, was updated in the same commit.
`uv.lock` was regenerated with the Dockerfile's pinned `uv==0.9.18`.

### #465 — 1×P1 — **fixed** (`cd094a4d`)

- `src/work_queue.py:438` — with `POLICY_ENGINE=cedar`, the default policy
  permits `get_work` without a trust check, so a broken registry profile
  reaches the handler *after* `claim_task` already set `status='claimed'`.
  Re-raising strands the task permanently (no stale-claim recovery path), and
  repeated calls can drain the pending queue.

Fixed by hoisting `_resolve_trust_level()` above the `claim_task` RPC — the
structural fix, which prevents the mutation rather than compensating for it,
and which matches the ordering `complete()` and `submit()` already use. Placed
after the policy-decision short-circuit and outside the `except Exception` that
tags the claim-duration metric, so the error is not swallowed. +1 regression
test asserting `claim_task` is never reached on trust failure.

**Vendor review (post-fix):** codex + grok + antigravity + pi dispatched, 2/4
returned parseable findings. Grok raised 3, all `low` / `accept`, none blocking:
a stale `source` docstring on `get_my_profile()`; the now-dead
`except TrustResolutionError: raise` inside the guardrails block; and the fact
that trust now resolves on every claim poll including empty-queue results.
Antigravity independently raised the dead-handler point but its output failed
to parse, so the consensus synthesizer scored it `unconfirmed` — the
confirmation math understates agreement whenever a vendor fails to emit valid
JSON.

### #468 — 2×P1, 4×P2 (plan-level)

Headline: the `(session_id, agent_id)` usage join would report INIT, PLAN and
SUBMIT_PR as `unattributed` on every run, because those phases insert
`dispatch_records` with a null `agent_id` and SQL nulls do not match.

### #467 — 3×P1, 2×P2 (plan-level)

Headline: with `PORT_LEASE_BACKEND=file` during a coordinator outage, the file
registry has no knowledge of coordinator leases, so identical arithmetic
selects the same slots. The bind probe does not close the gap because it does
not reserve the sockets.

## Compliance gap

All five Tier A PRs are missing the Change Summary template — no
`CHANGES MADE` / `DIDN'T TOUCH` / `CONCERNS` block in any body. Each is
flagged `description-incomplete` and scaffolded before merge.

## Execution notes

- Every PR carries the `proposal_acceptance` gate (origin `openspec`), so none
  is `auto_executable`. Each merge is an explicit operator-gated step.
- Strategy is `rebase` for all five (origin `openspec` — preserve granular
  commit history for `git blame` / `bisect`).
- After each merge: `git pull origin main`, then re-check staleness for the
  next node before presenting it.
- Fixes are made on the PR branches in dedicated worktrees, never in the shared
  checkout.

---

## Execution state (resume point — 2026-09-03 ~22:27 local)

Authoritative machine-readable state: `docs/merge-logs/2026-09-03-merge-plan.json`
(with its `2026-09-03-merge-plan.md` projection). Node `state.outcome` and
`state.blocking_reason` there are the source of truth; this section is the
narrative summary.

### Done

| Item | Result |
|---|---|
| Sync-point guard | Ghost pin on `route-supervise-gates-through-the-approval-gate-service` released via `worktree.py unpin` (worktree, branch, and change dir were all already gone; work archived on the roadmap branch at `58f19a19`). Guard now reports `clear`. |
| Dry-run triage | All 11 open PRs classified; Tier A (mergeable) vs Tier B (all `CONFLICTING`). |
| Plan bundle | Built, amended with the #464→#463 runtime edge and #472 as a prerequisite, revalidated. |
| **#465** | Fix pushed `cd094a4d`. Vendor review run (2/4 vendors parsed; 3 low/accept findings, none blocking). CI: 19 pass, 1 skipping, only `test-infra-skills` red. |
| **#464** | Fix pushed `fa3c66f1`. |
| **#472** | Opened — the Playwright probe guard. CI in progress. |
| **#473** | Filed — `coordinator_notify` duplicate overload, deferred to its own PR after this pass. |

### Next actions, in order

1. Wait for **#472** CI; confirm `test-infra-skills` passes. Merge with
   `--strategy squash` (origin `other`).
2. `git pull origin main`, then
   `merge_pr.py refresh-branch <n>` for **463, 465, 464** so each merge commit
   contains #472's fix. Without this they stay red — branch protection is
   `"strict": false`, so #472 landing does not retroactively green them.
3. Merge **#463** (rebase). Then `git pull origin main`.
4. `refresh-branch` **#464** again (now also picking up #463's migration 035),
   confirm CI, merge (rebase). Its `test-integration` will still be red from
   issue #473 — that check is *not* required, and the merge log must say so.
5. Merge **#465** (rebase).
6. Plan PRs **#468** (2×P1 + 4×P2) and **#467** (3×P1 + 2×P2 + a blocking
   `context_impact` block on its own `work-packages.yaml`). These are
   proposal-content defects → route through `/iterate-on-plan`, then
   multi-vendor plan review, then merge.
7. Close **#408** as superseded by #463/#464/#465, after reviewing its 2
   unresolved threads.
8. Scaffold the missing `CHANGES MADE / DIDN'T TOUCH / CONCERNS` block on every
   Tier A PR before merging it — all five lack it. (#472 already has one.)
9. Merge log (Step 13) + context convergence (Step 11.6).

### Open worktrees to clean up at the end

- `.git-worktrees/pr-fix-migration-bootstrap-cascade` (#464)
- `.git-worktrees/pr-fix-trust-resolution-fail-open` (#465)
- `.git-worktrees/fix-playwright-probe` (#472)

### Defects found this pass, beyond the PRs themselves

- **`merge_pr.py rerun-checks` misses cancelled runs.** It filters on
  `conclusion == "failure"`; a *cancelled* run does not match, so it reported
  "no failed workflow runs found" for #463 and did nothing. Not yet filed.
- **Consensus confirmation undercounts when a vendor emits invalid JSON.** On
  #465, grok and antigravity independently raised the same dead-handler
  finding, but antigravity's output failed to parse and was dropped, so the
  finding scored `unconfirmed`. Not yet filed.

---

## Execution state (resume point — 2026-09-04, supersedes the 2026-09-03 ~22:27 section)

### Done since the previous resume point

| Item | Result |
|---|---|
| **#472** Playwright probe fix | **Merged** (squash). 20 pass / 1 skip. `test-infra-skills` green. |
| `main` | advanced `4e2eda94` → `a84539bf` (#472) → +#465 |
| #463, #465 | `refresh-branch` applied; both rebuilt merge commits on the new `main` |
| Change Summary blocks | Added to **#463, #464, #465** (all three previously non-compliant) |
| Multi-vendor review | Run on **#465** (2/2 quorum) and **#463** (3/3 quorum) |
| **#465** | **Merged** (rebase). 6/6 required checks, 20 pass. |
| **#463** | Blocking vendor finding being fixed on-branch (see below) |
| Worktree cleanup | `.git-worktrees/fix-playwright-probe` torn down; local branch deleted |

### Issues filed

| # | Subject |
|---|---|
| #474 | Supabase backend: `datetime` in `agent_profiles` payload is not JSON-serializable — carried forward from #408's P1, **not** superseded by Tier A |
| #475 | No index on `audit_log.delegated_from` (deferred from #463 review) |
| #476 | Audit schema-alignment guard has two parsing blind spots, both fail open (deferred from #463) |
| #477 | `AuditService.drain()` not wired into coordinator lifecycle (deferred from #463) |
| #478 | `vendor_review` consensus **undercounts agreement** — same defect from two vendors counted as two unique findings |
| #479 | `merge_pr.py rerun-checks` ignores `cancelled` workflow runs |

`#478` and `#479` are the two tool defects the previous resume point listed as unfiled. Both are now filed with reproductions.

### #465 vendor finding — accepted, not fixed

One unconfirmed finding: the `except TrustResolutionError:` handler in `claim()` is unreachable after commit `cd094a4d` hoisted `_resolve_trust_level` above the `claim_task` RPC.

**Verified true** — `guardrails.py` neither imports nor raises `TrustResolutionError`, and the `claim()` try block calls only `get_guardrails_service`, `check_operation`, and `db.rpc`.

**Accepted anyway.** The handler is deliberate symmetry across all three guardrail call sites (`claim`, `complete`, `submit`); the latter two reach it live. The PR's own `test_every_guardrail_handler_re_raises_trust_failures` asserts it exists at every site, and it re-arms automatically if resolution is ever moved back inside the try. The vendor scored it non-blocking.

### #463 blocking finding — fixed on-branch

`AuditService.drain()` (`agent-coordinator/src/audit.py:174`) discards the `(done, pending)` tuple from `asyncio.wait`, so a timeout returns success while audit writes are still pending.

This is the **same silent-success class the PR exists to eliminate** — `_insert_audit_entry`'s own docstring names "a returned-but-unread error is the same as no error at all" as the original root cause of the empty audit trail. `drain()` reproduces it one layer up.

Found independently by **antigravity and grok**, but the consensus report said `confirmed_count: 0` (issue #478). The summary also reported `blocking_count: 1` alongside `confirmed_count: 0`, which contradicts the skill's own definition of blocking as a subset of confirmed.

Also being fixed: `test_drain_waits_for_fire_and_forget_writes` does not pin `config.audit.async_logging = True`, so with `AUDIT_ASYNC=false` it passes without exercising the fire-and-forget path at all.

### Gate note for the merge log

#463/#464/#465 classify as origin `openspec` because `discover_prs.py:5` deliberately maps `claude/*` branches to that origin. That is **intentional, not a misclassification**. Consequence: `rebase` strategy and a `proposal_acceptance` gate apply — but none of the three carries an `openspec/changes/<id>/` directory, so there is no proposal to accept and no `validation-report.md` path for the step-9.5 validation gate. Both gates are **vacuous by construction** here rather than satisfied. Recorded so a later reader does not mistake the absence of a proposal artifact for a skipped gate.

### Next actions, in order

1. **In flight:** sub-agent fixing `drain()` + the vacuous drain test on `claude/fix-audit-trail-delegated-from`, in `.git-worktrees/fix-463-drain`. Expect a pushed commit.
2. Wait for #463 CI. Required set is `test`, `test-infra-skills`, `test-skills`, `validate-specs`, `check-docker-imports`, `secret-scan` — `test-integration` is **not** required.
3. Merge **#463** (`rebase`), then `git pull origin main`.
4. `refresh-branch` **#464** so it picks up #463's migration `035`, then re-run its vendor review, then merge (`rebase`). Its `test-integration` stays red from **#473** — not required, must be stated in the merge log.
5. Plan **#468** (2×P1 + 4×P2) and **#467** (3×P1 + 2×P2 + a blocking `context_impact` block) via `/iterate-on-plan`, then multi-vendor plan review, then merge.
6. Close **#408** as superseded. Its P2 is genuinely dead (`_release_claimed_task` no longer exists on main); its P1 is preserved as **#474**.
7. Merge log (step 13) + context convergence (step 11.6).
8. Tear down `.git-worktrees/pr-fix-migration-bootstrap-cascade`, `.git-worktrees/pr-fix-trust-resolution-fail-open`, `.git-worktrees/fix-463-drain`.

### Environment note

`gh pr edit --body-file` fails on this repo with a Projects-classic GraphQL error (gh 2.45.0). Use `gh api repos/jankneumann/agentic-coding-tools/pulls/<n> -X PATCH -F body=@<file>`. Saved to memory; the failure is in gh's pre-mutation read, so it gives no partial-write signal — always verify with `gh pr view <n> --json body`.

---

## BLOCKER discovered 2026-09-04: #463 hangs `test-integration`

**#463 must not be merged as it stands.** All six required checks pass, but the
non-required `test-integration` job hangs, and that job has no `timeout-minutes`
(issue #480), so it runs to GitHub's 6-hour default. Merging would hang that job
on `main` on every run.

### Evidence

| Branch | `test-integration` |
|---|---|
| #472 | pass, 57s |
| #465 | pass, 55s |
| `main` @ `b30233cf` | pass |
| **#463** | hung twice — 68 min and ~30 min, both cancelled manually |

Both runs stall at the identical point. 54 items collected; last line printed:

```
tests/integration/postgres/test_work_queue_postgres.py::TestWorkQueueConcurrencyPostgres::test_concurrent_claims_distribute_tasks PASSED [ 75%]
```

75% is the boundary between `tests/integration/postgres/` and `tests/e2e/postgres/`.
The first file there alphabetically is **`test_audit_live.py::TestAuditTrailLive`**.

### What it is NOT

- **Not #463's own new tests.** All three `test_audit_log_insert.py` tests pass, at 1%, 3% and 5%.
- **Not the `drain()` timeout defect.** The hang reproduces both before and after `e2b7bb9c`.
- **Not a flaky runner.** Two independent runs, identical stall point; `main` green.

### Likely mechanism (unverified — no local PostgreSQL available)

`TestAuditTrailLive` tests are **synchronous** (`def`, not `async def`) and drive the app
through `api_client`. `POST /memory/store` triggers `log_operation` on the fire-and-forget
path.

#463 adds `AuditService._pending`, a strong-reference set that stops the loop
garbage-collecting those tasks before they run. That is the correct fix for its target bug,
but it also means tasks that previously vanished now survive — and something in the
synchronous `TestClient` teardown appears to wait on them.

Candidate fix: scope `_pending` to the service lifetime and drain-or-cancel on teardown, so
retained tasks cannot outlive the client that created them.

### Recommended sequencing

Fix **#480 first, as its own PR to `main`** — same pattern the operator approved for #472.
A healthy `test-integration` run is under a minute, so a `timeout-minutes` of ~15 converts a
hang into a fast, legible failure. Without it, every #463 iteration costs a 6-hour hung job,
which makes the debugging loop impractical. A concurrency group is also missing: a new push
does not cancel the superseded run, so two hung jobs ran simultaneously here.

### Consequence for the plan

#463 blocked → **#464 blocked** (it needs #463's migration `035`). Tier A is therefore
stalled at 2 of 4 merged (#472, #465). #467 and #468 are unaffected and remain available.

### Issues filed for this blocker

- **#480** — `test-integration` has no `timeout-minutes`; also missing a concurrency group.

---

## CI blocker fixed — PR #481 merged 2026-09-04

Closes **#480**. Merged with `rebase`; 20/20 checks pass, 1 skipped.

### Prior-work search (done before building)

| Branch | Finding | Action |
|---|---|---|
| `claude/ci-pipeline-speedup-cp02l8` | Contained **exactly** the needed `concurrency` block, with measured justification (3 of 30 superseded runs still executing) | **523 commits behind**, month old, no PR, bundles a large CI restructure. Design carried over with attribution; branch not resurrected. |
| `openspec/rescope-context-drift-enforcement` | Its `timeout-minutes: 20` is on `dependency-update-remediation`, a job it adds — already in `main` | Not relevant |
| Issues | Only #480 | No duplicate |

### Scope was larger than #480 stated

#480 was filed about `test-integration` alone. Enumeration found **15 of 21 jobs**
unbounded across `ci.yml` **and** `security.yml` — including **all six required status
checks**. A hang in any required check blocks every merge in the repository for six hours.

Ceilings sized from observed durations on `main`, reusing the 10/15/20 tiers already in
the file. Slowest unbounded job was `test-infra-skills` at 3.2 min, not `test-integration`.

### Regression guard

`skills/tests/ci_coverage/test_ci_job_timeouts.py` — every job bounded, no ceiling above
30 min, every workflow cancels superseded PR runs (and **only** PR runs), all six required
checks bounded and still present under those names.

Placed beside the existing CI-coverage guard in a directory `testpaths` already names, so
it is itself run by CI. **Verified it actually executed** in the `test-infra-skills` log,
not merely that it passed locally — the failure mode that directory's docstring records is
a guard that reports green while checking nothing.

**Negative-tested:** removing `test-infra-skills`'s timeout fails 2 tests (one naming it as
a required check); removing `security.yml`'s concurrency fails 1.

### What this does and does not do

- **Does:** convert a hang into a legible failure in ≤20 min instead of a 6-hour job, and
  stop superseded PR runs accumulating.
- **Does NOT:** fix #463's `test-integration` hang. That remains open and #463/#464 stay
  blocked. What changes is that each iteration now costs ~15 min rather than 6 hours,
  which makes the debugging loop practical.

`test-integration` passed in **57s** on #481, re-confirming the hang is #463-specific.

---

## Review of the #463 / #464 fixes from the other session — 2026-09-04

Both PRs are green (20/20, `test-integration` 1m1s and 53s). Both fixes are **approved**.
Both diagnoses were better than the ones recorded above, and each refutes one of them.

### #463 — `f20f7818` terminate the global pool on `reset_db()`

**My earlier hypothesis was wrong.** I attributed the hang to the `_pending` strong-reference
set. The commit disproves it directly: pristine `main` + migration `035` alone hangs identically.

**Actual root cause** (`pg_stat_activity`): a fire-and-forget audit `INSERT` whose test event
loop closed mid-query leaves a backend `active` in `ClientRead`, holding `RowExclusiveLock` on
`audit_log` in an implicit transaction. The next e2e test's app startup re-runs migrations and
`008` blocks on that lock forever. `reset_db()` dropped the pool reference without terminating
it — a pre-existing leak that `035` made reachable, because before it every insert failed fast
on the missing column and released its lock.

Fix is on the right path — `reset_db()` is called from all three postgres conftests. Negative-
tested per the commit. Correctly scoped to test infrastructure; production relies on OS socket
close at exit, and #477 is the production-side answer.

Non-blocking concerns: the closed-loop fallback reaches into asyncpg private attributes via
`getattr(..., None)` + `continue`, so an upgrade makes it a **silent** no-op (caught only by the
postgres integration test); `except RuntimeError` is broader than the one message it targets.

### #464 — `0f0ba4de` add `23505` to the first-run allowlist

**My earlier attribution was wrong.** I recorded #464's red `test-integration` as caused by
#473 alone and "NOT caused by this PR". The proximate cause was in #464.

**Actual root cause:** psql seeding leaves `schema_migrations` empty, so the first-run pass
re-executes every migration. #464's narrowed allowlist — correct in itself — stopped that pass
at `019` (unique_violation on renames), after `015` had re-run and clobbered `025`'s rewrite of
`notify_work_queue_change`, before `025` could restore it. The trigger was left in the 5-arg
form, which is ambiguous next to `025`'s overload. **#473 is real but latent** on `main`, where
every trigger uses the 7-arg form.

Fix is sound for the failure; `migrated_database` is function-scoped, so the test's
`DELETE FROM schema_migrations` is isolated. The residual hazard — re-executing non-idempotent
migrations on a seeded DB at all — is bounded, not closed. Filed as **#482** with three options;
option 2 (seeding records what it applied) removes the hazard rather than managing it.

### Records corrected

- PR #463: correction comment posted, mechanism restated.
- Issue #473: downgraded from "breaks integration tests" to "latent, no current caller".
- PR #464 Change Summary: CONCERNS bullet replaced with the accurate cause.
- Plan bundle: both nodes updated, `#463` unblocked.

### Merge readiness

Neither branch includes #465, #481, or (for #464) #463. Both are green on their current merge
commits and `strict: false` permits merging as-is. Order stands: **#463 → pull → refresh #464 →
CI → #464**, so #464's fresh-database test runs against `035`.

---

## Tier A complete — 2026-09-04

All four nodes merged:

| PR | Strategy | Result |
|---|---|---|
| #472 | squash | 20 pass, 1 skip |
| #463 | rebase | 20/20; hang fix reviewed on `f20f7818`, review notes addressed on `4a250f97` |
| #464 | rebase | 20/20 including `test-integration` at 1m4s, against `main` with #463's migration `035` and pool-termination fix |
| #465 | rebase | 20/20 |

Plus infrastructure: **#481** (CI timeouts + concurrency), merged ahead of #463/#464 so their
debugging iterations were bounded rather than 6-hour hangs.

Sync-point guard ran clean before #463/#464; no concurrent agent held a pin.

### Issues filed this pass

#474 (Supabase datetime, carried from #408), #475–#477 (deferred #463 findings),
#478 (vendor consensus undercount), #479 (`rerun-checks` ignores cancelled runs),
#480 (CI timeout, closed by #481), #482 (residual seeded-migration hazard).

### Corrections made to prior records in this doc

- #463 hang: **not** `_pending` retention (my hypothesis) — a pre-existing `reset_db()`
  pool leak, made reachable by `035`. See the dedicated review section above.
- #464 `test-integration` red: **not** solely #473 (my earlier attribution) — #464's own
  narrowed allowlist stopped the first-run migration pass early. #473 downgraded to latent.

### Remaining from the original plan

1. Plan **#468** and **#467** via `/iterate-on-plan`, then multi-vendor plan review, then merge.
2. Close **#408** as superseded (P2 dead, P1 preserved as #474).
3. Merge log (step 13) + context convergence (step 11.6).
