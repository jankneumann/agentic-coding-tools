---
schema_version: 1
gates:
  # Every gate ships as `block` — copying this template to TRUST_POSTURE.md
  # unchanged is byte-identical to today's behavior (every human gate parks the
  # loop and waits for a person). Flip individual gates to `auto` or
  # `notify_with_timeout` as you decide to delegate them.
  gatekeeper_escalation:
    disposition: block
  proposal_approval:
    disposition: block
  plan_review_convergence_failure:
    disposition: block
  validation_failure:
    disposition: block
  escalate_resume:
    disposition: block
  replan_required:
    disposition: block
  pr_creation:
    disposition: block
  merge:
    disposition: block
  roadmap_approval:
    disposition: block
---

# Trust Posture Contract (template)

This is the **template** for the repo-owned trust posture contract. It is not
active. To adopt a posture, copy it to the repo root as `TRUST_POSTURE.md` and
edit the front matter above:

```bash
cp TRUST_POSTURE.template.md TRUST_POSTURE.md
```

While `TRUST_POSTURE.md` is **absent**, every gate resolves to `block` — exactly
the behavior the autopilot/roadmap loops have today. The contract only ever
*widens* what the automation may do; there is no way for it to make behavior more
permissive by accident.

## What this file does

Each human gate in the autopilot / roadmap loops gets a machine-readable
*disposition* instead of prose in a SKILL.md. The approval gate service
(`skills/shared/approval_gate.py`, roadmap item ri-05) reads this contract at each
gate and acts on the disposition. The loader/validator is
`skills/shared/trust_posture.py`; the schema is
`openspec/schemas/trust-posture.schema.json`.

## Dispositions

| disposition | meaning |
|---|---|
| `auto` | Proceed unattended; log the decision to the audit trail. No human. |
| `notify_with_timeout` | File a coordinator approval, send a notification, poll until `timeout_seconds` elapses, then apply `default_action`. Requires `timeout_seconds` (positive integer) **and** `default_action`. |
| `block` | Park the loop state and wait for a human to resume. Today's behavior. |

For `notify_with_timeout`, `default_action` is what happens when the timer
expires with no human response:

| default_action | on expiry |
|---|---|
| `proceed` | Allow the gated action (as if a human approved). |
| `block` | Park the loop (as if the gate were `block`). |

`timeout_seconds` and `default_action` are **only** valid for
`notify_with_timeout`; setting them on an `auto` or `block` gate is a validation
error (it usually means a mis-placed field).

## The nine gates

| gate key | prose name | fires when |
|---|---|---|
| `gatekeeper_escalation` | GATEKEEPER escalation | the GATEKEEPER phase raises an escalation |
| `proposal_approval` | proposal approval | PLAN produces a proposal awaiting human sign-off |
| `plan_review_convergence_failure` | plan-review convergence failure | the multi-vendor plan review fails to converge |
| `validation_failure` | validation failure | VALIDATE / VAL_REVIEW records a failing gate |
| `escalate_resume` | ESCALATE resume | a loop parked in ESCALATE needs a human to resume |
| `replan_required` | replan_required | a roadmap item enters `replan_required` |
| `pr_creation` | PR creation | the loop is ready to open a pull request |
| `merge` | merge | the SUBMIT_PR → DONE merge handoff |
| `roadmap_approval` | roadmap approval | a roadmap's DAG of items is ready to authorize (distinct from `proposal_approval`, which authorizes one change) |

A gate omitted from `gates:` resolves to `block` (fail-closed). Only an unknown
gate key or an unknown disposition is a hard validation error.

## Worked example

A posture that auto-creates PRs, notifies-with-a-one-hour-timeout on merge
(defaulting to *not* merging), and blocks everything else:

```yaml
---
schema_version: 1
gates:
  pr_creation:
    disposition: auto
  merge:
    disposition: notify_with_timeout
    timeout_seconds: 3600
    default_action: block
  # all other gates omitted -> block
---
```

## Validate your contract

```bash
skills/.venv/bin/python -m shared.trust_posture validate TRUST_POSTURE.md
skills/.venv/bin/python -m shared.trust_posture show TRUST_POSTURE.md
```
