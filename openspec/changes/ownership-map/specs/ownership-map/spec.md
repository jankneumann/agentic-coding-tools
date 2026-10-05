# ownership-map Specification (delta)

Capability `ownership-map`: the git-native ownership map (`openspec/owners.yaml`), its resolver,
check and `CODEOWNERS` projection. Human principal declarations themselves are specified in the
`agent-identity` delta of this change; this capability consumes them.

## ADDED Requirements

### Requirement: Ownership Map Schema

The repository MAY declare an ownership map at `openspec/owners.yaml`. When present, the file
SHALL validate against `openspec/schemas/owners.schema.json`, which SHALL require
`schema_version: 1` and a `default_owner` naming a registered human principal, and SHALL
accept `assignments` keyed by `capabilities` (OpenSpec capability directory names),
`roadmap_items` (`<roadmap-id>/<item-id>`) and `paths` (repo-relative glob patterns restricted
to `*`, `**`, `?`, leading `/` and trailing `/`). Every assignment SHALL list at least one owner;
`decision_rights` and `acceptance_rights` MAY be listed and SHALL default to the owners. Owner
lists SHALL contain human principal ids only. The schema SHALL reject unknown keys at every level.
A present file that fails validation, or that names an owner absent from the human principal
registry, SHALL cause the resolver to fail closed with a configuration error rather than fall
back to any default.

#### Scenario: Minimal valid map loads
- **GIVEN** an `openspec/owners.yaml` containing `schema_version: 1`, `default_owner: jan` and no
  `assignments`
- **AND** the registry declares human principal `jan`
- **WHEN** `load_ownership()` runs
- **THEN** it SHALL return an `OwnershipContext` whose `default_owner` is `jan`

#### Scenario: Missing default owner rejected
- **WHEN** `openspec/owners.yaml` omits `default_owner`
- **THEN** `load_ownership()` SHALL raise `OwnershipConfigError` naming the missing field
- **AND** no resolver call SHALL return a solo-mode result

#### Scenario: Unknown key rejected
- **WHEN** an assignment carries a key other than `owners`, `decision_rights` or
  `acceptance_rights` (for example `reviewers`)
- **THEN** schema validation SHALL fail and the error SHALL name the offending path

#### Scenario: Unregistered owner fails closed
- **WHEN** `assignments.capabilities.agent-identity.owners` lists `nobody`
- **AND** the registry declares no human principal `nobody`
- **THEN** `load_ownership()` SHALL raise `OwnershipConfigError` naming `nobody` and the
  assignment it appears in

#### Scenario: Agent named as owner rejected
- **WHEN** an owner list names `claude-local`, which is an `agents:` key in the registry
- **THEN** `load_ownership()` SHALL raise `OwnershipConfigError` stating that owners must be human
  principals

#### Scenario: Unsupported glob syntax rejected
- **WHEN** a `paths` key uses negation (`!docs/**`) or a character class (`src/[ab]/**`)
- **THEN** schema validation SHALL fail
- **AND** the error SHALL state the supported pattern subset

### Requirement: Owner Resolution

The resolver SHALL answer `resolve_capability(name)`, `resolve_roadmap_item(roadmap_id,
item_id)` and `resolve_path(repo_relative_path)` with an `OwnerSet` carrying `owners`,
`decision_rights`, `acceptance_rights`, `source` (`explicit`, `default_owner` or `solo`) and
`matched_rule`. Capability and roadmap item lookups SHALL be exact matches. Path lookups SHALL
select the most specific matching `paths` rule, ranked by the length of the literal prefix
before the first glob metacharacter and then by total pattern length, with ties resolved in
favor of the later rule in file order. Any subject with no matching assignment SHALL resolve to
the `default_owner` with `source: default_owner`. The resolver SHALL never return an empty
owner set.

#### Scenario: Explicit capability assignment
- **GIVEN** `assignments.capabilities.agent-identity: {owners: [jan], acceptance_rights: [kim]}`
- **WHEN** `resolve_capability("agent-identity")` is called
- **THEN** the result SHALL have `owners == (jan,)`, `decision_rights == (jan,)`,
  `acceptance_rights == (kim,)`, `source == "explicit"` and `matched_rule == "agent-identity"`

