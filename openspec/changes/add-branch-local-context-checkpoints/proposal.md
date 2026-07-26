# Add branch-local context checkpoints

## Why

Large branch changes need current review context *before* main convergence. Today a
reviewer opening a feature PR has no machine-readable answer to "what project context
did this branch invalidate?" — the deterministic producers, the architecture graph, and
the semantic index all describe `main`, not the branch.

The obvious fix — run the ri-07 refresh inside the feature worktree — is unsafe as it
stands, for three concrete reasons found in the current code:

1. **The semantic index would write canonical `main` state.**
   `semantic_adapter.py:296-309` hardcodes `--namespace-kind main --namespace-key main`
   into the indexer argv. Downstream, promotion into the shared index is gated on exactly
   `namespace_kind is MAIN and namespace_key == "main"`
   (`indexing_runtime_models.py:130-136`). A refresh from a feature worktree therefore
   promotes branch content into the canonical index.

2. **Nothing enforces the work package's read scope.**
   The entire refresh path contains zero `read_allow` / `deny` handling. The indexer
   supports it (`indexing_policy.py:228`, CLI flags `--read-allow` / `--deny` /
   `--scope-file`) and ri-08 shipped `index_scopes()` to compute exactly that resolved
   set — but the two ends are not connected, so a checkpoint would index files the
   package was never permitted to read.

3. **The existing guard does not cover the relevant surface.**
   `checkout_policy.classify_checkout()` reasons purely about the *worktree path*: cwd
   under `.git-worktrees/` means mutation is allowed. It says nothing about writes to the
   git **common dir** — which is clone-global (verified: from a linked worktree,
   `git rev-parse --git-common-dir` resolves to the main clone's `.git`). A checkpoint can
   sit inside a managed worktree, pass every existing gate, and still write clone-global
   state.

ri-08 anticipated this item and left a labelled socket: its detector is deliberately
git-free with a `--changed-file` entry point, documented at
`skills/validate-packages/SKILL.md:47` as "how ri-09 will feed it a checkpoint's own
file list".

## What Changes

- Add a **checkpoint mode** to the project-context refresh lifecycle that runs against a
  work package's own changed-file list inside a feature worktree.
- Thread a **non-`main` index namespace** (`feature` / `work_package`) through
  `semantic_adapter.py`, so the existing promotion gate structurally prevents a branch
  from mutating the canonical index.
- Thread the package's **resolved read scope** (ri-08 `index_scopes()`) into the indexer
  argv, so checkpoint execution cannot read outside `read_allow` minus `deny`.
- Emit a **tracked, change-local checkpoint report** listing affected capabilities, APIs,
  architecture nodes, decisions, documentation, and the semantic index revision.
- Trigger the checkpoint from `implement-feature` at the per-package boundary, driven by
  the package's ri-08 `context_impact` surfaces.
- Architecture coverage uses the existing standalone `diff_architecture.py`
  (baseline-vs-current graph diff) rather than a new slice mode, because
  `architecture-provenance.schema.json` pins `mode` to the enum `full|quick`.

### Decided at discovery

| Question | Decision |
|---|---|
| What triggers a checkpoint | The package's ri-08 `context_impact` surfaces — not a new size field |
| Advisory or blocking | **Report-only.** Turning drift into a failure is ri-10's job |
| Semantic index default | Index when configured; degrade silently otherwise (consistent with ri-07 D4) |
| Report location | Tracked, change-local, so it appears in the PR diff |

### Explicit assumption carried from discovery

Deriving the trigger from `context_impact` means a package with **no** `context_impact`
block — ri-08 status `unmigrated` — never produces a checkpoint. This is accepted: ri-08
already ships `--strict-legacy` as the single flag that promotes `unmigrated` to a
failure once migration completes, and that flag is the intended closer for this gap. The
checkpoint report records `unmigrated` explicitly rather than silently reporting "no
impact", so the difference is visible to a reviewer.

## Approaches Considered

### Approach A — New `checkpoint()` mode inside the ri-07 orchestrator

Add a third entry point beside `generate()` and `check()` in `orchestrator.py`,
parameterized by namespace, scope, and changed-file list. `cli.py` gains a `checkpoint`
subcommand that `implement-feature` invokes.

**Pros**
- One seam; a reader looking for "how project context is refreshed" finds all modes together.
- Reuses `decide_outcome()`, the `RefreshResult` shape, and the exit-code convention.
- Smallest conceptual surface for future maintainers.

**Cons**
- **Poisons the canonical per-revision operation.** D2 makes exactly one operation per
  `(repository_id, source_revision)`, and results are append-only and immutable per
  producer. A checkpoint that claims the branch HEAD revision's operation would make a
  later legitimate refresh at that same SHA *reuse* scope-restricted, feature-namespaced
  results as if they were canonical.
- Isolation would rest on the incidental fact that `repository_id` defaults to
  `repo_root.name` (`orchestrator.py:145`) — the *worktree directory name*. Setting
  `PROJECT_CONTEXT_REPO_ID` silently collapses that separation.
- Forces the shared ledger to carry records that are, by construction, not canonical.

**Effort**: M

### Approach B — Checkpoint as a composing module that never writes the ri-06 ledger *(Recommended)*

A new `checkpoint.py` in `skills/project-context-refresh/scripts/` composes the pieces
that already exist: ri-08's `context_impact` detector for surface inference, the
deterministic producers in **check** mode, `diff_architecture.py` for the architecture
delta, and `semantic_adapter.py` with a `feature`/`work_package` namespace plus the
package's resolved scope. It emits its own change-local report against a new
`context-checkpoint.schema.json`, reusing ri-06 *types* (`ProducerResult`,
`SemanticIndexReference`) for the payload while never touching the ri-06 operation
**store**.

**Pros**
- Structurally cannot poison the canonical per-revision operation — the failure mode that
  sinks Approach A is unreachable, not merely avoided by convention.
- Isolation is enforced by the namespace key and the promotion gate, both of which already
  exist and are already tested downstream.
- Honours ri-07 D7 ("main is never written directly") without weakening `checkout_policy`,
  and matches the existing report-artifact conventions in `openspec/schemas/`.
- Read-only against the working tree: producers run in `check` mode, so a checkpoint cannot
  rewrite `docs/`, `openspec/specs/`, or any other tracked producer output.

**Cons**
- Two code paths that both "run producers" — the orchestrator's and the checkpoint's — with
  a genuine risk of drift between them over time.
- A second report contract to version and validate alongside the ri-06 manifest.
- Slightly more code than Approach C.

**Effort**: M

### Approach C — Parameterize the existing `generate()` with namespace and store overrides

Thread `namespace`, `scope`, and an `OperationStore(base_dir=…)` override through the
current `generate()` so a checkpoint is "a generate with different arguments".

**Pros**
- Least new code by a clear margin.
- No second report contract; the existing manifest is the output.

**Cons**
- `store.py` documents `base_dir` as an "adapter or test seams" override; routing product
  behaviour through it converts a test hook into load-bearing infrastructure.
- `generate()` **writes** producer outputs into the tracked working tree. A checkpoint that
  regenerates `docs/` and `openspec/specs/` on a feature branch produces exactly the
  canonical-artifact mutation the roadmap item forbids.
- The manifest path `.git-context/context-refresh-manifest.json` has no revision or
  namespace component, so a checkpoint would overwrite the worktree's real refresh manifest.
- Conflates two different trust levels — canonical and scope-restricted — in one artifact
  shape.

**Effort**: S

### Selected Approach

**Approach B — Checkpoint as a composing module that never writes the ri-06 ledger.**
Selected at Gate 1 without modification.

Approach A (third orchestrator mode) and Approach C (parameterized `generate()`) are
recorded above for review context and are not being implemented. Both were rejected for
the same reason: they place scope-restricted, feature-namespaced results into storage the
system treats as canonical.

### Recommendation

**Approach B.** The decisive argument is the Approach A / C failure mode rather than any
advantage of B in isolation: both alternatives place scope-restricted, feature-namespaced
results into storage that the system treats as canonical. Because D9 makes a recorded
producer result *immutable for its revision*, that contamination is not self-healing — a
later refresh reuses it verbatim rather than correcting it. B's cost is real (a second
producer-running path, a second contract) but it is maintenance cost, whereas A and C carry
a correctness risk in the durable ledger.

