# Change: ownership-map — human principals and the git-native ownership map

> Parent roadmap: `multiplayer-collaboration` (item `ri-02`, Phase 1 "Identity and early visibility")
> Change ID: `ownership-map`
> Effort: L (decomposed into five M/S work packages; see `work-packages.yaml`)
> Priority: 1
> Depends on: nothing. `ri-01` (principles guide) is in flight and is cited, not required.
> Unblocks: `ri-03` (on-behalf-of chains), `ri-06` (collision owners), `ri-08` (queue attribution),
> `ri-09` (owner-routed escalation), `ri-12`, `ri-14`, `ri-17`.

## Why

Every team-mode behavior in the `multiplayer-collaboration` roadmap asks the same question —
*who owns X?* — and today nothing in the toolkit can answer it. The only principal registry,
`agent-coordinator/agents.yaml`, describes **agents** (harness identities with a transport, a
trust level and an API key). Humans appear nowhere: `approval.py`'s `decided_by` is a free
string, `TRUST_POSTURE.md` gates assume whoever runs the skill owns the intent, and PR routing
is whatever GitHub does by default. The motivating incident in the roadmap proposal — two
developers reconciling competing specs as "whose diff wins", and one waiting on the other's
implementation because "domain ownership" meant "I write this code" — is downstream of this
gap: there is no artifact that separates *decision and acceptance rights* over a capability
from *labor* on it (principles P1, P2, P3).

This change supplies the substrate. It does three things and deliberately no more:

1. **Human principals join the existing registry.** `agents.yaml` gains an optional `humans:`
   block (display name, GitHub handle, email, domains, availability). The roadmap constraint
   forbids a parallel registry, and the `principal-credential-architecture` roadmap already
   made `agents.yaml` the one place a human declares an identity — so humans go there, in the
   same principal namespace as agents, and are **never** projected into agent runtime state
   (no profile row, no identity-map entry, no AppRole).
2. **A git-native ownership map, `openspec/owners.yaml`,** schema-validated against
   `openspec/schemas/owners.schema.json`, assigns owners plus optional decision and acceptance
   rights to OpenSpec capabilities, roadmap items and repository paths, with a mandatory
   repository-default owner as the fail-closed fallback.
3. **A resolver library and check** that any skill can import from the git checkout alone —
   coordinator down, no network — and a `CODEOWNERS` emit/reconcile so GitHub review routing
   and the ownership map cannot silently disagree.

The acceptance outcomes from `roadmap.yaml` `ri-02` are the contract this change is measured
against; each maps to a `### Requirement:` in `specs/ownership-map/spec.md` and to tasks in
`tasks.md`:

| # | Acceptance outcome (ri-02) | Spec requirement |
|---|---|---|
| 1 | Schema-validated `owners.yaml` resolves an owner set for any capability, roadmap item, or contract path, falling back to a declared repository-default owner | Ownership Map Schema; Owner Resolution |
| 2 | A check reports capabilities with no owner and owners that are not registered principals in the extended registry (no separate registry) | Ownership Check; agent-identity / Human Principal Registry Extension |
| 3 | With no `owners.yaml`, every resolver call returns the sole repository principal and existing skill suites pass unchanged | Solo Mode |
| 4 | Resolver works from the checkout with the coordinator unavailable; generated `CODEOWNERS` has no routing disagreements in a reconcile check | Coordinator Independence; CODEOWNERS Projection |
| 5 | `owners.yaml` is registered in `docs/guides/state-artifacts.md` with writer, authority, missing/stale behavior | Durable Artifact Registration |

## What Changes

- **`agent-coordinator/agents.yaml` schema (`AGENTS_SCHEMA` in `src/agents_config.py`)** gains an
  optional top-level `humans:` mapping of human principals. Each entry requires `display_name`
  and may carry `github`, `email`, `domains`, `availability` and `description`. Human ids share
  the principal namespace with agent names; a collision is a load error. `load_agents_config()`
  keeps its return type; a new `load_human_principals()` returns `HumanEntry` records. **Not
  BREAKING**: a registry without `humans:` validates and projects exactly as today.
- **Registry projection invariant** (`tests/test_registry_projection.py`) gains a rule: human
  principals produce no agent projection (no profile row, no identity entry, no dispatch config,
  no AppRole), so the "humans are not agents" boundary fails CI rather than drifting.
