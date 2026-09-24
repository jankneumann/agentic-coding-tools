# Change Context: add-skill-audit

Phase 3 complete. Phase 1 filled Req ID, Spec Source, Description, Contract Ref,
Design Decision and Test(s); Phase 2 filled Files Changed after implementation;
Phase 3 filled Evidence from the `spec` validation phase, which verified every
requirement against the live system at `8ee790a`.

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Skill Audit Skill — CLI surface, layer classification (deterministic pre-pass then one batched analyst call), dispatch profile, findings ledger, markdown report; read-only over the audited skill | contracts/schemas/skill-audit-findings.schema.json | D1, D2, D9 | skills/skill-audit/scripts/{skill_audit,classifier,dispatch_profile,report,audit_paths}.py, skills/skill-audit/references/layers.md | skills/tests/skill-audit/test_classifier.py, test_dispatch_profile.py, test_report.py, test_cli.py | pass 8ee790a (live run on `quick-task`: ledger carries layers, dispatch profile and findings; report written) |
| skill-workflow.2 | specs/skill-workflow/spec.md | Skill Audit Remediation Safety — `contract` layer never carries `delete`; teaching citing repo-specific tokens downgrades to `keep` | contracts/schemas/skill-audit-findings.schema.json | D5 | skills/skill-audit/scripts/audit_findings.py, skills/skill-audit/install_assets/openspec/schemas/skill-audit-findings.schema.json | skills/tests/skill-audit/test_findings_schema.py, test_classifier.py | pass 8ee790a (9 tests: guard raises before write; schema `if/then` rejects delete on contract) |
| skill-workflow.3 | specs/skill-workflow/spec.md | Skill Audit Freshness and Hand-off — freshness stamp, `--check-freshness` exit codes, `--propose` candidate-work stubs through the improve-harness projection helper | openspec/schemas/candidate-work.schema.json | D6, D8 | skills/skill-audit/scripts/{report,skill_audit}.py | skills/tests/skill-audit/test_freshness.py, test_propose.py | pass 8ee790a (8 tests; 4 live `--propose` stubs validated against candidate-work.schema.json) |
| skill-workflow.4 | specs/skill-workflow/spec.md | Skill Audit Convention Selection — `rightsizing` default vs `current`; `convention_drift` findings name the offending rule | --- | D7 | skills/skill-audit/scripts/conventions.py | skills/tests/skill-audit/test_report.py, test_cli.py | pass 8ee790a (report header reads `convention: rightsizing` by default) |
| skill-workflow.5 | specs/skill-workflow/spec.md | Skill Audit Degrades Without the Coordinator — exit 0, `evidence: unavailable`, empty tier table | --- | D4, D10 | skills/skill-audit/scripts/evidence_join.py | skills/tests/skill-audit/test_evidence_join.py | pass 8ee790a (run against a closed port: exit 0, `evidence: unavailable` recorded) |
| skill-workflow.6 | specs/skill-workflow/spec.md | Skill Audit Skill Packaging — ≤150 lines, one-level references, `related:`, manifest and testpaths registration, passes with and without `triggers:` | --- | D7, D9 | skills/skill-audit/SKILL.md, skills/skill-audit/references/usage.md, skills/install-manifest.json, skills/pyproject.toml | skills/tests/skill-audit/test_skill_md.py, skills/tests/install_sh/test_install_manifest.py, skills/tests/ci_coverage/test_ci_test_coverage.py | pass 8ee790a (14 tests; SKILL.md 102 lines; `install.sh --check` mirrors match) |
| agent-archetypes.1 | specs/agent-archetypes/spec.md | Archetype Definition Schema (MODIFIED) — optional `procedure_mode` at schema_version 4; v3 files load with every archetype `guided`; unknown values and unknown keys rejected | skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json | D3 | agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py, skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json, openspec/schemas/archetypes.schema.json | agent-coordinator/tests/test_archetypes_yaml.py, test_agents_config.py | pass 8ee790a (123 tests; v3 loads all-guided, v4 accepted, unknown value and unknown key rejected) |
| agent-archetypes.2 | specs/agent-archetypes/spec.md | Procedure Mode Prompt Injection — one appended sentence per mode from module constants, `procedure_mode` on `ResolvedArchetype` and the endpoint response, escalation preserves the mode, bridge passthrough optional | skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json | D3 | agent-coordinator/src/agents_config.py, agent-coordinator/src/coordination_api.py, openspec/contracts/agent-coordinator/openapi/archetypes.yaml, skills/coordination-bridge/scripts/coordination_bridge.py | agent-coordinator/tests/test_phase_archetype_resolution.py, skills/tests/coordination-bridge/test_archetype_resolve.py | pass 8ee790a (29 + 12 tests; live: INIT verbatim, PLAN goal-directed, IMPLEMENT byte-identical guided, escalation preserves mode) |
| harness-engineering.1 | specs/harness-engineering/spec.md | Capability Gap Signals Joined to Dispatch Tier — attribution precedence loop-state then discovery then `unknown`, tier rows, source preservation, `tier_concentrated_failure` at 60% / 3 sessions | contracts/schemas/skill-audit-findings.schema.json | D4 | skills/skill-audit/scripts/evidence_join.py | skills/tests/skill-audit/test_evidence_join.py | pass 8ee790a (13 tests incl. the absent-identity guard). NOTE: exercised by fixtures only — see the requirement's own note; the production join is inert until `/memory/query` exposes identity fields. |

