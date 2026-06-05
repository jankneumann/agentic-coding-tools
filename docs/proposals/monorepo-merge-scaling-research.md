# Monorepo Merge Scaling: Industry Practices vs Current Implementation

Research analysis comparing our `merge-pull-requests` skill and coordinator merge queue against proven practices from Google (Piper/CitC/TAP), Meta (Sapling/Buck2), Microsoft (VFS for Git/1ES), and other large-scale monorepo operators.

## Executive Summary

Our current merge infrastructure handles the **single-operator, moderate-throughput** case well: staleness detection, multi-vendor review, origin-aware strategy selection, and coordinated merge ordering. However, it lacks the patterns needed to scale from ~10 concurrent PRs to 100-1000 — the regime where AI agent fleets will operate. The critical gaps are: **speculative merge testing**, **semantic conflict detection**, **automatic cascading rebase**, **build-graph-aware CI**, and **automatic rollback**.

---

## What We Have Today

| Capability | Implementation | Files |
|---|---|---|
| PR discovery & classification | 8 origin types, draft/stacked/fork detection | `discover_prs.py` |
| Staleness detection | fresh/stale/obsolete with pattern matching | `check_staleness.py` |
| File-level conflict detection | PR pairs sharing modified files | SKILL.md Step 6 |
| Origin-aware merge strategy | rebase for agents, squash for deps/bots | `merge_pr.py` |
| CI failure classification | transient vs stale-merge vs PR-specific | SKILL.md Step 5b |
| Branch refresh | GitHub Update Branch API | `merge_pr.py refresh-branch` |
| Multi-vendor review | Dispatch to Codex/Gemini, consensus synthesis | `vendor_review.py` |
| Coordinator merge queue | Priority-ordered, pre-merge conflict revalidation | `merge_queue.py` |
| Resource conflict analysis | FULL/PARTIAL/SEQUENTIAL feasibility | `feature_registry.py` |
| Post-merge cleanup | OpenSpec archival, worktree/branch cleanup | `post_merge_cleanup.py` |
| Merge logging | Per-session decision audit trail | SKILL.md Step 13 |
| Active-agent guard | Sync-point safety, heartbeat-based liveness | SKILL.md prereqs |

## Gap Analysis: What Industry Leaders Do That We Don't

### Gap 1: Speculative / Optimistic Merge Testing

**What Google does (TAP — Test Automation Platform):**
Every CL (changelist) is tested not just in isolation, but against the **combined state** of all CLs ahead of it in the submit queue. If CL-1 and CL-2 are both queued, CL-2's tests run against `main + CL-1 + CL-2`. If CL-1 fails, CL-2 is re-tested against `main + CL-2` only.

**What GitHub Merge Queue does:**
Creates temporary merge-group branches that combine multiple queued PRs. CI runs against the combined state. If any PR in the group fails, it's ejected and the group is re-tested without it.

**Our gap:**
Our coordinator `merge_queue.py` tracks priority and resource conflicts, but never constructs combined test states. PRs are tested and merged one at a time. At 10 PRs this is fine; at 100 PRs with 30-minute CI pipelines, serial testing creates a 50-hour queue.

**Why it matters for agents:**
50 agents producing 50 PRs/day with 20-minute CI means the serial merge queue alone takes ~17 hours. Speculative testing collapses this to ~1-2 hours by testing in parallel.

**Implementation sketch:**
```
1. Group non-conflicting PRs (using existing file-overlap + resource claim data)
2. Create temporary combined branches: main + group[0..N]
3. Run CI against combined state
4. On failure: bisect the group, eject failing PR, re-test remainder
5. On success: fast-forward merge all PRs in the group
```

**Complexity: HIGH** — requires CI orchestration, branch management, and failure bisection logic.

---

### Gap 2: Semantic Conflict Detection

**What Google does (Tricorder + Build Deps):**
Two CLs can conflict without touching the same file. CL-A changes a function signature in `lib.py`; CL-B calls that function from `app.py`. File-level overlap shows zero conflict, but the combined state won't compile.

Google uses build-system dependency graphs (Blaze/Bazel) to identify transitive conflicts: if CL-A modifies a build target, all CLs touching targets that depend on it are flagged.

**What Meta does:**
Buck2's dependency graph provides the same transitive impact analysis. Combined with Sapling's stacking model, conflicts are detected at the module/package level.

