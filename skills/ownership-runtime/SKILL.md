---
name: ownership-runtime
description: "Git-native ownership map resolver, check and CODEOWNERS projection: who owns a capability, roadmap item or path"
category: Infrastructure
tags: [ownership, multiplayer, runtime, shared-library, codeowners]
---

# Ownership Runtime

Shared library that answers "who owns this?" from the git checkout alone. It reads the
`humans:` block of the principal registry and the ownership map `openspec/owners.yaml`, and
projects the map to `.github/CODEOWNERS`. It needs no coordinator: it imports nothing from the
coordinator, opens no network connection, and gives identical answers whether or not one is
reachable.

This is an infrastructure skill — not user-invocable. Import from `<skill-base-dir>/scripts/`
after resolving this loaded skill directory. Dependencies are `pyyaml` and `jsonschema`.

## Import surface

```python
import sys
sys.path.insert(0, "<skill-base-dir>/scripts")   # or ".../../ownership-runtime/scripts" from a sibling skill

from owners import load_ownership, OwnershipConfigError

ctx = load_ownership()                                   # repo_root defaults to the git toplevel, else the cwd
ctx.mode                                                 # "solo" | "team"
ctx.resolve_capability("agent-identity")                 # -> OwnerSet
ctx.resolve_roadmap_item("multiplayer-collaboration", "ri-02")
ctx.resolve_path("openspec/contracts/agent-coordinator/openapi/v1.yaml")
```

`OwnerSet(owners, decision_rights, acceptance_rights, source, matched_rule)`:

- `owners`, `decision_rights`, `acceptance_rights` are tuples of `Principal` (`id`, `kind="human"`,
  `display_name`, `github`, `email`, `source`); `owner_ids` gives the ids. `decision_rights` and
  `acceptance_rights` default to `owners`.
- `source` is `explicit`, `default_owner` or `solo`. `matched_rule` is the key that matched
  (`capability:<cap>` for a rule implied by a capability assignment) or `None`.
- The resolver never returns an empty owner set and never returns a non-human principal.

Lookups for capabilities and roadmap items are exact. Path lookups rank every matching rule — explicit
`paths` rules and the two rules each capability implies (`openspec/specs/<cap>/`,
`openspec/contracts/<cap>/`) — by literal-prefix length, then pattern length, and the later rule wins
a tie (implied rules first, then `paths` in file order). Path patterns use CODEOWNERS/gitignore
semantics for the supported subset (`*`, `**` as a whole segment, `?`, leading and trailing `/`);
a single-segment `dir/` matches at any depth and `/dir/` is anchored at the root.

## Mode contract for downstream items

`ctx.mode` is `"team"` iff the registry declares two or more human principals, else `"solo"`. It is
derived from the number of humans, **not** from whether `openspec/owners.yaml` exists, so a
one-maintainer repository can author a map without changing behavior.

**Downstream roadmap items MUST branch on `ctx.mode`, never on file presence.** In solo mode add no
prompt, gate or check; every `resolve_*` call returns the sole repository principal (`source="solo"`
without a map). Without a map the sole principal is the single declared human, else a synthetic
`git:<email>` principal from `git config user.email`, else the `repository-default` sentinel.

## Failure semantics

An absent map is valid. A present map that fails validation, names an unregistered owner, names an
agent as an owner, or a registry with two or more humans and no map, raises `OwnershipConfigError`
(`.code`, `.subject`). Authority decisions fail closed: **do not catch it and fall back to solo.**

## CLI

All commands accept `--repo-root DIR` (default: git toplevel) and run with plain `python3`.

```bash
python3 "<skill-base-dir>/scripts/check_owners.py" [--codeowners] [--strict] [--json]
python3 "<skill-base-dir>/scripts/codeowners.py" emit [--write] [--json]
python3 "<skill-base-dir>/scripts/codeowners.py" reconcile [--json]
```

- `check_owners.py` exits `1` on any error finding; `--strict` also promotes warnings (never
  `info`). `--json` emits `{schema_version, mode, strict, exit_code, findings:[{severity, code,
  subject, message}]}`; consumers key on `code`. Codes: `invalid_map`, `invalid_registry`,
  `registry_not_found`, `unknown_owner`, `agent_as_owner`, `team_registry_without_map`,
  `registry_outside_repo`, `missing_github_handle`, `codeowners_disagreement`, `not_a_git_checkout`
  (errors); `unowned_capability`, `unowned_roadmap_item` (warnings, team mode only),
  `unknown_capability`, `unknown_roadmap_item`, `sentinel_principal`, `codeowners_stale`,
  `codeowners_missing`, `orphan_managed_block` (warnings); `no_ownership_map` (info).
- `codeowners.py emit` renders the managed block between `# BEGIN ownership-map` and
  `# END ownership-map`, ordered by ascending specificity so GitHub's last-match-wins agrees with the
  resolver. `--write` replaces only the block in `.github/CODEOWNERS` and preserves all other text
  byte-for-byte. It fails closed with no write when there is no map (`no_ownership_map`) or an emitted
  owner has no `github` handle.
- `codeowners.py reconcile` compares, for a probe set built from `git ls-files`, the owners GitHub would
  select from the whole file with the resolver's owners. Any difference is a disagreement (exit `1`);
  a block that differs from a fresh emit is stale (warning, with a diff). It needs a git checkout.

**Roadmap items have no path**, so they have no `CODEOWNERS` line; they resolve only through
`resolve_roadmap_item()`.

## Registry location

`OWNERSHIP_REGISTRY_PATH` → `registry:` in `owners.yaml` → `agent-coordinator/agents.yaml` →
`agents.yaml` at the repository root → none. Only the `humans:` block (validated against
`human-principals.schema.json`) and the keys of `agents:` are read. The `registry:` value and the
default locations must stay inside the repository (`registry_outside_repo`).

## Schemas

`install.sh` installs `owners.schema.json` and `human-principals.schema.json` into the target
repository's `openspec/schemas/` from this skill's `install_assets/`. The coordinator keeps an inline
mirror of the human principal schema, pinned equal by a test.
