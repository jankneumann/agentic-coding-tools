# File tree

## When to use

Show responsibility layout across a few directories — what lives where for this
question.

## Smallest-view rule

Stop at the depth that names the responsibility. One-line comments on folders
beat nested file dumps.

## Worked example

Adapted from humanlayer's MIT `show-me` skill
([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):

```text
src/
├── commands/       # parses user actions
├── sessions/       # owns session state
└── transport/      # sends API requests
```

## File locations

The tree *is* the location map. Prefer real paths from the checkout; read the
directories before sketching. Not graph-backed.
