# Tasks — add-skill-audit

Sizes follow the plan-feature sizing table (XS ≤ 30 min · S ≤ 2 h · M ≤ 1 day). No L or XL tasks.
Within each phase, test tasks precede the implementation they verify (TDD RED → GREEN).
Phases 1 and 2 share no write paths and run in parallel; Phase 3 depends on both.

## Phase 1 — `procedure_mode` on archetypes (package `wp-procedure-mode`)

- [x] 1.1 Extend `agent-coordinator/tests/test_archetypes_yaml.py` and `test_agents_config.py`: v3 file with no `procedure_mode` loads with every archetype `guided`; `procedure_mode: strict` fails schema validation naming the archetype and value; an unknown archetype key still fails; the authored roster's `runner` and `architect` modes are read from the YAML and asserted equal to what `load_archetypes_config` exposes (no literals)
  **Spec scenarios**: agent-archetypes "procedure_mode absent loads as guided", "Unknown procedure_mode is rejected", "Unknown archetype keys are still rejected"
  **Contracts**: `skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json`
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/test_archetypes_yaml.py`, `agent-coordinator/tests/test_agents_config.py`
  **Size**: S

- [x] 1.2 Extend `agent-coordinator/tests/test_phase_archetype_resolution.py`: `INIT` resolves with `system_prompt` ending in the `verbatim` constant and `procedure_mode == "verbatim"`; `PLAN` ends with the `goal-directed` constant containing `skill-procedure-deviation`; `IMPLEMENT` returns the implementer prompt byte-for-byte with `procedure_mode == "guided"`; escalation on `loc_estimate` keeps the implementer's mode; the `/archetypes/resolve_for_phase` response carries `procedure_mode`
  **Spec scenarios**: agent-archetypes "Verbatim archetype gets the verbatim sentence", "Goal-directed archetype names the deviation ledger", "Guided archetype is unchanged", "Escalation preserves the mode"
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/test_phase_archetype_resolution.py`, `agent-coordinator/tests/test_report_status_phase_archetype.py`
  **Size**: S

- [x] 1.3 Add `procedure_mode` (enum `verbatim|guided|goal-directed`, optional) to the archetype entry in `archetypes.schema.json`; bump `agent-coordinator/archetypes.yaml` to `schema_version: 4`; set `runner: procedure_mode: verbatim` and `architect: procedure_mode: goal-directed` with a two-line comment each citing D3
  **Spec scenarios**: as 1.1
  **Design decisions**: D3
  **Dependencies**: 1.1
  **Files**: `skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json`, `agent-coordinator/archetypes.yaml`
  **Size**: XS

- [x] 1.4 In `agent-coordinator/src/agents_config.py`: add `procedure_mode: str = "guided"` to `ArchetypeConfig`; parse and validate it in `load_archetypes_config` (structured error on unknown value); define `PROCEDURE_MODE_SENTENCES` as module constants; append the sentence in `resolve_archetype_for_phase` after a blank line for non-`guided` modes; add `procedure_mode` to `ResolvedArchetype` and to the `resolve_archetype_for_phase_endpoint` response model in `coordination_api.py`
  **Spec scenarios**: as 1.2
  **Design decisions**: D3
  **Dependencies**: 1.2, 1.3
  **Files**: `agent-coordinator/src/agents_config.py`, `agent-coordinator/src/coordination_api.py`
  **Size**: M

- [x] Checkpoint: run `agent-coordinator/tests/test_archetypes_yaml.py test_agents_config.py test_phase_archetype_resolution.py test_teams.py test_report_status_phase_archetype.py`, review diff, verify scope stays inside `agent-coordinator/**` and the archetype schema file

- [x] 1.5 Extend `skills/tests/coordination-bridge/test_archetype_resolve.py`: a response with `procedure_mode` is returned intact; a response without it is returned unchanged and callers see no key
  **Spec scenarios**: agent-archetypes "Bridge tolerates an older coordinator"
  **Design decisions**: D3
  **Dependencies**: None
  **Files**: `skills/tests/coordination-bridge/test_archetype_resolve.py`
  **Size**: XS

- [x] 1.6 In `skills/coordination-bridge/scripts/coordination_bridge.py` `try_resolve_archetype_for_phase`, keep the required-key check as is and document `procedure_mode` as an optional passthrough in the docstring; no behaviour change
  **Spec scenarios**: as 1.5
  **Design decisions**: D3
  **Dependencies**: 1.5
  **Files**: `skills/coordination-bridge/scripts/coordination_bridge.py`
  **Size**: XS