#### Scenario: Unassigned capability falls back to the default owner
- **GIVEN** no assignment for capability `model-routing`
- **WHEN** `resolve_capability("model-routing")` is called
- **THEN** the result SHALL have `owners == (default_owner,)` and `source == "default_owner"`
- **AND** `matched_rule` SHALL be `None`

#### Scenario: Most specific path rule wins
- **GIVEN** `paths` rules `openspec/contracts/**: {owners: [jan]}` and
  `openspec/contracts/agent-coordinator/**: {owners: [kim]}` in that order
- **WHEN** `resolve_path("openspec/contracts/agent-coordinator/openapi/v1.yaml")` is called
- **THEN** `owners` SHALL be `(kim,)` and `matched_rule` SHALL be
  `openspec/contracts/agent-coordinator/**`

#### Scenario: Equal specificity resolved by file order
- **GIVEN** two `paths` rules with identical literal-prefix length and pattern length that both
  match a path, the second listing `kim`
- **WHEN** `resolve_path()` is called for that path
- **THEN** `owners` SHALL be `(kim,)`

#### Scenario: Roadmap item resolution
- **GIVEN** `assignments.roadmap_items."multiplayer-collaboration/ri-02": {owners: [jan]}`
- **WHEN** `resolve_roadmap_item("multiplayer-collaboration", "ri-02")` is called
- **THEN** `owners` SHALL be `(jan,)` with `source == "explicit"`
- **AND** `resolve_roadmap_item("multiplayer-collaboration", "ri-03")` SHALL resolve to the
  default owner

### Requirement: Ownership Check

A check command (`check_owners.py`) SHALL report, as **errors**: an invalid or unregistered
owner anywhere in the map (including `default_owner`), an agent id used as an owner, an invalid
map, and a registry declaring two or more human principals while no `openspec/owners.yaml`
exists. It SHALL report, as **warnings**: every capability directory under `openspec/specs/`
and every item in any `openspec/roadmaps/*/roadmap.yaml` with no explicit assignment, and a
solo principal that is the sentinel. The command SHALL exit `1` on any error, `0` otherwise,
and `--strict` SHALL promote warnings to errors. `--json` SHALL emit a stable machine-readable
report listing each finding with `severity`, `code`, `subject` and `message`.

#### Scenario: Unowned capability reported
- **GIVEN** `openspec/specs/model-routing/` exists and the map has no assignment for it
- **WHEN** the check runs
- **THEN** the report SHALL contain a warning with code `unowned_capability` and subject
  `model-routing`
- **AND** the exit code SHALL be `0` without `--strict` and `1` with `--strict`

#### Scenario: Unregistered owner reported as error
- **GIVEN** the map assigns capability `agent-identity` to `nobody`
- **WHEN** the check runs
- **THEN** the report SHALL contain an error with code `unknown_owner`, subject `nobody`
- **AND** the exit code SHALL be `1`

#### Scenario: Team registry without a map is an error
- **GIVEN** the registry declares humans `jan` and `kim`
- **AND** no `openspec/owners.yaml` exists
- **WHEN** the check runs
- **THEN** the report SHALL contain an error with code `team_registry_without_map`
- **AND** the message SHALL state that `openspec/owners.yaml` with a `default_owner` is required

#### Scenario: Clean repository passes
- **GIVEN** every capability and roadmap item has an explicit assignment, every owner is a
  registered human, and `CODEOWNERS` reconciles
- **WHEN** the check runs with `--codeowners --strict --json`
- **THEN** the exit code SHALL be `0` and the JSON `findings` list SHALL be empty

### Requirement: Solo Mode

When no `openspec/owners.yaml` exists and the registry declares at most one human principal,
the resolver SHALL operate in solo mode: `OwnershipContext.mode` SHALL be `solo`, and every
`resolve_*` call SHALL return an `OwnerSet` whose `owners`, `decision_rights` and
`acceptance_rights` all equal the sole repository principal with `source: solo`. The sole
principal SHALL be derived in this order: the single declared human; else a principal derived
from `git config user.email` (matched to a declared human by email when one exists, otherwise a
synthetic principal with id `git:<email>`); else the sentinel principal `repository-default`.
Solo mode SHALL add no prompts, gates or checks to any existing skill, and the existing
`skills/tests` and `agent-coordinator/tests` suites SHALL pass unchanged with the map absent.
`mode` SHALL be derived from the number of distinct human principals, not from the presence of
the map, so a one-principal repository that authors `owners.yaml` remains in solo mode.

