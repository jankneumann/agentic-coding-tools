# Judge fix-tier classification in fix-scrub

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-fix-tier-classification-in-fix-scrub`
> Effort: S
> Priority: 4

## Summary

Replace the two string tests in fix_scrub.classify with Noul("An agent could act on this marker without asking a human") and Noul("This finding includes a concrete, applicable fix"), keeping _is_ruff_fixable and source-based routing deterministic.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- A ten-word TODO with no actionable content lands in the ask-a-human tier and a terse but actionable one does not, covered by fixtures in skills/tests/fix-scrub.
- _is_ruff_fixable still classifies by ruff rule prefix with no decision call, asserted by a call-count test.
- The character-count and substring rules remain the fallback and existing classify tests pass with the helper stubbed to None.

## Rationale

Pilot step 4. "Ten characters follow the TODO" and "the text contains 'proposed fix'" are judgments dressed as string tests, and they mis-tier both terse-but-actionable markers and verbose-but-useless ones. Tiers are a plan rather than an action, so the risk of a wrong label is bounded.