- [x] Checkpoint: run `skills/tests/coordination-bridge`, `skills/tests/autopilot/test_phase_archetype_e2e.py`, `skills/tests/vendor-neutral-autopilot`, confirm the autopilot fold forwards the appended sentence with no code change

## Phase 2 — `skill-audit` skill (package `wp-skill-audit`)

- [x] 2.1 Write `skills/tests/skill-audit/test_findings_schema.py` against `contracts/schemas/skill-audit-findings.schema.json` copied to `install_assets`: a minimal valid ledger validates; `layer: contract` with `remediation: delete` fails; unknown `kind` fails; `evidence.benchmark` may be null or absent
  **Spec scenarios**: skill-workflow "Contract sections cannot be deleted"
  **Contracts**: `contracts/schemas/skill-audit-findings.schema.json`
  **Design decisions**: D5
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_findings_schema.py`, `skills/tests/skill-audit/fixtures/ledgers/*.json`
  **Size**: S

- [x] 2.2 Copy the schema to `skills/skill-audit/install_assets/openspec/schemas/skill-audit-findings.schema.json` and add `skills/skill-audit/scripts/findings.py` with a `Finding` dataclass, a `Ledger` builder, the contract-delete guard that raises before write, and `write_ledger()`
  **Spec scenarios**: as 2.1
  **Design decisions**: D5
  **Dependencies**: 2.1
  **Files**: `skills/skill-audit/install_assets/openspec/schemas/skill-audit-findings.schema.json`, `skills/skill-audit/scripts/findings.py`
  **Size**: S

- [x] 2.3 Write `skills/tests/skill-audit/test_classifier.py` with a `FixedStub` and `FailingStub` model backend and fixture SKILL.md files (`all_shaped.md`, `mixed.md`, `teaching_with_repo_token.md`): all-shaped yields zero model calls and zero `unclassified`; mixed yields exactly one call carrying every undecided section; failing stub labels the batch `unclassified` and logs one warning; teaching that names `docs/decisions/` is `keep` with the token in `evidence.repo_specific_tokens`; two runs produce byte-identical ledgers
  **Spec scenarios**: skill-workflow "Shaped sections are classified without a model call", "Undecidable prose is batched into one model call", "Invalid model output never becomes a label", "Teaching that cites repo specifics is kept", "Classification is deterministic"
  **Design decisions**: D1, D2, D10
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_classifier.py`, `skills/tests/skill-audit/fixtures/skills/**`
  **Size**: M

- [x] 2.4 Implement `skills/skill-audit/scripts/classifier.py`: markdown section parser (headings, fenced blocks, tables, ordered lists, paragraphs), the D2 rule table as named rules, `ModelBackend` protocol with `resolve_analyst()` via `coordination_bridge.try_resolve_archetype_for_phase` (omit model on failure), single batched call with strict `{section_id: label}` schema, `unclassified` on invalid output, finding generation for `teaching_inferable`, `procedure_without_probe`, `constraint_without_reason`, `contract_unpinned`, `missing_deviation_protocol`; write `references/layers.md` from the same rule table
  **Spec scenarios**: as 2.3
  **Design decisions**: D1, D2
  **Dependencies**: 2.2, 2.3
  **Files**: `skills/skill-audit/scripts/classifier.py`, `skills/skill-audit/references/layers.md`
  **Size**: M

- [x] Checkpoint: run `skills/tests/skill-audit`, review diff, verify scope stays inside `skills/skill-audit/**` + `skills/tests/skill-audit/**`

- [x] 2.5 Write `skills/tests/skill-audit/test_dispatch_profile.py` with a fixture `archetypes.yaml` (bare ids, `{model, thinking}`, one provider missing `frontier`, one archetype with `procedure_mode`): every provider in the file appears; tuples equal `archetype_roster.resolve_tier_for_provider`; the missing-frontier provider shows `degraded_from: frontier`; `procedure_mode` is reported when present and `null` otherwise
  **Spec scenarios**: skill-workflow "Dispatch profile follows the roster"
  **Design decisions**: D4
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_dispatch_profile.py`, `skills/tests/skill-audit/fixtures/archetypes.yaml`
  **Size**: S

- [x] 2.6 Implement `skills/skill-audit/scripts/dispatch_profile.py`: archetypes for lifecycle skills from `phase_mapping` (skill → phases map documented in `references/dispatch-map.md`, seeded from the agent-archetypes "Skill Model Hint Integration" table), otherwise from fenced `Task(`/`Agent(` examples in the SKILL.md; providers enumerated from `model_aliases`; resolution through `archetype_roster`
  **Spec scenarios**: as 2.5
  **Design decisions**: D4
  **Dependencies**: 2.5
  **Files**: `skills/skill-audit/scripts/dispatch_profile.py`, `skills/skill-audit/references/dispatch-map.md`
  **Size**: S

- [x] 2.7 Write `skills/tests/skill-audit/test_evidence_join.py` with a stubbed bridge, a recorded `/memory/query` response, a fixture `loop-state.json`, and a fixture discovery response: attribution via loop-state; via discovery heartbeat window; `unknown` bucket keeps the entry; 5/7 concentration across 4 sessions emits `tier_concentrated_failure` with count `5/7`; sources preserved and multi-source fraction counts once; coordinator down yields exit `0`, `evidence.status == "unavailable"`, empty `tier_rows`
  **Spec scenarios**: harness-engineering "Failure attributed through loop-state", "Failure attributed through discovery heartbeat", "Unattributable failure is kept", "Concentrated failure produces a finding", "Sources are preserved through the join"; skill-workflow "Coordinator down"
  **Design decisions**: D4, D10
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_evidence_join.py`, `skills/tests/skill-audit/fixtures/evidence/**`
  **Size**: M

- [x] 2.8 Implement `skills/skill-audit/scripts/evidence_join.py` importing `build_memory_query`, `_extract_tag`, `_extract_all_tags`, `deduplicate_findings` from `improve-harness/scripts/analyze_failures.py` (resolved via `<skill-base-dir>/../improve-harness/scripts`), loop-state scan under `openspec/changes/**/loop-state.json` (archive included), discovery lookup through the bridge, `unknown` bucket, tier rows, `multi_source_fraction`, and the 60 percent / 3 sessions concentration rule
  **Spec scenarios**: as 2.7
  **Design decisions**: D4
  **Dependencies**: 2.7
  **Files**: `skills/skill-audit/scripts/evidence_join.py`
  **Size**: M

- [x] Checkpoint: run `skills/tests/skill-audit`, review diff, verify no import of `agents_config` (consumer-portability rule) and no write outside the output dir

- [x] 2.9 Write `skills/tests/skill-audit/test_report.py`, `test_freshness.py`, `test_propose.py`, `test_cli.py`: report contains histogram, dispatch profile, tier table, ranked findings, both outlines, and the four stamp fields; `--check-freshness` exits `1` on hash mismatch printing both hashes and changed `reviewed` dates, `0` on match, `1` with no report; `--propose` writes two stubs for three findings sharing `(kind, section)`, each valid against `candidate-work.schema.json` with `provenance` naming report and finding id and `suggested_change_id` `rightsize-<skill>-<kind>`; `--convention` default header line; `--convention current` on a tail-less `user_invocable: true` fixture yields `convention_drift` naming `assert_tail_block_present`; rightsizing on a 520-line fixture and a nested-reference fixture yields `convention_drift`; `--all` wall time ≤ 60 s with the stub (skips without corpus)
  **Spec scenarios**: skill-workflow "Roster rotation makes the audit stale", "Fresh audit passes the check", "Candidate-work stubs are schema-valid and deduplicated", "Default convention is rightsizing", "Current convention flags a missing tail block"
  **Contracts**: `openspec/schemas/candidate-work.schema.json`
  **Design decisions**: D6, D7, D8, D9
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_report.py`, `skills/tests/skill-audit/test_freshness.py`, `skills/tests/skill-audit/test_propose.py`, `skills/tests/skill-audit/test_cli.py`
  **Size**: M

