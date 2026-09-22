# Structural diff

## When to use

The point is what changed in shape, and the surrounding structure already exists.

## Smallest-view rule

Diff only the nodes the question cares about. Match the diff shape to the topic
(component vs file layout).

## Worked example

Adapted from humanlayer's MIT `show-me` skill
([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):

For a component change:

```diff
 <SessionPage>
   useSessionEvents()
   <SessionToolbar>
+    <RunSkillButton />
   <SessionTimeline>
+    <SkillResultCard />
```

For a file-layout change:

```diff
 src/
 ├── commands/
+│   └── show-me.ts       # expands the slash command
 ├── sessions/
-└── transport.ts
+└── transport/
+    ├── client.ts
```

## File locations

Paths in the diff are the locations. Confirm them by reading the tree before
sketching. Not graph-backed.
