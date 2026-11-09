# Usage: a worked audit of `merge-pull-requests`

## 1. Run it

```bash
python3 "<skill-base-dir>/scripts/skill_audit.py" merge-pull-requests --propose
```

Output (paths are consumer-project-relative):

```text
merge-pull-requests: 9 finding(s), evidence available, report docs/reports/skill-audit/merge-pull-requests-2026-09-16.md, ledger docs/reports/skill-audit/merge-pull-requests-findings.json, candidate-work docs/reports/skill-audit/merge-pull-requests-candidate-work.json
```

When the coordinator is unreachable or memory recall is unauthorized the
first line on stderr is `skill-audit: evidence unavailable (<reason>)`, the
exit code is still `0`, and the report's `evidence:` header names the reason.

## 2. Read the report

Header lines first: `convention:` tells you which lint shape produced the
`convention_drift` findings; `evidence:` tells you whether the tier table
below is populated or empty for a reason; `model_calls:` is `0` when every
section was decided by the pre-pass and at most `1` otherwise.

**Layer histogram.** A skill with most sections in `teaching` is paying
frontier tokens for prose the model already knows; a skill with most in
`procedure` but no probes cannot tell a goal-directed tier when it is done.

**Dispatch profile.** One row per `(archetype, provider)`. `degraded_from:
frontier` marks a provider that resolved the frontier request to its premium
model; `procedure_mode` shows the roster's density knob when set.

**Tier failure table.** One row per tier that ran a failing phase, with the
attribution source (`loop-state`, `discovery`, `unknown`). A
`tier_concentrated_failure` finding names the tier holding ≥ 60 % of failures
across ≥ 3 sessions with its `count` (for example `5/7`).

**Ranked findings.** Non-`keep` findings first, ordered by kind:
`tier_concentrated_failure`, `contract_unpinned`, `constraint_without_reason`,
`procedure_without_probe`, `missing_deviation_protocol`, `convention_drift`,
then `teaching_inferable`. `keep` findings are listed last so the
`repo_specific_tokens` that protected them stay visible.

**Outlines.** The lean SKILL.md outline lists the contract and constraint
sections to keep in place; the `references/procedure.md` outline lists the
procedure sections to move, with their step counts.

**Freshness stamp.** `archetypes_sha256` is what `--check-freshness` compares.

## 3. Feed `--propose` into `/prioritize-proposals`

`<skill>-candidate-work.json` is written through the same projection helper
`/improve-harness` uses, so it validates against
`openspec/schemas/candidate-work.schema.json` and `/prioritize-proposals`
reads it with no new reader. One stub per non-`keep` `(kind, section)`;
`provenance.source_artifact` is the report path and `provenance.finding_ids`
the ledger ids it merges. The `suggested_change_id` carries
`rightsize-<skill>-<kind>` inside the schema's canonical `update-` prefix,
suffixed with the section slug so two sections of one kind never collide.

## 4. Keep it fresh

```bash
python3 "<skill-base-dir>/scripts/skill_audit.py" --all --check-freshness
```

Prints one line per skill with both hashes and the `reviewed_dates` delta,
exit `1` if any report is missing or stale. CI runs this as a non-blocking
job; staleness is a prompt to re-audit, not a defect in the change under
review.

## Testing without a model or a coordinator

- Leave `SKILL_AUDIT_MODEL_CMD` unset: no model call is made and undecided
  prose is `unclassified`.
- Pass `--archetypes <fixture.yaml>` and `--skills-root <dir>` (hidden flag)
  to audit synthetic skills against a synthetic roster, as
  `skills/tests/skill-audit/` does (source-contribution-only).