#### Scenario: Single declared human is the sole principal
- **GIVEN** no `openspec/owners.yaml` and a registry declaring exactly one human `jan`
- **WHEN** any `resolve_*` call runs
- **THEN** it SHALL return `owners == (jan,)`, `source == "solo"`, and `ctx.mode == "solo"`

#### Scenario: Git identity derived when the registry has no humans
- **GIVEN** no `openspec/owners.yaml`, a registry with no `humans:` block, and
  `git config user.email` set to `dev@example.org`
- **WHEN** `resolve_capability("anything")` is called
- **THEN** the sole principal SHALL have `id == "git:dev@example.org"` and
  `source == "git-config"`

#### Scenario: Sentinel when no identity is available
- **GIVEN** no map, no registry humans and no git identity
- **WHEN** any `resolve_*` call runs
- **THEN** it SHALL return the `repository-default` sentinel with `source == "sentinel"`
- **AND** it SHALL NOT raise

#### Scenario: One-principal repository with a map stays solo
- **GIVEN** a registry declaring exactly one human and an `openspec/owners.yaml` naming that
  human as `default_owner`
- **WHEN** `load_ownership()` runs
- **THEN** `ctx.mode` SHALL be `solo`
- **AND** `resolve_capability()` for an explicitly assigned capability SHALL report
  `source == "explicit"`

#### Scenario: Existing suites unchanged with the map absent
- **GIVEN** the repository checkout with `openspec/owners.yaml` temporarily absent
- **WHEN** the pre-existing `skills/tests` and `agent-coordinator/tests` suites run
- **THEN** they SHALL pass with no test file modified by this change other than the additions it
  introduces

### Requirement: Coordinator Independence

The resolver, check and `CODEOWNERS` tooling SHALL operate from the git checkout alone. They
SHALL import no module from `agent-coordinator/src`, SHALL open no network connection, and
SHALL produce identical results whether or not a coordinator is reachable. The registry SHALL
be located, in order, from `OWNERSHIP_REGISTRY_PATH`, the map's `registry` field,
`agent-coordinator/agents.yaml`, then `agents.yaml` at the repository root; only its `humans:`
block and the keys of `agents:` SHALL be read.

#### Scenario: Resolution with the coordinator unreachable
- **GIVEN** `COORDINATION_API_URL` points at a closed port and `COORDINATION_TRANSPORT` is unset
- **WHEN** the resolver test suite runs
- **THEN** every test SHALL pass and no socket SHALL be opened

#### Scenario: Consumer repository registry at the root
- **GIVEN** a fixture repository with `agents.yaml` at its root declaring one human and no
  `agent-coordinator/` directory
- **WHEN** `load_ownership()` runs
- **THEN** the human SHALL be resolved as the sole principal

#### Scenario: No private coordinator imports
- **WHEN** `skills/shared/validate_install_manifest.py` scans `skills/ownership-runtime/`
- **THEN** it SHALL report no `src.` import and no path reference into `agent-coordinator/`

### Requirement: CODEOWNERS Projection

`codeowners.py emit` SHALL render a managed block in `.github/CODEOWNERS`, delimited by
`# BEGIN ownership-map` and `# END ownership-map` markers, containing one `*` line for the
`default_owner`, two lines per capability assignment (`openspec/specs/<cap>/` and
`openspec/contracts/<cap>/`) and one line per `paths` rule, each owner rendered as
`@<github>`, ordered by ascending specificity so that GitHub's last-match-wins selection
agrees with the resolver's most-specific-wins selection. Text outside the markers SHALL be
preserved. A human in an emitted owner set without a `github` handle SHALL make emission fail.
`codeowners.py reconcile` SHALL compare, for a probe set covering every tracked file under
`openspec/specs/` and `openspec/contracts/`, every tracked file matching each `paths` rule,
each rule's literal prefix, and one unmatched path, the owners GitHub would select from the
whole file against the resolver's owners; any difference SHALL be reported as a disagreement
error, and a managed block differing from a fresh emit SHALL be reported as stale. The
projection SHALL never be read back into `openspec/owners.yaml`.

