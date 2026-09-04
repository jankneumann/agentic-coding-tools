# Contracts — add-autopilot-simplify-phase

Evaluated sub-types:

- **OpenAPI** — none. No HTTP surface is introduced or modified. The coordinator's
  `POST /archetypes/resolve_for_phase` is consumed unchanged for the new phase.
- **Database** — none.
- **Events** — none new. Two existing file-carried records gain fields and are
  governed by their existing schemas rather than by new contracts here:
  - `loop-state.json` (schema v5 → v6): `simplify_enabled: bool`,
    `simplify_baselines: {b0: sha, b1: sha} | null`, `simplify_report_path: str | null`.
    Governed by `LoopState` in `skills/autopilot/scripts/autopilot.py` and mirrored in
    `openspec/schemas/convergence-state.schema.json`.
  - `review-findings.schema.json`: one additional `type` enum value, `test_quality`.
    Governed by the canonical schema and its install-assets mirror.
- **Type generation** — none. Both records are consumed by existing Python dataclasses.

Coordination boundary between the two implementation packages is the **absence** of
shared files: `wp-autopilot-phase` writes only under `skills/autopilot/**`,
`agent-coordinator/{src/agents_config.py,archetypes.yaml}`, and the convergence-state
schemas; `wp-review-diagnostic` writes only the review-findings / consensus-report
schemas, `vendor_review.py`'s fallback enums, and `parallel-review-implementation/SKILL.md`.
The `simplify-report.json` shape that SIMPLIFY writes is defined by the existing
`verify_behavior_preservation.py` report plus the evidence counters named in the
"Autopilot SIMPLIFY Phase Evidence" requirement; it is an output artifact, not an
interface between packages.
