# Implementation Review: route-supervise-gates-through-the-approval-gate-service

You are an independent implementation reviewer. Review the code changes for
`route-supervise-gates-through-the-approval-gate-service` in this repository —
ri-04 of the roadmap-supervisor-orchestration roadmap: routing every gate the
supervise skill raises through skills/shared/approval_gate.py.

## Read these (read-only — do NOT modify any file)

- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/proposal.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/design.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/tasks.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/specs/**/spec.md`
- The full implementation diff: `git diff dc34ac85..9df30940` in this repo (or
  `git log --oneline dc34ac85..9df30940` then inspect each commit)

## Ground the review in the real code

Key files this change edits:
- `skills/supervise/scripts/gate_router.py` (new, ~770 lines) — the single seam
  onto ApprovalGate: `evaluate`, `answer`, `resolve_parked`, `require_approval_ref`,
  `gate_log`, `roadmap_fingerprint`
- `skills/shared/approval_gate.py` — adds `notified` and `timeout_seconds` to
  `ApprovalDecision`/`_Draft`, `check_filed`, `console_decision`,
  `build_gate_decision_record`
- `skills/supervise/scripts/execution.py` — `ExecutionAdapter.prepare`'s new
  `roadmap_approval_ref` requirement, `resume`'s provenance check
- `skills/supervise/scripts/cycle_state.py` — `gate-check`/`gate-answer`/`gate-log`
  CLI subcommands
- `skills/supervise/SKILL.md` — the prose-gate rewrite
- Test files: `skills/tests/supervise/test_gate_router.py`,
  `test_gate_router_e2e.py`, `test_prose_free_gates.py`, updates to
  `test_execution.py`, `test_workflow_contract.py`, `test_cycle_state.py`

## Output

Write findings as a JSON array conforming to
`openspec/schemas/review-findings.schema.json` to stdout only — do not write
any file. Use the eight-axis schema and five-prefix severity from
`parallel-review-implementation`'s SKILL.md. If you find nothing above `fyi`,
say so explicitly with a `none`-severity finding summarizing what you checked.
