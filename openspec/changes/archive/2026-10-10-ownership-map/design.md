# Design — ownership-map

Phase 1 of the `multiplayer-collaboration` roadmap (`ri-02`). Scope: human principals in the
existing registry, the `openspec/owners.yaml` ownership map, a coordinator-independent resolver
and check, and a `CODEOWNERS` projection with reconcile. No consumers are wired (`ri-03`,
`ri-08`, `ri-09`, `ri-14` do that); no coordinator persistence.

## Context

The roadmap proposal's assumption table names the gap directly: "whoever runs the skill owns
the intent" lives in `/plan-feature` approval, `TRUST_POSTURE.md` and `approval.py`'s free-string
`decided_by`. The `principal-credential-architecture` roadmap (`pca-01`, change
`derive-agent-identity-from-registry`) already established that `agent-coordinator/agents.yaml`
is the only place a human declares a principal, and that everything the coordinator enforces
is a mechanical projection of it with a CI invariant guarding the projection
(`docs/registry-identity-projection.md`). Human principals have to fit that model without
becoming agents.

The closest in-repo analog for a repo-owned contract with a fail-closed loader is
`skills/shared/trust_posture.py` reading `TRUST_POSTURE.md`: absent file → documented default
behavior, present-but-invalid → loud error, never silently repaired. The ownership map follows
that shape.

## Decisions

### D1 — Human principals are a `humans:` block in `agents.yaml`, in the agent principal namespace, and are never projected

`AGENTS_SCHEMA` gains an optional top-level `humans` property. Each entry:

```yaml
humans:
  jan:
    display_name: "Jan Neumann"        # required
    github: "jankneumann"              # optional; required for CODEOWNERS emission (D8)
    email: "jan@example.org"           # optional; declared for ri-03 commit-author attribution, not consumed here (D5)
    domains: [agent-coordinator, skills] # optional, advisory slugs; nothing routes on them yet
    availability:                      # optional, declared for later items, not interpreted here
      timezone: Europe/Berlin
      hours: "09:00-18:00"
      days: [mon, tue, wed, thu, fri]
    description: "Repository maintainer"
```

