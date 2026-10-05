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
    email: "jan@example.org"           # optional; used for git-config matching (D5)
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

- Capability and roadmap item lookups are exact-key matches.
- Path lookups rank every matching `paths` rule by *specificity* — length of the literal
  prefix before the first glob metacharacter, then total pattern length — and the most
  specific rule wins; ties go to the later rule in file order. This ranking is what D8's
  emitter inverts into `CODEOWNERS` line order.
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
2. Otherwise `git config user.email` (then `user.name`) in the checkout: if the email matches a
   declared human, that human; else a synthetic `Principal(id="git:<email>",
   source="git-config", display_name=user.name or email)`.
3. Otherwise (no registry human, no git identity — e.g. a bare CI container)
   `Principal(id="repository-default", source="sentinel")`. The check reports this as a
   warning; the resolver never raises in solo mode.

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

`codeowners.py reconcile` builds a probe set — every tracked file under `openspec/specs/` and
`openspec/contracts/`, every tracked file matching each explicit `paths` rule, each rule's
literal prefix as a synthetic path, and one path matching no rule — and for each probe compares
the owner handles GitHub would pick (last matching line in the *whole* file, including
unmanaged lines, using CODEOWNERS glob semantics) with the resolver's owners mapped to handles.
Any difference is a **disagreement** (error). A managed block whose content differs from a
fresh emit is **stale** (warning, with the diff). `CODEOWNERS` never feeds back into
`owners.yaml`; there is no import direction.

*Rejected*: emitting one line per *file* to sidestep glob-semantics differences. It makes the
file churn on every new spec and still cannot cover files that do not exist yet. Restricting the
pattern subset (D3) is the cheaper way to keep the two matchers equivalent, and the reconcile
test proves it on the real tree.

### D9 — Check semantics: authority findings are errors, advisory findings are warnings

`check_owners.py [--codeowners] [--strict] [--json]` reports:

| Finding | Severity | Why |
|---|---|---|
| `owners.yaml` fails schema | error | invalid authority state (D4) |
| owner id not a registered human (incl. `default_owner`); agent id used as owner | error | outcome 2; fail closed |
| registry declares ≥ 2 humans and no `owners.yaml` | error | D5 |
| human in an emitted owner set lacks `github` (with `--codeowners`) | error | D8 |
| `CODEOWNERS` disagreement (with `--codeowners`) | error | outcome 4 |
| capability under `openspec/specs/` with no explicit assignment (resolves to default) | warning | outcome 2's "no owner" — advisory, because the default owner *does* own it |
| roadmap item in any `openspec/roadmaps/*/roadmap.yaml` with no explicit assignment | warning | same |
| solo principal is the sentinel (D5 step 3) | warning | the repository has no identifiable human |
| `CODEOWNERS` managed block stale or absent while `owners.yaml` exists | warning | derived projection out of date |

Exit code 1 on any error; `--strict` promotes warnings. Output is a stable JSON document under
`--json` so later items can consume it. The check runs in CI through a test in
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
(the `bao-vault` default), which is why the fourth location exists.

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

## Open questions carried to implementation

- Whether `domains` should be validated against the set of capability directory names (then a
  domain is a capability) or stay free-form. Left free-form here; `ri-06` (collision owners)
  is the first consumer and can tighten it.
- Whether the probe set in D8 should also include every tracked file in the repository when the
  map has a `*`-level rule only. Deferred: with only the default line, every file resolves to the
  same owner and the probe is redundant.

## Risks

- **GitHub glob semantics drift.** Mitigated by restricting the pattern subset (D3) and by the
  reconcile test on the real tree; if GitHub changes semantics the test, not production routing,
  is what breaks.
- **Reader duplication.** The skills-side registry reader (D10) and the coordinator loader could
  diverge on what a valid human is. D2's pinned schema is the guard; the reader validates
  against the same JSON the coordinator's dict is proven equal to.
- **Scope creep into routing.** Every downstream consumer is named as a non-goal; this change
  ships the question's answer only.
