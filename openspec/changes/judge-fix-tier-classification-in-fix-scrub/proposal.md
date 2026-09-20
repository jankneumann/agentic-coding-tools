# Judge fix-tier classification in fix-scrub

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-fix-tier-classification-in-fix-scrub`
> Effort: S
> Priority: 4

## Summary

Replace the two string tests in `skills/fix-scrub/scripts/classify.py` with
`Noul("Could an agent act on this marker without asking a human?")` and
`Noul("Does this finding include a concrete, applicable fix?")`, batched into
one `decide()` call per `classify()` run, keeping `_is_ruff_fixable` and all
source-based routing deterministic. See `design.md` for the batching, fallback,
and threshold decisions (D1–D5), why no `dry_run` CLI flag is wired (D6), and
a test-location correction (D7).

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A ten-word TODO with no actionable content lands in the manual (ask-a-human)
  tier and a terse but actionable one lands in the agent tier, covered by
  fixtures in `skills/fix-scrub/tests/test_classify_judgment.py` (corrected
  from the scaffolded `skills/tests/fix-scrub` — see design.md D7).
- `_is_ruff_fixable` still classifies by ruff rule prefix with no `decide()`
  call, asserted by a call-count test.
- The character-count and substring rules remain the fallback, and all 32
  pre-existing tests in `skills/fix-scrub/tests/test_classify.py` pass
  unmodified (they call `classify_finding` directly, bypassing the new
  batching path entirely).

## Rationale

Pilot step 4. "Ten characters follow the TODO" and "the text contains 'proposed
fix'" are judgments dressed as string tests, and they mis-tier both
terse-but-actionable markers and verbose-but-useless ones. Tiers are a plan
rather than an action, so the risk of a wrong label is bounded.