Contract Ref note: `packages/gen-eval/scripts/generate_contract_refs.py` exists in this
repository, but neither `contracts/schemas/skill-audit-findings.schema.json` nor
`archetypes.schema.json` declares a `traceability` / `x-traceability` block, so no
contract document cites these requirements' derived identifiers and the generator would
write `---` for every row. The column is therefore filled by hand with the schema each
requirement validates against, per the fallback shape in the template. Re-run the
generator if a traceability block is added during implementation.

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Deterministic pre-pass first; one batched model call per skill | Makes the determinism and cost NFRs testable without an LLM in CI | `skills/skill-audit/scripts/classifier.py` | LLM-first would need ≥74 calls for `--all` and would make the common case non-deterministic |
| D2 — Layer definitions are shape rules, written once | One source for the classifier docstring and the report legend | `classifier.py` rule table, `references/layers.md` | Rules that live in two places drift |
| D3 — `procedure_mode` on the archetype, injected at coordinator resolution only | The tier is resolved in exactly one place; the autopilot fold forwards `system_prompt` unchanged | `agents_config.py` (`ArchetypeConfig`, `PROCEDURE_MODE_SENTENCES`, `resolve_archetype_for_phase`), `coordination_api.py` | Prompt-string hints are untestable; a skill-owned policy file is a second source of truth |
| D4 — Evidence join precedence and the `unknown` bucket | Entries must never be dropped for lack of a tier | `skills/skill-audit/scripts/evidence_join.py` | Dropping unattributable failures biases the tier table toward well-instrumented runs |
| D5 — Findings schema with a guard, and a reserved benchmark slot | Contract sections are load-bearing; a later benchmark change must not need a schema bump | `skill-audit-findings.schema.json` `if/then`, `scripts/audit_findings.py` guard | Schema alone is a second line of defence, not the first |
| D6 — Freshness is a content hash, checked non-blocking in CI | Staleness is a prompt to re-audit, not a defect in the change under review | `scripts/report.py`, `.github/workflows/ci.yml` job `skill-audit-freshness` | A blocking gate would fail PRs for unrelated roster edits |
| D7 — Convention selection defaults to rightsizing; the skill's own tests pass in both frontmatter states | The repo is mid-transition between two skill conventions | `scripts/conventions.py`, `test_skill_md.py` explicit key assertions | Hardcoding today's invariants would break when ri-10 and ri-13 land |
| D8 — Candidate-work stubs through the improve-harness projection helper | `/prioritize-proposals` needs no new reader | `scripts/skill_audit.py` calling `project_candidate_work` / `write_projection` | Two stub shapes would fragment the discovery pipeline |
| D9 — Read-only over the audited skill; output location; name collision | The audit proposes, the rightsizing changes edit | `scripts/skill_audit.py`, `docs/reports/skill-audit/` | An audit that edits cannot be trusted to report |
| D10 — Tests are deterministic and LLM-free in CI | CI has no vendor CLI and no budget for model calls | `skills/tests/skill-audit/fixtures/**`, stub backends | Live-model tests are flaky and expensive |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|------------|---------|------|-------------|-------------|------------|

## Coverage Summary

- **Requirements traced**: 9/9
- **Tests mapped**: 9 requirements have at least one test
- **Evidence collected**: 9/9 requirements have pass evidence at `8ee790a`; 0 fail, 0 deferred
- **Gaps identified**: `harness-engineering.1` passes on fixtures but is inert against
  production data, because `POST /memory/query` exposes none of `agent_id`,
  `session_id` or `agent_type`. Stated in the requirement itself and pinned by a test
  proving absent identities cannot produce a `tier_concentrated_failure` finding.
- **Deferred items**: Smoke, Security and E2E have not run. `gate_logic` classifies this
  surface deployable because the change edits `agent-coordinator/src`, so those phases are
  required and the pre-merge gate halts until they do. They need a container runtime;
  verified unavailable here (docker daemon unresponsive, podman absent).
