---
name: good-skill
description: A well-formed skill used as a positive fixture for content invariants
category: Testing
tags: [fixture, testing]
triggers:
  - "good skill"
user_invocable: true
---

# Good Skill

This is a minimal but compliant SKILL.md.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "Skipping tests is fine for fixtures" | Fixtures themselves prove the invariant works; skipping them voids the contract. |
| "The skill is too small to need a tail block" | Convention applies regardless of size. |
| "I'll add the tail block later" | Later never comes; convention requires it now. |

## Red Flags

- Frontmatter is missing required keys.
- A SKILL.md cites `references/<file>.md` that does not exist.
- A skill declares `user_invocable: true` but ships no tail block.

## Verification

1. `assert_frontmatter_parses` returns a dict.
2. `assert_required_keys_present` does not raise.
3. `assert_tail_block_present` does not raise.