**Our gap:**
`check_staleness.py` and SKILL.md Step 6 only compare **file paths**. Two PRs modifying `src/api/users.py` and `src/models/user.py` respectively show zero overlap, even though one might break the other's import chain.

The coordinator's lock key namespaces (`api:`, `db:`, `contract:`) partially address this for API contracts and database schemas, but only when agents explicitly declare their resource claims in `work-packages.yaml`. Changes outside the OpenSpec flow have no semantic conflict detection.

**Implementation sketch:**
```
1. Build a lightweight dependency graph from imports/requires
   (Python: ast.parse → Import/ImportFrom; JS/TS: regex on import/require)
2. For each PR, compute "impact set" = files changed + transitive dependents
3. Flag PR pairs where impact sets overlap (even if file sets don't)
4. Use coordinator lock keys as the curated layer for cross-feature conflicts
```

**Complexity: MEDIUM** — import parsing is straightforward; keeping the dep graph current is the challenge.

---

### Gap 3: Automatic Cascading Rebase

**What Google does (CitC — Clients in the Cloud):**
Every developer's workspace is a virtual filesystem overlay on the latest state of the repository. There's no "stale branch" problem because you're always working against HEAD. When you submit a CL, it's atomically applied to the current HEAD, not to the snapshot when you started.

**What Graphite/Sapling do (Stacked Diffs):**
When the base of a stack merges, all dependent PRs in the chain are automatically rebased. The developer doesn't manually run `git rebase`.

**Our gap:**
When PR #42 merges, our skill re-runs staleness detection for the next PR (SKILL.md Step 11 "Re-check Staleness After Merge"). But it doesn't **automatically rebase** queued PRs. The operator must manually run `refresh-branch` or rebase locally.

At scale, this becomes a major bottleneck: every merge invalidates N other PRs, each requiring human attention to refresh.

**Implementation sketch:**
```
1. After each merge, compute which queued PRs overlap with the merged PR's files
2. For non-conflicting overlaps: auto-call refresh-branch (GitHub Update Branch API)
3. For conflicting overlaps: flag for human attention
4. Use coordinator merge queue to track which PRs need refresh
```

**Complexity: LOW-MEDIUM** — the building blocks exist (`refresh-branch`, staleness detection). The gap is orchestration logic.

---

### Gap 4: Build-Graph-Aware CI (Affected Test Selection)

**What Google does (TAP):**
TAP uses the Blaze/Bazel build graph to identify exactly which test targets are affected by a CL. A change to `lib/auth.py` only runs tests that transitively depend on `lib/auth.py`, not the entire test suite. This reduces median CI time from 30 minutes to 2-3 minutes.

**What Meta does:**
"Affected tests" determination using Buck2's build graph. Only tests whose transitive dependency closure includes a changed file are executed.

**What Microsoft does (1ES Pipeline):**
Test Impact Analysis (TIA) uses binary instrumentation to map test-to-code relationships. On a PR, only tests that cover changed code paths run.

**Our gap:**
Every PR runs the full CI pipeline. As the test suite grows, this becomes the dominant bottleneck in merge throughput. The current `merge_pr.py` has no concept of test targeting.

**Implementation sketch:**
```
1. Instrument test runs to record which source files each test touches
   (coverage.py for Python, Istanbul for JS/TS)
2. Store the mapping: test_file → set(source_files_exercised)
3. On PR, compute: affected_tests = {t for t in tests if t.sources ∩ pr.files ≠ ∅}
4. Run only affected_tests in CI
5. Periodically run full suite to catch dependency drift
```

**Complexity: HIGH** — requires coverage instrumentation, mapping storage, and CI pipeline changes.

---

### Gap 5: Automatic Rollback / Revert

**What Google does:**
If a submitted CL breaks the build (detected by continuous testing against HEAD), Google's systems automatically generate a revert CL and submit it. The original author is notified. The tree stays green.

**What Meta does:**
Similar auto-revert for CLs that cause signal regression in continuous integration.

**Our gap:**
No rollback automation whatsoever. If a merged PR breaks main, the operator must manually create a revert PR. At scale with agent-authored changes, a single broken merge can block dozens of subsequent PRs in the queue.

**Implementation sketch:**
```
1. After merge, monitor CI on main for the next N minutes
2. If main CI fails and the failure is in files modified by the just-merged PR:
   a. Auto-create revert PR: `git revert <merge-sha> && gh pr create`
   b. Fast-track the revert through the merge queue
   c. Notify the original agent/operator
3. Log the revert in merge-log with forensics
```

