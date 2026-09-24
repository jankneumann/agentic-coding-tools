# Add supervisor candidate-work digest

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `add-supervisor-candidate-work-digest`
> Roadmap item: `ri-13`
> Effort: S
> Priority: 3

## Why

`/supervise cycle` ends in a digest (`SKILL.md:176-187`) that is chat-only prose: no
file, no schema, no memory of what it showed. The cycle ledger's `seen_keys` can
suppress a stub the operator already saw, but cannot say what rank it had, what the
operator decided, or why — so a deferred stub is either re-proposed as new or lost.
Candidate-work stubs (ri-11's `candidate-work.schema.json`) have no home between
cycles: they are passed as an ad-hoc `stubs.json` and explicitly kept out of the
repo under `--dry-run`. `/prioritize-proposals` validates stubs but ranks only
`openspec/changes/` proposals. And "the operator's yes flows into `/plan-roadmap
<proposal-path>`" (`SKILL.md:217`) hands over a proposal path — a stub has none.

The supervisor is meant to be the courier that carries discovery findings into
roadmap decisions (the standardized back-edge). Today the courier has no bag, no
ledger of what was delivered, and no way to hand a single finding to the roadmap
without first writing a proposal for it. The handoff record change
(`extend-handoff-document-with-supervisor-record`) now provides the
`back_edge.digested_stubs[]` slot; this change fills it.

## What Changes

1. **Stub store.** `openspec/supervise/candidates/<encoded-stub-key>.json` — one tracked file
   per surviving stub, written by SENSE after dedupe, byte-stable (`sort_keys`,
   trailing newline). Lifecycle lives in `back_edge.digested_stubs`, not in the file;
   a pre-SENSE, pre-fingerprint maintenance pass removes `approved`/`rejected` files,
   wakes due deferrals, and rebuilds the digest from caches for every lifecycle mutation
   even when the repository tree is otherwise unchanged. The path is
   inside the supervisor's `_ALLOWED_WRITE_PREFIXES`; keys are accepted only in the
   canonical `change:<change-id>` or `prov:<hex32>` forms and encoded reversibly.

2. **Structured rubric, sub-agent scored, deterministically ranked.**
   `contracts/schemas/rubric-score.schema.json` fixes five factors, each 1–5 with a
   one-line justification: `relevance` (is the finding still true), `value` (impact
   if done), `readiness` (can it start now), `scope_fit` (is it one change), `risk`
   (blast radius). The host runs `digest.py prepare-batch --as-of <RFC3339>` to build
   one bounded, sanitized manifest and dispatches one rubric sub-agent with that payload;
   the sub-agent's only output is schema-valid JSON. `digest.py rank --batch-manifest
   <path> --scores <path>` validates exact keys, fingerprint, and the echoed host-owned
   timestamp before folding in dependency status, provenance staleness, and prior decision
   signals and emitting the ordered digest with per-factor breakdown. Staleness uses the
   last Git commit timestamp for an unchanged tracked source artifact; modified, untracked,
   missing, unsafe, and future-dated sources degrade to null rather than using
   clone-dependent mtime or producing negative staleness.
   The total order is dependency-ready pending work first, then weighted score
   (`3*relevance + 3*value + 2*readiness + scope_fit + risk`, with risk inverted so 5
   is safest), then `stub_key`; future-deferred work is a final bucket. One point is
   deducted per complete 30 days of staleness, capped at five. Scores are cached as
   singleton rubric documents at
   `openspec/supervise/candidates/<encoded-stub-key>.rubric.json`, keyed by the cycle
   fingerprint. Supervisor-owned store/cache/digest files are excluded from that
   fingerprint, so output-only commits do not invalidate the cache. The store is capped
   at 20 surviving candidates: overflow fails atomically and is surfaced as degraded
   output, bounding each changed-cycle scoring run to one batch. The full canonical prompt
   manifest—not only provenance excerpts—is capped at 64 KiB; an individually oversized
   stub fails before dispatch and remains stored for correction. An unchanged fingerprint
   reuses the prior validated digest without dispatch.

3. **Candidate digest artifact, composed by the host.** `digest.py rank` writes the
   candidate-focused `openspec/supervise/digest.json`
   (`contracts/schemas/digest.schema.json`); `digest.py digest` renders only its
   candidate additions. Fresh candidates appear under **New this cycle**, retained
   pending/deferred backlog appears under **Needs a decision**, and every candidate is
   present in `ranked`. The host composes those additions with the existing verified
   gates, active changes, ready roadmap items, blockers, and degraded sensors; the
   artifact never replaces those operational sections. The persisted file contains no
   run-dependent reuse flags. `generated_at` preserves the host-owned scoring time and
   `state_updated_at` records a later cache-only lifecycle rebuild, so unchanged inputs are
   byte-identical while lifecycle changes remain visible. On an unchanged fingerprint with
   no lifecycle transition, the prior file is validated and re-presented byte for byte.

4. **Approval → refine-roadmap.** `digest.py stub-to-request <stub_key>
   --roadmap <id> [--after ri-NN]` renders a `refine-roadmap` request YAML with one
   `op: add` whose item maps the stub (`title`, `description` + provenance line,
   `rationale`, `effort`, dependency refs) and an
   `acceptance_outcomes` placeholder the host drafts in-conversation and the operator
   confirms. Local change dependencies become `depends_on`; cross-roadmap dependencies
   become `external_depends_on`; satisfied archived dependencies are omitted; unresolved
   candidate dependencies stop request generation. Stub priority is copied explicitly;
   `--after` changes YAML insertion position but does not imply priority renumbering.
   The host runs `refiner.py preview`, shows effects, then `apply
   --expect-base-sha256`. A stub that needs a new roadmap goes through
   `/plan-roadmap --new <slug> "<pitch>" --draft` instead. Neither path dispatches
   implementers.

5. **Decisions persist.** Ranking synchronizes every pending/deferred backlog entry to
   `back_edge.digested_stubs`. Each operator decision (`approved` with route and the
   resulting `roadmap_ref` when applicable, `deferred` with optional `until`, `rejected`
   with reason) is merged into the rehydrated record via `digest.py decide`; canonical
   supervisor-record schemas and `cycle_state` sanitization gain those optional fields.
   The supervisor record (handoff + mirror) and the ledger's `seen_keys` are updated as
   today, without overwriting newer handoff-carried durable state.

6. **Bounded, untrusted, transactional rubric evidence.** The single batch contains at
   most 20 stubs and a 64-KiB canonical serialized prompt manifest, including complete
   stub payloads and mechanical inputs, with at most 2 KiB from each provenance
   artifact. Evidence is read only from contained regular repo files (never symlinks or
   URIs), redacted with `roadmap-runtime`'s `sanitize_string`, and delimited as untrusted
   data; unavailable provenance yields `staleness_days: null`, no penalty, and a degraded
   marker. The host enforces a 120-second timeout and one retry. Any missing, partial,
   invalid, timestamp-mismatched, or oversized result preserves the prior valid digest and
   does not advance the successful cycle fingerprint. Valid multi-file updates use a
   durable roll-forward journal containing typed replace and delete operations. Lifecycle
   maintenance includes terminal candidate/cache deletions and mirror/digest replacements in
   one transaction; non-digest parents are fsynced before `digest.json` is replaced last.

7. **SKILL.md.** CYCLE steps 1–5 are rewritten around lifecycle maintenance, retained
   backlog, store, bounded rubric dispatch, `rank`, composable rendering, and the
   decision loop; INTAKE gains "approve from digest". `TestWorkflowContract` moves with
   the reworded sections.

## Approaches Considered

### Approach 1: Tracked stub store + rubric sub-agent + deterministic rank + refine-roadmap seam (Recommended)

Stubs persist as files; a schema-constrained sub-agent produces factor scores; the
script validates, adds mechanical signals, ranks, caches, and renders; approval is a
previewed `refine-roadmap` add.

- **Pros**
  - Interpretable: every rank has five named factor scores and a justification.
  - Reproducible: given the same scores the rank is a pure function; scores are
    cached per fingerprint so an unchanged tree ranks identically without a call.
  - Host-assisted invariant intact — the model is dispatched by the host, never
    from `scripts/`.
  - Uses `refine-roadmap`'s transaction (preview, base-sha, strict validate) instead
    of inventing a roadmap writer.
- **Cons**
  - Two schemas and a cache directory to maintain.
  - Until ri-12 lands, the store fills only from fixtures or hand-normalized stubs.
- **Effort**: S–M (roadmap says S; the rubric contract is the extra)

### Approach 2: Extend `/prioritize-proposals` with a stub lane

Add stubs to its inventory, rubric, and JSON report; the digest reads that report.

- **Pros**
  - One ranking surface for proposals, roadmap items, and stubs.
- **Cons**
  - Touches another skill's prose rubric and persisted report schema; its report is
    keyed by `change_id`, which stubs do not have.
  - `--dry-run` forbids invoking it, so the digest would need a second path anyway.
- **Effort**: M

### Approach 3: Host-only digest, stubs inline in the handoff

No new scripts; the host ranks in conversation and the full stub payloads ride in
`back_edge`.

- **Pros**
  - Smallest diff.
- **Cons**
  - Non-reproducible ranking; the skill's idempotency promise no longer holds.
  - Handoff and mirror grow with the backlog and churn every sense.
- **Effort**: S

### Recommendation

Approach 1. Approach 3 gives up the property the supervisor exists to provide —
that a scheduled re-run is detectable and repeatable. Approach 2 puts the stub lane
in a skill the cycle may not invoke under `--dry-run`. Approach 1 keeps judgment
where the model is good (per-factor scoring against evidence) and arithmetic where
the script is good (weights, mechanical signals, caching, ordering).

### Selected Approach

**Approach 1** (Gate 1, 2026-08-29). Discovery decisions carried into the design:
(a) stubs persist as tracked files under `openspec/supervise/candidates/`; (b) ranking
is a host-dispatched rubric sub-agent constrained to a JSON schema, with the final
ordering computed deterministically in code from the factor scores plus mechanical
signals, cached per fingerprint; (c) approval routes through `refine-roadmap`'s
previewed `add` transaction, not a new roadmap writer; (d) every CYCLE run is the
periodic checkpoint. The digest logic lands in a new `scripts/digest.py` so
`cycle_state.py` keeps its current surface.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Reproducibility | Rank stability | Same scores + same tree ⇒ byte-identical `digest.json`; unchanged fingerprint ⇒ no rubric dispatch | VALIDATE (unit) |
| Interpretability | Per-item breakdown | 100% of ranked stubs carry five factor scores, justifications, and mechanical signals | VALIDATE (unit) |
| Safety | Roadmap mutation | Approval always goes through `refiner.py preview` then `apply --expect-base-sha256`; no direct `roadmap.yaml` write from supervise scripts | VALIDATE (unit + contract test) |
| Isolation | Host-assisted invariant | `skills/supervise/scripts/` still imports no LLM SDK and makes no network call | VALIDATE (existing test) |
| Compatibility | Dry-run | `--dry-run` writes nothing under `openspec/supervise/`; cached scores may be read and any rebuild is emitted only to stdout | VALIDATE (unit) |
| Security | Rubric evidence | No URI/symlink/out-of-root read; 2 KiB per artifact, 64 KiB full prompt manifest, secret redaction, data delimiters | VALIDATE (unit) |
| Performance | Dispatch bound | At most 20 candidates and exactly one rubric batch per changed cycle | VALIDATE (unit) |
| Resilience | Publication/retry | Interrupted replacement rolls forward; failed scoring leaves the successful fingerprint unadvanced | VALIDATE (unit + integration) |

## Impact

- new `skills/supervise/scripts/digest.py` (`store`, `prepare-batch`, `rank`, `digest`, `stub-to-request`, `decide` subcommands; imports `cycle_state` helpers), updates to `cycle_state.py`, `skills/supervise/SKILL.md`, `skills/supervise/templates/rubric-prompt.md`
- Contracts: change-local and stable runtime copies of `rubric-score.schema.json` and
  `digest.schema.json`; extensions to canonical `supervisor-record.schema.json` and
  `supervisor-record-mirror.schema.json`
- Specs: `supervise` (ADDED Candidate-Work Digest, ADDED Digest Approval Routing)
- Tests: `skills/tests/supervise/`

## Out of Scope

- Making generators emit stubs (ri-12).
- Dispatching implementers or opening PRs from the digest (roadmap-altitude gate).
- Ranking `openspec/changes/` proposals (stays in `/prioritize-proposals`).
- Training or fine-tuning a scorer.

## Dependencies

- `ri-02` create-supervise-skill-with-conversational-intake — completed
- `ri-05` extend-handoff-document-with-supervisor-record — completed; provides `back_edge`
- `ri-11` define-canonical-candidate-work-schema — completed
- `ri-16` add-cross-roadmap-readiness-resolver — completed; its typed cross-roadmap
  reference rules are reused, but its ready-frontier output is not a complete status index.
  Ranking and routing therefore walk strict roadmap YAML, active changes, and archived
  changes so completed, blocked, pending, and nonexistent prerequisites stay distinct.
- `refine-roadmap` skill — on main (`e610553c`)

> **Integration note (ri-04, `route-supervise-gates-through-the-approval-gate-service`).**
> The current `cycle` §5 is the `cycle_state.py gate-check` / `gate-answer` protocol.
> This change composes the artifact-backed candidate digest before that block and
> preserves the existing roadmap-approval gate; it must not reintroduce the retired
> prose-only stop.

## Acceptance Outcomes

- A supervise session produces a ranked digest of schema-valid candidate stubs on request or at its periodic checkpoint.
- Approving a stub from the digest refines an existing roadmap, or scaffolds a draft
  proposal with `/plan-roadmap --new` when no roadmap fits, without leaving the conversation.
- Digest state (last-digested stubs, standing decisions) survives session rehydration via the handoff record.