- [x] 2.10 Implement `skills/skill-audit/scripts/report.py` (markdown renderer, freshness stamp from `sha256(archetypes.yaml)` and `reviewed` dates, lean-SKILL.md and `procedure.md` outlines from the layer table), `skills/skill-audit/scripts/conventions.py` (`rightsizing` and `current` rule sets; `current` delegates to `skill_invariants` assertions), and `skills/skill-audit/scripts/skill_audit.py` (argparse for one skill or `--all`, `--evidence-window`, `--convention`, `--propose` via `improve_candidate_work.project_candidate_work`/`write_projection`, `--check-freshness`, `--output-dir`; exit codes `0` ok, `1` stale or input error)
  **Spec scenarios**: as 2.9
  **Design decisions**: D6, D7, D8, D9
  **Dependencies**: 2.4, 2.6, 2.8, 2.9
  **Files**: `skills/skill-audit/scripts/report.py`, `skills/skill-audit/scripts/conventions.py`, `skills/skill-audit/scripts/skill_audit.py`
  **Size**: M

- [x] Checkpoint: run `skills/tests/skill-audit`, run `skill_audit.py quick-task --output-dir /tmp/sa` end to end with the stub backend, review the generated report by eye, verify scope

- [x] 2.11 Write `skills/tests/skill-audit/test_skill_md.py`: frontmatter parses; explicit keys `name`, `description`, `category`, `tags`, `user_invocable: true`, `related` (do not call `assert_required_keys_present`); passes with `triggers:` present and with it stripped in a temp copy; references resolve and are one level deep; tail block present; line count ≤ 150; `related` does not include `audit-choices`
  **Spec scenarios**: skill-workflow "Skill test passes in both frontmatter states"
  **Design decisions**: D7, D9
  **Dependencies**: None
  **Files**: `skills/tests/skill-audit/test_skill_md.py`
  **Size**: S

