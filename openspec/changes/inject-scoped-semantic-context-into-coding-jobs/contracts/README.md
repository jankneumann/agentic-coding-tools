# Contracts: scoped semantic context injection (ri-12)

Two JSON Schemas describe the **skill-side** artifact that ri-12 produces: the
`Semantic code context` section handed to a coding job, and the per-hit
provenance record inside it.

| Schema | Describes |
|---|---|
| `schemas/semantic-context-section.schema.json` | One `SemanticContextResult` — the whole section, injected or fallback |
| `schemas/semantic-context-hit.schema.json` | One `InjectedHit` — the per-hit provenance record |

## What these are *not*

They do not describe the coordinator's HTTP surface. That is ri-03's
`openspec/contracts/code-search/v2.yaml` (`POST /search/code`,
`GET /search/code/status`) and it is unchanged by ri-12. These schemas describe
what a skill produces *after* consuming that response: a bounded, deduplicated,
locally re-scoped subset with rendering provenance attached.

## Field mapping to the ri-03 response

The coordinator's `CodeSearchHit` (`agent-coordinator/src/code_search.py:198`)
uses different names for two fields than the roadmap's acceptance wording. The
mapping is fixed here and asserted by a test so the two vocabularies cannot
drift apart silently:

| ri-03 `CodeSearchHit` | ri-12 `InjectedHit` | Note |
|---|---|---|
| `similarity` | `score` | Same value, roadmap's name |
| `source_revision` | `indexed_commit` | The commit the serving index was built from |
| `file_path` | `file_path` | |
| `start_line` / `end_line` | `start_line` / `end_line` | |
| `index_id` | `index_id` | |
| `scope_decision` | `scope_decision` | Always `allowed`; a hit that fails the local re-check is omitted, not downgraded |
| `language`, `content` | `language`, `content` | Verbatim |

## Closed enums

`omissions[].reason` — exactly seven values. Two dedup reasons from D5
(`duplicate_exact`, `duplicate_contained`), four budget reasons from D6
(`hit_count_cap`, `file_count_cap`, `hit_line_cap`, `total_line_cap`), and
`scope_filtered` for a hit dropped by the local deny re-check (D2).

`fallback.trigger` — exactly four values, from D8: `stale`, `unavailable`,
`mismatched`, `out_of_scope`. `fallback.strategy` is the constant
`exact_search`, matching ri-03's `Fallback.strategy`
(`agent-coordinator/src/code_search.py:211`).

## Structural invariants

The section schema enforces, via `oneOf`, that:

- `status: "injected"` requires `provenance`, forbids `fallback`, and requires a
  non-empty `hits` array.
- `status: "fallback"` requires `fallback`, forbids `provenance`, and requires
  `hits` to be empty.

This mirrors ri-03's own `validate_state_invariants`
(`agent-coordinator/src/code_search.py:227`), where a non-ready state must carry
zero results. A section that claims to be injected while carrying a fallback is
unrepresentable.

## Enforced, not merely described

A description is not a constraint, so two invariants these schemas assert in
prose are also enforced by `pattern`:

- **`index_id` is a UUID.** `format: uuid` is an *annotation*; a JSON Schema
  validator ignores it unless a format checker is explicitly installed, and
  neither the tests nor any consumer installs one. Without the accompanying
  pattern, any string — `"not-a-uuid"` — would validate, and "which index served
  this hit" would stop being answerable. Both the per-hit `index_id` and
  `provenance.index_id` carry the pattern.
- **`file_path` is repository-relative with no `..` segment.** It applies to
  rendered hits and to `omissions[].file_path` alike. The rendered section names
  files a worker is invited to open, so a path escaping the repository would be a
  scope claim the artifact must be structurally unable to make. The pattern still
  admits ordinary names containing dots (`docs/guides/a..b.md`).

One invariant is stated but *not* enforceable: `end_line >= start_line` compares
two sibling properties, which JSON Schema cannot express. It is a producer
obligation, checked by the retrieval helper's own tests rather than here.

## Promotion

Both schemas are promoted to `openspec/contracts/code-search/schemas/` **inside
this change**, before archival, per `openspec/contracts/README.md`. Tests load
them from that stable path, never from `openspec/changes/<id>/contracts/`, so
archiving this change cannot break them. The two copies must stay
byte-identical and are changed in the same commit.

Both obligations are gates, not conventions:

| Test | Fails when |
|---|---|
| `skills/tests/context-engineering/test_promoted_semantic_context_contracts.py` | a schema is authored but never promoted, the two copies drift by a byte, or a promoted schema still declares a change-local `$id` |
| `skills/tests/context-engineering/test_semantic_context_schemas.py` | a schema stops rejecting a contradictory state, or this README's enum counts and mapping table drift from the schemas |

Because `$id` names the promoted location, the section schema's relative
`$ref` to the hit schema resolves to its promoted sibling — a change-local `$id`
would send that reference into the directory archival moves.