- **New JSON schemas under `openspec/schemas/`** — `owners.schema.json` (the ownership map) and
  `human-principals.schema.json` (the `humans:` block). Both ship as install assets of the new
  skill so consumer repositories receive them through `skills/install.sh`. A test pins the
  coordinator's inline `humans` schema equal to the JSON file: one shape, two validators.
- **New infrastructure skill `skills/ownership-runtime/`** (not user-invocable, same pattern as
  `roadmap-runtime`): `scripts/owners.py` (loader + resolver), `scripts/principals.py` (registry
  reader, solo-principal derivation, mode), `scripts/codeowners.py` (emit/reconcile) and
  `scripts/check_owners.py` (CLI). Depends only on `pyyaml` and `jsonschema`, which the skills
  environment already carries, plus the `git` binary for `rev-parse`/`config`/`ls-files`.
  Imports nothing from `agent-coordinator/src`. Capability assignments govern the capability's
  `openspec/specs/<cap>/` and `openspec/contracts/<cap>/` paths as implied rules so the
  resolver and the emitted `CODEOWNERS` agree by construction (design D4). The check's advisory
  `unowned_*` findings are emitted in team mode only (design D14), so a solo repository's CI
  does not break every time a capability or roadmap item is added.
- **`openspec/owners.yaml` for this repository** plus a generated managed block in
  `.github/CODEOWNERS`, so outcomes 1, 2 and 4 are exercised against a real tree in CI, not
  only against fixtures. This repository has one human principal, so it stays in **solo mode**
  (see design D6) and no skill behavior changes.
- **Documentation**: `owners.yaml` row in `docs/guides/state-artifacts.md`; `ownership-runtime`
  in `skills/install-manifest.json` and `docs/skills-catalogue.md`; SKILL.md documents the
  import surface and CLI for downstream roadmap items.

### Non-goals

- **On-behalf-of chains, correlation ids, trailers** — `ri-03`, `ri-04`. The resolver returns
  principals; it does not record who acted for whom.
- **Routing anything.** No approval gate, escalation, digest, queue entry or PR template reads
  the map yet (`ri-08`, `ri-09`, `ri-10`, `ri-12`, `ri-14`, `ri-17`). This change ships the
  answer to "who owns X?", not the callers.
- **Availability-based behavior.** `availability` is declared so later items can consume it; nothing
  here interprets it.
- **Agents as owners.** Ownership ends at a human (P1). Agent principals may not appear in
  `owners.yaml`; this is a schema-level check, not a convention.
- **GitHub teams (`@org/team`) as owners**, organization identity providers, cross-repository
  ownership federation, branch-protection enforcement of `CODEOWNERS`. `CODEOWNERS` is a
  derived projection and GitHub remains the enforcer.
- **Coordinator persistence of human principals** (tables, APIs). `HumanEntry` is loaded in
  process for later items; nothing is written to Postgres or OpenBao.

## Approaches Considered

### Approach 1: Humans in `agents.yaml`, assignments in `owners.yaml`, skills-side resolver (Recommended)

Extend `AGENTS_SCHEMA` with `humans:`; author `openspec/owners.yaml` as a separate,
schema-validated assignment file; ship the resolver as an infrastructure skill that parses both
files directly with `pyyaml` + `jsonschema`; derive `CODEOWNERS` from the map.

- **Pros**: honors the no-parallel-registry constraint literally (one registry file, one
  principal namespace); assignments live in `openspec/` next to the specs, contracts and
  roadmaps they reference, so a PR touching a capability shows its ownership diff alongside;
  resolver works with only a checkout; schema files follow the existing `openspec/schemas/` +
  `install_assets/` pattern, so consumers get them via `install.sh`.
- **Cons**: two files to keep consistent (mitigated by the check: unknown owner is an error);
  the coordinator's inline schema and the shipped JSON schema must be pinned equal by test;
  skills read `agents.yaml` without the coordinator's loader, so secret interpolation and
  agent-side validation are deliberately not performed (only `humans:` is validated).
- **Effort**: L, decomposed to M/S packages.

### Approach 2: Self-contained `owners.yaml` carrying principals and assignments

One file declares both the humans and what they own; `agents.yaml` is untouched.

