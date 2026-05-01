# Skill Tail Block — Canonical Template

Every `user_invocable: true` skill MUST end with the three sections below, in this exact order. Copy this template into your `SKILL.md` and replace the example content with skill-specific entries.

## Why this convention exists

The tail block forces every skill to predict its own failure modes:

- **Common Rationalizations** — surfaces the excuses an agent (or human) might use to skip the skill's discipline. By naming the excuse and the counterargument up front, the skill makes "I'll skip X because Y" auditable.
- **Red Flags** — turns the skill's invariants into observable signals. A reviewer or sister-agent can scan for these without re-reading the whole skill.
- **Verification** — gives the next agent a concrete checklist that proves the skill was actually applied (not just nominally invoked).

Together, these turn the skill from prose into a testable contract. The content-invariant test framework at `skills/tests/_shared/conftest.py` enforces presence and minimum content thresholds (≥3 rationalizations, ≥3 red flags, ≥3 verification items, in correct order). Skills that omit the block fail their `test_skill_md.py`.

## Minimum content thresholds

- ≥3 rationalization rows
- ≥3 red-flag bullets
- ≥3 numbered verification items
- The three section headers must appear in the order shown below

## Exemptions

- `user_invocable: false` skills (infrastructure / orchestrator-loaded) are exempt — they're never directly executed by an operator and their invariants are tested by the calling skill.

## Template (copy below this line)

```markdown
## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I'll do X later — the deadline is tight" | Later never comes; the skill's discipline is the *only* time it gets done. |
| "This codebase already does Y instead" | Existing patterns may pre-date this convention; document the deviation, don't silently extend it. |
| "Tests are slow — I'll skip them this time" | Skipping the verification step turns the skill into theater. |

## Red Flags

- The implementation matches the request word-for-word but skipped the design decision named in the discovery step.
- A reviewer cannot point to a single concrete signal that the skill was applied.
- The commit message says "applied X" but the code shows none of X's hallmarks.

## Verification

1. Cite the specific section of this skill that informed the implementation.
2. Show the artifact (file path + line range) where the skill's discipline is visible.
3. Confirm the relevant Red Flag did not occur — if it did, name the mitigation.
```

## Example: filled-in tail block from a hypothetical TDD skill

```markdown
## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I'll write the test after I see the code work" | Reverses RED→GREEN; you'll write a test that passes by construction, proving nothing. |
| "This is a tiny change — no test needed" | The Beyonce Rule still applies; if you liked it enough to write it, put a test on it. |
| "Tests slow me down" | Tests slow down the wrong things (rework, regressions); they speed up the right things (refactoring with confidence). |

## Red Flags

- A new feature commit that touches `src/` but not `tests/`.
- All assertions in a new test pass on the *unmodified* baseline (the test would have passed before the fix).
- The test file was created *after* the implementation file (`git log --diff-filter=A`).

## Verification

1. The first commit in the feature contains only test changes (RED phase).
2. The second commit makes the test pass with minimal implementation (GREEN phase).
3. Coverage of the new code path is ≥1 explicit assertion plus ≥1 negative-case assertion.
```