#### Scenario: Emit ordering yields agreement
- **GIVEN** `paths` rules `openspec/contracts/**` (jan) and
  `openspec/contracts/agent-coordinator/**` (kim), both humans with `github` handles
- **WHEN** `emit` runs and then `reconcile` runs over the result
- **THEN** the managed block SHALL list `*`, then `openspec/contracts/**`, then
  `openspec/contracts/agent-coordinator/**`
- **AND** `reconcile` SHALL report zero disagreements

#### Scenario: Hand-edited line that disagrees is reported
- **GIVEN** an emitted `CODEOWNERS` with an additional unmanaged line
  `openspec/specs/agent-identity/ @someone-else` appended after the managed block
- **WHEN** `reconcile` runs
- **THEN** it SHALL report a disagreement for `openspec/specs/agent-identity/spec.md` naming
  both owner sets
- **AND** the exit code SHALL be `1`

#### Scenario: Missing GitHub handle fails emission
- **GIVEN** `default_owner` is a human with no `github` field
- **WHEN** `emit` runs
- **THEN** it SHALL fail with an error naming the principal and the field
- **AND** `.github/CODEOWNERS` SHALL NOT be modified

#### Scenario: Stale block reported and unmanaged text preserved
- **GIVEN** a `CODEOWNERS` with unmanaged lines before the managed block and a map edited since
  the last emit
- **WHEN** `reconcile` runs
- **THEN** it SHALL report the block as stale with a diff
- **AND** `emit --write` SHALL replace only the managed block, leaving the unmanaged lines
  byte-identical

#### Scenario: Repository CODEOWNERS reconciles
- **GIVEN** this repository's `openspec/owners.yaml` and `.github/CODEOWNERS`
- **WHEN** `reconcile` runs in CI
- **THEN** it SHALL report zero disagreements and a fresh managed block

### Requirement: Durable Artifact Registration

`openspec/owners.yaml` SHALL be registered in the artifact inventory of
`docs/guides/state-artifacts.md` with its path and holder, canonical writer (humans by reviewed
PR; no skill writes it), authority (owner, decision-right and acceptance-right sets with the
repository-default owner as fail-closed fallback; `CODEOWNERS` is a derived projection),
consumers, and missing-or-stale behavior (absence means solo mode; invalid or unregistered
owners fail closed and are never repaired from `CODEOWNERS`, git history or the coordinator;
a stale `CODEOWNERS` is regenerated from the map, never the reverse).

#### Scenario: Inventory row present
- **WHEN** `docs/guides/state-artifacts.md` is read
- **THEN** its inventory table SHALL contain a row for `openspec/owners.yaml` whose cells cover
  canonical writer, authority, consumers and missing-or-stale behavior
- **AND** the row SHALL state that `.github/CODEOWNERS` is a derived projection

#### Scenario: Guide tests still pass
- **WHEN** `skills/tests/state-artifacts/` runs
- **THEN** every existing assertion SHALL pass with the new row present

### Requirement: Portable Distribution

The `ownership-runtime` skill SHALL be declared `portable` in `skills/install-manifest.json`,
SHALL ship `owners.schema.json` and `human-principals.schema.json` under
`install_assets/openspec/schemas/`, and those copies SHALL be byte-identical to the canonical
files under `openspec/schemas/`. The skill SHALL be listed in `docs/skills-catalogue.md` as an
infrastructure skill.

#### Scenario: Install payload validates
- **WHEN** `bash skills/install.sh --check` runs
- **THEN** `ownership-runtime` SHALL be present in the payload with no manifest, reference or
  asset-drift violation

#### Scenario: Schema copies pinned
- **WHEN** the byte-identity test compares `openspec/schemas/owners.schema.json` and
  `openspec/schemas/human-principals.schema.json` with their `install_assets` copies
- **THEN** each pair SHALL be identical
