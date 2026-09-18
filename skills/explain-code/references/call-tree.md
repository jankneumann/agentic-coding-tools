# Call tree

## When to use

Show runtime control flow — who calls whom for the current question.

## Smallest-view rule

Keep only the calls the question needs. Prefer `--hops 1` or `2`; widen only when
a missing hop hides the point. Prefer one direction (`out` or `in`) over `both`.

## Worked example

Adapted from humanlayer's MIT `show-me` skill
([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):

```text
submitForm
  createSession
    persistPrompt
    launchAgent
  navigateToSession
```

## File locations

Every node should carry its file (and line when known), e.g.
`createSession  (sessions/create.ts:40)`. When grounded, copy paths from
`build_atlas.py --tree` output rather than inventing them.