B's stated con is worth mitigating in design: the checkpoint should invoke producers
through the existing `registry.run_producer(...)` seam rather than reimplementing producer
dispatch, which keeps the drift surface to orchestration only.

## Impact

- **Affected specs**: `project-context-refresh-orchestration` (checkpoint mode, isolation
  guarantees), `skill-workflow` (implement-feature trigger, validate-packages reuse).
- **Affected code**: `skills/project-context-refresh/scripts/` (new `checkpoint.py`,
  `semantic_adapter.py` namespace + scope threading, `cli.py` subcommand),
  `skills/implement-feature/SKILL.md` (per-package trigger), new
  `openspec/schemas/context-checkpoint.schema.json`.
- **Not affected**: the ri-06 operation store and manifest contract are untouched; ri-05
  producer implementations are called, not modified.

### Known conflicts

- **PR #276** (`codebase-atlas`) ships a "branch-local docs freshness gate" — conceptual
  overlap plus mechanical conflicts on `skills/pyproject.toml` and
  `skills/install-manifest.json`.
- `openspec/expose-fail-closed-semantic-code-search` (ri-03) is **unmerged**, 32 commits
  ahead of main with no PR, and rewrites `packages/code-search/**`. ri-09 does not depend
  on it, and the `--namespace-kind` support ri-09 needs is already on main — but
  `semantic_adapter.py` changes will need reconciling when that branch lands.
- A ri-09 proposal stub exists on the roadmap branch and on the ri-03 branch; neither is on
  main, and this proposal supersedes both.

## Out of Scope

- Turning checkpoint drift into a CI or merge failure — that is ri-10.
- Running convergence on `main` after merge — that is ri-11.
- Injecting checkpoint results into coding-job context — that is ri-12.
- Adding an architecture *slice* mode, which would require changing the `mode` enum in
  `architecture-provenance.schema.json`.
- Migrating existing work packages to declare `context_impact`.
