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

1. **Stub store.** `openspec/supervise/candidates/<stub_key>.json` — one tracked file
   per surviving stub, written by SENSE after dedupe, byte-stable (`sort_keys`,
   trailing newline). Lifecycle lives in `back_edge.digested_stubs`, not in the file;
   a stub whose decision is `approved` or `rejected` is removed from the store by the
   next cycle. The path is inside the supervisor's `_ALLOWED_WRITE_PREFIXES`.

2. **Structured rubric, sub-agent scored, deterministically ranked.**
   `contracts/schemas/rubric-score.schema.json` fixes five factors, each 1–5 with a
   one-line justification: `relevance` (is the finding still true), `value` (impact
   if done), `readiness` (can it start now), `scope_fit` (is it one change), `risk`
   (blast radius). The host dispatches one rubric sub-agent per batch with the stub,
   its provenance artifact excerpt, and the ready set; the sub-agent's only output is
   schema-valid JSON. `cycle_state.py rank --scores scores.json` validates the scores,
   folds in the mechanical signals it computes itself (dependency readiness from
   `ready_across_roadmaps`, provenance staleness, prior `deferred` → sink, prior
   `rejected` → drop), and emits the ordered digest with per-factor breakdown.
   Weights live in code. Scores are cached at
   `openspec/supervise/candidates/<stub_key>.rubric.json` keyed by the cycle
   fingerprint; an unchanged fingerprint reuses them, so two runs over an unchanged
   tree rank identically without re-dispatching.

3. **Digest artifact.** `cycle_state.py digest` renders the ranked list into the
   existing five sections and writes `openspec/supervise/digest.json`
   (`contracts/schemas/digest.schema.json`); the host prints the prose from it.
   Every ranked stub carries `stub_key`, `rank`, factor scores, mechanical signals,
   and `decision: pending`. When the fingerprint is unchanged the prior digest is
   re-presented from `back_edge` and the store, not re-ranked.

4. **Approval → refine-roadmap.** `cycle_state.py stub-to-request <stub_key>
   --roadmap <id> [--after ri-NN]` renders a `refine-roadmap` request YAML with one
   `op: add` whose item maps 1:1 from the stub (`title`, `description` +
   provenance line, `rationale`, `effort`, `priority`, `depends_on`) and an
   `acceptance_outcomes` placeholder the host drafts in-conversation and the operator
   confirms. The host runs `refiner.py preview`, shows effects, then `apply
   --expect-base-sha256`. A stub that needs a new roadmap goes through
   `/plan-roadmap --new --draft` instead. Neither path dispatches implementers.

5. **Decisions persist.** Each operator decision (`approved` with the resulting
   `roadmap_ref`, `deferred` with optional `until`, `rejected` with reason) is
   recorded in `back_edge.digested_stubs` via `cycle_state.py decide`, written to the
   supervisor record (handoff + mirror) at the end of the cycle, and the ledger's
   `seen_keys` is updated as today.

6. **SKILL.md.** CYCLE steps 2–5 are rewritten around the store, rubric dispatch,
   `rank`, `digest`, and the decision loop; INTAKE gains "approve from digest".
   `TestWorkflowContract` moves with the reworded sections.

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
| Compatibility | Dry-run | `--dry-run` writes nothing under `openspec/supervise/` and reuses cached scores only | VALIDATE (unit) |

## Impact

- new `skills/supervise/scripts/digest.py` (`store`, `rank`, `digest`, `stub-to-request`, `decide` subcommands; imports `cycle_state` helpers), `skills/supervise/SKILL.md`, `skills/supervise/templates/rubric-prompt.md`
- Contracts: `rubric-score.schema.json`, `digest.schema.json`
- Specs: `supervise` (ADDED Candidate-Work Digest, ADDED Digest Approval Routing)
- Tests: `skills/tests/supervise/`

## Out of Scope

- Making generators emit stubs (ri-12).
- Dispatching implementers or opening PRs from the digest (roadmap-altitude gate).
- Ranking `openspec/changes/` proposals (stays in `/prioritize-proposals`).
- Training or fine-tuning a scorer.

## Dependencies

- `ri-02` create-supervise-skill-with-conversational-intake — completed
- `ri-05` extend-handoff-document-with-supervisor-record — planned (this branch); provides `back_edge`
- `ri-11` define-canonical-candidate-work-schema — completed
- `ri-16` add-cross-roadmap-readiness-resolver — **not started**. Declared by the
  roadmap as a dependency, but this plan does not need the resolver itself: its
  mechanical readiness signal reads `cycle_state.ready_across_roadmaps`, which
  ri-02 shipped. Sequence after ri-16 only if the roadmap ordering is enforced.
- `refine-roadmap` skill — on main (`e610553c`)

## Acceptance Outcomes

- A supervise session produces a ranked digest of schema-valid candidate stubs on request or at its periodic checkpoint.
- Approving a stub from the digest routes it into /plan-roadmap without leaving the conversation.
- Digest state (last-digested stubs, standing decisions) survives session rehydration via the handoff record.
