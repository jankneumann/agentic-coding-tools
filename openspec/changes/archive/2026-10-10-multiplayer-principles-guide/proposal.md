---
deployable: false
---

# Publish the multiplayer collaboration principles guide

> Parent roadmap: `multiplayer-collaboration` (item `ri-01`)
> Change ID: `multiplayer-principles-guide`
> Effort: S
> Priority: 1

## Why

The toolkit is built and dogfooded by one developer and then installed into team
repositories. Assumptions that hold only for a single principal (whoever runs the skill
owns the intent; dependencies are on whole items; rationale artifacts get read; and five
more) travel with it invisibly and fail in a recognizable way in team use. The
`multiplayer-collaboration` roadmap (`openspec/roadmaps/multiplayer-collaboration/proposal.md`)
answers those failures with ten principles (P1-P10) and 19 follow-on changes, each of which
cites the principles it serves.

Today those principles exist only inside a roadmap proposal, which is a planning artifact
that gets archived. Later changes, reviewers, and agents need a stable, linked reference
that:

1. states the principles under stable IDs so specs and skill text can cite `P4` rather
   than restating it;
2. fixes the **solo mode** versus **team mode** vocabulary before any code branches on it,
   including the guarantee that solo mode adds no new prompts, gates, or PR checkpoints;
3. records which existing mechanism or planned change implements each principle, so a
   principle with nothing behind it is visible.

## What Changes

- **New guide** `docs/guides/multiplayer-collaboration.md` containing:
  - a *Modes* section that defines solo mode and team mode and states the solo-mode
    guarantee (no new prompts, gates, or PR checkpoints);
  - the ten principles P1-P10, grouped as in the roadmap (who decides / what gets shared /
    how signals flow), each with an *Implemented by* line naming at least one existing
    mechanism (a repository path) or planned roadmap change (a change-id);
  - the single-principal assumption table (eight rows, from the roadmap) with an added
    *Addressed by* column;
  - a per-skill solo-mode versus team-mode behavior table naming the change that
    delivers each team-mode behavior;
  - an *Authority and maintenance* section stating that the guide is descriptive, that
    OpenSpec specs are normative, and how the guide stays current as sibling changes land.
- **Links**: a short *Multiplayer Collaboration* section in `AGENTS.md`, and an entry in
  `docs/guides/documentation.md` under *Foundational*.
- **Guard test** `skills/tests/multiplayer-collaboration/test_multiplayer_guide.py` that
  checks the guide's structure, the two inbound links, that every cited repository path
  exists, and that every cited change-id resolves (active or archived) through
  `change_dir()`; registered in `skills/pyproject.toml` `testpaths` so the default CI
  sweep runs it.

## Non-Goals

- No runtime behavior change in any skill, script, or coordinator module. Nothing reads
  the guide at runtime.
- No mode-detection code. The guide *defines* solo and team mode; detection is implemented
  by `ownership-map` (ri-02).
- No `openspec/owners.yaml` schema, principal registry, or other durable state artifact;
  therefore no `docs/guides/state-artifacts.md` registration.
- The guide is not installed into consumer repositories by `skills/install.sh` (which does
  not copy `docs/`). Installed skills must cite principles by ID and must not depend on
  the guide file being present.
- No edits to `roadmap.yaml` or to sibling changes' artifacts.

## Impact

- **Specs**: ADDED requirements in the new capability `multiplayer-collaboration`
  (`specs/multiplayer-collaboration/spec.md`). This is the capability every sibling change
  in the roadmap also targets; this change is the first to create it.
- **Files created**: `docs/guides/multiplayer-collaboration.md`,
  `skills/tests/multiplayer-collaboration/test_multiplayer_guide.py`.
- **Files modified**: `AGENTS.md` (new section of at most four lines),
  `docs/guides/documentation.md` (one list entry), `skills/pyproject.toml` (one
  `testpaths` entry so CI collects the guard test; the CI-coverage guard requires it).
- **Downstream**: sibling changes in `multiplayer-collaboration` cite principle IDs and the
  mode vocabulary from the guide; a sibling that is renamed or superseded must update the
  guide's change-id references (the guard test fails otherwise).
- **Risk**: documentation-only; no migrations, endpoints, secrets, or new dependencies.

## Dependencies

- None. (See design.md, *Open questions*: no sibling currently declares `depends_on: [ri-01]`.)

## Acceptance Outcomes

- `docs/guides/multiplayer-collaboration.md` exists and is linked from both `AGENTS.md` and
  `docs/guides/documentation.md`.
- Each of the ten principles names at least one capability or existing mechanism that
  implements it.
- The guide contains the single-principal assumption table and a per-skill solo-mode versus
  team-mode behavior section stating that solo mode adds no new prompts, gates, or PR
  checkpoints.
- `cd skills && .venv/bin/python -m pytest tests/multiplayer-collaboration` passes and
  `openspec validate multiplayer-principles-guide --strict` passes.
