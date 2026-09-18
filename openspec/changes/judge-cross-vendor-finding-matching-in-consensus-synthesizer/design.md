# Design: Judge cross-vendor finding matching in consensus_synthesizer

> Change ID: `judge-cross-vendor-finding-matching-in-consensus-synthesizer`
> Roadmap item: `ri-05` of `roadmap-jev-system-one-integration-assessment`

## Context

`skills/parallel-infrastructure/scripts/consensus_synthesizer.py`'s
`ConsensusSynthesizer._match_all` greedily pairs findings across vendors by
calling the pure, synchronous `match_score(a, b) -> (score, basis)` for every
candidate pair and keeping the best per other-vendor. `match_score` has four
bands in descending strength: `location+type` (0.95), `snippet` (0.9),
`location` (0.8), then three Jaccard token-overlap bands
(`file+type+description`, `file+description`, `type+description`, capped at
0.85/0.8/0.75). Everything below `MATCH_THRESHOLD` (0.6) scores 0.0 and the
findings stay separately `unconfirmed`.

`skills/parallel-infrastructure/scripts/review_ledger.py`'s `_match_existing`
also calls `match_score` (imported alongside `MATCH_THRESHOLD`) for its own,
unrelated purpose: deduplicating findings across review *rounds* in the
ledger, not across vendors in one round. This item does not touch that call
site's behavior — see Non-Goals.

## Real API surface (grounding, not aspiration)

Confirmed by reading the actual fixture referenced in this item's own
acceptance outcome
(`openspec/changes/add-orchestrator-adjudication-review-gate/fixtures/pr484-consensus.json`,
23 entries, `consensus-report.schema.json` shape): only one of the two real
defects named in that other change's proposal is a genuine cross-vendor pair
scored 0.0 today —

- antigravity id 1 (critical): "Spec contract mismatch between build_atlas.py
  --tree footer format and explain-code grounding disclosure line."
- pi id 14 (medium): "Multi-language disclosure footer format unspecified: ...
  Design shows 'python 14% / sql 37% covered' with slashes but spec uses
  ellipsis... format mismatch."

