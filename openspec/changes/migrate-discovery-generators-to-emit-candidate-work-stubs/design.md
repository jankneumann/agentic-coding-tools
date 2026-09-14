# Design: candidate-work producer and consumer migration

## Context

The canonical schema is closed (`additionalProperties: false`) and is already
consumed by ri-11's `load_candidate_work()`. Producer artifacts are intentionally
richer and must not be flattened. Plan-roadmap currently ingests proposals and
refine-roadmap owns transactional mutation of existing roadmap workspaces. ri-13
adds the conversational approval surface later.

## Decisions

### D1 — Canonical adapters emit additive sidecars

Each producer keeps its current output and projects eligible entries into a JSON
array of candidate-work stubs. JSON serialization is byte-stable (`indent=2`,
`sort_keys=True`, trailing newline). Default sidecars are producer-specific and
adjacent to the rich artifact: `bug-scrub-candidate-work.json`,
`improve-harness-candidate-work.json`, and `explore-feature-candidate-work.json`. An
explicit output path may override the default, but replacement fails if an existing
valid non-empty batch at that path contains another generator.

### D2 — Validate before atomic persistence

skills/shared/candidate_work.py owns schema discovery, single/batch validation,
canonical JSON bytes, and atomic replacement. The existing ri-11 validator remains a
thin compatibility wrapper, so producers do not import another product skill. The
writer rejects duplicate final suggested IDs, validates the full list, sorts by the
total key `(priority, suggested_change_id)`, and only then atomically writes canonical
JSON. Failure preserves the prior file; successful empty discovery writes an empty
array. A shared multi-file loader validates each object or array independently,
concatenates inputs in CLI order, and rejects duplicate final IDs across the union.

### D3 — Producer mappings are deterministic and conservative

- Bug-scrub maps one promoted finding to one stub. Finding ID and report path become
  provenance; severity maps to the shared priority scale; effort uses the exhaustive
  category-only table below; the slug uses a valid `update-` prefix.
- Improve-harness maps one ranked capability gap to one stub. Source entry IDs become
  finding IDs, `max_severity` maps to the shared priority scale, source rank is retained
  as a bounded tag, and the previous markdown proposal helper/flag remains as a
  compatibility wrapper for one migration window.
- Explore-feature maps only untracked shortlist items. Existing/scaffolded entries
  stay in `opportunities.json` but do not create duplicate candidate work. HMW/lens
  data and non-change-ID blockers remain in the rich artifact and contribute only
  bounded tags/rationale. Only blockers that resolve to an exact candidate, active,
  or archived change ID become `depends_on` entries.

