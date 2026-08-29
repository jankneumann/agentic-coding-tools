# DRAFT — rescope-context-drift-enforcement

> **Status: draft only. This is not a change directory, and this file is not an
> OpenSpec artifact.** It is stored inside `fix-architecture-freshness-evidence/`
> because that change's `proposal.md` defers items 4-7 to it, and a scratch file is
> not a durable home for the reasoning.
>
> `rescope-context-drift-enforcement` cannot become a real change until the four
> prerequisite changes are archived (see Preconditions). A change with no spec deltas
> fails `openspec validate --strict`, and `validate-specs` is a required status check;
> the deltas below have no archived baseline to modify until archiving completes.
>
> Once the precondition clears, run `/plan-feature` against this text. It carries the
> planning evidence -- file:line references, mechanism trade-offs, and the test pins an
> implementer will hit -- that would otherwise have to be rediscovered.

## Why

The deterministic context drift gate reports drift accurately and attributes it wrongly.

`gate.py:600-650` evaluates whole-tree producer freshness at the checked-out revision.
Only the work-package context-impact sub-check is scoped to `git diff main...HEAD`.
On a `pull_request` event `actions/checkout` supplies the *merge commit*, so every open
PR inherits whatever drift already exists on `main`. The consequence is recorded in
`docs/merge-logs/2026-08-24.md:26`:

> `context-drift-gate` failed identically on 12 unrelated PRs, including 1-line
> dependabot bumps that cannot cause context drift. Gate log named the cause:
> unarchived OpenSpec changes plus stale architecture artifacts **at the PR's merge
> base**.

The remediation was `refresh-branch`, and three of the nine PRs needed a *second*
refresh once the convergence commit landed. That is the signature of a gate whose
verdict is a function of `main`'s tip rather than of the branch under test.

This blocks something the repository has already decided it wants.
`docs/guides/session-completion.md:26-67` documents the branch-protection promotion as
an open gap — the `gh api` call is written out, awaiting one precondition: *"Do not
apply the promotion until the gate is green on `main`; making a red check required
blocks every merge."* The gate cannot be reliably green while it blames every PR for
`main`'s debt. Fixing attribution is therefore not a weakening of the gate; it is the
precondition for strict enforcement.

