# Tasks — ownership-map

> Change ID: `ownership-map` · Roadmap item `multiplayer-collaboration/ri-02`

Sizes per the plan-feature sizing table. TDD ordering: every test task precedes the
implementation task it verifies and that task depends on it. Spec scenario references name
`<capability> / "<scenario>"` in `specs/`; design decisions reference `design.md`. No task is
XL; the `CODEOWNERS` work is L-adjacent and is split into emit (4.1 / 4.2) and reconcile
(4.3 / 4.4).

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Phase 1 — Contracts: schemas promoted to their stable homes

- [x] 1.1 Write `skills/tests/ownership-runtime/test_schema_copies.py` pinning the two schema
      files: `openspec/schemas/owners.schema.json` and
      `openspec/schemas/human-principals.schema.json` are byte-identical to their
      `skills/ownership-runtime/install_assets/openspec/schemas/` copies and to the drafts under
      this change's `contracts/schemas/` (located with `change_dir()`), and both parse as
      Draft 2020-12 JSON Schema (S)
      **Spec scenarios**: ownership-map / "Schema copies pinned"
      **Design decisions**: D2, D7, D12
      **Dependencies**: none
- [x] 1.2 Promote the draft schemas from `contracts/schemas/` to `openspec/schemas/` and to
      `skills/ownership-runtime/install_assets/openspec/schemas/`; add positive and negative
      fixture instances under `skills/tests/ownership-runtime/fixtures/` exercising every
      `additionalProperties: false` boundary and the restricted glob pattern (S)
      **Spec scenarios**: ownership-map / "Unknown key rejected", "Unsupported glob syntax
      rejected", "Registry path escaping the repository rejected" (schema half)
      **Design decisions**: D3
      **Dependencies**: 1.1
- [x] 1.3 Create the test package skeleton `skills/tests/ownership-runtime/__init__.py` and
      `conftest.py` with the shared fixture builder (`make_repo(tmp_path, humans=..., owners=...,
      agents=..., git=True)` writing a registry, an optional map and an initialized git
      checkout), so every later package only adds test modules to an existing package (S)
      **Design decisions**: D12
      **Dependencies**: none
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Registry extension (agent-coordinator)

- [x] 2.1 Write `agent-coordinator/tests/test_human_principals.py` — `humans:` block validates,
      missing `display_name` rejected, unknown field rejected, human id colliding with an agent
      name raises `ValueError` naming both, `load_human_principals()` returns `HumanEntry`
      records and an empty list for a registry without humans, `load_agents_config()` return
      value unchanged with and without the block (M)
      **Spec scenarios**: agent-identity / "Human id colliding with an agent name rejected",
      "Human entry missing display name rejected", "Registry without humans unchanged"
      **Design decisions**: D1
      **Dependencies**: none
- [x] 2.2 Write the schema-mirror test — `HUMAN_PRINCIPAL_SCHEMA` equals
      `openspec/schemas/human-principals.schema.json` minus `$schema`/`$id`/`title`/`description` (S)
      **Spec scenarios**: agent-identity / "Schema mirror pinned"
      **Design decisions**: D2
      **Dependencies**: 1.2
- [x] 2.3 Implement `HUMAN_PRINCIPAL_SCHEMA`, the `humans` property on `AGENTS_SCHEMA`, the
      `HumanEntry` dataclass, `load_human_principals()`, and the agent/human namespace collision
      check inside `load_agents_config()` in `agent-coordinator/src/agents_config.py` (M)
      **Dependencies**: 2.1, 2.2
- [x] 2.4 Write the projection-invariant extension tests — rule 6 checker (no human id in
      profile rows, assignments, identity map, dispatch configs or `project_principals()`
      output) plus the negative test that injects a human-named profile row and proves the
      checker fires (S)
      **Spec scenarios**: agent-identity / "Human principal declared without agent projection",
      "Invariant catches a human projected as an agent"
      **Design decisions**: D1, D12
      **Dependencies**: 2.3
- [x] 2.5 Add rule 6 (`_human_projection_violations`) to
      `agent-coordinator/tests/test_registry_projection.py` and wire it into the positive
      invariant test over the real registry (S)
      **Dependencies**: 2.4
- [x] 2.6 Declare the maintainer as the first human principal in
      `agent-coordinator/agents.yaml` (`humans:` block with `display_name`, `github`, `domains`
      and, only if the maintainer wants it published, `email` — nothing in this change reads it,
      D5), taking the handle from `gh api user` (falling back to the owner of the `origin` remote
      when `gh` is unauthenticated, and saying so in the checkpoint), with a header comment
      explaining the block and pointing at the `ownership-map` capability (S)
      **Design decisions**: D1
      **Dependencies**: 2.3
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Resolver, principals and check (skills/ownership-runtime)

