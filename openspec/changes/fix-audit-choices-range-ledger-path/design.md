# Design: fix-audit-choices-range-ledger-path

## Context

`run_audit.py` has one path derivation, at line 145:

```python
change_dir = repo_root / "openspec" / "changes" / change_id
```

`change_id` arrives unvalidated. For the change-id form it is a change id and
the result is right. For the standalone form it is `range:<base>..<head>`, and
the result is a directory named after a commit range inside the active-changes
tree.

`prioritize-proposals` is the only other producer of an artifact carrying the
six-field header (`schema_version`, `generated_at`, `git_sha`, `generator`,
`run_id`, `event_kind`). It hit the same problem and resolved it explicitly:
`prioritize-proposals/SKILL.md` states that the legacy
`openspec/changes/prioritized-proposals.{md,json}` paths "belong to the
openspec/changes/ namespace and were the wrong home for a meta-report", and the
output moved to `openspec/priorities/<YYYY-MM-DD>-HHMMSS-<sha7>/`.

## Goals / Non-Goals

**Goals**

- A standalone range audit writes somewhere that is not the active-changes tree.
- The change-id form is byte-for-byte unchanged.
- The run-id format has one definition rather than two.
- `prioritize-proposals` keeps writing exactly what it writes today.

**Non-Goals**

- No change to the schema, the ledger format, the entry pipeline, the six-field
  header, or the always-exit-0 contract.
- No change to the recorded `change_id`. It stays `range:<base>..<head>`, which
  canonical scenario `skill-workflow.12` pins.
- Not the full codeviz shared-helper migration. `artifact_header.py` is left
  where it is; only path construction moves. That migration is a roadmap item
  with its own sequencing, and this change should not pre-empt the rest of it.

## Decisions

- **D1: Destination is `openspec/choices/<YYYY-MM-DD>-HHMMSS-<sha7>/`.**
  Mirrors the one shipped instance of this artifact class, including
  `latest.{json,md}` rewritten at `openspec/choices/` for most-recent access.
  The run directory is tracked, like `openspec/priorities/`.
  - *Alternative rejected*: the codeviz roadmap's
    `<dir>/<YYYY-MM-DD>/<run-id>.json`. It is the written rule, but it has
    never shipped, it disagrees with the working implementation, and it names a
    single `.json` where this artifact is a `.json` + `.md` pair. Following an
    unshipped rule over a shipped precedent would leave the repository with two
    layouts for one artifact class instead of one.
  - *Alternative rejected*: encoding the range in the path with an escaping
    scheme. Nothing in this repository encodes a commit range in a path, and
    `audited_range` already carries both full shas in the payload, so the range
    is recoverable from file contents. The shipped precedent puts run identity
    in the path and everything else in the payload.

- **D2: The shared module holds the run-id format, not the filenames.**
  `skills/shared/artifact_paths.py` exports `build_run_id(now, head_sha)` and
  `RUN_ID_RE`. Each producer keeps its own small frozen dataclass naming its own
  files, because they do not share those: `prioritize-proposals` writes
  `report.{md,json}` and `audit-choices` writes `choices.{json,md}`. A shared
  `build_paths` would have to know about both callers, which is the coupling
  this approach was chosen to avoid.
  - `skills/shared/` is declared in `install-manifest.json` under
    `shared_libraries`, so it ships with every skill automatically. No
    `cross_skill_dependencies` entry is needed, and the dependency-direction
    linter names `skills/shared/` as an explicitly permitted import source.

- **D3: `apply_retention` moves to the shared module too.** It operates purely
  on a directory of run-id-named subdirectories and is the same concern. Leaving
  it in `prioritize-proposals` would mean copying it into `audit-choices`,
  reintroducing for retention exactly the duplication D2 removes for paths.
  Archive-not-delete semantics and the default retain count are preserved as-is.

- **D4: The `prioritize-proposals` migration is guarded by a characterization
  test written first.** That skill is being refactored to fix a bug in a
  different skill, which is the shape of change that quietly alters behavior.
  A test pins its current on-disk output — directory name, both filenames,
  `latest.*` contents, and the archive destination — before any code moves, and
  must pass unchanged afterwards. The migration may not change a byte of what
  it writes.

- **D5: Destination routing lives in `run_audit.py`, keyed on the recorded id.**
  A single helper maps the recorded `change_id` to an output directory: ids
  beginning `range:` route to the dated run directory, everything else to
  `openspec/changes/<change-id>/`. Keeping the branch in the driver rather than
  in the shared module means the shared module stays ignorant of OpenSpec
  concepts, and the routing is one function to test directly.
  - The prefix test is on the **recorded** id, which the skill controls and the
    canonical spec pins, not on the raw argument. A change id that merely
    contains `..` or a colon is not special.

- **D6: The read-only contract names both destinations.** `SKILL.md`'s
  Read-Only Contract and its matching Red Flags line are both written today as
  `openspec/changes/<change-id>/choices.json` and `choices.md`. Both gain the
  range-form destination explicitly rather than being loosened to a rule, so
  `test_readonly_posture.py` keeps asserting a literal, checkable set. The
  posture test gains a range-form case proving such a run writes only to the
  new location.

## Risks / Trade-offs

- **Refactoring a working skill to fix another.** Accepted, and mitigated by
  D4's characterization test. The alternative was a third copy of the run-id
  format, which the operator explicitly chose against.
- **A new tracked tree grows over time.** `openspec/choices/` accumulates one
  directory per standalone audit. D3 carries the retention policy across, so it
  is bounded the same way `openspec/priorities/` is.
- **Two layouts remain in the repository for event artifacts** — this one and
  the codeviz roadmap's unshipped mandate. This change does not resolve that
  disagreement; it picks the shipped side and says so, leaving the roadmap item
  to reconcile them.

## Migration Plan

Additive plus one guarded refactor. Order: characterization test for
`prioritize-proposals` (before anything moves), then the shared module, then the
`prioritize-proposals` migration, then the `audit-choices` routing and its
tests, then the contract wording and docs. Rollback is reverting the shared
module and restoring the two original call sites; no on-disk artifact format
changes, so ledgers and reports already written stay valid either way.
