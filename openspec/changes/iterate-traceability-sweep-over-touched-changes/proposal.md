# Iterate the requirement-traceability sweep over touched changes

> Change ID: `iterate-traceability-sweep-over-touched-changes`
> Effort: XS
> Priority: 2

## Why

The `requirement-traceability-sweep` CI job refuses any pull request whose diff
touches more than one `openspec/changes/<id>/` directory ("ambiguous — pull
request touches multiple change directories"). That rule was written when every
pull request carried exactly one change. It no longer holds: `/plan-roadmap`
scaffolds sibling changes in one branch, and a planning session can refine
several of them together (PR #435 carries three). The `merge_group` branch of the
same job already iterates over every batched change and blocks if any fails —
the pull-request branch is stricter than the merge candidate it feeds, which is
backwards. Each change is gated on its own `--change <id>` scope regardless, so
iterating loses nothing the ambiguity rule protected.

## What Changes

- `.github/workflows/ci.yml` — the `pull_request` branch derives the set of
  touched change ids and invokes the gate once per id, blocking if any
  invocation fails (the same loop `merge_group` uses). The ambiguity error is
  removed.
- `skills/tests/validate-feature/test_ci_sweep_wiring.py` — the byte-synced
  `SWEEP_FRAGMENT` follows; the ambiguous-case test is replaced by two tests
  mirroring the merge-group pair (iterates once per change; blocks if any
  invocation fails after visiting every id).
- `gen-eval-framework` spec — the "full sweep" requirement's `pull_request`
  paragraph and its scenario are amended to the per-change rule.

## Approaches Considered

### Approach 1: Iterate on `pull_request` exactly as `merge_group` does (Recommended)
- **Pros**: one rule for both blocking events; no new code path; each change
  still gated on its own scope. **Cons**: a pull request with an unrelated
  change directory in its diff is gated on it too — which is the correct
  outcome. **Effort**: XS

### Approach 2: Keep the ambiguity rule and split multi-change pull requests
- **Pros**: no CI change. **Cons**: makes `/plan-roadmap` scaffold branches and
  batched planning unmergeable as a single unit; contradicts the merge-group
  behaviour. **Effort**: S per affected PR, forever

### Selected Approach
Approach 1 (operator decision, 2026-08-30).

## Out of Scope

Union mode, the `push` report-only run, and the unresolvable-base rules are
unchanged.
