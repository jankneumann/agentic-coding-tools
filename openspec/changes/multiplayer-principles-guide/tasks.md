# Tasks: Publish the multiplayer collaboration principles guide

> Change ID: `multiplayer-principles-guide`

Source content for every task: `openspec/roadmaps/multiplayer-collaboration/proposal.md`
(principles, assumption table, capability *Serves* lines) and
`openspec/roadmaps/multiplayer-collaboration/roadmap.yaml` (change-ids, acceptance
outcomes). Design decisions D1-D8 are in `design.md`.

Dependency graph: `1.1 -> 1.2`, `1.1 -> 2.1`, `1.1 -> 3.1`, `1.1 -> 4.1`, then `5.1` after all.
Independent after 1.1: 1.2, 2.1, 3.1, 4.1 (disjoint files). Max parallel width: 4.
Sequential chains: 1 (`1.1 -> {1.2, 2.1, 3.1, 4.1} -> 5.1`).

## 1. Guard test (red)

- [x] 1.1 Write `skills/tests/multiplayer-collaboration/test_multiplayer_guide.py` per
  design D7, with one test per spec requirement: inbound links and no links into
  `openspec/changes/` or `openspec/roadmaps/` (D8); P1-P10 headings and
  `**Existing:**` / `**Planned:**` implementer resolution; assumption table (columns, eight
  rows, resolvable *Addressed by*); `## Modes` section, exact guarantee sentence,
  `ownership-map` and "passive output" present;
  per-skill table (nine named rows, non-empty *Solo mode* / *Team mode* cells,
  resolvable *Delivered by*);
  `## Authority and maintenance` phrases; plus one `tmp_path` case proving the
  change-id resolution helper accepts an archived-only change (spec scenario *Archival
  of a cited change does not fail the guard*). Link targets are compared after
  stripping any `#fragment`. Use `repo_root_from` / `change_dir` from
  `openspec_paths`; no literal `openspec/changes/<id>/` paths. Each assertion message
  names the failing principle, row, link, or section.
  - Files: `skills/tests/multiplayer-collaboration/test_multiplayer_guide.py` (new)
  - Depends on: none
  - Verify: `cd skills && .venv/bin/python -m pytest tests/multiplayer-collaboration`
    fails (guide absent), and
    `.venv/bin/python -m pytest tests/openspec_paths` passes.
  - Requirements: the six guide requirements in `specs/multiplayer-collaboration/spec.md`

- [ ] 1.2 Register `tests/multiplayer-collaboration` in `testpaths` in
  `skills/pyproject.toml`, next to `tests/state-artifacts`, with a one-line comment
  naming this change. Naming the directory on the pytest command line bypasses
  `testpaths`, so 1.1's verify step alone cannot catch a missing entry.
  - Files: `skills/pyproject.toml`
  - Depends on: 1.1
  - Verify: `cd skills && .venv/bin/python -m pytest --collect-only -q | grep multiplayer-collaboration`
    lists the guard test, and `.venv/bin/python -m pytest tests/ci_coverage` passes.
  - Requirements: Guard test runs in the default CI sweep

## 2. Write the guide

- [ ] 2.1 Create `docs/guides/multiplayer-collaboration.md` with, in order: introduction
  (purpose; the roadmap named by id `multiplayer-collaboration` in prose, **not linked**,
  because `/archive-roadmap` moves it to `openspec/roadmaps/archive/<date>-<id>/`;
  `multiplayer-simulation-harness` cited as serving all principles); `## Modes` (D2 definitions, exact guarantee sentence,
  passive-output clause, solo until `ownership-map` ships); `## Principles` with
  `### P1.` to `### P10.` grouped as in the roadmap (group labels as bold text, not
  headings), each with statement,
  `**Existing:**` links and `**Planned:**` change-ids per the D3 mapping;
  `## Single-principal assumptions` table (eight rows + *Addressed by*);
  `## Skills in solo and team mode` table (D5 rows, cells derived from roadmap
  acceptance outcomes); `## Authority and maintenance` (D6). Use these headings
  verbatim; the guard test locates sections by them.
  - Files: `docs/guides/multiplayer-collaboration.md` (new)
  - Depends on: 1.1
  - Verify: guard-test assertions for principles, assumption table, modes, per-skill
    table, and authority pass.
  - Requirements: Principles are stated with implementers; Single-principal assumption
    table; Solo and team mode vocabulary; Per-skill solo and team behavior table; Guide
    states its authority and maintenance rule

## 3. Link from AGENTS.md

- [ ] 3.1 Add a `## Multiplayer Collaboration` section to `AGENTS.md`, after
  *Worktree Management* and before *Documentation*, in the existing house style: at
  most four lines, one sentence of purpose (principles P1-P10 and the solo/team mode
  vocabulary) and a `See [multiplayer collaboration guide](docs/guides/multiplayer-collaboration.md)`
  link. Do not edit `CLAUDE.md` (it imports `AGENTS.md`).
  - Files: `AGENTS.md`
  - Depends on: 1.1
  - Verify: guard-test link assertion for `AGENTS.md` passes.
  - Requirements: Multiplayer collaboration guide is published and linked

## 4. Link from the documentation index

- [ ] 4.1 Add `- [Multiplayer Collaboration](multiplayer-collaboration.md) — Principles
  P1-P10, solo vs team mode, and the single-principal assumptions later capabilities
  cite.` under *Foundational* in `docs/guides/documentation.md`.
  - Files: `docs/guides/documentation.md`
  - Depends on: 1.1
  - Verify: guard-test link assertion for `documentation.md` passes.
  - Requirements: Multiplayer collaboration guide is published and linked

## 5. Verify

- [ ] 5.1 Run `cd skills && .venv/bin/python -m pytest tests/multiplayer-collaboration tests/openspec_paths tests/state-artifacts tests/docs tests/ci_coverage`
  (all pass) and `openspec validate multiplayer-principles-guide --strict` (valid).
  - Files: none
  - Depends on: 1.2, 2.1, 3.1, 4.1
  - Requirements: all
