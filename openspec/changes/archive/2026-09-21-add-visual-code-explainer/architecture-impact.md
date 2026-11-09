# Architecture Impact: add-visual-code-explainer

## Scope

Adds a prompt-only `explain-code` skill and a stdlib `codebase-atlas --tree`
text export over existing `symbolEdges` call adjacency. No API, database,
compose, or package-runtime surface changes.

## Boundaries

- New code is confined to `skills/codebase-atlas/**` (tree export) and
  `skills/explain-code/**` (SKILL.md + references), plus install-manifest /
  pyproject testpaths wiring and docs delivery-status notes.
- The skill never runs `--ensure` or the analysis pipeline; it only reads
  freshness via `run_architecture.py --check` and optional `--tree` output.
- HTML / file / browser side effects remain out of scope (D9).

## Diagnostics

- Architecture gate mode: **advisory**
- Baseline diff vs merge-base `0ad06de2`: 0 new cycles, 0 node/edge delta in
  the committed graph view for this skills/docs change
- Scoped flow validation on the implementation diff: 0 findings
- Structural linters: advisory size nits on pre-existing long docs and
  review-cache artifacts only — no new dependency-direction or cross-layer
  violations attributable to the feature code

## Result

Safe to merge from an architecture perspective. No blocking structural
findings; advisory mode does not elevate size nits to gate failures.
