# Change: Add prioritize-proposals skill

## Why
Teams need a reliable way to decide which OpenSpec proposals should be implemented next, especially when recent commits may have already resolved or altered planned work.

## What Changes
- Add a `/prioritize-proposals` skill that analyzes active OpenSpec changes and recent code history.
- Evaluate which proposals are still relevant, which need refinement, and which can be deprioritized due to conflicts.
- Produce a prioritized “what to do next” ordered list optimized for minimal file conflicts.

## Impact
- Affected specs: skill-workflow
- Affected code: new skill implementation under `/skills` and any supporting utilities