The guide also records why simply deleting the PR gate is not an option: `docs/decisions/`
drifted on `main` in the first place (issue #157) precisely because a non-required check
was repeatedly merged past while red. That experiment has already been run.

## Preconditions

Four changes are task-complete but unarchived, and they own every requirement this
change modifies:

| Change | Tasks | Owns |
|---|---|---|
| `add-deterministic-context-drift-gates` | 33/33 | gate exit codes, drift classification, provenance baseline |
| `add-deterministic-context-producer-checks` | 22/22 | the whole `project-context-refresh` capability |
| `integrate-main-context-convergence` | 38/38 | `merge-pull-requests` Step 11.6 convergence |
| `add-branch-local-context-checkpoints` | 28/28 | orchestration, skill-workflow |

Archiving them is itself worth doing independently: `openspec.projection` drift is
permanently informational (`orchestrator.py:472`) because active changes always carry
unmerged spec deltas, and unarchived changes were one of the two named causes of the
12-PR incident.

## What Changes

### 1. Attribute drift to its owner (item 4)

The gate gains an inherited-vs-introduced classification on `pull_request`. Drift
already present at the merge base is reported as an annotation naming `main` as owner;
drift the branch introduced remains a failure. `commits_behind_base_upstream` — already
computed by `describe_tree` (`gate.py:709-753`) — is surfaced in the message.

**Mechanism.** `compute_input_fingerprint` reads working-tree bytes only:
`_iter_root_files_git` (`provenance.py:326`) uses `git ls-files --cached --others
--exclude-standard`, which takes no revision, and `_discover` (`provenance.py:394`)
calls `read_bytes()` on the filesystem path. Three routes exist, in ascending cost:

- **Path-only ancestry inference (recommended).** `git diff --name-only
  <provenance.source_revision>..<merge_base> -- <input_roots>`. If no relevant path
  changed, the base was fresh; if some did, it was already stale. No content hashing, no
  payload-format change, no second checkout. Precedent: `checkpoint.py:339` already
  reads baseline artifacts via `git show <merge-base>:<path>`, and `checkpoint.py:385`
  resolves merge bases. Inherited-vs-introduced is a coarser question than freshness
  itself, so a path-level over-approximation is sound — it can only misclassify
  introduced drift as inherited when a file changed and changed back, which is the safe
  direction for a gate that is trying to stop blaming PRs.
- **Revision-aware primitives.** Add `git ls-tree` + `cat-file --batch` alongside the
  working-tree path. Most precise, but `ls-tree` yields git blob SHAs rather than the
  `sha256` the payload hashes, so the payload format would change and invalidate every
  recorded `input_fingerprint`.
- **Second checkout.** `git worktree add --detach` at the merge base in CI only. Provably
  correct — `test_provenance.py:346` already proves clone-equality — at the cost of CI time.

### 2. Move the blocking claim to where it is well-defined (item 5)

The blocking verdict moves to `merge_group` and `push: main`; `pull_request` keeps a
reporting run. A whole-tree freshness claim is only well-defined at `main`'s tip, and
`merge_group` evaluates exactly the prospective tip *before* it lands.

The reusable normative precedent is `gen-eval-framework/spec.md:1234`: *"The sweep SHALL
run as a single CI job on three events — `pull_request`, `merge_group`, and `push` to the
integration branch. […] A required check that does not run on `merge_group` is not a
check on the merge candidate."* No requirement currently governs the drift gate's event
set at all — `ci.yml:206` carries no `if:` guard and silently inherits the workflow-level
`on:`.

**The convergence window must be designed around.** `main_convergence.py` does not push
the merge: `merge_pr.py:381` shells out to `gh pr merge`, so GitHub lands the merge commit
server-side, and the convergence commit is a separate later local push
(`main_convergence.py:1601`, then `:1633`). `main` is therefore transiently stale between
the two. A required check on `push: main` would turn `main` red for that window. Options:
key the main-tip gate on the `Context-Refresh-Operation:` trailer (`main_convergence.py:940`)
or the ri-06 operation record, both of which already exist for idempotence.

### 3. Auto-remediate the cheap producers (item 6)

`documentation.inventory`, `decisions.timeline`, and `api.contracts` are small,
byte-deterministic, and fast. A CI job regenerates and commits to the PR branch,
converting a gate into a servo. The `architecture` producer is explicitly excluded — it
needs tree-sitter and writes megabytes. Push permissions, loop prevention, and rebase
interaction all need design.

### 4. Instrument the ratchet (item 7)

Log per gate run whether drift was inherited or introduced. `docs/merge-logs/metrics.jsonl`
exists with a `MergeEvent` schema (`merge_events.py:26-45`) whose `event_type` is an open
string, so a `context_gate` event type is additive. This gives the advisory→blocking flip
evidence, consistent with the documented `clean_runs_before_flip: 3` vocabulary in
`architecture.config.yaml`.

## Acceptance criterion

`context-drift-gate` is green on `main` across a week of real PRs, and the promotion in
`docs/guides/session-completion.md:47-53` is applied so that
`gh api .../required_status_checks --jq '.contexts'` lists all seven contexts. The guide
instructs deleting its "known gap" section once that holds.

## Known constraints for the implementer

- `test_classify_degradation.py:235` **hard-pins**
  `INFORMATIONAL_PRODUCERS == frozenset({OPENSPEC_PROJECTION})`. Any reclassification
  breaks it deliberately. The `informational_producer_ids` keyword on
  `classify_degradation` (`orchestrator.py:518`) is already the injectable seam.
- `test_gate.py:824` (`test_makefile_target_reproduces_the_ci_invocation`) parses the
  `Makefile` to assert the CI invocation matches. Changing the target signature breaks it.
- `gate.py:665-667` has a fallback that calls `describe_tree` with the *default* base when
  `tree=None`, diverging from the passed `--base`. Rescoping `base` must address it.
- `cli.py:372-379`'s `--base` help text claims it is "used only to scope work-package
  context-impact validation". That is already stale — `run_gate:575` uses it
  unconditionally for `describe_tree`.
- `gate-drift-with-mirrors-hooks-and-blocking-ci` (0/10) will add a mirror-drift CI job;
  every `skills/` edit needs `install.sh` re-run before push.

## Relationship to `fix-architecture-freshness-evidence`

That change (items 1-3 of the original seven) is independent and lands first. It repairs
the RPC probe's wall-clock staleness, declares the heavy generated JSON unmergeable, and
demotes 2.76 MB of artifacts to a `local-cache` tier. None of its work depends on the
spec baseline this change needs.
