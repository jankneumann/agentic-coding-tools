# Design: Judge decision-tag backfill in explore-feature

## Context

`propose_tags_for_archive` walks archived `session-log.md` files, extracts untagged Decision bullets, and routes each to a capability via `classify_decision`'s keyword-overlap heuristic. This item replaces that routing with a calibrated `Choice` judgment, batched per session-log phase — the textbook Jev shape per `docs/proposals/jev-system-one-integration-assessment.md` A5: "ticket routing with a no-match option."

## Decisions

### D1: Batching granularity is one call per session-log phase, not per file or per decision

The roadmap item's own wording — "batched as many questions over one session-log phase as shared state" — is explicit. `_extract_untagged_decisions` already returns each decision's `(phase_name, phase_date, ...)`; `propose_tags_for_archive` groups by `(phase_name, phase_date)` before calling `_classify_phase_decisions` once per group, with one `Choice` question per decision keyed by its `decision_index`. A file with three phases makes three calls, not one; a phase with five decisions makes one call, not five.

### D2: The judged and keyword paths share one category universe

The `Choice`'s criteria are derived from `keyword_map`'s own keys (`sorted(keyword_map)`), not a hardcoded list of the seven default tags. A caller that passes a custom or reduced keyword map (as this item's own tests do) gets a judgment constrained to that same reduced set, so the judged and fallback paths can never disagree about what capabilities exist to route to.

### D3: A malformed answer for one decision doesn't discard a phase's whole batch

Mirroring the lesson from `ri-15`'s Codex-caught partial-answer bug: `_classify_phase_decisions` returns a dict keyed by `decision_index`, populated only for decisions whose answer was present, named a recognized capability, and carried a numeric confidence. A decision missing from that dict (its own answer was malformed or absent, even though sibling decisions in the same batch answered successfully) falls back to `classify_decision` individually — it does not force the rest of the phase's judged results to be discarded too. Only a whole-call failure (module missing, `decide()` returns no usable answer at all) makes every decision in the phase fall back.

### D4: `"none"` is not a fallback signal — it's a confident negative

A `Choice` answer of `"none"` is a successful, confident classification (the judgment doesn't need more information; it just doesn't think a listed capability applies). It is not a degradation case, so it does not fall back to the keyword heuristic — it is recorded directly as `proposed_capability=None`, `confidence=<the judgment's own value>`, landing in the report's `no_match` bucket exactly like today's no-keyword-match case.

## Non-goals

- Changing `classify_decision`, `_extract_untagged_decisions`, or the CLI.
- A live TypeSafe SDK installation (see the parent proposal's Non-Goals).
