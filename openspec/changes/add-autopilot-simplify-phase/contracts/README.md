# Contracts — add-autopilot-simplify-phase

Evaluated sub-types:

- **OpenAPI** — none. No HTTP surface is introduced or modified. The coordinator's
  `POST /archetypes/resolve_for_phase` is consumed unchanged for the two new phases.
- **Database** — none.
- **Events** — one new file-carried record, plus two existing records that gain fields
  and stay governed by their existing schemas:
  - `events/simplify-review.schema.json` — **the coordination boundary of this change.**
    The artifact the Review role of `simplify-implementation` writes to
    `openspec/changes/<change-id>/simplify-review.json` and the Apply role consumes.
    It is a review-findings document (`review_type: simplify`) whose findings carry the
    catalog `pattern`, the Chesterton's Fence verdict, the coverage decision, and, for
    `test_quality` findings, the prune-ledger fields. `test-prune-ledger.md` is rendered
    from it (`simplify_review.py render-ledger`), never hand-written, in the orchestrated
    path. Composed by `allOf` over the canonical review-findings schema by `$id`; validators
    must register both documents. Fixtures: `fixtures/simplify-review.valid.json` (three
    findings: a self-mocking test to prune, the seam it held open, and a seam kept for a
    specified consumer) and `fixtures/simplify-review.invalid.json` (a change-detector
    prune with `covered_by: null`, rejected by the conditional rule).
  - `review-findings.schema.json` (canonical + install mirror; `consensus-report` copies;
    `vendor_review._FALLBACK_ENUMS`): `review_type` gains `simplify`; `type` gains
    `simplification` and `test_quality`. Additive.
  - `loop-state.json` (schema v5 → v6): `simplify_enabled`, `simplify_baselines`
    (`{b0, b1}`), `simplify_review_path`, `simplify_report_path`. Governed by `LoopState`
    and mirrored in `convergence-state.schema.json`.
- **Type generation** — none. All records are consumed by existing Python dataclasses
  or by the new `simplify_review.py` helper.

Package boundary: `wp-contracts` freezes every enum and the artifact schema first.
`wp-simplify-skill` (Review/Apply roles, `simplify_review.py`), `wp-autopilot-phases`
(`SIMPLIFY_REVIEW` / `SIMPLIFY_APPLY`), and `wp-review-diagnostic` (implementation-review
checklist) then run in parallel against the frozen shape and share no writable path.