- [x] 2.12 Write `skills/skill-audit/SKILL.md` (≤ 150 lines: frontmatter with `triggers:` for today's invariants, purpose, arguments table, the five-step run, output locations, when to re-run, tail block per `skills/references/skill-tail-template.md`) and `references/usage.md` (worked example on `merge-pull-requests`, reading the report, feeding `--propose` into `/prioritize-proposals`)
  **Spec scenarios**: as 2.11
  **Design decisions**: D7, D9
  **Dependencies**: 2.10, 2.11
  **Files**: `skills/skill-audit/SKILL.md`, `skills/skill-audit/references/usage.md`
  **Size**: S

- [x] Checkpoint: run `skills/tests/skill-audit`, `python3 skills/shared/validate_install_manifest.py` dry-run on the new directory, review the cumulative package diff

## Phase 3 — Integration (package `wp-integration`)

- [x] 3.1 Register `skill-audit` in `skills/install-manifest.json` (`distribution: portable`, `cross_skill_dependencies: [shared, coordination-bridge, improve-harness]`, `installed_assets` for the schema) and add `tests/skill-audit` to `testpaths` in `skills/pyproject.toml`
  **Spec scenarios**: skill-workflow "Install manifest and testpaths include the skill"
  **Design decisions**: D9
  **Dependencies**: 2.12
  **Files**: `skills/install-manifest.json`, `skills/pyproject.toml`
  **Size**: XS

- [x] 3.2 Add CI job `skill-audit-freshness` to `.github/workflows/ci.yml` with `continue-on-error: true` running `skill_audit.py --all --check-freshness` from the installed skills venv and emitting a workflow annotation on exit `1`
  **Spec scenarios**: skill-workflow "Roster rotation makes the audit stale"
  **Design decisions**: D6
  **Dependencies**: 3.1
  **Files**: `.github/workflows/ci.yml`
  **Size**: S

- [ ] 3.3 Add a "Auditing a skill for model-tier fit" paragraph to `docs/guides/skills.md` naming the command, the report location, and the re-run trigger; create `docs/reports/skill-audit/README.md` describing the directory
  **Spec scenarios**: (documentation of 2.10)
  **Design decisions**: D6, D9
  **Dependencies**: 3.1
  **Files**: `docs/guides/skills.md`, `docs/reports/skill-audit/README.md`
  **Size**: XS

- [ ] Checkpoint: run `bash skills/install.sh --check`, `skills/.venv/bin/python -m pytest skills/tests/ci_coverage`, review diff

- [ ] 3.4 Merge `wp-procedure-mode` and `wp-skill-audit`; run `bash skills/install.sh --mode rsync --deps none --python-tools none` to regenerate `.claude/skills/` and `.agents/skills/`; run the full skills suite, the coordinator suite, and `openspec validate add-skill-audit --strict`
  **Spec scenarios**: all
  **Design decisions**: —
  **Dependencies**: 1.6, 2.12, 3.1, 3.2, 3.3
  **Files**: `.claude/skills/skill-audit/**`, `.agents/skills/skill-audit/**`, `.claude/skills/coordination-bridge/**`, `.agents/skills/coordination-bridge/**`
  **Size**: S

- [ ] 3.5 Run the first audits (`merge-pull-requests`, `validate-feature`, `test-driven-development`, `debugging-and-error-recovery`, `performance-optimization`, `api-and-interface-design`) with `--propose`, commit the reports under `docs/reports/skill-audit/`, and append the Implement-phase session log via `PhaseRecord.write_both()` with any `### Capability Gaps Observed`
  **Spec scenarios**: skill-workflow "Candidate-work stubs are schema-valid and deduplicated"
  **Design decisions**: D8, D9
  **Dependencies**: 3.4
  **Files**: `docs/reports/skill-audit/*.md`, `docs/reports/skill-audit/*-findings.json`, `openspec/changes/add-skill-audit/session-log.md`
  **Size**: S

- [ ] Checkpoint: confirm every spec scenario is cited by at least one test task above; confirm no task title contains " and " joining two outcomes; run `openspec validate add-skill-audit --strict`
