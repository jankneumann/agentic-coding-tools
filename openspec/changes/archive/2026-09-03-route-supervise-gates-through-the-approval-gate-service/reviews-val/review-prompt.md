# VAL_REVIEW: route-supervise-gates-through-the-approval-gate-service

You are an independent reviewer performing the final review gate before this
change's PR is opened, for `route-supervise-gates-through-the-approval-gate-service`
— ri-04 of the roadmap-supervisor-orchestration roadmap: routing every gate the
supervise skill raises through `skills/shared/approval_gate.py` against
`TRUST_POSTURE.md`. This phase runs because the GATEKEEPER judge flagged the
change as security-relevant (it implements a trust/approval boundary) and
required a validation-stage review in addition to the implementation review
already completed.

## Read these (read-only — do NOT modify any file)

- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/proposal.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/design.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/validation-report.md`
  — the VALIDATE phase's own findings (spec/evidence/security/e2e, all pass)
- The full implementation diff: `git diff dc34ac85..bf0d8cf7` in this repo (or
  `git log --oneline dc34ac85..bf0d8cf7` then inspect each commit)
- Prior review rounds, so you don't re-litigate settled findings:
  `openspec/changes/route-supervise-gates-through-the-approval-gate-service/reviews-impl/round-1/findings-*.json`
  and `reviews-impl/round-2/findings-*.json` (2 CRITICAL + 4 NIT found in round 1,
  all independently verified closed in round 2 by two vendors)

## What to focus on

This is a final gate, not a re-run of the implementation review. Prioritize:

1. **Correctness of the trust boundary end to end** — does every code path that
   can execute delegated work (`skills/supervise/scripts/execution.py`'s
   `prepare`/`resume`, `skills/supervise/scripts/gate_router.py`'s
   `evaluate`/`answer`/`resolve_parked`) actually require and verify a durable
   `roadmap_approval_ref` or parked-gate `approval_ref` before any effect a
   human didn't authorize?
2. **Security**: fail-closed behavior on every coordinator-unreachable path,
   audit completeness (every gate decision lands in `gate_decisions` with no
   silent skip), replay/forgery resistance of `approval_ref` and
   `roadmap_fingerprint`.
3. **Contract adherence**: do the new/changed JSON schemas
   (`openspec/schemas/gate-decision.schema.json`, the `contracts/schemas/`
   copies, `delegated-dispatch-attempt.schema.json`,
   `supervised-dispatch-request.schema.json`) match what the code actually
   writes and reads?
4. **Performance**: nothing in the hot gate-check/gate-answer path does
   unbounded work (e.g. `gate_log`/mirror projection scaling with history size
   in a way that would matter in practice).

## Output

Write findings as a JSON array conforming to
`openspec/schemas/review-findings.schema.json` to stdout only — do not write
any file. Use the eight-axis schema and five-prefix severity from
`parallel-review-implementation`'s SKILL.md. If you find nothing above `fyi`,
say so explicitly with a `none`-severity finding summarizing what you checked.
