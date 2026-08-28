# Design — rescope-context-drift-enforcement

## Context

The gate is a fitness function whose verdict is currently a function of the environment it
runs in, not only of the tree it judges. Three consumers depend on it: the CI check, the
`make context-drift-gate` local command, and — once promoted — branch protection. The
promotion is what forces the issue: an advisory check that disagrees with itself is an
annoyance, a required one is an outage.

Verified during planning, on a branch byte-identical to `origin/main`:

| Invocation | Outcome | Diff size |
|---|---|---|
| `--base main` (stale local ref) | drift, exit 2 | `main...HEAD` = 53 files |
| `--base origin/main` | fresh, exit 0 | `origin/main...HEAD` = 0 files |
| CI job `98378668232`, same tree | success | — |

## Decisions

### D1 — Base resolution prefers the remote ref, and records what it chose

Order: `origin/<base>` when it resolves, else the local ref, else error. The report records
the resolved revision.

`origin/<base>` is preferred because `describe_tree` (`gate.py:735`) already compares
against it, and because a fresh `actions/checkout` has no local base branch, so CI is
already effectively using it. Preferring the local ref instead would make CI the outlier and
would not fix the reproducibility failure.

Recording the resolved revision is not decoration. Today the ambiguity is invisible: the
report states `commits_behind_base_upstream: 0` while the drift it reports derives from
being behind. A reader cannot tell which base produced which claim.

**Rejected**: making `--base` mandatory. That moves the ambiguity into every caller and
breaks `test_gate.py:824`, which asserts the Makefile invocation matches CI's.

### D2 — Attribution uses path-level ancestry, not content

`git diff --name-only <provenance.source_revision>..<merge_base> -- <input_roots>`.

Content comparison is unavailable at another revision: `_iter_root_files_git`
(`provenance.py:326`) uses `git ls-files --cached --others --exclude-standard`, which takes
no revision, and `_discover` (`provenance.py:394`) calls `read_bytes()` on the filesystem
path. Making them revision-aware would mean hashing `git cat-file` output, and `ls-tree`
yields git blob SHAs rather than the `sha256` the payload hashes — changing the payload
format invalidates every recorded `input_fingerprint`.

Path-level is sound for this question because attribution is coarser than freshness. It can
misclassify introduced drift as inherited only when a file changed and changed back within
the range. That is the safe direction: the failure being fixed is *falsely blaming a
branch*, so the bias must run away from blame.

### D3 — Attribution is a separate axis, not a fifth group

`classify_degradation` keeps its four disjoint groups and its purity. Attribution is
computed alongside and attached to findings in the report.

This is forced by two constraints. `test_classify_degradation.py:235` hard-pins
`INFORMATIONAL_PRODUCERS == frozenset({OPENSPEC_PROJECTION})`, and `TestPurity`
(`test_classify_degradation.py:374-435`) asserts the function performs no IO by patching.
Attribution *requires* IO — it shells out to git. Folding it in would break both, and would
conflate "how severe" with "whose fault", which are independent.

### D4 — Event behaviour lives inside one always-running job

The gate job keeps running on all three events and branches on
`EVENT_NAME: ${{ github.event_name }}` inside the step, with an explicit `*)` arm that
exits non-zero.

This is the repository's established shape, not an invention:
`requirement-traceability-sweep` (`ci.yml:626`, dispatch at `ci.yml:737-798`) does exactly
this, and its comment rejects the job-level `if:` alternative — *"a required check that does
not run on `merge_group` is not a check on the merge candidate, and an unguarded job on an
event with no rule below is the unfalsifiable green this gate exists to prevent."*

**Rejected**: `if: github.event_name != 'pull_request'` on the job. A skipped required check
reports success to branch protection, which is the precise hazard the existing comment
names.

### D5 — The servo is confined to dependabot, and to a job-scoped write grant

Three constraints, each traceable to a documented failure:

