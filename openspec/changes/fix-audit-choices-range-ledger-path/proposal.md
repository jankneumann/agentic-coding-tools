# Change: fix-audit-choices-range-ledger-path

## Why

`audit-choices` has two invocation forms. Given a change id it writes its ledger
pair to `openspec/changes/<change-id>/`, which is correct. Given a bare
`<base-sha>..<head-sha>` range it records `change_id` as the literal string
`range:<base>..<head>` — and `run_audit.py:145` derives the output directory
straight from that string:

```python
change_dir = repo_root / "openspec" / "changes" / change_id
```

So a standalone range audit creates
`openspec/changes/range:abc1234..def5678/`. That is not a change. It has no
`proposal.md`, it is not valid OpenSpec, and it sits in the tree every sweep
over `openspec/changes/` reads. The colon and the double dot are also the only
place in this repository where a commit range is encoded into a path at all.

The defect is known and was deliberately deferred. Two rounds of plan review on
`add-decision-choices-ledger`'s follow-up found it and both times ruled it out
of scope, because that proposal forbade driver changes; the archived
`design.md` names this change id as the follow-up. Here the driver is in scope.

The repository already answered this question once. `prioritize-proposals`
produces the only other artifact carrying the same six-field header, hit the
same problem, and resolved it explicitly — its skill file states that
`openspec/changes/prioritized-proposals.md` "belongs to the openspec/changes/
namespace and was the wrong home for a meta-report", and moved the output to a
dated run directory under `openspec/priorities/`. A range-form ledger is the
same class of artifact with the same problem, so it gets the same shape rather
than a new one.

## What Changes

- `run_audit.py` stops deriving its output directory from the raw `change_id`.
  A change-id invocation keeps writing to `openspec/changes/<change-id>/`,
  byte-for-byte as today. A `range:` invocation writes to
  `openspec/choices/<YYYY-MM-DD>-HHMMSS-<sha7>/choices.{json,md}`, with
  `latest.{json,md}` rewritten at `openspec/choices/` for cheap most-recent
  access.
- A retention helper archives rather than deletes, mirroring
  `prioritize-proposals/scripts/retention.py`: oldest runs move to
  `openspec/choices/archive/<run-id>/` once the active count exceeds the
  retention limit.
- The read-only contract in `skills/audit-choices/SKILL.md` names both
  permitted destinations explicitly, as does the matching Red Flags line, and
  `test_readonly_posture.py` proves a range run writes only to the new
  location.
- `docs/guides/workflow.md` documents where a standalone audit puts its output.

No change to the schema, the ledger format, the entry pipeline, the six-field
header, or the always-exit-0 contract. The recorded `change_id` stays
`range:<base>..<head>`, which is what canonical scenario `skill-workflow.12`
pins — that scenario constrains the recorded value and the exit code, never the
path, so this change does not contradict it.

## Approaches Considered

### 1. Copy the run-id builder into audit-choices — **Recommended**

Add `skills/audit-choices/scripts/choices_paths.py` with the same pure
`build_run_id` / `build_paths` shape as `priorities_paths.py`, and a
`retention.py` alongside it.

- **Pros**: `audit-choices` stays self-contained, which is how it already
  treats this exact dependency — `choices_ledger.py` carries the six-field
  header "copied verbatim" from `prioritize-proposals/scripts/artifact_header.py`
  under the parent change's D4, so copying the path builder is the established
  relationship between these two skills rather than a new one. No install
  manifest edit, no import that the dependency linter has to reason about, and
  the pure-function shape keeps the tests fast and deterministic.
- **Cons**: A third copy of the run-id format. If the format ever changes, two
  skills change.
- **Effort**: S

### 2. Import the builder from prioritize-proposals

Declare `prioritize-proposals` as a dependency of `audit-choices` in
`skills/install-manifest.json` and import `priorities_paths` directly.

- **Pros**: One definition of the run-id format. The manifest already carries
  cross-skill dependencies of exactly this kind, including
  `"cleanup-feature": ["audit-choices", ...]`, so the mechanism is proven.
- **Cons**: Couples a read-only auditor to a ranking skill it has nothing else
  to do with, and drags `prioritize-proposals` into every runtime that installs
  `audit-choices`. The names would read wrong at the call site: a choices
  ledger asking `priorities_paths` where to live.
- **Effort**: S

### 3. Extract the builder to `skills/shared/`

Create `skills/shared/artifact_paths.py`, migrate `prioritize-proposals` onto
it, and have `audit-choices` use it too.

- **Pros**: The genuinely correct long-term home, and the direction the code
  already points — `artifact_header.py`'s own docstring says "Once
  `skills/shared/artifact_header.py` ships (codeviz roadmap), migrate this
  module to that helper without changing the on-disk schema." `skills/shared/`
  exists and the dependency linter explicitly permits importing from it.
- **Cons**: Turns a narrow bug fix into a refactor of a second, unrelated,
  working skill, and re-tests `prioritize-proposals` to fix `audit-choices`.
  The shared-helper migration is a codeviz roadmap item with its own sequencing;
  pre-empting it here does that work in the wrong change.
- **Effort**: M — and the one selected

**Recommended at Gate 1: Approach 1.** Smallest blast radius.

## Selected Approach

**Approach 3 — extract to `skills/shared/`.** The operator chose the end state
over the cheaper local fix, and one discovery made after the recommendation was
written supports it: `skills/shared/` is declared in `install-manifest.json`
under `shared_libraries`, so it installs alongside every skill automatically.
Approach 3 therefore needs no `cross_skill_dependencies` entry at all, which was
the main structural cost counted against it, and the dependency linter already
names `skills/shared/` as an explicitly permitted import source.

The extraction is deliberately narrow. What the two producers share is the
**run-id format**, not their filenames: `prioritize-proposals` writes
`report.{md,json}` and `audit-choices` writes `choices.{json,md}`. So
`skills/shared/artifact_paths.py` holds `build_run_id` and the `RUN_ID_RE`
that parses it back, and each skill keeps its own small paths dataclass naming
its own files. Extracting the filenames too would produce a shared helper that
knows about both callers, which is the coupling this approach exists to avoid.

`apply_retention` moves to the shared module on the same reasoning: it operates
purely on a directory of run-id-named subdirectories, it is the same concern,
and leaving it behind would mean copying it — reintroducing, for retention, the
duplication this approach was chosen to remove.

Because `prioritize-proposals` is a working skill being refactored to fix a bug
in a different one, its migration is guarded: a characterization test pins its
current on-disk output **before** the migration, and must still pass after.
The migration is not allowed to change a single byte of what that skill
writes.

## Impact

- Affected specs: `skill-workflow` (one MODIFIED requirement — the standalone
  range scenario gains a location clause it currently lacks)
- Affected skills: `audit-choices` (driver, SKILL.md contract wording),
  `prioritize-proposals` (migrated onto the shared helper, output unchanged)
- New shared library module: `skills/shared/artifact_paths.py`
- Affected docs: `docs/guides/workflow.md`
- New tracked tree: `openspec/choices/`
- Parent change: `add-decision-choices-ledger` (archived), which recorded this
  as the named follow-up
