# Design: Route review convergence on per-finding dispositions

## Context

`convergence_loop.converge()` currently treats every blocking ledger item the
same way each round: build a `scoped_fix_payload` for all of them, hand the
whole batch to `fix_callback` in one call, then `mark_addressed()` all of
them unconditionally. The only per-round signal is the aggregate `trend`
list (post-compact blocking counts), and the only exit besides convergence
is the blunt stall rule `trend[-1] >= trend[-stall_window]` or the
`max_rounds` ceiling.

This under- and over-fires: it fires on a round that legitimately fixed
three findings and surfaced two new ones (net progress, but `trend` looks
flat), and it fails to fire when the *same* finding keeps bouncing between
`addressed` and reopened by `compact()` because the fixer keeps
re-addressing something reviewers keep rejecting -- `trend` can look like
it's decreasing while one specific item is dead weight.

## D1: Where the judgment lives

A new pure-function module, `skills/autopilot/scripts/convergence_disposition.py`,
mirrors the `gatekeeper_shadow.py` / `phase_outcome_shadow.py` shape: guarded
`import system_one_decisions` (never a pre-bound name, per the package's own
stubbing rule), a `classify_round(...)` entry point that returns a plain
dict on success and degrades to an unambiguous default on every
unavailability branch. `convergence_loop.converge()` calls it once per round,
immediately before building fix payloads (the existing step 2k), never
before the stall/convergence checks at 2i/2j -- those must keep reading the
raw, un-filtered `blocking` list so `max_rounds` and the stall rule are
unaffected by anything this item adds (acceptance outcomes 1 and 5).

## D2: One `decide()` call per round, not one per finding

`decide(state, questions, *, site)` already accepts a dict of *named*
questions and returns a same-shaped dict of answers (see
`gatekeeper_shadow.build_shadow_entry`, which asks for `verifiability`,
`risk`, and `verdict` in one call). `classify_round()` follows the same
shape: one `"continue"` `Noul` question ("another fix round is likely to
reduce blocking findings") plus one `f"disposition_{item_id}"` `Choice`
question per blocking item, all in a single `decide()` call. This keeps the
per-round judgment cost flat (one call regardless of how many findings are
open) instead of N+1 calls.

## D3: The four dispositions all reuse existing ledger functions

The scaffolded proposal named `reject_out_of_scope_fix` as the existing path
for `reject_out_of_scope`. That function's real signature is
`reject_out_of_scope_fix(files_modified: list[str], allowed: list[str]) -> None`
-- it diffs an *already-applied* fix against its cited paths and raises
`ScopeViolation` if the fixer strayed. It has no ledger-item parameter and
cannot express "don't even attempt a fix for this finding." The one existing
function shaped for that is `park_item(ledger, item, *, reason="disagreement")`,
already used for the disagreement/needs-human case. All three "do not fix
this round" dispositions call the same function with a different `reason`:

| disposition | `park_item(..., reason=)` |
|---|---|
| `needs_human` | `"disagreement"` (the existing default -- `is_blocking_item` and `adjudication_items` already treat `parked`/`disagreement` consistently) |
| `defer_to_followup` | `"deferred_to_followup"` |
| `reject_out_of_scope` | `"out_of_scope"` |

No new field is added to `_LEDGER_ITEM_KEYS`; `parked_reason` already exists
and is free-text. This is what "no new ledger mutation surface" (acceptance
outcome 3) actually means: one function, three reason strings, zero new
schema.

`fix_now` is the only disposition that keeps an item in the batch handed to
`fix_callback`; everything else is parked before the batch is built, so
`mark_addressed()` (which only flips `status == "open"` items) never touches
a parked item.

## D4: Degradation default

`classify_round()` returns `{}` (no dispositions) on any of: module missing,
`decide()` returns `None`, or the blocking list is empty. `converge()` reads
it with `.get(item_id, "fix_now")` -- every blocking item defaults to
`fix_now` when the judgment is unavailable, which is exactly today's
behavior: every blocking item goes to `fix_callback`, unconditionally. This
is the same "record/act nothing on unavailability" contract `gatekeeper_shadow`
and `phase_outcome_shadow` already established, adapted here because this
judgment is load-bearing (it decides what gets dispatched) rather than
observational -- the safe default has to be "dispatch everything," matching
the pre-existing behavior bit for bit.

## D5: Replay comparison is fixture-scoped, not production-scoped

`converge()`'s `trend` list is a local variable; nothing in this codebase
persists a round-by-round blocking-count history today, and the only real
`ledger.json` on disk (`add-visual-code-explainer`'s) is a single end-state
snapshot from an unrelated feature, not a trend sequence. So
`replay_dispatch_counts(rounds)` in the new module is a pure function over a
caller-supplied list of per-round blocking-item lists (each item carrying an
optional `disposition`, defaulting to `fix_now`), returning
`{"old_dispatch_count", "new_dispatch_count", "terminal_blocking_count"}`.
The old count sums every round's raw blocking-item count (today's
unconditional dispatch); the new count sums only `fix_now` items per round.
A test exercises it against a fixture trend where one item is disposed
`defer_to_followup`/`reject_out_of_scope` every round while still counted as
blocking (mirroring the rationale's "fixer keeps re-addressing a finding
reviewers keep rejecting" case) and asserts `new_dispatch_count <
old_dispatch_count` for the same `terminal_blocking_count`. Comparing against
genuine multi-round production trends is deferred until autopilot actually
persists that history from real runs -- the same deferral shape ri-04's
kappa, ri-06's disagreement rate, and ri-07's sprint measurement each used.

## Non-goals

- Persisting `trend` to disk for future replay is out of scope for this
  item; the replay function accepts trend data from any source, but nothing
  here adds a writer.
- No change to `is_blocking_item`, `adjudication_items`, or the disagreement
  escalation path (`adjudication` at step "2h") -- those are unrelated
  mechanisms this item does not touch.

## Depends on

- `ri-05`

## Open questions

None outstanding -- resolved during grounding (this file supersedes the
scaffolded placeholders).
