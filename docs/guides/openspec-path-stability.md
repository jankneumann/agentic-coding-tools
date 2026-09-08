# OpenSpec path stability in tests

## The rule

**A test must never hold `openspec/changes/<change-id>/` as a literal path.**

`openspec archive <id>` moves the directory to
`openspec/changes/archive/<YYYY-MM-DD>-<id>/`. Any test that pinned the active
path breaks at that moment — and the moment has nothing to do with what the test
guards.

Enforced by `skills/tests/openspec_paths/test_change_path_stability.py`, which
fails any test file containing a literal path naming a change id the repo
actually has. Synthetic ids used as fixtures (`my-change`, `foo`,
`add-health-check-endpoint`) are not flagged, because the guard matches against
change ids read off the filesystem rather than against a regex shape.

## Why this failure mode is worse than it looks

Three properties combine badly:

1. **The failure is uncorrelated with the cause.** The test breaks on the day its
   change *lands*, not the day its contract *drifts*. Whoever archives the change
   gets a failure in a test they have never read, about a contract they did not
   touch.
2. **It is invisible until it fires.** The pinned path is correct for the whole
   active life of the change. No review, no CI run, and no local test pass can
   surface it beforehand.
3. **It fires once, permanently.** Archival happens once per change, often long
   after the test was written and after its author has moved on.

A test cannot be reviewed into safety here. That is why there is a guard.

## Incident record

| Date | What broke | How it was found |
|---|---|---|
| ~2026-05 | `run_eval.py:31`'s `REPO_ROOT = HERE.parents[3]` — "correct only until archival added a path segment", making the D9 evaluation unreproducible | recorded in `packages/context-eval/tests/test_promoted_contracts.py` |
| 2026-07-25 | `packages/code-search/tests/test_index_record_contract.py` (8 assertions) when `add-revision-aware-semantic-index-registry` archived | **nothing** — CI runs only `gen-eval` and `context-eval` of the four `packages/` suites, so it sat red for six weeks |
| 2026-09-08 | 30 assertions across 4 files, in one archive sweep | CI, after the fact |

The 2026-09-08 sweep is the instructive one. Twenty-one of those assertions were
in `skills/tests/context-engineering/test_promoted_semantic_context_contracts.py`
— a file whose entire purpose is preventing archive-drift. Its docstring names
the hazard exactly ("moves to `openspec/changes/archive/<date>-<id>/` the moment
this change is archived"), and design decision D10 requires promoting the schema
inside the change so no consumer can bind to a vanishing path. The guard then
bound to that path itself and failed on the event it existed to make safe.

The promotion it enforced was correct throughout — the promoted copies were
intact. Only the guard's own footing was wrong. **A rule can be enforced
correctly by a mechanism that does not apply the rule to itself.**

## What to do instead

### First: do you need the change-local copy at all?

For **contracts**, usually not. The stable home is
`openspec/contracts/<capability>/` (see `openspec/contracts/README.md`), and a
change is expected to promote its contract there *within* the change, precisely
so consumers never bind to a path that disappears.

`packages/context-eval/tests/test_promoted_contracts.py` is the exemplar: it
loads the promoted copy for every assertion, and reads the change-local copy only
to byte-compare the two. Archival cannot break it.

If you are reaching into a change directory for a contract, prefer promoting the
contract and reading the promoted path.

### Otherwise: resolve at read time

```python
from openspec_paths import change_dir, repo_root_from

CHANGE = change_dir(repo_root_from(__file__, 3), "some-change-id")
CONTRACT = CHANGE / "contracts" / "thing.schema.json"
```

`change_dir` returns the active directory when it exists and the most recent
`archive/<date>-<id>/` otherwise. There is no stored path, so nothing runs at
archive time and nothing can be bypassed.

`repo_root_from(__file__, N)` replaces a bare `parents[N]`. That index is
archive-fragile in its own right: a path segment added or removed above the test
silently changes which directory you get, with no error — which is exactly the
~2026-05 incident in the table above.

### Where the helper lives

The three test trees have separate virtualenvs and no shared importable package,
so the helper is mirrored, and the copies are pinned byte-identical by
`test_shared_helper_copies_are_byte_identical`:

| Tree | Helper | Import works because |
|---|---|---|
| `skills/` | `skills/tests/_shared/openspec_paths.py` | `pythonpath = ["tests/_shared"]` in `skills/pyproject.toml` |
| `agent-coordinator/` | `agent-coordinator/tests/_shared/openspec_paths.py` | same setting in `agent-coordinator/pyproject.toml` |
| `packages/*/` | inline copy | each package has its own venv and no path to either |

Adding a fourth copy is fine; add it to the byte-identity test's list.

## Considered and rejected: a path registry updated at archive time

The intuitive fix is to record each change's current path somewhere and have the
archive step rewrite it. It was rejected for three reasons:

1. **A change-local config moves with the change.** If the file lives inside
   `openspec/changes/<id>/`, archival relocates it too, and the test still cannot
   find it — the bootstrapping problem simply recurses one level.
2. **`openspec archive` is a third-party CLI** (v1.7.0). It cannot be hooked, so
   the rewrite must live in a wrapper such as `/cleanup-feature`. A direct
   `openspec archive` — the documented CLI fallback, and what the 2026-09-08
   sweep actually ran twelve times — would silently skip it.
3. **It is another write-step that can fail to run.** This repo has already been
   burned by that shape: the 2026-05-12 incident, where a deferred `make
   decisions` left a stale decision index blocking every unrelated PR until
   someone bisected it.

A registry would also store the archive date, which the filesystem already
knows. Resolving at read time needs no coordination between the test and the
archive operation, which is why it wins.

## Related

- `openspec/contracts/README.md` — the stable contract home and why promotion exists
- [worktree management guide](worktree-management.md)
- [session completion guide](session-completion.md)
