# Component tree

## When to use

Show UI or module structure with the state and boundaries that matter for the
question.

## Smallest-view rule

Collapse children that are not on the path of the question. One focused subtree
beats a full app tree.

## Worked example

Adapted from humanlayer's MIT `show-me` skill
([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):

```tsx
<SessionPage> (apps/example/src/routes/session.tsx)
  useSessionEvents()
  <SessionToolbar>
    <RunSkillButton> (packages/ui)
```

## File locations

Attach the defining file path in parentheses on each node that the reader might
open. Read those files before sketching; this form is not graph-backed.