**Complexity: MEDIUM** — the git mechanics are simple; the monitoring and attribution logic is the work.

---

### Gap 6: Batch / Grouped Merging

**What Google does:**
Independent CLs are grouped and submitted together. The submit queue processes batches, not individual items.

**What GitHub Merge Queue does:**
Configurable `merge_group` sizes (e.g., test 5 PRs at once). Entire groups are tested together and merged atomically.

**Our gap:**
`merge_pr.py` merges one PR at a time. SKILL.md Step 10 determines merge order, but each merge is a separate operation with separate CI validation. The coordinator's merge queue dequeues one at a time via `get_next_to_merge()`.

**Implementation sketch:**
```
1. Partition queued PRs into non-conflicting groups (using file overlap + resource claims)
2. For each group: create combined test branch, run CI
3. On success: merge all PRs in group (sequentially but without re-testing)
4. On failure: split group in half, re-test each half (binary bisection)
```

**Complexity: MEDIUM** — partitioning and bisection logic, plus combined branch management.

---

### Gap 7: Dependency-Aware Merge Ordering Across Features

**What Google does:**
The submit queue understands dependencies between CLs. If CL-B imports a new symbol from CL-A, CL-A is submitted first automatically.

**Our gap:**
Within a single feature, the DAG scheduler (`dag_scheduler.py`) handles work-package dependencies. But across features in the merge queue, ordering is purely by priority number. There's no detection of "Feature B's code imports from Feature A's new module, so A must merge first."

The coordinator's `feature_registry.py` tracks resource claims for conflict detection, but not dependency relationships between features.

**Implementation sketch:**
```
1. When enqueuing a feature, analyze its PR diff for new exports/APIs
2. Compare against other queued features' imports/API calls
3. Build a cross-feature dependency DAG
4. Enforce topological merge ordering (within priority tiers)
```

**Complexity: MEDIUM-HIGH** — cross-feature dependency detection requires code analysis.

---

### Gap 8: Merge Throughput Metrics & Queue Health

**What Google does:**
Extensive metrics on submit queue latency, rejection rates, revert rates, and queue depth. Teams are held accountable for their CL rejection rates.

**What all large-scale operators do:**
Queue health dashboards showing: median time-in-queue, p95 latency, conflict rate, auto-revert rate, speculative test pass rate, CI utilization.

**Our gap:**
The merge log (`docs/merge-logs/`) captures decisions but doesn't aggregate metrics. There's no dashboard, no trend analysis, no alerting on queue health degradation.

**Implementation sketch:**
```
1. Emit structured events from merge_pr.py: {timestamp, pr, action, duration, result}
2. Store in coordinator DB (new merge_metrics table)
3. Add /metrics endpoint to coordinator API
4. Build summary queries: daily throughput, avg queue time, conflict rate
5. Surface in kanban-viz or separate dashboard
```

**Complexity: LOW** — mostly instrumentation and reporting.

---

### Gap 9: Stacked Diff Management

**What Sapling/Graphite do:**
Full lifecycle management for PR chains: auto-rebase on base merge, combined CI for the stack, one-click merge of entire stacks.

**Our gap:**
SKILL.md Step 4 warns about stacked PRs but treats them as edge cases to handle manually. The coordinator has `decomposition="stacked"` in the merge queue (R12) and auto-creates feature flags, but the merge skill doesn't leverage this for chain management.

**What we'd need:**
```
1. Detect stacked PR chains automatically (already partially done: is_stacked flag)
2. Visualize the chain: PR#1 → PR#2 → PR#3
3. Auto-rebase downstream PRs when upstream merges
4. Merge entire chain in sequence when all are approved
5. Toggle feature flag on final stack slice merge
```

**Complexity: MEDIUM** — the coordinator already has the primitives; the gap is skill-level orchestration.

---

### Gap 10: Automatic Trivial Conflict Resolution

**What large teams do:**
Certain conflict types are always resolvable mechanically:
- **Lock files**: regenerate from manifests (`package-lock.json`, `uv.lock`)
- **Import sorting**: re-run formatter (isort, prettier)
- **Generated code**: re-run code generator (protobuf, OpenAPI)
- **Version bumps**: take the later version
- **CHANGELOG**: append both entries