Human ids and agent names share one namespace (`^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, the slug
pattern `openbao_credentials.topology` already enforces for agents); `load_agents_config()`
raises `ValueError` on a collision, naming both entries. Humans are **not** `AgentEntry`
objects: `load_agents_config()` keeps returning only agents, so `sync_profiles()`,
`get_api_key_identities()`, `get_dispatch_configs()` and `project_principals()` are untouched
by construction. A new `load_human_principals(path) -> list[HumanEntry]` sits beside it.

*Rejected*: entries with `type: human` inside `agents:`. Every agent field (`profile`,
`trust_level`, `transport`, `capabilities`) is meaningless for a human, the schema's `required`
list would need a discriminator, and every projection would need an exclusion clause — the
exact failure shape D2 of `derive-agent-identity-from-registry` had with the `evaluator`
role profile. A separate block makes "humans are not agents" structural.

### D2 — One shape, two validators, pinned equal by test

The coordinator cannot read `openspec/` at runtime (it ships in a container without it), and
the skills-side reader must not import `src.agents_config` (portability, D7). So the human
principal entry schema exists twice: inline as `HUMAN_PRINCIPAL_SCHEMA` in `agents_config.py`
(referenced by `AGENTS_SCHEMA["properties"]["humans"]["additionalProperties"]`) and as
`openspec/schemas/human-principals.schema.json`. A test in `agent-coordinator/tests` asserts
the JSON file, minus `$schema`/`$id`/`title`/`description` metadata, equals the Python dict.
This is the same single-definition discipline the Unified Trust Scale used (D4 of pca-01),
applied to a schema instead of a range.

### D3 — `openspec/owners.yaml` is the ownership map; subjects are capabilities, roadmap items and paths

```yaml
schema_version: 1
default_owner: jan                                  # required; a human principal id
registry: agent-coordinator/agents.yaml             # optional; see D10
assignments:
  capabilities:
    agent-identity:
      owners: [jan]                                 # required, >= 1 human principal id
      decision_rights: [jan]                        # optional; defaults to owners
      acceptance_rights: [jan]                      # optional; defaults to owners
  roadmap_items:
    multiplayer-collaboration/ri-02: { owners: [jan] }
  paths:
    "openspec/contracts/agent-coordinator/**": { owners: [jan] }
```

Validated by `openspec/schemas/owners.schema.json` (`additionalProperties: false`
throughout). Capability keys are `openspec/specs/<name>` directory names; roadmap item keys are
`<roadmap-id>/<item-id>`; path keys are repo-relative glob patterns restricted to the subset
of syntax that `CODEOWNERS` and the resolver interpret identically (`*`, `**`, `?`, leading
`/`, trailing `/`; no `!` negation, no `[...]` classes — D8). Owners are human principal ids
only; an agent name in any owner list is a check error (proposal non-goal "agents as owners").

The subset is only safe if both matchers apply the same rules, so the rules are fixed here
rather than left to whichever glob library the implementer reaches for. The resolver's matcher
implements exactly this table (the `CODEOWNERS` / gitignore interpretation), and the loader
rejects any `paths` key the schema admits but the table does not cover:

| Pattern shape | Matches | Note |
|---|---|---|
| no `/` anywhere (`*.md`, `README.md`) | the basename at any depth | unanchored |
| a `/` at the start or in the middle (`openspec/specs/x/`, `docs/*.md`, `/README.md`) | anchored at the repository root | a leading `/` is accepted and equivalent |
| a single segment whose only `/` is trailing (`schemas/`, `build/`) | a directory of that name **at any depth**, and every file under it | unanchored directory rule — gitignore/`CODEOWNERS` semantics; write `/schemas/` to anchor it at the root |
| trailing `/` (`openspec/specs/agent-identity/`) | every file under that directory, recursively | directory rule; anchoring follows the two rows above |
| `*`, `?` | within one path segment only; never match `/` | a wildcard **final** segment matches at that depth only (`docs/*` matches `docs/a.md`, not `docs/b/a.md` — GitHub `CODEOWNERS` semantics, which differ from gitignore here); a literal final segment (`docs/guide`) also covers a directory's contents |
| `**` as a whole segment (`**/foo`, `a/**/b`, `a/**`) | zero or more whole segments | `a/**` matches everything under `a/` |
| `**` embedded in a segment (`a/b**c`) | **rejected by the loader** with `OwnershipConfigError` | GitHub treats it as `*`; excluding it removes the one place the two matchers could legitimately differ |

The `registry:` field is a repo-relative path confined to the repository: the schema rejects a
leading `/` and any `..` segment, and `principals.py` additionally resolves the value and raises
`OwnershipConfigError` (`registry_outside_repo`) if it escapes `repo_root` (D10).
`OWNERSHIP_REGISTRY_PATH` is operator-controlled and is not confined.

*Rejected*: inline ownership in each `spec.md`/`roadmap.yaml`. It scatters the map across
dozens of files, makes "who owns everything?" a crawl, and `roadmap.yaml` is written by
`plan-roadmap`/`refine-roadmap` tooling that would then have to preserve hand-edited owner
fields.

### D4 — Resolution semantics and the `OwnerSet` result

```python
ctx = load_ownership(repo_root)                      # OwnershipContext; never raises on absence
ctx.mode                                             # "solo" | "team"  (D6)
ctx.resolve_capability("agent-identity")             # -> OwnerSet
ctx.resolve_roadmap_item("multiplayer-collaboration", "ri-02")
ctx.resolve_path("openspec/contracts/agent-coordinator/openapi/v1.yaml")

OwnerSet(owners, decision_rights, acceptance_rights, source, matched_rule)
#   source ∈ {"explicit", "default_owner", "solo"}; matched_rule is the key that matched or None
Principal(id, kind="human", display_name, github, email, source)
#   source ∈ {"registry", "git-config", "sentinel"}
```

- `load_ownership(repo_root=None)`: `repo_root` defaults to `git rev-parse --show-toplevel`
  from the current directory, else the current directory itself. Nothing else about the
  location is inferred.
- Capability and roadmap item lookups are exact-key matches.
- Every capability assignment **implies two path rules**, `openspec/specs/<cap>/` and
  `openspec/contracts/<cap>/`, carrying the capability's owner set. `resolve_path()` ranks
  implied and explicit `paths` rules in one pool, so `openspec/specs/agent-identity/spec.md`
  resolves to the owner of capability `agent-identity` unless a more specific explicit rule
  covers it. Without this D8 cannot hold: GitHub would route those directories by the emitted
  capability lines while the resolver answered `default_owner`, and reconcile would report a
  disagreement on every spec file. An implied match reports `matched_rule ==
  "capability:<cap>"` and `source == "explicit"`.
- Path lookups rank every matching rule (implied and explicit) by *specificity* — length of
  the literal prefix before the first glob metacharacter, then total pattern length — and the
  most specific rule wins. Ties go to the later rule in *rule order*: all implied rules first
  (in capability key order), then the explicit `paths` rules in file order. An explicit rule
  therefore always beats an implied rule of equal specificity, which is the only way an author
  can override a capability's ownership of one of its own directories. This ranking is what
  D8's emitter writes out, lowest precedence first, as `CODEOWNERS` line order. ("File order" relies on PyYAML preserving
  mapping order on load, which it does.)
- Any subject with no matching rule resolves to `default_owner` with `source="default_owner"`.
  There is no "unowned" result from the resolver; "unowned" is a *check* finding (D9).
- `owners.yaml` present but invalid (schema failure, unknown owner id, agent id as owner,
  `default_owner` not registered) → `OwnershipConfigError` from `load_ownership()`. Authority
  decisions fail closed; callers must not catch this and fall back to solo.
- `decision_rights` / `acceptance_rights` default to `owners` so a one-line assignment is
  complete and later items (`ri-09`, `ri-13`) can distinguish the two without every author
  having to.

### D5 — Where the sole repository principal comes from in solo mode

With no `openspec/owners.yaml`, every `resolve_*` call returns `OwnerSet(owners=(p,),
decision_rights=(p,), acceptance_rights=(p,), source="solo")` where `p` is derived in order:

1. The registry (D10) declares exactly one human → that human (`source="registry"`).
2. Otherwise `git config user.email` (then `user.name`) in the checkout: a synthetic
   `Principal(id="git:<email>", source="git-config", display_name=user.name or email)`.
   There is deliberately no "match the email to a declared human" step: rule 1 already fires
   whenever exactly one human is declared, and two or more humans without a map is the error
   below, so such a match could never be reached. The registry's `email` field is therefore
   **not consumed by this change**; it is declared so `ri-03` can attribute commit authors to
   principals, and a maintainer who prefers not to publish it may omit it with no effect here.
3. Otherwise (no registry human, no git identity — e.g. a bare CI container, or an exported
   tree with no `.git` directory or no `git` binary) `Principal(id="repository-default",
   source="sentinel")`. The check reports this as a warning; the resolver never raises in solo
   mode.

If the registry declares **two or more** humans and there is no `owners.yaml`, there is no sole
principal to return. That configuration is a team registry without an ownership map, and
`load_ownership()` raises `OwnershipConfigError` naming the fix (author `owners.yaml` with
`default_owner`). Returning "whoever is running this" in a multi-human repository is precisely
the single-principal assumption this epic removes, so it is an error, not a fallback.

*Rejected*: a `default_principal:` field in `agents.yaml`. It would make the registry carry an
ownership fact, which belongs in the map; and in the one-human case it is redundant with rule 1.

### D6 — Mode is derived from how many humans exist, not from whether `owners.yaml` exists

`ctx.mode == "solo"` iff fewer than two distinct human principals are resolvable (registry
humans, or the git-config/sentinel principal when there are none). `team` otherwise. The roadmap
constraint "solo mode must be unchanged: with one principal and no `owners.yaml`" is satisfied
either way; defining mode by principal count additionally lets a one-maintainer repository —
this one — author `owners.yaml` to dogfood the check and `CODEOWNERS` without flipping later
items (`ri-09`'s gates, `ri-12`'s draft PRs, `ri-17`'s checkpoints) into team behavior.
Downstream items MUST branch on `ctx.mode`, never on file presence. Recorded here so the
contract exists before any consumer is written.

### D7 — The resolver is an infrastructure skill, `skills/ownership-runtime/`

Layout mirrors `roadmap-runtime` (shared library skill, not user-invocable):

```
skills/ownership-runtime/
  SKILL.md                         # import surface, CLI, mode contract for consumers
  scripts/__init__.py
  scripts/owners.py                # load_ownership(), OwnershipContext, OwnerSet, resolution (D4)
  scripts/principals.py            # registry location (D10), humans reader, solo derivation (D5), mode (D6)
  scripts/codeowners.py            # emit / reconcile (D8)
  scripts/check_owners.py          # CLI (D9)
  install_assets/openspec/schemas/owners.schema.json
  install_assets/openspec/schemas/human-principals.schema.json
skills/tests/ownership-runtime/    # tests, per docs/guides/skills.md
```

Consumers import via the house sibling convention
(`sys.path.insert(0, "<skill-base-dir>/../ownership-runtime/scripts")`). Dependencies are
`pyyaml` and `jsonschema`, both already in `skills/pyproject.toml`. The skill is declared
`portable` in `skills/install-manifest.json` and never imports `src.*` or walks a path into
`agent-coordinator/`, which `skills/shared/validate_install_manifest.py` already rejects.

*Rejected*: `skills/shared/ownership.py` (the `trust_posture.py` precedent). `shared/` is for
flat helper modules; this change ships two install assets, a CLI and a SKILL.md documenting a
contract for six later items, which is what skill directories are for. Also rejected: a
user-invocable `/check-ownership` skill — the check is run by tests and by later skills, and a
slash command for it would be a seventh thing to install for no caller.

### D8 — `CODEOWNERS` is a derived projection with a managed block; emit order makes GitHub agree with the resolver

`codeowners.py emit` writes (or prints) a block in `.github/CODEOWNERS`:

```
# BEGIN ownership-map (generated from openspec/owners.yaml — do not edit; run codeowners.py emit)
*                                              @jankneumann
openspec/specs/agent-identity/                 @jankneumann
openspec/contracts/agent-coordinator/**        @jankneumann
# END ownership-map
```

- Lines are ordered by **ascending** specificity (D4's ranking), so GitHub's last-match-wins
  selects the same rule the resolver's most-specific-wins selects. `*` (from `default_owner`)
  is always first.
- Every capability assignment emits two lines, `openspec/specs/<cap>/` and
  `openspec/contracts/<cap>/`. Roadmap items have no path and emit nothing; this is documented
  in SKILL.md.
- Owners map to `@<github>`. A human in any emitted owner set without a `github` handle is an
  emit error (fail closed; the alternative is silently dropping a reviewer).
- Text outside the markers is preserved verbatim and reported by `reconcile` as *unmanaged*.
- Line order is D4's precedence restated for last-match-wins (same ranking, lowest first): ascending specificity, and at equal
  specificity implied capability lines before explicit `paths` lines, so GitHub's last match is
  the rule the resolver picks.
- With no `openspec/owners.yaml` there is nothing to project. `emit` exits `1` with
  `no_ownership_map` and writes nothing: the solo principal may have no handle, and inventing a
  `*` line would make `CODEOWNERS` an authority of its own. `reconcile` exits `0` with an
  informational `no_ownership_map` finding — unless a managed block is present, which is an
  `orphan_managed_block` warning (the map was removed but its projection survived).

`codeowners.py reconcile` builds a probe set — every tracked file under `openspec/specs/` and
`openspec/contracts/`, every tracked file matching each explicit `paths` rule, each rule's
literal prefix as a synthetic path, and one path matching no rule — and for each probe compares
the owner handles GitHub would pick (last matching line in the *whole* file, including
unmanaged lines, using CODEOWNERS glob semantics) with the resolver's owners mapped to handles.
Any difference is a **disagreement** (error). A managed block whose content differs from a
fresh emit is **stale** (warning, with the diff). `CODEOWNERS` never feeds back into
`owners.yaml`; there is no import direction. The probe set comes from `git ls-files`, so
`reconcile` requires a git checkout and the `git` binary; outside one it fails with
`not_a_git_checkout` rather than probing an incomplete tree.

*Rejected*: emitting one line per *file* to sidestep glob-semantics differences. It makes the
file churn on every new spec and still cannot cover files that do not exist yet. Restricting the
pattern subset (D3) is the cheaper way to keep the two matchers equivalent, and the reconcile
test proves it on the real tree.

### D9 — Check semantics: authority findings are errors, advisory findings are warnings

`check_owners.py [--codeowners] [--strict] [--json]` reports:

| Code | Finding | Severity | Why |
|---|---|---|---|
| `invalid_map` | `owners.yaml` fails schema, or a `paths` key falls outside the D3 table | error | invalid authority state (D4) |
| `invalid_registry` | the registry cannot be parsed, a `humans:` entry fails the human schema, a human id fails the principal-id pattern, or a human id collides with an agent name | error | the registry is an authority input (D1, D10); fail closed |
| `registry_not_found` | `OWNERSHIP_REGISTRY_PATH` or the map's `registry:` names a file that does not exist | error | an explicit location that is missing is a configuration error, not "no registry" (D10) |
| `unknown_owner` | owner id not a registered human (incl. `default_owner`) | error | outcome 2; fail closed |
| `agent_as_owner` | agent id used as owner | error | D13 |
| `team_registry_without_map` | registry declares ≥ 2 humans and no `owners.yaml` | error | D5 |
| `registry_outside_repo` | `registry:` resolves outside `repo_root` | error | D3, D10 |
| `missing_github_handle` | human in an emitted owner set lacks `github` (with `--codeowners`) | error | D8 |
| `codeowners_disagreement` | `CODEOWNERS` disagreement (with `--codeowners`) | error | outcome 4 |
| `not_a_git_checkout` | `--codeowners` requested outside a git checkout | error | D8; reconcile cannot build its probe set |
| `codeowners_unreadable` | `.github/CODEOWNERS` exists but cannot be read or decoded as UTF-8 (with `--codeowners`, and on `emit --write`) | error | D8; the projection cannot be compared or spliced, and `--json` consumers must get a finding, not a traceback |
| `unowned_capability` | capability under `openspec/specs/` with no explicit assignment (resolves to default) | warning, **team mode only** | outcome 2's "no owner" — advisory, because the default owner *does* own it; suppressed in solo mode (D14) |
| `unowned_roadmap_item` | item in any active `openspec/roadmaps/<id>/roadmap.yaml` (never `archive/`) with no explicit assignment | warning, **team mode only** | same |
| `unknown_capability` | `capabilities` key with no `openspec/specs/<key>/` directory | warning | a typo here silently un-assigns the real capability; the key set is closed, so it is checkable |
| `unknown_roadmap_item` | `roadmap_items` key naming no item in any active roadmap | warning | same. `paths` keys are deliberately *not* checked: a rule for a directory that does not exist yet is legitimate |
| `sentinel_principal` | solo principal is the sentinel (D5 step 3) | warning | the repository has no identifiable human |
| `codeowners_stale` / `codeowners_missing` | managed block stale or absent while `owners.yaml` exists (with `--codeowners`) | warning | derived projection out of date |
| `orphan_managed_block` | managed block present but no `owners.yaml` (with `--codeowners`) | warning | projection outlived its source |
| `no_ownership_map` | no `owners.yaml` (with `--codeowners`) | info | nothing to reconcile; solo mode adds no checks |

Exit code 1 on any error; `--strict` promotes warnings, never `info`. Output is a stable JSON
document under `--json` so later items can consume it; the `code` column above is that
document's machine contract — consumers key on codes, never on message text. The check runs in CI through a test in
`skills/tests/ownership-runtime/` against the real repository (same pattern as
`test_registry_projection.py`): a warning-free, error-free run is the invariant.

### D10 — Registry location for the skills-side reader

`principals.py` locates the registry in this order: `OWNERSHIP_REGISTRY_PATH` env var →
`registry:` in `owners.yaml` → `<repo_root>/agent-coordinator/agents.yaml` →
`<repo_root>/agents.yaml` → none (zero humans). It reads **only** the `humans:` block
(validated against `human-principals.schema.json`) and the *keys* of `agents:` (for the
namespace-collision check). No `${VAR}` interpolation, no secrets file, no agent-field
validation — those belong to the coordinator's loader and this reader must not become a second
one. Consumer repositories installed via `install.sh` typically have `agents.yaml` at the root
(the `bao-vault` default), which is why the fourth location exists. The `registry:` value and
the two default locations are resolved against `repo_root` and must stay inside it
(`registry_outside_repo`); the environment variable is exempt because an operator sets it.

### D11 — `owners.yaml` is a durable artifact; its registration row

Added to the inventory table in `docs/guides/state-artifacts.md`:

| Field | Value |
|---|---|
| Artifact class | **Ownership map** |
| Path / holder | `openspec/owners.yaml`, tracked on the default branch of the repository it governs |
| Canonical writer | Humans, by reviewed PR. No skill writes it; `codeowners.py` writes only the derived `.github/CODEOWNERS` managed block |
| Authority | Authoritative for owner, decision-right and acceptance-right sets over capabilities, roadmap items and paths; the repository-default owner is the fail-closed fallback. `CODEOWNERS` is a derived projection |
| Consumers | `ownership-runtime` resolver and check; later roadmap items (`ri-03`, `ri-08`, `ri-09`, `ri-12`, `ri-14`, `ri-17`) |
| Missing or stale behavior | Absence is valid and means solo mode (every call resolves to the sole repository principal, D5). Present-but-invalid, or naming an unregistered owner, fails closed: the resolver raises and the check exits 1; it is never repaired from `CODEOWNERS`, git history or the coordinator. A stale `CODEOWNERS` is reported by reconcile and regenerated from `owners.yaml`, never the reverse |

The guide's rehydration order is unchanged: ownership is reference data read on demand, not
execution state, so it does not enter the eight-step sequence.

### D12 — Test placement and the registry projection invariant extension

- Resolver, principals, check and `CODEOWNERS` tests live in `skills/tests/ownership-runtime/`
  and use `tmp_path` fixture repositories with synthetic change ids; the one repository-level
  test (`test_repository_invariant.py`) reads the real `openspec/owners.yaml`,
  `agent-coordinator/agents.yaml` and `.github/CODEOWNERS`. No test holds
  `openspec/changes/<id>/` literally (`docs/guides/openspec-path-stability.md`); the only
  change-local artifacts referenced are the draft schemas in `contracts/`, and those are
  compared against their promoted copies via `change_dir()`.
- `agent-coordinator/tests/test_human_principals.py` covers the schema, loader and collision
  check; `test_registry_projection.py` gains rule 6 — for every `HumanEntry`, no profile row,
  identity entry, assignment, dispatch config or AppRole principal carries its id — with a
  negative test that injects a human-named profile row and proves the checker fires.
- Byte-identity tests pin `openspec/schemas/*.schema.json` to their
  `install_assets/openspec/schemas/` copies (the `openspec_paths` mirror pattern), because
  `install.sh` only *reports* drift between them.

### D13 — Owners are humans; the map never names an agent

Enforced in three places so it cannot be argued around: the owners schema documents it, the
check rejects any owner id that resolves to an `agents:` key (error), and `resolve_*` never
returns a `Principal` with `kind != "human"`. `ri-13` ("owner may restrict an item to a named
principal's agents") will add an `implementer` field to the subjects it governs; that is a
different right and stays out of `owners`.

### D14 — Solo mode suppresses the advisory "unowned" findings

`unowned_capability` and `unowned_roadmap_item` are emitted only when `ctx.mode == "team"`.
With one human principal every subject is owned by that human by construction, so "no explicit
assignment" carries no information — and this repository has 40 capability directories and
roughly 190 roadmap items. If the repository invariant test (task 5.1) demanded a warning-free
`--strict` run with those findings active, every later `/plan-feature` that adds a spec
directory and every `/plan-roadmap` run would break CI until `owners.yaml` was edited, which is
exactly the solo-mode friction the roadmap constraint forbids. In team mode the findings stay:
there, "which human owns this?" is a real question with a wrong default answer.

*Rejected*: running the repository invariant without `--strict` (it would also stop exercising
the promotion path for the error-class findings), and authoring an exhaustive `owners.yaml` for
this repository (≈230 entries that churn with every planning change and demonstrate nothing a
dozen representative entries do not — task 5.2 now asks for the representative set).

## Open questions carried to implementation

- Whether `domains` should be validated against the set of capability directory names (then a
  domain is a capability) or stay free-form. Left free-form here; `ri-06` (collision owners)
  is the first consumer and can tighten it.
- Whether the probe set in D8 should also include every tracked file in the repository when the
  map has a `*`-level rule only. Deferred: with only the default line, every file resolves to the
  same owner and the probe is redundant.
- Whether `email` should be dropped from the human principal schema until `ri-03` has a
  consumer (D5 shows nothing in this change reads it). Kept optional here because the schema is
  the contract later items build on and adding a field later is a schema revision; the human
  reviewer may strike it at approval time.

## Risks

- **GitHub glob semantics drift.** Mitigated by restricting the pattern subset (D3) and by the
  reconcile test on the real tree; if GitHub changes semantics the test, not production routing,
  is what breaks.
- **Reader duplication.** The skills-side registry reader (D10) and the coordinator loader could
  diverge on what a valid human is. D2's pinned schema is the guard; the reader validates
  against the same JSON the coordinator's dict is proven equal to.
- **Scope creep into routing.** Every downstream consumer is named as a non-goal; this change
  ships the question's answer only.