1. **Regenerate against a current base.** `docs/merge-logs/2026-08-24.md:29` records that
   `rerun-checks` was "theatre" because it replays the same merge commit; the fix was
   `refresh-branch`. A servo that regenerates on a stale base commits artifacts that are
   themselves drift.
2. **Same argv for check and write.** `generate_tool_descriptor.py:570-573`: *"`--check`
   asserts byte identity against what it would generate from its own argv, so passing flags
   here that the write step does not (or vice versa) reports drift on a perfectly
   up-to-date file."* A servo whose regenerate command differs from the gate's check command
   oscillates forever.
3. **Never emit a degenerate artifact.** Same file, `:296-304`: a write path that can emit an
   empty artifact "would make the byte-identity assertion compare empty against empty
   forever."

Write permission is declared on the remediation job only. Both workflows are
`permissions: contents: read` today with no job-level overrides anywhere, and `GITHUB_TOKEN`
appears once as a read token — so this is the repository's first write grant, and confining
it is the whole reason the scope is dependabot-only.

**Rejected**: a servo on all pull requests. Larger blast radius for the first write
escalation, and human PRs already have an author who can run one command.

### D6 — Context-impact attributes by declared scope

A changed path is attributed to a work package when that package's declared scope covers
it. Co-presence in a diff is not authorship.

Archiving always moves a `work-packages.yaml` into the diff while the surrounding commit
regenerates unrelated artifacts — which is exactly how PR #423 produced
`wp-integration: undeclared surface 'decisions'`, blaming an archived change for five
decision documents the archive commit itself had regenerated.

### D7 — Metrics are an additive event type

`event_type` on `MergeEvent` (`merge_events.py:28`) is an open `str`, and `to_dict()`
(`:41`) drops `None` fields, so a `context_gate` record adds no required field to existing
readers. `merge_metrics.py:27-31` switches on known types and ignores others.

### D8 — Both promotion notes are rewritten together

`introduce-fitness-function-gates` wrote `session-completion.md:69-115` immediately below
the known-gap section, back-referencing it as *"Same additive endpoint as the
`context-drift-gate` promotion above"*, and `specs/fitness-functions/spec.md:115-116` makes
that adjacency normative. Deleting one note alone leaves a spec-level claim pointing at
nothing.

## Migration

Ordering matters because later phases depend on earlier semantics:

1. Base resolution lands first. Attribution against an unpinned base is meaningless.
2. Attribution lands second, reported but not yet affecting exit codes.
3. Event-aware exit codes land third, once attribution is trustworthy.
4. The servo lands last, because it acts on the gate's verdict.

Phases 1–3 are observable before they are enforced: after phase 2 the report carries
attribution while exit codes are unchanged, which is the window for reading real runs before
the flip.

## Rollback

Each phase reverts independently. Reverting the exit-code phase restores today's behaviour
while leaving the recorded base revision and attribution in the report — strictly more
information than today, with the old verdict. Reverting the servo removes the only write
grant. No durable record changes, so nothing needs migrating back.

## Risks

| Risk | Mitigation |
|---|---|
| Attribution wrongly marks introduced drift inherited, letting real drift through on a PR | It still blocks at `merge_group` and on `push: main`, where all blocking drift counts — the merge candidate is checked before it lands |
| The servo pushes a bad commit to a dependabot branch | Dependabot branches are disposable; the servo never touches human branches, and a wrong artifact is caught by the gate on the same PR |
| First `contents: write` grant becomes a template for wider use | The requirement makes the confinement normative, not conventional — a scenario asserts no workflow-level grant exists |
| `test_gate.py` (~890 lines) pins current report shape | Report additions are additive; the schema's `tree` block is already outside the top-level `required` list for exactly this reason |
| Ruff 0.16.0 blocking gate on the three edited files | `install.sh` re-run and `ruff check` are explicit tasks, not checkpoint afterthoughts |
