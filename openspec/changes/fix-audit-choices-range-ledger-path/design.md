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
  `openspec/choices/` is created by the first standalone audit and is simply
  absent from a clean checkout until then — that absence is not drift, and no
  `.gitkeep` is added. `apply_retention` already tolerates a missing base
  directory (`list_active_runs` returns `[]`), so nothing has to seed it.
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
  `skills/shared/artifact_paths.py` exports `build_run_id(now, head_sha)`,
  `RUN_ID_RE`, and `parse_run_id` — the function that gives the regex its
  contract (`(date, "", "legacy")` for the legacy entries already on disk under
  `openspec/priorities/`) and the one `list_active_runs` calls. Each producer
  keeps its own small frozen dataclass naming its own files, because they do not
  share those: `prioritize-proposals` writes `report.{md,json}` and
  `audit-choices` writes `choices.{json,md}`. A shared `build_paths` would have
  to know about both callers, which is the coupling this approach was chosen to
  avoid.
  - `skills/shared/` is declared in `install-manifest.json` under
    `shared_libraries`, so it ships with every skill automatically. No
    `cross_skill_dependencies` entry is needed, and the dependency-direction
    linter names `skills/shared/` as an explicitly permitted import source.
  - **Import bootstrap.** The shared package is reached the way
    `worktree.py` reaches `shared.environment_profile`:
    `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` followed by
    `from shared.artifact_paths import ...`. `parents[2]` is `skills/` in the
    source tree and the install target (`.claude/skills/`, `.agents/skills/`,
    or a consumer repository's equivalent) in a runtime copy, because
    `install.sh` ships `shared/` as a sibling of every skill directory
    (`SHARED_LIBS`). Each importing module — `priorities_paths.py`,
    `retention.py`, `choices_paths.py` — carries the bootstrap itself, so it
    works both when a test imports the module through a `scripts/`-only
    `sys.path` entry and when `SKILL.md` runs it as a script.
  - `priorities_paths.py` re-exports `build_run_id`, `RUN_ID_RE` and
    `parse_run_id`; `retention.py` re-exports `apply_retention`,
    `list_active_runs`, `RetentionResult` and `ARCHIVE_DIRNAME`. Everything that
    imports those names from where they are today keeps working unchanged,
    which is what lets D4 require the existing tests to stay untouched.

- **D3: `apply_retention` moves to the shared module too.** It operates purely
  on a directory of run-id-named subdirectories and is the same concern. Leaving
  it in `prioritize-proposals` would mean copying it into `audit-choices`,
  reintroducing for retention exactly the duplication D2 removes for paths.
  Archive-not-delete semantics and the default retain count are preserved as-is.
  - The default lives in one place: the shared module exports
    `DEFAULT_RETAIN = 30`, the value `retention.py`'s CLI default and
    `prioritize-proposals/SKILL.md`'s `RETAIN_N` both hard-code today. Both
    callers use it. The Plan phase left the count for `openspec/choices/` as an
    open question; it is kept at 30 rather than re-derived, because nothing
    about a choices ledger makes it cheaper or dearer to keep than a priorities
    report, and one number for one artifact class is the point of D3.

- **D4: The `prioritize-proposals` migration is guarded by a characterization
  test written first.** That skill is being refactored to fix a bug in a
  different skill, which is the shape of change that quietly alters behavior.
  A test pins its current on-disk output — directory name, both filenames,
  `latest.*` contents, and the archive destination — before any code moves, and
  must pass unchanged afterwards. The migration may not change a byte of what
  it writes.
  - The guard has three parts, because the function-level pin alone would not
    catch the one failure this migration actually introduces. **(1)** The
    function-level pins above, asserting exact strings. **(2)** Subprocess cases
    that invoke the entry points `prioritize-proposals/SKILL.md` really calls —
    `priorities_paths.py run-id`, `priorities_paths.py paths <id> --base`, and
    `retention.py --base --retain` — from a runtime-shaped copy of the scripts
    (`<tmp>/prioritize-proposals/scripts/` beside `<tmp>/shared/`). No existing
    test runs these as subprocesses (`test_smoke_e2e.py` exercises only
    `artifact_header.py`), and the D2 import bootstrap can only fail when a
    module runs as a script from an installed copy — precisely the path the
    skill's bash uses and the tests otherwise never take. **(3)** The three
    pre-existing test modules — `test_priorities_paths.py`, `test_retention.py`,
    `test_smoke_e2e.py` — are not edited. The work package verifies this with
    `git diff --quiet` against the merge base, so D2's re-exports are proven by
    tests that predate the change rather than by tests written alongside it.
  - `prioritize-proposals/SKILL.md` does not change: its invocations are the
    CLI entry points, and those are unchanged by construction.

- **D5: Destination routing lives in `run_audit.py`, keyed on the recorded id.**
  A single helper maps the recorded `change_id` to an output directory: ids
  beginning `range:` route to the dated run directory, everything else to
  `openspec/changes/<change-id>/`. Keeping the branch in the driver rather than
  in the shared module means the shared module stays ignorant of OpenSpec
  concepts, and the routing is one function to test directly.
  - The prefix test is on the **recorded** id, which the skill controls and the
    canonical spec pins, not on the raw argument. A change id that merely
    contains `..` or a colon is not special.
  - `collect_evidence.py` derives the same `openspec/changes/<change_id>` path
    for its own purpose — reading `proposal.md`, `session-log.md` and the other
    change artifacts into the evidence bundle — and is deliberately left alone.
    It only reads; a missing directory degrades to empty excerpts by design;
    and a range audit has no change artifacts to read in the first place. It
    never creates a directory, which is what task 4.3's "no `range:` directory
    anywhere under `openspec/changes/`" assertion relies on. Routing it through
    the D5 helper would make the collector look for change artifacts inside a
    dated run directory, which is meaningless.

- **D6: The read-only contract names both destinations and every effect of a
  range run.** `SKILL.md`'s Read-Only Contract and its matching Red Flags line
  are both written today as `openspec/changes/<change-id>/choices.json` and
  `choices.md`. Both gain the range-form destination explicitly rather than
  being loosened to a rule, so `test_readonly_posture.py` keeps asserting a
  literal, checkable set. The posture test gains a range-form case proving such
  a run writes only to the new location.
  - A range run has exactly three permitted effects, and the contract names all
    three: the run directory's `choices.{json,md}`; the `latest.{json,md}`
    rewrite at `openspec/choices/`; and retention's move of older run
    directories into `openspec/choices/archive/`. Naming only the first two
    would have the skill violate its own Red Flags bullet by design on the
    thirty-first standalone audit.
  - `latest.*` are byte-identical copies of the run's pair, made with
    `shutil.copyfile` — the same relationship `prioritize-proposals` has
    between `report.*` and its `latest.*`. The contract's "only writer"
    sentence is reworded accordingly: `write_ledger_pair` stays the only thing
    that *produces* ledger content; the copy produces none, and retention moves
    directories without opening a file.
  - The Output section of `SKILL.md` lists the range-form destination alongside
    the change-id one, for the same literal-set reason.

- **D7: The run directory is named from the header the ledger already
  carries.** The dated directory is built from the same two values the
  driver hands `make_header`: its `resolved_now` datetime and
  `resolved_git_sha`. Pass those, **not** `header["generated_at"]` —
  `make_header` stores that field as a formatted string
  (`%Y-%m-%dT%H:%M:%SZ`) while `build_run_id` requires a UTC-aware datetime and
  raises on anything else. The directory therefore encodes the same `now` and
  repository `HEAD` the ledger's six-field header records.

  **The header derives the base run id, not necessarily the directory name.**
  D8's collision guard can place a run at a `-2` / `-3` sibling of that base,
  and the suffix is not recorded anywhere in the header — the schema is out of
  scope for this change, so there is nowhere to put it. A ledger's location is
  therefore *discoverable* from its own contents rather than computable from
  them: derive the base with `build_run_id`, then glob `<base>*` under the
  standalone-audit root and match on the ledger's `audited_range`. That is a
  weaker property than the first draft of this decision claimed, and it is the
  true one — so a ledger's location is derivable from its own contents,
  and the run-id means the same thing it means for `prioritize-proposals`: when
  and at what `HEAD` the artifact was produced. The audited head is not the
  input: it is already recorded in `audited_range`, and D1 puts run identity in
  the path and everything else in the payload.
  - The header's `run_id` field stays the caller's. `run_audit.py` requires
    `--run-id`, and `iterate-on-implementation` passes
    `iterate-on-implementation-<UTC ISO timestamp>` so a ledger can be traced to
    the workflow run that produced it. That is a different identity from the
    directory's, and unlike `prioritize-proposals` the two are not made equal:
    forcing the caller's id into the path would put an uncontrolled string
    back into a directory name, which is the defect being fixed.
  - *Alternative rejected*: naming the directory from the audited `head_sha`.
    It reads naturally ("the audit of that head") but two audits of the same
    range at different `HEAD`s would differ only by timestamp while claiming
    the same sha, and the value is one lookup away in `audited_range`.
  - This decision was taken without a user in the loop (autopilot sub-agent);
    it is recorded here as a decision rather than an assumption so plan
    approval can overturn it in one place.

- **D8: Range ledgers are per-run snapshots, and retention can never fail a
  successful run.** `write_ledger` merges into an existing `choices.json` by
  `stable_id`, which is how the change-id form satisfies the canonical
  "Re-audit is idempotent" scenario. A range run normally targets a fresh
  dated directory, so that merge normally does not fire. **It is not
  "never".** `build_run_id` resolves to the second, so two standalone audits
  begun in the same UTC second at the same `HEAD` compute the same run id,
  land in the same directory, and `write_ledger` merges the second snapshot
  into the first — two distinct audits silently combined.
  `prioritize-proposals` has the same property and has shipped with it, but a
  human takes minutes to start a second priorities run while nothing stops a
  script from starting two audits back to back. The routing helper therefore
  refuses to reuse an existing run directory: when the computed path already
  exists it appends `-2`, `-3`, … until one is free. Two consequences the
  first draft of this decision got wrong:

  - **`RUN_ID_RE` must accept the suffix.** The regex moved in task 2.2 is
    `^(\d{4}-\d{2}-\d{2})(?:-(\d{6}|legacy)(?:-([a-f0-9]+))?)?$`, which
    rejects `2026-09-12-030000-abc1234-2`. `list_active_runs` filters
    directories through `parse_run_id`, so an unextended regex makes retention
    silently stop seeing exactly the directories the guard creates — the tree
    would grow without bound and the bounding scenario would still pass. The
    shared regex gains an optional trailing `-<n>` group and `parse_run_id`
    returns it. `prioritize-proposals` never produces a suffix; accepting one
    costs it nothing.
  - **The guard checks the archive too.** Retention moves old runs to
    `<root>/archive/<run-id>/`, so an active path can free up while the
    archived name persists. A later audit computing that same base would take
    the now-free active path and, on the next retention pass, collide with the
    archived directory. The helper tests both locations before accepting a
    name.

  With those two corrections the merge genuinely never fires for the range
  form, and the scenario still holds — ids are
  content-derived, so the same decision gets the same `stable_id` in every
  snapshot, and no file ever gains a duplicate — but "update in place" is a
  change-id-form behaviour, and `latest.*` is a copy of the newest snapshot,
  not a merged view across runs. `SKILL.md`'s verification step for
  idempotency is reworded so a range re-audit compares the two run
  directories' ledgers rather than one file with itself.
  - Retention runs last, after the pair and `latest.*` are written, and is
    wrapped on its own: a failure (a `shutil.move` that cannot complete) logs a
    warning and leaves the result `ok=True` with both paths set. Without that,
    the driver's D6-of-the-parent catch-all would report `ok=False,
    json_path=None` for a run whose ledger was in fact persisted — a false
    failure to the workflow. The never-raises contract is kept either way; what
    changes is that a housekeeping failure cannot masquerade as a write
    failure.

## Risks / Trade-offs

- **Refactoring a working skill to fix another.** Accepted, and mitigated by
  D4's three-part guard — function-level pins, the CLI entry points run as
  subprocesses from a runtime-shaped layout, and the pre-existing tests held
  byte-unchanged. The alternative was a third copy of the run-id format, which
  the operator explicitly chose against.
- **The import bootstrap is the one new runtime dependency.** After this
  change, `prioritize-proposals` and `audit-choices` both need `shared/` beside
  their skill directory at runtime. `install.sh` already guarantees that for
  every install target, and the manifest validator checks the payload, so the
  exposure is an out-of-tree copy of a single skill directory — the same
  exposure `worktree.py` already accepts for `environment_profile`.
- **Two run identities on one ledger.** The header `run_id` (caller's) and the
  directory run-id (D7) differ. Accepted: they answer different questions —
  which workflow run produced this, and when/at what `HEAD` — and the second is
  derivable from the header, so nothing is lost.
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