Both describe the same footer/percent-format contract defect from two
vendors' independent, differently-phrased observations — exactly the
paraphrase gap Jaccard token-overlap misses (their description token sets
barely intersect). The other named defect (pi id 12, "nodes that export
returns") has no antigravity counterpart anywhere in the 23 entries; it is a
genuine single-vendor finding, out of scope here (see proposal.md Non-Goals).

`consensus-report.schema.json` (what this fixture actually contains) does not
preserve each contributing finding's `file_path`/`line_range` — those exist
only on the raw per-vendor `Finding` the fixture's own PR review produced,
which was never itself committed anywhere. The fixture-replay test (tasks.md
3.1) therefore reconstructs both `Finding`s from the fixture's `description`/
`type`/`criticality`/`axis` fields and assigns them the one file both
descriptions explicitly name (`build_atlas.py`'s `--tree` footer/disclosure
output) — an honest reconstruction of what the real review almost certainly
saw, not a byte-for-byte replay of data the schema never kept. This is
disclosed in the test's own docstring.

`system_one_decisions.decide()` and its plain-dict `Noul` question form are
already established by `ri-01`-`ri-04`; no new API surface to confirm there.
Unlike `gen_eval.semantic_judge.evaluate_semantic` (async), every call site in
`consensus_synthesizer.py` and `review_ledger.py` is synchronous — `decide()`
is called directly, no `asyncio.to_thread` needed.

## Decisions

### D1 — The judged path lives beside `match_score`, not inside it

`match_score(a, b)` stays a pure, synchronous, two-argument function with its
existing behavior byte-for-byte unchanged — `review_ledger.py`'s
`_match_existing` keeps calling it directly and is not affected by this item.
Batching ("N questions over one shared per-file state") is fundamentally an
orchestration concern: it needs visibility into every candidate pair sharing
a file, which a pairwise `match_score(a, b)` signature cannot provide. A new
function, `_judge_pairs(file_path, pairs, *, site) -> dict[pair_index, float]`,
takes the *list* of same-file, same-axis, fast-path-unresolved candidate
pairs for one file and returns one noul confidence per pair from a single
`decide()` call. Only `ConsensusSynthesizer._match_all` calls it.

`match_score` itself is refactored internally (still public, same signature,
same return values for the same inputs) so its location/snippet bands are
exposed as `_fast_path_score(a, b)` — `_match_all` calls this first, for
every candidate pair, to determine which pairs need no LLM call at all
(acceptance outcome: fast-path pairs issue zero `decide()` calls).

### D2 — Judged eligibility and batching shape

A candidate pair `(a, b)` is eligible for judgment when:
1. `_canonical_axis(a.axis) == _canonical_axis(b.axis)` (same axis — the
   existing hard gate at the top of `match_score`).
2. `_fast_path_score(a, b)` returned `0.0` (no location/snippet match).
3. `_paths_match(a.file_path, b.file_path)` and neither is `None` (judgment
   needs a concrete shared file to batch by; a pair with no file on either
   side has nothing to batch against and falls straight to Jaccard).

`_match_all` groups every eligible pair by `a.file_path` (normalized via
`_normalize_path`) and, once per distinct file with ≥1 eligible pair, calls
`_judge_pairs` with:

```python
state = {
    "file_path": file_path,
    "pairs": {
        f"pair_{i}": {"a": {"vendor": a.vendor, "description": a.description},
                       "b": {"vendor": b.vendor, "description": b.description}}
        for i, (a, b) in enumerate(pairs)
    },
}
questions = {
    f"pair_{i}": {
        "type": "noul",
        "instructions": f"In state.pairs.pair_{i}, findings a and b describe "
                          "the same underlying defect.",
    }
    for i in range(len(pairs))
}
answers = system_one_decisions.decide(state, questions, site="parallel-infrastructure.consensus_match")
```

One `decide()` call handles every judgeable pair on that file in this
synthesis run, regardless of how many vendor pairs it involves — this is
what makes the call-count test ("fast-path pairs issue no call") meaningful:
a file with zero eligible pairs never triggers a call, and a file with five
eligible pairs triggers exactly one.

### D3 — Unavailability and the Jaccard fallback

When `system_one_decisions` isn't installed, or `decide()` returns `None`
(any of its own unavailability branches), `_judge_pairs` returns an empty
dict — `_match_all` treats every pair from that file as un-judged and falls
through to the existing Jaccard bands for them, unchanged. This is the literal
reading of "keeping ... the Jaccard bands as the fallback": Jaccard now only
runs for a same-file+axis pair when judgment could not be reached (helper
unavailable) or was reached but scored below threshold, and continues to run
unconditionally for pairs judgment was never eligible for (no shared file).

### D4 — `evidence_class` override and `match_basis`

`FindingMatch.basis` is set to the literal string `"judged"` when a pair's
final score came from `_judge_pairs` (never composed with the existing basis
strings like `"location+type"`). `ConsensusSynthesizer._consensus_evidence_class`
gains one new branch, checked first: `if match.basis == "judged": return
JUDGMENT` — unconditionally, before the existing "all contributors judgment"
check. This is the whole point of the item: a probabilistic match, however
confident, is never allowed to promote a consensus finding into
`blocking_count` the way a deterministic corroboration does.

### D5 — `MATCH_THRESHOLD` moves into `review-rules.json`

Mirrors `_coverage_quorum_threshold()`'s existing exact pattern (design D5 of
`add-deterministic-review-preprocessing`): a `DEFAULT_MATCH_THRESHOLD = 0.6`
constant added to `review_rules.py`, a `"match_threshold": 0.6` key added to
`review-rules.json`'s default layer, and a `_default_match_threshold()`
function in `consensus_synthesizer.py` that reads
`review_rules.DEFAULT_MATCH_THRESHOLD` (degrading to the literal `0.6` only if
`review_rules` itself fails to import — the same defensive shape
`_coverage_quorum_threshold()` uses). The module-level `MATCH_THRESHOLD` name
stays (both `ConsensusSynthesizer.__init__`'s default parameter and the CLI's
`--threshold` default reference it, and `review_ledger.py`'s existing `from
consensus_synthesizer import MATCH_THRESHOLD` needs no change at all), but its
value now comes from this function call instead of being a bare literal.
`review_ledger.py` already has no other threshold literal of its own
(confirmed by reading the file) — it satisfies "read from config" purely by
transitively importing the now-config-sourced constant.

Deliberately *not* full project-override support (a `.review-rules.json`
project layer): `_coverage_quorum_threshold()`'s own docstring explains why —
`consensus_synthesizer.py`'s CLI has no natural `cwd` to resolve a project
override against. `match_threshold` follows the identical constraint for the
identical reason.

## Non-goals (out of scope for this item)

- `review_ledger.py`'s own matching gains no judged path.
- No new `event_sink` telemetry wiring (same non-goal as `ri-04`).
- Seeded-defect-set precision regression measurement (deferred; see
  proposal.md).
- Matching the fixture's singleton second defect (no antigravity counterpart
  exists to match it against).
