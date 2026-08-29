# Design — Branch-local context checkpoints

## Context

ri-07 landed a refresh lifecycle that is deliberately canonical: one immutable operation
per `(repository_id, source_revision)` (D2), producer results sealed for their revision
(D9), and a rule that main is only ever written at a sync point (D7). ri-08 landed a
git-free context-impact detector with a `--changed-file` entry point built for this item.

This change adds a **branch-local checkpoint**: a read-only, scope-restricted, per-work-package
report of what project context a branch has invalidated. It must produce that report
*without* becoming a second writer of canonical state.

Selected approach (Gate 1): **Approach B** — a composing module that reuses ri-06 *types*
and the ri-05 producer registry, but never writes the ri-06 operation *store*.

## Decisions

### D1 — A checkpoint never writes the ri-06 operation ledger

`checkpoint.py` does not construct an `OperationStore`, does not call
`create_or_load` / `record_producer_result` / `finalize`, and does not emit a
`RefreshManifest`. It reuses the ri-06 *dataclasses* (`ProducerResult`,
`SemanticIndexReference`, `ValidationResult`, `Fallback`, `SafeError`) as the payload
shape of its own report.

This is the load-bearing decision. ri-07 D9 makes a recorded producer result immutable
for its revision and reused verbatim by later runs. A checkpoint result is
scope-restricted and feature-namespaced — it is *not* equivalent to a canonical result.
Writing one into the shared ledger would be unrecoverable by design rather than by
accident, because nothing in the ri-06 contract can distinguish or supersede it.

Enforced by test: a checkpoint run asserts that
`<git-common-dir>/project-context/refresh-operations/` gains no entries.

### D2 — The trigger is the package's ri-08 `context_impact`, and `unmigrated` is reported explicitly

`implement-feature` decides whether to run a checkpoint for a package by calling ri-08's
detector with the package's own changed-file list (`--changed-file`, never `--base`, so
the decision has no git dependency and works on an uncommitted worktree).

A package whose declared-or-inferred surfaces intersect the *context-invalidating* set
gets a checkpoint. A package with **no** `context_impact` block is ri-08 status
`unmigrated`; it produces no checkpoint, and the reason is recorded as the literal string
`unmigrated` in the implement-feature summary rather than being reported as "no impact".

The distinction matters because `declared_surfaces()` returns `None` for a missing block
and `frozenset()` for an explicit empty list (`context_impact.py:190-200`) — an assertion
of "affects nothing" is evidence; a missing block is absence of evidence. Collapsing them
would let an unmigrated package look verified.

ri-08's `--strict-legacy` flag is the intended closer for this gap and is out of scope here.

### D3 — Producers run in `check` mode only; the checkpoint is read-only against the working tree

The checkpoint invokes producers through the existing
`registry.run_producer(producer_id, "check", repository, source_revision)` seam
(`registry.py:159-211`) — never `"generate"`.

This is what satisfies acceptance outcome #3 ("branch-local generated artifacts remain
isolated from canonical main artifacts"): the four current `check`-mode producers have no
write path into `docs/`, `docs/decisions/`, or `openspec/specs/`. It also means the
checkpoint cannot create the diff noise that a tracked report would otherwise risk.

**Precision about the strength of this guarantee.** `registry.run_producer` does not
*structurally* prevent a `check`-mode adapter from writing — nothing in the registry
enforces read-only behaviour, and the invariant holds because the four landed adapters
respect it, not because the seam forbids it. The checkpoint's tests assert it from both
sides (the mode argument passed, and a byte-identical tracked tree after a run against a
dirty worktree), which is the strongest available check. Downstream work must not read
this decision as a registry-level guarantee; **ri-10 in particular should assert
read-only-ness rather than assume it.**

Going through `registry.run_producer` rather than reimplementing dispatch is the
mitigation for Approach B's acknowledged cost — the drift surface between the two paths
is orchestration only, not producer semantics.

### D4 — Index namespace is `work_package`, keyed `<change-id>--<package-id>`

`semantic_adapter.py` gains a namespace parameter. The checkpoint passes
`--namespace-kind work_package --namespace-key <change-id>--<package-id>`; the existing
`main`/`main` values remain the default so ri-07's behaviour is unchanged.

Isolation is then enforced by machinery that already exists and is already tested:
promotion into the canonical index is gated on
`namespace_kind is MAIN and namespace_key == "main"`
(`indexing_runtime_models.py:130-136`, `indexing_runtime.py:405,417,442`). A checkpoint
literally cannot reach the promotion path.

The `--` separator matches the existing worktree branch convention
(`worktree.py:331-356`), which exists because git cannot hold both `refs/heads/a/b` and
`refs/heads/a/b/c`. Reusing it keeps one naming rule in the system.

