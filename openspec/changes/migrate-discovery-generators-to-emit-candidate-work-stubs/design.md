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
`sort_keys=True`, trailing newline). The default sidecar is adjacent to the rich
artifact; an explicit output path may override it.

### D2 — Validate before atomic persistence

skills/shared/candidate_work.py owns schema discovery, single/batch validation,
canonical JSON bytes, and atomic replacement. The existing ri-11 validator remains a
thin compatibility wrapper, so producers do not import another product skill. The
writer rejects duplicate suggested IDs, validates the full list, sorts by priority,
change ID, and provenance, and only then atomically writes canonical JSON. Failure
preserves the prior file; successful empty discovery writes an empty array.

### D3 — Producer mappings are deterministic and conservative

- Bug-scrub maps one promoted finding to one stub. Finding ID and report path become
  provenance; severity maps to the shared priority scale; effort uses an exhaustive
  category/severity table; the slug uses a valid `update-` prefix.
- Improve-harness maps one ranked capability gap to one stub. Source entry IDs become
  finding IDs, criticality maps to the shared priority scale, source rank is retained
  as a bounded tag, and the previous markdown proposal helper/flag remains as a
  compatibility wrapper for one migration window.
- Explore-feature maps only untracked shortlist items. Existing/scaffolded entries
  stay in `opportunities.json` but do not create duplicate candidate work. HMW/lens
  data and non-change-ID blockers remain in the rich artifact and contribute only
  bounded tags/rationale. Only blockers that resolve to an exact candidate, active,
  or archived change ID become `depends_on` entries.

Every adapter normalizes hinted or derived slugs through the canonical prefix set.
An existing `add-`, `update-`, `remove-`, or `refactor-` prefix is retained; `fix-`
is normalized to `update-`; and an unprefixed slug receives `update-`.

All emitted stubs populate `provenance.generator` even though the schema leaves it
optional.

### D4 — Candidate ranking is a distinct typed lane

`/prioritize-proposals --candidate-work <path>` loads and validates an object or
array, ranks stubs with stable tie-breakers, and can render them alongside active
proposals without pretending a stub is already scaffolded. Every adapter emits a
shared five-band priority estimate: critical/immediate=1, high=2, medium/normal=3,
low=4, and informational/backlog=5. Source-local rank never bypasses this common
scale. Candidate readiness uses `depends_on`; size uses `effort`; provenance supports
relevance checks. A mixed batch retains the originating generator in output.

### D5 — Plan-roadmap owns candidate-to-item mapping, not direct active-roadmap writes

A reusable helper validates one approved stub and maps it to one roadmap item:

| Candidate field | Roadmap item field |
|---|---|
| `title` | `title` |
| `description` + provenance summary | `description` |
| `rationale` | `rationale` |
| `effort` | `effort` |
| `priority` | new-roadmap item `priority`; retained in provenance for existing-roadmap intake |
| `suggested_change_id` | `change_id` |
| `depends_on` | resolved dependency item IDs |

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
lint/type-error/code-marker map to XS, test/deferred map to S, and
architecture/security/spec map to M, with unknown categories rejected rather than
silently guessed. Improve-harness emits every ranked gap: critical/high/medium/low
map to priority 1/2/3/4 and effort L/M/S/XS, while source rank is retained in a
bounded `source-rank-N` tag. A file report gets an adjacent sidecar;
stdout-only behavior remains write-free without an explicit candidate output, and the
legacy proposal flag remains. Explore-feature emits only opportunities whose exact
normalized hinted or derived change ID is absent from active and archived changes and
is not marked existing; it maps stable ID, problem statement, why-now, effort, a
bounded 1..5 priority from shortlist rank, and only blockers that resolve to exact
change IDs. Prose blockers are retained in rationale/tags, not `depends_on`.

All producers retain rich output and populate generator/source provenance. Colliding
normalized slugs receive a stable eight-hex SHA-256 suffix derived from provenance.
Candidate text is inert data: renderers escape Markdown/terminal structure and never
dereference, fetch, or execute provenance URIs.

### Candidate ranking

Candidate work is a separate report lane, never an input to the active-proposal score.
Dependencies resolve by exact change ID within the batch, then roadmap items, then
archives. Batch edges are topologically ordered; completed dependencies are satisfied;
active-incomplete or unknown dependencies mark a candidate blocked. Cycles and duplicate
suggested IDs fail the lane. The ready-queue key is priority, effort XS through XL,
generator, then suggested change ID; blocked candidates follow ready ones.

### Candidate intake

The plan-roadmap candidate_intake helper accepts exactly one stub, nonblank
operator-approved outcomes, and exactly one new-roadmap or existing-roadmap target.
New-roadmap mode additionally requires a kebab-case roadmap ID and capability; it
creates a complete schema-version-1 envelope whose `source_proposal` is the candidate
provenance source and whose sole approved `ri-01` item carries the capability. Existing
mode assigns the next free ri-NN and omits priority from the refine add operation so
refine-roadmap assigns max+1 without collisions. Both modes preserve the candidate
priority in provenance/rationale and assign exact change ID, actor, source, and
rationale. Exact dependency change IDs map to local or unique external item references;
completed archives are satisfied. Unknown, ambiguous, cyclic dependencies and
active/archive change-ID collisions fail before writes.

New-roadmap mode feeds the existing validate/save/scaffold path with overwrite disabled.
Existing-roadmap mode emits exactly one refine add operation; the host must run preview
and apply with its base hash. The helper never writes an active roadmap. Measurable is an
operator approval judgment; code validates a non-empty list of nonblank outcomes. ri-13
must call this helper after ri-12 rather than maintain a second mapping.

## Failure semantics

- Invalid or unmappable producer data: explicit error, no sidecar replacement.
- Invalid or colliding normalized change ID: explicit error, no sidecar replacement.
- Invalid mixed batch: fail before ranking; include the offending batch index.
- Duplicate suggested IDs or a dependency cycle: fail before ranking or persistence.
- Missing acceptance outcomes: refuse candidate intake.
- Dependency that cannot be resolved to the target roadmap: refuse and name it.
- Existing-roadmap mutation without refine-roadmap preview/apply: unsupported.

## Test strategy

Tests precede implementation. Every producer suite proves a representative output
passes the real ri-11 validator, normalizes invalid/legacy prefixes, separates prose
blockers from dependency IDs, and leaves no partial file on malformed input. Consumer
tests cover a mixed three-generator batch on the shared priority scale, deterministic
ordering, inert rendering, invalid-batch refusal, complete one-item new-roadmap
creation with capability, and collision-free existing-roadmap refine request
generation. A cross-skill integration test exercises producer fixtures through
ranking and intake without hand editing. Install-manifest validation proves every
portable skill that imports the shared helper declares its dependency before mirror
sync.

## Compatibility notes

The migration is additive. Existing markdown, JSON report, and opportunities fields
remain observable contracts under Hyrum's Law. New candidate sidecars are version 1;
there is no parallel schema version or producer-specific extension field.