- **Pros**: simplest consumer story (one file, one schema); no coordinator changes at all.
- **Cons**: is exactly the parallel registry the roadmap constraints forbid — `ri-03` would then
  need to join two principal namespaces to build on-behalf-of chains, and `ri-09` would resolve
  `decided_by` against a registry the coordinator cannot see; identity facts (GitHub handle,
  email) duplicated the moment any later item needs them coordinator-side.
- **Effort**: M.

### Approach 3: `CODEOWNERS` as the source of truth; derive the map from it

Author `.github/CODEOWNERS` by hand and parse it into an ownership view.

- **Pros**: zero new files; GitHub-native; non-adopters already understand it.
- **Cons**: cannot express capabilities or roadmap items (they are not paths), cannot separate
  decision rights from acceptance rights, cannot name a repository-default owner distinct from
  `*`, and its glob semantics are GitHub-specific; a resolver built on it inherits every
  limitation the epic exists to remove.
- **Effort**: S.

### Approach 4: Coordinator-hosted ownership table and API

Store assignments in Postgres, expose `GET /ownership/resolve`, have skills call it.

- **Pros**: one live authority; natural fit for `ri-08`/`ri-09` which already talk to the
  coordinator.
- **Cons**: violates the planning-time constraint that ownership "must function with only the
  git remote"; teammates without coordinator access could not answer "who owns X?"; canonical
  state would live outside git, inverting `docs/guides/work-queue-truth-projection.md`.
- **Effort**: L.

### Selected Approach

**Approach 1.** It is the only option that satisfies all three hard constraints at once —
no parallel registry, git-native canonical state, resolver usable without the coordinator —
and it leaves `agents.yaml` as the single place a human declares *any* principal, which is what
`ri-03`'s on-behalf-of chains will need. The two-file consistency cost is paid once by the
check (unknown owner = error) and the schema-mirror test, both of which run in CI. Approaches
2–4 are recorded above as rejected; design.md records the finer-grained decisions
(D1–D13).

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Operability (coordinator independence) | Resolver and check run with `COORDINATION_API_URL` unset and no network | 100% of resolver tests pass in that configuration | implement (test), validate |
| Compatibility (solo mode) | Existing `skills/tests` and `agent-coordinator/tests` suites | Pass with no test edits when `owners.yaml` is absent | implement (checkpoint), validate |
| Performance | Cold `load_ownership()` + 1,000 `resolve_*` calls on a 200-rule map | < 250 ms design budget; the test asserts a 4× margin (1 s) so CI variance cannot flake it | implement (test with budget) |
| Portability | `skills/install.sh --check` payload validation | `ownership-runtime` installs standalone; no `agent-coordinator` import or path | implement, CI `test-infra-skills` |
| Correctness (projection) | Reconcile check over every tracked path under `openspec/specs`, `openspec/contracts`, every explicit rule and a default probe | 0 disagreements between `CODEOWNERS` and resolver | implement (test), CI `test-skills` |

## Impact

- **Affected specs**: new capability `ownership-map`; `agent-identity` gains one ADDED
  requirement (human principal registry extension).
- **Affected code**: `agent-coordinator/src/agents_config.py` (schema + `HumanEntry` loader),
  `agent-coordinator/tests/test_registry_projection.py` (one new rule), new
  `skills/ownership-runtime/`, new `skills/tests/ownership-runtime/`.
- **Affected config/docs**: `agent-coordinator/agents.yaml` (`humans:` block),
  `openspec/owners.yaml` (new), `.github/CODEOWNERS` (new, managed block),
  `openspec/schemas/owners.schema.json` and `human-principals.schema.json` (new),
  `skills/install-manifest.json`, `docs/skills-catalogue.md`, `docs/guides/state-artifacts.md`.
- **Risk**: low. Nothing reads the map yet; the only runtime-behavior change is that an
  `agents.yaml` with a malformed `humans:` block or an id colliding with an agent now fails to
  load, which is the intended fail-loud posture of the registry.

## Rollback

Delete `openspec/owners.yaml` and the `humans:` block: every resolver call returns to solo
mode and the registry projects exactly as before. The `CODEOWNERS` managed block can be
removed independently; GitHub then routes as it did before this change. No migrations, no
coordinator state.