- [x] 3.1 Write `skills/tests/ownership-runtime/test_principals.py` — registry location order
      (env var, `registry:` field, `agent-coordinator/agents.yaml`, root `agents.yaml`, none);
      only `humans:` and `agents:` keys are read (a registry with an invalid `agents:` entry
      still yields its humans); solo derivation order (single human, synthetic `git:<email>`,
      sentinel — no email matching, D5); a `registry:` value resolving outside `repo_root`
      raises `OwnershipConfigError` (`registry_outside_repo`); `repo_root` defaults to the git
      toplevel; `mode` derived from human count (M)
      **Spec scenarios**: ownership-map / "Single declared human is the sole principal",
      "Git identity derived when the registry has no humans", "Sentinel when no identity is
      available", "Consumer repository registry at the root", "Registry path escaping the
      repository rejected" (loader half)
      **Design decisions**: D5, D6, D10
      **Dependencies**: 1.2, 1.3
- [x] 3.2 Implement `skills/ownership-runtime/scripts/principals.py` — `Principal`,
      `locate_registry()`, `load_human_principals()` (validated against the shipped JSON schema),
      `derive_solo_principal()`, `derive_mode()` (S)
      **Dependencies**: 3.1
- [x] 3.3 Write `skills/tests/ownership-runtime/test_owners.py` — minimal map loads; missing
      `default_owner`, unregistered owner, agent-as-owner each raise `OwnershipConfigError`;
      explicit capability with distinct acceptance rights; default fallback with
      `matched_rule is None`; most-specific path rule wins; equal-specificity tie by rule order;
      implied capability rules for `openspec/specs/<cap>/` and `openspec/contracts/<cap>/` with
      `matched_rule == "capability:<cap>"`, and an explicit rule beating an implied rule of equal
      specificity; the D3 matching table (unanchored basename, anchored, unanchored single-segment `dir/`
      vs anchored `/dir/`, trailing `/`, `**`
      whole-segment, embedded `**` rejected); roadmap item explicit and fallback; solo mode with
      map absent; one-principal repository with a map stays `solo`; team registry without a map
      raises; performance budget (200-rule map, 1,000 resolutions — the design budget is 250 ms,
      the test asserts a 4× margin of 1 s so CI variance cannot flake it) (M)
      **Spec scenarios**: ownership-map / "Minimal valid map loads", "Missing default owner
      rejected", "Unregistered owner fails closed", "Agent named as owner rejected", "Embedded
      double-star rejected", "Explicit capability assignment", "Single-segment directory rule matches at any depth",
      "Unassigned capability falls back
      to the default owner", "Most specific path rule wins", "Equal specificity resolved by file
      order", "Capability assignment governs its spec and contract paths", "Explicit path rule
      overrides an implied capability rule", "Roadmap item resolution", "One-principal
      repository with a map stays solo"
      **Design decisions**: D3, D4, D5, D13
      **Dependencies**: 3.2
- [x] 3.4 Implement `skills/ownership-runtime/scripts/owners.py` — `load_ownership()`,
      `OwnershipContext`, `OwnerSet`, `OwnershipConfigError`, the three `resolve_*` methods and
      the path specificity ranking (M)
      **Dependencies**: 3.3
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 3.5 Write `skills/tests/ownership-runtime/test_check_owners.py` — `unowned_capability`
      and `unowned_roadmap_item` warnings in team mode and their suppression in solo mode (D14);
      `unknown_capability` / `unknown_roadmap_item` warnings for dangling keys (archived roadmaps
      excluded); `unknown_owner`, `agent_as_owner`, `registry_outside_repo` and
      `team_registry_without_map` errors; `sentinel_principal` warning; exit codes with and
      without `--strict` (`info` never promoted); every emitted `code` is in the D9 table and
      the `--json` shape is stable (S)
      **Spec scenarios**: ownership-map / "Unowned capability reported", "Solo mode emits no
      unowned findings", "Dangling capability assignment reported", "Unregistered owner reported
      as error", "Team registry without a map is an error"
      **Design decisions**: D9, D14
      **Dependencies**: 3.4