### D5 — Read scope is threaded from ri-08 `index_scopes()` into the indexer argv

The checkpoint resolves the package's permitted read set via ri-08's
`index_scopes()` / `IndexScopes.allows()` (`context_impact.py:163-187`, which resolves
`read_allow` minus `deny` with deny winning) and passes it to the indexer as
`--read-allow` / `--deny`.

Enforcement is downstream and pre-existing: `indexing_policy.py:228` rejects a path that
does not match a non-empty `read_allow`. ri-09 supplies the policy; it does not
reimplement the check.

### D6 — Architecture coverage is a graph diff against the merge-base, not a slice

`architecture-provenance.schema.json` pins `mode` to the enum `full|quick`; there is no
slice mode and adding one would be a contract change. `diff_architecture.py` already
exists standalone (`--baseline --current --output`, `diff_graphs()` at `:51`) and is wired
into nothing.

The checkpoint therefore reports two independent architecture facts:

1. **Freshness** — the read-only, mtime-independent provenance comparison, answering "is
   this branch's architecture artifact current for this revision?"
2. **Delta** — `diff_architecture.py` between the merge-base `architecture.graph.json`
   (read out of git with `git show <base>:<path>`) and the **working-tree** graph,
   yielding the affected architecture nodes for the report.

These answer different questions and can disagree: a stale artifact produces an empty or
misleading delta. The report carries both, and a stale-artifact delta is labelled as such
rather than presented as authoritative. That labelling is enforced by the contract, not
merely described — `context-checkpoint.schema.json` carries an `if/then` making
`delta_authoritative: true` invalid whenever `freshness` is not `fresh`.

**Working-tree, not committed, is the correct "current" side.** A checkpoint exists to
describe a branch mid-flight; diffing two *committed* graphs would blind it during exactly
the window it is for — an uncommitted worktree between package completion and commit. The
freshness finding already carries the caveat that the working-tree graph may be stale, so
nothing is lost by reading it live.

**Freshness is read via `arch_utils.provenance.check_freshness`, not by shelling
`run_architecture.py --check`.** The CLI wrapper collapses ri-04's `stale` and `invalid`
into a single non-zero exit, and the report needs them distinct: `invalid` maps to
`unknown` ("we cannot vouch for this artifact"), which is not the same claim as `stale`
("this artifact is out of date"). Same computation and same provenance basis — only the
call boundary differs.

### D7 — The report is tracked, change-local, and byte-stable for a fixed revision

Target: `openspec/changes/<change-id>/context-checkpoints/<package-id>.json`, validated
against a new `openspec/schemas/context-checkpoint.schema.json`.

Tracked, because the stated purpose is review context and a reviewer reads the PR diff.
Byte-stability is achieved with the same rules ri-07 uses for its manifest
(`docs/project-context-refresh.md:68-84`): UTF-8, sorted keys, two-space indent, single
trailing newline, and exclusion of volatile fields — timestamps, attempt counters,
absolute paths, and raw exception text. Re-running a checkpoint at an unchanged revision
must produce no diff.

The schema is named `context-checkpoint.schema.json`, **not** `checkpoint.schema.json`,
because the latter is already the autopilot-roadmap resume-state contract in the same
directory.

### D8 — Report-only: a checkpoint never fails the build

`checkpoint.py` exits 0 whenever it produced a valid report, including when producers
report drift. Drift is data in the report, not an exit code.

ri-10 (`add-deterministic-context-drift-gates`) owns turning drift into a CI or merge
failure. Shipping a gate here would give ri-10 a gate to rework rather than a signal to
consume. The one non-zero exit is operational failure — the checkpoint could not produce
a valid report at all.

### D9 — The semantic index is degradable, never fatal

Inherited unchanged from ri-07 D4. When `POSTGRES_DSN` and the embedding configuration
are present the checkpoint indexes into its `work_package` namespace; when they are
absent it records a `not-configured` status with an `exact-search` fallback and continues.
An indexing error is reduced to a bounded reason, never raised.

This keeps one uniform posture toward the index across the orchestrator and the
checkpoint, rather than two.

### D10 — The common-dir blind spot is closed by an explicit assertion, not by `checkout_policy`

`checkout_policy.classify_checkout()` reasons about the worktree *path* only, so a write
to the clone-global git-common-dir passes it. Rather than widen that module — which would
change behaviour for every existing caller — the checkpoint asserts its own invariant
(D1) directly, and a regression test pins it.

Widening `checkout_policy` to understand common-dir writes is a reasonable future change
but would need its own proposal; it affects every mutating skill.

## Edge cases the decisions above did not resolve