Every adapter normalizes hinted or derived slugs through the canonical prefix set.
An existing `add-`, `update-`, `remove-`, or `refactor-` prefix is retained; `fix-`
is normalized to `update-`; and an unprefixed slug receives `update-`. An explicit
source hint is normalized as-is and remains unsuffixed. Derived IDs use only the
immutable producer `source_id` for both their readable base and identity hash. The base
is formed by lowercasing `source_id`, replacing each maximal run outside ASCII
`[a-z0-9]` with one hyphen, stripping edge hyphens, and using `item` if empty. The
final ID is `<normalized-source-id-slug>-<identity-hash>`, where `identity-hash` is the
first eight lowercase hex characters of SHA-256 over an identity object containing
exactly `generator` and `source_id`. Bug-scrub uses the exact finding ID,
improve-harness uses the normalized capability gap (trim surrounding whitespace,
collapse internal whitespace to one ASCII space, and lowercase), and explore-feature
requires and uses the exact stable opportunity ID. The identity object is encoded with
`json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
and UTF-8 before hashing. Titles, report paths, source-entry collections, rank, and all
other volatile provenance are excluded. Later evidence or title edits therefore cannot
rename an earlier candidate. Duplicate final IDs, including two colliding explicit
hints, fail the whole batch.

All emitted stubs populate `provenance.generator` even though the schema leaves it
optional.

### D4 — Candidate ranking is a distinct typed lane

`/prioritize-proposals --candidate-work <path>` accepts a repeatable option, loads and
validates each object or array, deterministically merges all supplied sidecars, rejects
duplicate final IDs across the union, ranks stubs with stable tie-breakers, and
renders them alongside active
proposals without pretending a stub is already scaffolded. Every adapter emits a
shared five-band priority estimate: critical/immediate=1, high=2, medium/normal=3,
low=4, and informational/backlog=5. Bug-scrub severity and improve-harness `max_severity` map directly to those bands.
Explore-feature reuses its documented formula `impact*0.4 + strategic_fit*0.25 +
(4-effort)*0.2 + (4-risk)*0.15 + focus_match*0.1` with the existing numeric
mappings, whose closed range is 1.0..3.1. Score >=2.75 maps to 2, >=2.00 to 3,
>=1.50 to 4, and lower scores to 5. Explore-feature has no critical/immediate source
field and therefore never emits priority 1. Source-local rank is retained only as provenance and never
bypasses this common scale. Candidate readiness uses `depends_on`; size uses `effort`;
provenance supports relevance checks. A mixed batch retains the originating generator
in output.

### D5 — Plan-roadmap owns candidate-to-item mapping, not direct active-roadmap writes

A reusable helper validates one approved stub and maps it to one roadmap item:

| Candidate field | Roadmap item field |
|---|---|
| `title` | `title` |
| `description` + provenance summary | `description` |
| `rationale` | `rationale` |
| `effort` | `effort` |
| `priority` | new-roadmap item `priority`; retained in request rationale for existing-roadmap intake |
| `suggested_change_id` | `change_id` |
| `depends_on` | target item IDs, external roadmap item refs, or explicit satisfied-archive rationale |

Measurable `acceptance_outcomes` are required from the approved request; they are
not invented by the deterministic helper. Unresolved dependencies fail clearly.
New-roadmap requests also require an operator-approved `roadmap_id` and `capability`;
the envelope uses schema version 1, the candidate provenance source as
`source_proposal`, approved status, and one `ri-01` item carrying that capability.
The helper then feeds the existing validate/save/scaffold path. For an existing
roadmap it emits/uses a refine-roadmap add request and its preview/apply transaction,
omitting execution priority so refine-roadmap assigns the next free priority while
retaining the candidate priority in the request rationale. The helper never
overwrites an active roadmap directly.

### D6 — ri-13 is a caller, not a second implementation

This change does not edit supervisor digest code. ri-13 should be refined after ri-12
to call the candidate intake helper for its `stub-to-request` path. That keeps the
approval conversation in supervise and the mapping/mutation policy in plan-roadmap.

## Refined executable contracts

### Producer mapping

Bug-scrub emits every finding already selected by its severity filter to the report
output directory. Severity maps critical through info to priority 1 through 5;
`lint`/`type-error`/`code-marker` map to XS,
`test-failure`/`deferred-issue` map to S, and
`architecture`/`security`/`spec-violation` map to M, with unknown categories
rejected rather than silently guessed. Improve-harness emits every ranked gap:
critical/high/medium/low map to priority 1/2/3/4. Effort derives from affected-skill
count rather than severity: one skill maps to S, two or three to M, and four or more
to L; missing affected-skill evidence maps to M plus an `effort-estimate-default` tag.
Source rank is retained in a bounded `source-rank-N` tag. A file report gets its
producer-specific adjacent sidecar; stdout-only behavior remains write-free without
an explicit
candidate output, and the
legacy proposal flag remains. Explore-feature emits only opportunities whose exact
normalized hinted or derived change ID is absent from active and archived changes and
is not marked existing; it maps stable ID, problem statement, why-now, effort, the
weighted-score bands from D4, and only blockers that resolve to exact change IDs.
Shortlist rank is provenance only. Prose blockers are retained in rationale/tags, not
`depends_on`.

All producers retain rich output and populate generator/source provenance. Derived
slugs unconditionally receive the stable identity suffix defined in D3; duplicate
final IDs are rejected. Bug-scrub and explore-feature derive the base from their
required immutable source IDs; improve-harness derives it from the normalized
`capability_gap`. Mutable titles never contribute to a derived ID.
Candidate text is inert data: renderers escape Markdown/terminal structure and never
dereference, fetch, or execute provenance URIs.

### Candidate ranking

Candidate work is a separate report lane, never an input to the active-proposal score.
Ranking and intake share one resolver that groups every exact change-ID match across
the candidate batch, items in active roadmaps, active OpenSpec changes, and archived
OpenSpec changes. A group is satisfied only when every match is a completed roadmap
item or an archived-completed change. If exactly one live match remains,
it determines the outcome: an in-batch candidate creates a graph edge, a live roadmap
item is local or external according to its roadmap, and an active change without a
roadmap item remains unresolved. Completed/archive records for the same lifecycle lineage do
not make a unique live match ambiguous; two or more live matches do. Unknown or
multiple-live dependencies fail intake and seed blocked status in ranking. In-batch
dependencies create graph edges and do not by themselves mark a candidate blocked.
Blocked status propagates to all transitive in-batch dependents. Ranking uses Kahn
topological traversal: among zero-indegree nodes, choose by `(blocked_tier, priority,
effort XS..XL, generator_key, suggested_change_id)`, where ready is tier 0, blocked is
tier 1, and `generator_key = provenance.generator or ""` for schema-valid hand-authored
stubs. This preserves every dependency-before-dependent edge while keeping ready
components before blocked components. Cycles, duplicate suggested IDs, and conflicting
live dependency matches fail the lane before scoring.

### Candidate intake

The plan-roadmap candidate_intake helper accepts exactly one stub, nonblank
operator-approved outcomes, and exactly one new-roadmap or existing-roadmap target.
New-roadmap mode additionally requires a kebab-case roadmap ID and capability; it
creates a complete schema-version-1 envelope whose `source_proposal` is
`provenance.source_artifact` and whose sole approved `ri-01` item carries the
capability. Existing mode freshly loads the target workspace, assigns the next free
ri-NN in the one add request immediately before refine-roadmap preview, and omits
priority so refine-roadmap validates the ID and assigns max+1 without collisions. Both
modes preserve the candidate
priority in the request rationale and assign exact change ID, actor, source, and
rationale. The shared resolver collapses duplicate completed/archive lifecycle records. A
uniquely live
target-roadmap item becomes its local `ri-NN`; a uniquely live item in another roadmap
becomes `external_depends_on: ["roadmap-id:ri-NN"]`; and an all-completed dependency is
recorded as `Satisfied dependency: <change-id> (completed)` in the rationale with no
live edge. Each conversion is explicit in the preview. Unknown dependencies, active changes without a unique roadmap item, retired-only
failed/skipped/superseded groups, and multiple live matches fail before writes.

New-roadmap mode feeds the existing validate/save/scaffold path with overwrite disabled.
Existing-roadmap mode emits exactly one refine add operation against a freshly loaded workspace. Existing refine-roadmap behavior supplies omitted
priority as max+1, rejects duplicate
explicit `change_id` values already present in roadmap items, and validates the helper-assigned next free item ID in that preview. Apply uses the preview base hash and refuses if the
roadmap changed, so neither the ID nor priority can go stale. The helper never writes an
active roadmap. Measurable is an
operator approval judgment; code validates a non-empty list of nonblank outcomes. ri-13
must call this helper after ri-12 rather than maintain a second mapping.

## Failure semantics

- Invalid or unmappable producer data: explicit error, no sidecar replacement.
- Invalid or duplicate final suggested change ID: explicit error, no sidecar replacement.
- Invalid mixed batch: fail before ranking; include the offending batch index.
- Duplicate suggested IDs or a dependency cycle: fail before ranking or persistence.
- Missing acceptance outcomes: refuse candidate intake.
- Dependency that cannot be resolved to one unique live local/external item or an all-completed lifecycle group: refuse and name it.
- Existing-roadmap mutation without refine-roadmap preview/apply: unsupported.

## Test strategy

Tests precede implementation. Every producer suite proves a representative output
passes the real ri-11 validator, normalizes invalid/legacy prefixes, derives
membership-independent IDs, separates prose blockers from dependency IDs, writes an
empty requested sidecar when nothing is eligible, and leaves no partial file on
malformed input. Consumer tests cover a mixed three-generator batch on the shared
priority scale, the exact Kahn traversal including blocked propagation, deterministic
ordering, inert rendering, cycle/duplicate refusal, complete one-item new-roadmap
creation with capability, and collision-free existing-roadmap refine request
generation. A cross-skill integration test exercises producer fixtures through
ranking and intake without hand editing. Install-manifest validation proves every
portable skill that imports the shared helper declares its dependency and that both
harness mirror manifests are synchronized.

## Compatibility notes

The migration is additive. Existing markdown, JSON report, and opportunities fields
remain observable contracts under Hyrum's Law. New candidate sidecars are version 1;
there is no parallel schema version or producer-specific extension field.
