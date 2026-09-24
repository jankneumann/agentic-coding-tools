---
name: skill-audit
description: Audit a SKILL.md for model-tier fit — classify its sections by layer (contract, constraint, procedure, teaching), profile which dispatch tiers run it, join capability-gap evidence to those tiers, and emit a findings ledger, a stamped report, and candidate-work stubs. Read-only over the audited skill. Not the coordinator audit trail and not the audit-choices decision ledger.
category: Development
tags: [skills, rightsizing, model-tiers, archetypes, evidence, read-only]
triggers:
  - "skill audit"
  - "audit skill"
  - "model-tier fit"
  - "rightsize skill"
user_invocable: true
related: [improve-harness, agent-ergonomics, prioritize-proposals]
requires:
  coordinator:
    required: []
    safety: []
    enriching: [CAN_MEMORY]
---

# Skill Audit

Every SKILL.md is read by every tier the roster dispatches. This skill says,
per skill, which prose a frontier model pays for and an economy model needs,
and which tier is actually failing it. It **never edits the audited skill**:
its only writes are the report, the findings ledger, and candidate-work
stubs under `--output-dir`. Findings are proposals; the rightsizing changes
own the rewrite.

## Arguments

| Argument | Meaning |
|---|---|
| `<skill-name>` \| `--all` | One skill directory under the skills root, or every skill |
| `--evidence-window <days>` | Memory window for `affected_skill:` signals (default `30`) |
| `--convention rightsizing\|current` | Lint shape: rightsizing (default; no `triggers:`, tail block optional, ≤ 500 lines, references one level deep) or today's `skill_invariants.py` |
| `--propose` | Also write `<skill>-candidate-work.json` for `/prioritize-proposals` |
| `--check-freshness` | Exit `1` when the newest report's roster hash differs from `archetypes.yaml` (or no report exists) |
| `--output-dir <path>` | Where reports, ledgers, and stubs go (default `docs/reports/skill-audit/`, consumer-project-relative) |

Exit codes: `0` ok; `1` stale (`--check-freshness`) or input error.

## Run

```bash
python3 "<skill-base-dir>/scripts/skill_audit.py" merge-pull-requests
python3 "<skill-base-dir>/scripts/skill_audit.py" --all --propose
python3 "<skill-base-dir>/scripts/skill_audit.py" validate-feature --check-freshness
```

The roster is `agent-coordinator/archetypes.yaml` (override with
`--archetypes <path>` or `ARCHETYPES_YAML`). Undecided prose goes to a model
only when `SKILL_AUDIT_MODEL_CMD` names a command that reads the prompt on
stdin and prints `{section_id: label}` JSON; unset, those sections are
reported `unclassified` — never guessed.

## What one run does

1. Parse `SKILL.md` and every file one level below `references/` into sections.
2. Classify each section with the deterministic pre-pass in `references/layers.md`; batch whatever is left into at most one model call at the `analyst` archetype.
3. Build the dispatch profile from `references/dispatch-map.md` and `phase_mapping`, resolving every `(provider, model, thinking)` through `shared/archetype_roster.py`.
4. Join `affected_skill:<name>` memory entries to the tier that ran them (loop-state, then discovery heartbeat, then `unknown`) and flag `tier_concentrated_failure` at ≥ 60 % / ≥ 3 sessions.
5. Write `<skill>-findings.json` (schema `install_assets/openspec/schemas/skill-audit-findings.schema.json`), `<skill>-<date>.md`, and with `--propose` the candidate-work stubs.

Do not treat an `unavailable` evidence line as a failed run: the audit
completes on layer findings alone and exits `0`, because a missing
coordinator is a prompt to re-run later, not a defect in the skill.

## Output

- `<output-dir>/<skill>-<date>.md` — histogram, dispatch profile, tier failure table, ranked findings, lean-SKILL.md and procedure-reference outlines, freshness stamp.
- `<output-dir>/<skill>-findings.json` — the ledger; a `contract` finding can never carry `delete`.
- `<output-dir>/<skill>-candidate-work.json` — with `--propose`; same shape `/improve-harness` emits.

Worked example and how to read a report: `references/usage.md`.

## When to re-run

Re-run when `archetypes.yaml` changes (`--check-freshness` says so), when a
new tier or provider lands, or when `/improve-harness` shows fresh
`affected_skill:` signals. Reports are the evidence trail; commit them.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "The model can just classify everything; skip the pre-pass" | Then 74 skills cost 74 calls and the ledger changes between runs; the pre-pass is what makes the audit deterministic and cheap. |
| "Evidence is unavailable, so the report is useless" | Layer findings stand on their own; the tier table is additive. Note the reason and re-run when memory is reachable. |
| "This teaching section is obvious, delete it" | If it names a repo path, command, or decision, a model cannot infer it; the audit downgrades those to `keep` for that reason. |
| "I'll just fix the SKILL.md while I'm here" | The audit is read-only by contract; edits belong to a rightsizing change with its own review. |

## Red Flags

- A report whose `model_calls` exceeds 1 for a single skill, or exceeds 0 when every section was pre-pass decided.
- A `contract` finding with `remediation: delete` anywhere in a ledger.
- A `--check-freshness` run that passes although `archetypes.yaml` changed since the report date.
- Any file under `skills/<audited>/` modified by the run.

## Verification

1. `<output-dir>/<skill>-findings.json` validates against the shipped schema and two runs with the same inputs are byte-identical.
2. The report's tier failure table is present (even with zero rows) and the header states `convention:` and `evidence:`.
3. `--check-freshness` exits `0` immediately after the audit and `1` after any edit to `archetypes.yaml`.
