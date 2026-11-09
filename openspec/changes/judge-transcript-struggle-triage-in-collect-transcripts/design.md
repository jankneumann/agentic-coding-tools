# Design: Judge transcript struggle triage in collect-transcripts

## Context

`skills/collect-transcripts/scripts/triage.py` scores every ingested session
on four deterministic counters (`retry_count`, `tool_error_count`,
`scope_violation_count`, `user_correction_count`), then buckets a weighted
sum of those counters into `struggle_level` (none/low/medium/high) and flags
`flagged_for_deep_analysis` when the sum crosses a threshold. The weights
(1.0 / 2.0 / 3.0 / 2.5) and bucket edges (5.0 / 10.0) are hand-picked
constants with no calibration behind them.

The sibling prompt `skills/collect-transcripts/prompts/triage_v1.md` shows
the classification was always meant to be a judged call (it defines a full
LLM-facing rubric for exactly these four dimensions plus a struggle-level
verdict) -- but nothing in `triage.py` references it. The existing capability
spec (`harness-engineering`'s "Session Transcript Mining" requirement,
scenario "Triage scores every ingested session") already documents the
*intended* behavior as model-resolved ("resolve its model via the archetype
system... produce a score... single-shot struggle classification"). The
real code has drifted from that spec to pure arithmetic. This item closes
that drift, not just adds a new capability.

## D1: What gets judged, and what stays deterministic

The four counters stay exactly as they are -- pure, deterministic functions
over `NormalizedEvent` sequences, unchanged. Only the *classification* layer
changes:

- One round-level-style `Choice(struggle_level, {none, low, medium, high})`
  question, given the four counts plus the compacted transcript text as
  context.
- One `Noul("this session warrants deep analysis")` question, replacing the
  hard `composite_score >= threshold` cutoff.
- Two more `Noul`s the proposal names but the current code has no signal
  for at all: `Noul("the user redirected the agent")` (a judged version of
  `_count_user_corrections`'s heuristic) and
  `Noul("the agent did out-of-scope work")` (judged version of
  `_count_scope_violations`'s six-keyword substring match) -- these do NOT
  replace the deterministic counters (acceptance outcome 3 keeps them
  unchanged in the output schema); they are additional judged fields
  alongside the counters, for future consumers that want the judged read
  rather than the heuristic one. `TriageScore` gains
  `redirected_by_user: bool | None` and `out_of_scope_work: bool | None`
  (`None` when unavailable), leaving every existing field's meaning intact.

## D2: One `decide()` call per session, mirroring the established shape

Following `gatekeeper_shadow.build_shadow_entry` and
`convergence_disposition.classify_round`'s precedent: a single
`system_one_decisions.decide(state, questions, site=...)` call per session
carrying all four named questions (`struggle_level`, `deep_analysis`,
`user_redirected`, `out_of_scope`). `state` is `{"counters": {...4 counts...},
"transcript": <compacted text>}`.

## D3: The compaction helper is new work, not reuse

Grounding correction (see `proposal.md`): `normalize.py` has no compaction
helper today. `triage.py` gains `_compact_transcript(events: list[NormalizedEvent],
*, max_chars: int = 8000) -> str`: walks events, keeps only
`role in {USER, ASSISTANT, TOOL}`, and within each event's `content` blocks
keeps only `block.text` for `ContentType.TEXT`, `THINKING`, and
`TOOL_RESULT` blocks -- never `TOOL_USE`'s `tool_input` dict (that's the
"tool payload" acceptance outcome 2 requires excluded; a `TOOL_USE` block's
own `.text` field, when a harness populates it with a natural-language
description, is kept since it isn't the payload). Truncates to `max_chars`
from the end (most recent context is likeliest to explain struggle) and
prefixes a `"...(truncated)"` marker when cut. `max_chars=8000` is a
conservative token-budget proxy (~2000 tokens at a 4-chars/token estimate),
chosen the same way `gatekeeper_shadow._read_text_if_exists` callers cap
their reads -- no existing per-session token budget constant to reuse here.

## D4: Degradation contract

`_classify_session(counters, transcript) -> dict[str, Any]` (new function)
returns `{}` on any unavailability (module missing, `decide()` returns
`None`, or an expected answer key is missing/malformed) -- never raises.
`triage_session()` reads it with `.get(...)` per field:
- `struggle_level` / `composite_score`: unavailable -> `_classify_struggle`'s
  existing weighted-sum + bucket rule, byte-for-byte unchanged (acceptance
  outcome 1).
- `flagged_for_deep_analysis`: unavailable -> `composite_score >= threshold`,
  the exact current rule (`test_threshold_controls_flagging` asserts this
  directly and must keep passing).
- `redirected_by_user` / `out_of_scope_work`: unavailable -> `None`.

This mirrors `convergence_disposition`'s D4 exactly: since
`TYPESAFE_API_KEY` is unset in CI, every existing `test_triage.py` test
exercises this fallback path unmodified, satisfying acceptance outcome 4
without any test-side stubbing.

## Non-goals

- `deep_analyze.py` is untouched -- the rationale is explicit that it stays
  a full free-text LLM call (`capability_gap` is prose, not a bounded
  Choice), not a System One judgment.
- No change to `_count_retries`/`_count_tool_errors`/
  `_count_scope_violations`/`_count_user_corrections` themselves.
- No persistence of the judged answers beyond `TriageScore`'s existing
  `to_dict()`/serialization path -- no new storage format.

## Depends on

- `ri-05`