- [x] 3.6 Implement `skills/ownership-runtime/scripts/check_owners.py` (CLI; `--codeowners`
      delegates to 4.4's reconcile when present) (S)
      **Dependencies**: 3.5
- [x] 3.7 Write the coordinator-independence test — the resolver suite runs with
      `COORDINATION_API_URL` pointing at a closed port and a socket guard asserting no
      connection is attempted; AST scan asserts no `src.` import or `agent-coordinator` path in
      `skills/ownership-runtime/scripts/` (S)
      **Spec scenarios**: ownership-map / "Resolution with the coordinator unreachable", "No
      private coordinator imports"
      **Design decisions**: D7
      **Dependencies**: 3.4
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 4 — CODEOWNERS projection

- [x] 4.1 Write `skills/tests/ownership-runtime/test_codeowners_emit.py` — managed block
      markers; `*` first; two lines per capability; ascending specificity order with implied
      capability lines before explicit `paths` lines at equal specificity; `@handle` rendering;
      unmanaged text before and after the block preserved byte-for-byte on `emit --write`;
      missing `github` handle fails without modifying the file; no map → exit `1` with
      `no_ownership_map` and no file created (M)
      **Spec scenarios**: ownership-map / "Emit ordering yields agreement", "Missing GitHub
      handle fails emission", "Stale block reported and unmanaged text preserved", "Emit
      without a map fails closed"
      **Design decisions**: D8
      **Dependencies**: 3.4
- [x] 4.2 Implement `emit` in `skills/ownership-runtime/scripts/codeowners.py` — line
      generation, ordering, marker handling, `--write` (M)
      **Dependencies**: 4.1
- [x] 4.3 Write `skills/tests/ownership-runtime/test_codeowners_reconcile.py` — probe set
      construction (tracked spec/contract files, rule matches, literal prefixes, one unmatched
      path); GitHub last-match-wins matcher over the whole file including unmanaged lines;
      disagreement for a hand-added conflicting line; stale block detected with diff; clean emit
      reconciles with zero disagreements; managed block without a map → `orphan_managed_block`
      warning, exit `0`; outside a git checkout → `not_a_git_checkout` error (M)
      **Spec scenarios**: ownership-map / "Hand-edited line that disagrees is reported", "Stale
      block reported and unmanaged text preserved", "Emit ordering yields agreement", "Orphaned
      managed block reported"
      **Design decisions**: D8
      **Dependencies**: 4.2
- [x] 4.4 Implement `reconcile` in `codeowners.py` — CODEOWNERS-semantics matcher, probe set,
      comparison, stale detection, exit codes, `--json` (M)
      **Dependencies**: 4.3
- [x] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Dogfood, documentation, portability

- [ ] 5.1 Write `skills/tests/ownership-runtime/test_repository_invariant.py` — against the real
      checkout: `check_owners.py --codeowners --strict --json` exits `0` with an empty findings
      list; `codeowners.py reconcile` reports zero disagreements and a fresh block;
      `load_ownership().mode == "solo"`; the run stays green when a capability directory is
      added to a copy of the tree (D14: no `unowned_*` churn in solo mode) (S)
      **Spec scenarios**: ownership-map / "Clean repository passes", "Repository CODEOWNERS
      reconciles", "One-principal repository with a map stays solo", "Solo mode emits no
      unowned findings"
      **Design decisions**: D6, D9, D12, D14
      **Dependencies**: 2.6, 3.6, 4.4
- [ ] 5.2 Author `openspec/owners.yaml` for this repository — `default_owner` is the maintainer,
      plus a *representative* set of explicit assignments that exercises every resolver branch:
      capabilities `ownership-map` and `agent-identity`, roadmap item
      `multiplayer-collaboration/ri-02`, and `paths` rules for `openspec/contracts/**` and
      `openspec/schemas/**`. Not an exhaustive list: the repository is in solo mode, `unowned_*`
      findings are suppressed (D14), and the file must not churn with every new capability or
      roadmap item (S)
      **Design decisions**: D3, D6, D14
      **Dependencies**: 5.1
- [ ] 5.3 Generate `.github/CODEOWNERS` with `codeowners.py emit --write` (S)
      **Dependencies**: 5.2
- [ ] 5.4 Write the state-artifacts guide test extension — `skills/tests/state-artifacts/`
      asserts the inventory row for `openspec/owners.yaml` names `CODEOWNERS` as a derived
      projection and covers writer, authority and missing/stale cells; existing assertions
      untouched (S)
      **Spec scenarios**: ownership-map / "Inventory row present", "Guide tests still pass"
      **Design decisions**: D11
      **Dependencies**: none
- [ ] 5.5 Add the **Ownership map** row to `docs/guides/state-artifacts.md` per D11 (S)
      **Dependencies**: 5.4
- [ ] 5.6 Write `skills/ownership-runtime/SKILL.md` — import surface, `mode` contract for
      downstream items, CLI usage, roadmap-item-has-no-path note; add the skill to
      `skills/install-manifest.json` (`portable`) and `docs/skills-catalogue.md` (S)
      **Spec scenarios**: ownership-map / "Install payload validates"
      **Design decisions**: D7
      **Dependencies**: 3.6, 4.4
- [ ] 5.7 Solo-mode regression — with `openspec/owners.yaml` moved aside, run the full
      `skills/tests` and `agent-coordinator/tests` unit suites and record in the checkpoint that
      no pre-existing test assertion was modified or removed — the only edits to pre-existing test
      files are the additive extensions of tasks 2.5 and 5.4, listed by name in the checkpoint (S)
      **Spec scenarios**: ownership-map / "Existing suites unchanged with the map absent"
      **Design decisions**: D6
      **Dependencies**: 5.3
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Integration

- [ ] 6.1 Merge package branches; run `bash skills/install.sh --check`,
      `openspec validate --strict --all`, `skills/.venv/bin/python -m pytest skills/tests/`,
      `uv run pytest -m "not e2e and not integration"` plus `mypy --strict src/` and
      `ruff check .` in `agent-coordinator`; fix fallout (S)
      **Dependencies**: 5.1, 5.5, 5.6, 5.7
- [ ] Checkpoint: run tests, review diff, verify scope
