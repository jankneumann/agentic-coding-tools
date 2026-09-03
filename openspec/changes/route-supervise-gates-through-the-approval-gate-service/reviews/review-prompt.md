# Plan Review: route-supervise-gates-through-the-approval-gate-service

You are an independent plan reviewer. Review the OpenSpec change plan for
`route-supervise-gates-through-the-approval-gate-service` in this repository.
The plan has already been through two `/iterate-on-plan` passes; obvious
first-order gaps are likely already fixed. Look for what a second pass missed.

## Read these artifacts (read-only — do NOT modify any file)

- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/proposal.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/design.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/tasks.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/work-packages.yaml`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/specs/**/spec.md`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/contracts/**`
- `openspec/changes/route-supervise-gates-through-the-approval-gate-service/plan-findings.md`
  (what two prior iterations already fixed — do NOT re-report these)

## Ground the review in the real code

This plan claims specific things about existing code. VERIFY them; a plan that
misdescribes the code it edits is the most valuable finding you can produce.
Key files to check:

- `skills/shared/trust_posture.py` (the `Gate` / `Disposition` enums, gate count)
- `skills/shared/approval_gate.py` (`ApprovalGate.evaluate`, `_interpret_status`,
  `check_approval`, `build_default_gate`, notification/timeout/default-action semantics)
- `skills/autopilot/scripts/autopilot.py` (`build_gate_decision_record`, `build_gate_request`)
- `skills/autopilot/scripts/runner.py` (`_console_decision`, `gate-check` / `gate-answer` exit codes)
- `skills/supervise/scripts/execution.py` (`ExecutionAdapter.prepare`, `.resume`, attempt ledger)
- `skills/supervise/scripts/cycle_state.py` (`_GATES`, `write_mirror`, `supervisor-record`,
  `rehydrate`, `audit-writes`, `_ALLOWED_WRITE_PREFIXES`)
- `skills/supervise/SKILL.md` (the prose gates being removed)
- `skills/roadmap-runtime/scripts/*.py` (`CheckpointManager.record_gate_decision`)
- `openspec/schemas/{trust-posture,gate-decision,gate-request,supervisor-record,supervisor-record-mirror}.schema.json`
- `openspec/specs/{supervise,roadmap-orchestration,skill-workflow}/spec.md` (the LIVE specs the
  delta MODIFIES — check that each MODIFIED requirement in the delta reproduces every scenario
  of the live requirement, since OpenSpec replaces the whole requirement)
- `skills/tests/supervise/`, `skills/tests/autopilot/`, `skills/shared/tests/` (tests the plan
  claims exist or claims it will change)

## What to look for

Prioritise, in order:
1. **Correctness against reality** — a design decision that cannot work given the actual
   signatures/semantics of `ApprovalGate`, `CheckpointManager`, `write_mirror`, `ExecutionAdapter`.
2. **Spec-delta integrity** — MODIFIED requirements that drop or reword live scenarios;
   requirement text that contradicts a scenario; scenarios that are not testable.
3. **Contract consistency** — the five gate-bearing schemas, the `approval_ref` pattern,
   `additionalProperties: false` objects that would reject the new fields the plan adds
   (`decision_id`, `disposition`, `source` on `pending_gates[]`, and the new fields on
   gate-decision records).
4. **Work-package validity** — DAG acyclicity, non-overlapping write scopes between packages
   that can run in parallel (`wp-router` and `wp-skill-docs` run concurrently), lock coverage,
   whether a package's `write_allow` actually covers every file its tasks edit, and whether a
   verification command can pass inside that package's isolated worktree.
5. **Sequencing/atomicity** — a task that leaves the repository red between commits
   (e.g. growing an enum before/after the tests and schemas that pin it), or a package boundary
   that splits a change that must land together.
6. Security, resilience, observability, compatibility gaps in the plan itself.

## Output

Output ONLY a single JSON object conforming to `openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "route-supervise-gates-through-the-approval-gate-service",
  "reviewer_vendor": "<your model/vendor name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness",
      "severity": "critical",
      "type": "correctness",
      "criticality": "high",
      "description": "Critical: <what is wrong, naming the exact file/section>",
      "resolution": "<what the plan should say instead>",
      "disposition": "fix"
    }
  ]
}
```

Rules:
- `axis` is one of: correctness, readability, architecture, security, performance,
  observability, resilience, compatibility.
- `severity` is one of: critical, nit, optional, fyi, none — and `description` MUST start with
  the matching prefix (`Critical: `, `Nit: `, `Optional: `, `FYI: `, or no prefix for `none`).
- `criticality` is one of: high, medium, low.
- `disposition` is one of: fix, regenerate, accept, escalate. Keep it coherent with severity
  (critical/nit -> fix; optional/fyi/none -> accept; contradictions -> escalate).
- Include at least one `severity: none` positive observation.
- Do NOT re-report anything already listed in `plan-findings.md`.
- Do NOT invent file paths or line ranges — every path you cite must exist.
- No prose outside the JSON object.
