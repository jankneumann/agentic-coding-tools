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

`omissions[].reason` — exactly six values, from design decisions D5 and D6:

`duplicate_exact`, `duplicate_contained`, `hit_count_cap`, `file_count_cap`,
`hit_line_cap`, `total_line_cap`, plus `scope_filtered` for a hit dropped by the
local deny re-check (D2).

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

## Promotion

Both schemas are promoted to `openspec/contracts/code-search/schemas/` **inside
this change**, before archival, per `openspec/contracts/README.md`. Tests load
them from that stable path, never from `openspec/changes/<id>/contracts/`, so
archiving this change cannot break them. The two copies must stay
byte-identical and are changed in the same commit.
