# Scaffold roadmap items as validating OpenSpec changes, then refine before implementing

> Parent roadmap: none (defect-driven)
> Change ID: `scaffold-validating-roadmap-changes`
> Effort: M
> Closes: #348

## Why

The intended roadmap model is:

> A roadmap identifies the high-level OpenSpec change for each item. Each item carries
> preliminary minimal sketches — proposal, design (optional), and high-level specs — at
> roadmap-creation time, producing an OpenSpec setup that *validates* but needs
> refinement. After each item completes, the next item's plan is refined via
> `/plan-feature` or `/iterate-on-plan` using what was learned implementing its
> dependencies.

Two defects block it.

**The scaffolder creates `specs/` and never writes to it.** `scaffolder.py` had
`_write_proposal` and `_write_tasks` but no `_write_specs`; `scaffold_changes` called
`specs_dir.mkdir(exist_ok=True)` and stopped. Git does not track empty directories, so
the directory disappeared on commit and the change failed:

```
Change must have at least one delta. No deltas found.
```

Observed on PR #343, where three scaffolded items took `openspec validate --strict --all`
to 62 passed / 3 failed.

**Advancing a roadmap item skips planning.** `CheckpointManager.advance_to_next` set
`phase = IMPLEMENTING`. Because `should_skip_phase` orders `PLANNING` before
`IMPLEMENTING`, a freshly advanced item reported planning as already complete — so the
refinement pass was skipped silently rather than deliberately, against a change directory
holding nothing but an unrefined scaffold.

## What Changes

### New: `_write_specs` in `skills/plan-roadmap/scripts/scaffolder.py`

Emits `specs/<capability>/spec.md` with `## ADDED Requirements` derived from the item's
`acceptance_outcomes` — one outcome becomes one requirement plus one scenario. Every
roadmap item already carries them (114/114 across all five roadmaps), and an acceptance
outcome is already a statement about observable behavior, which is what a requirement is.

Requirement bodies lead with the modal verb, because OpenSpec's strict mode inspects only
a requirement's **first** line for SHALL/MUST. Outcomes that already state one are passed
through rather than wrapped twice. An item with no outcomes still produces a delta that
validates and says its requirements are placeholders.

### New: `_write_design` in the same module

Writes a `design.md` sketch, but only when the item carries a rationale or dependencies. A
design document that restates the title helps nobody, so its absence is meaningful.

### New: `capability` field on `RoadmapItem`

Names the capability directory a scaffolded delta belongs under. When absent, the roadmap
id is used — a placeholder the refinement pass is expected to correct, not a claim about
final placement. Added to `roadmap.schema.json`; all five existing roadmaps still validate.

### Modified: `CheckpointManager.advance_to_next`

Enters `PLANNING` rather than `IMPLEMENTING`. `PLANNING` already existed and already
sorted first, so this is a one-line correction that makes `should_skip_phase` behave as
its own phase order always implied.

### Marked as scaffolds

Generated deltas and designs carry a `SCAFFOLD` marker naming the roadmap and item they
came from. A sketch that does not announce itself gets mistaken for a considered spec.

## Non-Goals

- **Generating good requirements.** These are sketches that validate; refinement is a
  separate, deliberate pass. The change makes the refinement pass *happen*, not unnecessary.
- **Choosing the final capability.** The default is a placeholder and is documented as one.
- **Adding the roadmap suites to CI discovery.** Blocked on an unrelated defect — see below.

## Known limitation, deliberately not fixed here

`tests/plan-roadmap` and `tests/roadmap-runtime` are still absent from `testpaths` in
`skills/pyproject.toml`, so these 126 tests — including the 14 added here — do not run in
CI. Adding them breaks 30 unrelated collections: five flat `models.py` modules compete for
the bare name `models`, and the roadmap conftests' `sys.path.insert` binds it to the
roadmap dataclasses for the rest of the session, so suites expecting
`project-context-runtime`'s `models` fail with `cannot import name 'ChangeKind'`.

Disambiguating `models` is a repo-wide refactor and does not belong in this change. The
omission is recorded as a comment beside `testpaths` rather than left silent, and both
suites pass standalone.

## Verification

- New tests fail against the unmodified scaffolder (11 failed / 1 passed — the one pass is
  the design-skip negative control) and pass against the new one (12/12).
- `test_scaffolded_change_passes_openspec_strict` shells out to the real `openspec` CLI.
- `test_specs_survive_a_commit` does a real `git add`/`git commit` and asserts the delta is
  tracked — the property the original defect violated.
- Roadmap suites: 112 → 126 passed.
- Full CI-equivalent skills suite: 2344 passed, unchanged.
- All five existing roadmaps still validate against the amended schema.