**Our gap:**
All conflicts require human attention. The skill surfaces `CONFLICTING` status and asks the operator to rebase.

**Implementation sketch:**
```
1. When merge fails with CONFLICTING:
   a. Parse conflict markers to identify conflicted files
   b. Check if all conflicted files are in the "auto-resolvable" set
   c. If yes: run resolution strategy (regenerate, re-sort, take-later)
   d. Commit resolution and retry merge
   e. If no: surface to operator as today
```

**Complexity: LOW-MEDIUM** — file-type-specific resolution strategies, each simple individually.

---

## Priority Matrix

Ranked by impact on merge throughput when scaling to 50-1000 agents:

| Priority | Gap | Impact at Scale | Effort | Prereqs |
|----------|-----|----------------|--------|---------|
| **P0** | Gap 3: Auto Cascading Rebase | Eliminates manual refresh cycle | Low-Medium | Existing building blocks |
| **P0** | Gap 5: Auto Rollback | Keeps trunk green, unblocks queue | Medium | CI monitoring |
| **P1** | Gap 1: Speculative Merge Testing | 10-50x throughput improvement | High | CI orchestration |
| **P1** | Gap 6: Batch Merging | 5-10x throughput improvement | Medium | Non-conflicting grouping |
| **P1** | Gap 8: Metrics & Queue Health | Visibility into bottlenecks | Low | Instrumentation |
| **P2** | Gap 10: Auto Trivial Resolution | Reduces operator toil 30-50% | Low-Medium | File-type strategies |
| **P2** | Gap 2: Semantic Conflict Detection | Catches cross-file breaks | Medium | Import/dep analysis |
| **P2** | Gap 9: Stacked Diff Management | Enables incremental feature delivery | Medium | Coordinator R12 |
| **P3** | Gap 4: Affected Test Selection | Reduces CI time 5-10x | High | Coverage instrumentation |
| **P3** | Gap 7: Cross-Feature Dep Ordering | Prevents dependency-ordering failures | Medium-High | Code analysis |

## Recommended Roadmap

### Phase 1: Queue Velocity (P0 items)
- Implement auto cascading rebase using existing `refresh-branch` + staleness detection
- Add auto rollback with CI monitoring post-merge
- Add merge throughput metrics to coordinator

### Phase 2: Parallelism (P1 items)
- Build non-conflicting PR grouping using file overlap + resource claims
- Implement speculative merge testing with combined branches
- Wire batch merging into coordinator merge queue

### Phase 3: Intelligence (P2 items)
- Import-graph-based semantic conflict detection
- Auto-resolution for lock files, import sorting, generated code
- Stacked diff chain management leveraging coordinator R12

### Phase 4: Optimization (P3 items)
- Test impact analysis via coverage instrumentation
- Cross-feature dependency ordering in merge queue

---

## Appendix: Industry Reference Architecture

### Google (Piper + CitC + TAP)

```
Developer workspace (CitC — virtual FS overlay on HEAD)
  → Code review (Critique)
    → Submit queue (TAP — speculative parallel testing)
      → Auto-revert on breakage
        → Build graph (Blaze/Bazel) drives test selection
```

- **Scale**: 86TB monorepo, ~80,000 commits/week, ~45,000 engineers
- **Key insight**: Virtual filesystem eliminates the "stale branch" problem entirely
- **Merge latency**: Minutes (median), driven by affected-test runtime

### Meta (Sapling + Buck2)

```
Developer workspace (Sapling — stacking-first VCS)
  → Code review (Phabricator)
    → Land queue (speculative testing, auto-rebase stacks)
      → Auto-revert on signal regression
        → Build graph (Buck2) drives test selection
```

- **Scale**: Largest monorepo in existence, ~1000s of commits/day
- **Key insight**: Stacked diffs enable incremental review and merge
- **Merge latency**: ~15 minutes for typical diffs

### Microsoft (VFS for Git + 1ES)

```
Developer workspace (VFS for Git — virtual FS for huge repos)
  → Code review (Azure DevOps)
    → Merge queue (Azure Pipelines)
      → Test Impact Analysis (binary instrumentation)
```

- **Scale**: Windows repo (~300GB), Office repo, ~100,000 engineers
- **Key insight**: VFS for Git makes huge repos usable without full clone
- **Merge latency**: Varies by org; TIA reduces test time 80-90%
