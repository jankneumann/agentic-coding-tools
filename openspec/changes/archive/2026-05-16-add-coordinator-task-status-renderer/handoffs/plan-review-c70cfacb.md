# PLAN_REVIEW Handoff — plan-review-c70cfacb

**Phase:** PLAN_REVIEW
**Date:** 2026-05-15
**Author:** architect sub-agent (Opus 4.7)
**Change:** add-coordinator-task-status-renderer

## Rounds run

2 (round-1 + round-2).

## Vendors

`claude_code`, `codex`, `gemini` — all three succeeded in round-2 (round-1 gemini was empty due to the synthesizer crash; reconstructed manually).

## Per-round blocking trend

| Round | Blocking findings | After fixes |
|---|---|---|
| 1 | 12 | (rolled into round-2 inputs) |
| 2 | 6 | 0 |

## Top fixes applied (round-2)

| FIX | Finding IDs | Artifacts touched |
|---|---|---|
| FIX-1 — Cycle detection MUST precede any POST (two-phase ordering) | claude `r2-f1-cycle-detection-ordering` | `design.md` D8, `contracts/README.md` seeder steps 3–4, `spec.md` "Seeding aborts on dependency cycle" scenario, `tasks.md` 2.9a |
| FIX-2 — Renderer-layer timeout (not bridge envelope) | claude `r2-f2-renderer-timeout-bridge-mismatch` | `spec.md` Coordinator-Unreachable Fallback, `contracts/README.md` `--timeout-seconds` row |
| FIX-3 — Two-tier stale-marker idempotency via `.tasks-status.state.json` sidecar | claude `r2-f5-stale-marker-timestamp-still-violates-idempotency` (regression from round-1 f10) | `spec.md` idempotency scenario, `contracts/README.md` stale fallback section |
| FIX-4 — Authoritative-source invariant + spec scenario + in-block projection comment | codex `authoritative-checkbox-source-still-unresolved` (regression from round-1) | `design.md` new "Invariants" section, `spec.md` new "Managed block is a strict projection" scenario, `contracts/README.md` rendered-content format |
| FIX-5 — Seeder splits on managed-block markers; ignores generated lines | gemini `seeder-parses-managed-block` | `design.md` D8 managed-block exclusion, `contracts/README.md` seeder step 2, `tasks.md` new task 2.9b |
| FIX-6 — Pagination guard: hard ERROR on `len(results) == 100` for both renderer + seeder | gemini `limit-100-causes-data-corruption` | `contracts/README.md` renderer effects step 2 + seeder step 5, `spec.md` scenario .1 |

Also folded in (lightweight): task 2.8 wording correction to assert NO `metadata` field (codex `metadata-test-wording-regression`); "Future-impl risk" note on `wp:<id>` label-merge clobber (codex); accepted-known-limitation note on partial-stage pre-commit edge case (codex + gemini).

## Deferred items (with rationale)

- r2-f3 dependencies-annotation-format-unspecified (medium) — may resolve organically in IMPLEMENT when the parser is written; not blocking.
- r2-f4 issue-dict-fields-not-enumerated (medium) — implementer will define exact fixture shape during renderer work; surface in IMPL_REVIEW if it diverges from `Issue.to_dict()`.
- r2-f6 spec-scenario-numbering-shadow (low) — style consistency only.
- r2-f7 D11 coordinator-reachable detection (medium) — touches `/implement-feature` envelope; scope creep.
- r2-f8 pytest-cache evidence (low) — artifact-listing nit; the `expect_exit_code: 0` already encodes test-pass evidence.
- r2-f9 blocked-on-comparator-target (low) — comparator is already spec'd in contracts/README.md.
- codex wp-label-update-can-erase-identity-labels (medium) — documented as a TODO in design.md "Invariants"; lands when wp-labeling is implemented (not in this change).
- codex partial-staging-precommit-edge-case (medium) — documented as a known limitation; standard practice for formatter hooks.
- gemini unresolved-upstream-uuid-crash (medium) — partially addressed by FIX-6 (cap guard).
- gemini pre-commit-clobbers-partial-stage (low) — accepted alongside the codex equivalent.

## Validation

```
openspec validate add-coordinator-task-status-renderer --strict
# → "Change 'add-coordinator-task-status-renderer' is valid"
```

## Recommendation

**Proceed to IMPLEMENT.** Round-2 high-severity findings are fully addressed; the remaining medium/low findings are either documented as deferred follow-ups, accepted limitations, or items naturally caught during implementation review.
