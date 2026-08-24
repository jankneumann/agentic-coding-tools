# Change: <change-id>

## Why

<!-- 1-2 paragraphs on the problem/opportunity and why now -->

## What Changes

<!-- Bullet list of behavior/workflow changes.
     Mark breaking behavior explicitly with **BREAKING**. -->

## Non-Functional Requirements

<!-- Architectural qualities this change must hold to, as objective targets.
     Every entry needs a metric that can be measured, not an adjective:
     "p95 < 200ms under 50 rps", not "should be fast".
     Draw attributes from observability, resilience, performance,
     compatibility, operability -- whichever the change actually touches.
     "Verified by" names the phase or check that measures the target
     (e.g. Architecture validation, Performance phase, CI coverage job).
     If no NFR applies, say so explicitly -- do not leave the table empty. -->

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| <quality> | <what is measured> | <threshold> | <phase or check> |

## Approaches Considered

<!-- Present 2-3 distinct approaches (3-5 in --explore mode).
     Each approach should be a genuinely different way to solve the problem,
     not minor variations of the same solution. -->

### Approach 1: <name>

<!-- Description: 1-2 sentences on how this approach works -->
<!-- Pros: bullet list -->
<!-- Cons: bullet list -->
<!-- Effort: S / M / L -->

### Approach 2: <name>

<!-- Description: 1-2 sentences on how this approach works -->
<!-- Pros: bullet list -->
<!-- Cons: bullet list -->
<!-- Effort: S / M / L -->

### Recommended

<!-- Which approach and why. Reference specific pros/cons that make it the best fit. -->

### Selected Approach

<!-- Filled after Gate 1 direction approval.
     State which approach was selected by the user and any modifications requested. -->

## Impact

<!-- Affected specs and major code/doc touchpoints -->