These surfaced during implementation. Each is recorded with the resolution taken, so a
later reader does not mistake a deliberate choice for drift.

### The contract admits an `unmigrated` report that the trigger never produces

D2 says an unmigrated package produces no checkpoint, yet
`context-checkpoint.schema.json` accepts `context_impact.status: "unmigrated"`. That is
intentional and the two are kept separate rather than collapsed: **D2 owns the trigger**
(`should_checkpoint` returns `should_run=False` for unmigrated), while the **contract
stays total** — a caller that invokes a checkpoint directly still gets a schema-valid
report describing what it found. Narrowing the schema to make the state unrepresentable
would couple the report format to one caller's policy, and ri-10 may well want to record
"we looked, and this package was unmigrated".

### `undeclared` and `spurious_rationale` cannot be reported at all

ri-08's two *failing* statuses have no member in the contract's `context_impact.status`
enum, so a package in either state cannot produce a schema-valid report. This is treated
as "could not produce a valid report" under D8: the checkpoint raises, exits non-zero, and
writes nothing.

The alternative reading — exit 0 with a skip — was rejected because these statuses mean
the package's declaration is *wrong*, not merely absent. Silently skipping would make a
misdeclared package indistinguishable from a clean one, which is the same failure D2
avoids for `unmigrated`.

### A self-cancelling read scope degrades the index rather than failing the run

`ReadScope` rejects a scope whose `deny` cancels every `read_allow` glob, because an empty
`read_allow` means "no restriction" downstream — normalising it would *widen* the scope
rather than narrow it, turning a scope error into a scope escape.

When that happens the checkpoint follows D9 rather than aborting: the semantic index
degrades to `failed` with an `exact-search` fallback, and every deterministic producer
finding is retained. The deterministic half of the report is exactly the half that does
not depend on the scope, so discarding it would lose information for no safety gain.

## Risks and Open Questions

- **Namespace proliferation.** One index namespace per `(change, package)` creates
  Postgres identity per `repo_slug \0 namespace_kind \0 namespace_key \0 pipeline_fingerprint`
  (`indexer_pg.py:169-180`). There is no GC or retention on checkpoint namespaces. Left
  open; a retention policy is a candidate follow-up and is noted for ri-10/ri-11.
- **Conflict with the unmerged ri-03 branch.** `openspec/expose-fail-closed-semantic-code-search`
  rewrites `packages/code-search/**` and will need reconciling with the
  `semantic_adapter.py` namespace change when it lands.
- **PR #276 overlap.** `codebase-atlas` ships a "branch-local docs freshness gate";
  mechanical conflicts expected on `skills/pyproject.toml` and `skills/install-manifest.json`.

## Task-decomposition notes

Four task titles contain "and" and were deliberately kept fused, per the plan-feature
splitting heuristic's requirement that surviving conjunctions be recorded here:

- **1.3 install and mirror** — one outcome (the schema published), with the mirror
  regenerated by `install.sh` rather than hand-edited. Splitting would create a task whose
  only content is running a sync script.
- **2.3 namespace and scope parameters** — one signature change to one function. The two
  parameters are threaded through the same argv builder; splitting doubles the diff on
  `semantic_adapter.py` for no isolation benefit.
- **2.4 unchanged and green** — a single non-regression assertion, not two outcomes.
- **5.2 full suite and `openspec validate`** — one verification gate with two commands.

Checkpoint cadence deviates in Phase 3: tasks 3.1–3.4 are the TDD RED batch and carry no
interior checkpoint, because a checkpoint that asserts "tests are green" is meaningless
while tests are intentionally failing. The first Phase 3 checkpoint therefore lands at 3.6,
immediately after the implementation that turns them green. Six checkpoint markers cover
twenty-two sized tasks.

## Test Strategy

- **Isolation (D1)** — assert the refresh-operations directory under the resolved
  git-common-dir is unchanged across a checkpoint run.
- **Namespace (D4)** — assert the argv built by the adapter carries
  `work_package` / `<change-id>--<package-id>`, and that the default path still emits
  `main`/`main` so ri-07 is unregressed.
- **Scope (D5)** — a package whose `deny` excludes a path must produce argv that excludes
  it; deny must win over `read_allow`.
- **Read-only (D3)** — a checkpoint run against a dirty tree leaves every tracked producer
  output byte-identical.
- **Determinism (D7)** — two runs at one revision produce identical bytes; schema
  validation passes.
- **Trigger (D2)** — a package with no `context_impact` block yields no checkpoint and the
  reason `unmigrated`; an explicit empty `surfaces` list is distinguished from it.
- **Degradation (D9)** — with no `POSTGRES_DSN`, the report records `not-configured` and
  the run still exits 0.
