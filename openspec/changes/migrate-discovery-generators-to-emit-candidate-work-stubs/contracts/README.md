# Candidate-work integration contracts

This change introduces no new schema. It consumes these canonical contracts:

- `openspec/schemas/candidate-work.schema.json` — producer sidecars and candidate
  input to prioritize-proposals/plan-roadmap.
- `openspec/schemas/roadmap.schema.json` — mapped roadmap items and workspaces.
- `openspec/schemas/work-packages.schema.json` — implementation package plan.

## Sidecar contract

| Producer | Rich artifact retained | Candidate-work sidecar |
|---|---|---|
| bug-scrub | `bug-scrub-report.{md,json}` | adjacent `bug-scrub-candidate-work.json` |
| improve-harness | capability-gap report / legacy proposal markdown | explicit output or adjacent `improve-harness-candidate-work.json` |
| explore-feature | `docs/feature-discovery/opportunities.json` | `docs/feature-discovery/explore-feature-candidate-work.json` |

All sidecars are JSON arrays, validate fully before atomic replacement, serialize
with `indent=2`, sorted keys, and a trailing newline, populate `provenance.generator`, normalize
change IDs to add/update/remove/refactor prefixes, and use the shared five-band
priority scale. Only blockers that resolve to exact change IDs enter `depends_on`;
free-form blockers remain inert rationale or tags. An explicit destination containing
a valid non-empty batch from another generator is a collision and is not replaced.

Explicit source IDs are normalized as-is and remain unsuffixed. Derived IDs use the
immutable producer `source_id` for both base and hash. The base lowercases `source_id`,
replaces maximal runs outside ASCII `[a-z0-9]` with one hyphen, strips edge hyphens,
and falls back to `item` if empty. Derived IDs append the first eight lowercase hex
characters of SHA-256 over an identity object with exactly `generator` and `source_id`
keys. Improve-harness trims, whitespace-collapses, and lowercases `capability_gap`;
explore-feature requires the exact stable opportunity ID. Bug-scrub uses
`bug-finding-<semantic-hash>`, with the first 16 lowercase SHA-256 hex characters over
a canonical JSON object containing exactly `source`, `source_key`, `category`,
`file_path`, `detail`, `origin_change_id`, and `origin_artifact_path`. Source/category
are whitespace-collapsed and lowercased, paths use forward slashes, detail is
whitespace-collapsed and strips an exact leading `<file_path>:<line>:` coordinate, and
missing origin values use empty strings. `source_key` preserves stable collector keys:
ruff/mypy/markers strip `:<line>`, architecture/deferred strip the trailing ordinal,
OpenSpec uses `openspec` because detail/path identify the issue, and pytest/security
keys remain intact. The unmodified finding ID, line/index metadata, severity, title,
report path, and collector order/rank are excluded; the original ID remains provenance. The
objects are serialized with `json.dumps(identity, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` and UTF-8 encoded. Distinct semantic fingerprints that collide on
the compact bug source ID fail the complete batch, as do duplicate final IDs.
Explore-feature reuses its documented 1.0..3.3 weighted-score formula, including
`focus_match` from 0 through 3, and fixed D4
bands; shortlist rank is provenance only and explore never emits priority 1.
Bug-scrub severity and improve-harness `max_severity` are trimmed and lowercased;
unknown values fail with concise validation errors. Improve-harness derives effort from
affected-skill count, never severity. Ranking uses
the empty string when the optional provenance generator is absent. The repeatable `--candidate-work PATH` option validates every supplied object or array, concatenates
them in argument order, and rejects duplicates across the merged union before ranking.

## Approved intake contract

The shared lifecycle collector reads roadmap identity, item identity, change ID, and status without requiring archived roadmaps to satisfy the current full roadmap schema. Ranking, intake, and explore-feature known-change filtering consume that same exact model; malformed lifecycle fields fail consistently, while lifecycle-readable legacy archives remain usable.

The plan-roadmap intake accepts one schema-valid stub plus non-empty measurable
acceptance outcomes. New-roadmap mode also requires an approved roadmap ID and
capability and returns a complete schema-version-1 envelope using `provenance.source_artifact` as `source_proposal`. Existing-roadmap mode
returns a refine add request without an explicit execution priority, allowing refine-roadmap to assign max+1 while retaining
the candidate priority in the request rationale. A shared resolver groups exact matches by change ID,
maps one unique live roadmap item locally or externally, and records a group as
satisfied only when every record is a completed roadmap item or completed archive.
Failed, skipped, and superseded records remain unresolved. One active-change record
plus its sole live roadmap item collapses to one lineage; multiple live candidate or
roadmap owners are ambiguous. Unknown, active-without-roadmap, retired-only, or
multiple-live dependencies fail. Existing refine-roadmap supplies an
omitted priority as max+1, rejects duplicate item `change_id` values, and refuses stale
preview hashes. Intake does not write an existing roadmap itself.
