# Tasks — add-atomic-harness

Approach 2 (experimental-vendor tier + scoped workflow-executor pilot), per
`proposal.md` Selected Approach. Empirical facts A1–A20 in `design.md` are the only
permitted source for atomic CLI flags, output parsing, and session-store assumptions;
model slugs stay unpinned until task 1.2 lands (D8). Sequencing: start after
`add-frontier-model-tier` merges.

Phases map to work packages: Phase 1 → `wp-empirical`, Phase 2 → `wp-coordinator`,
Phase 3 → `wp-skills`, Phase 4 → `wp-frontend`, Phases 5–6 → `wp-docs-finalize`.

## Phase 0 — Baseline verification

- [ ] 0.1 Run the coordinator and skills gate suites on the merge base and record any pre-existing failures in this file (S)
  **Files**: openspec/changes/add-atomic-harness/tasks.md
  **Dependencies**: None
- [ ] 0.2 Confirm `add-frontier-model-tier` is merged; rebase this change's branch onto the post-merge base and re-run 0.1 if the base moved (S)
  **Files**: openspec/changes/add-atomic-harness/tasks.md
  **Dependencies**: 0.1
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 1 — Empirical facts and live re-probe (wp-empirical)

- [ ] 1.1 Re-verify probe rows A1–A17 against the pinned atomic version in the implementation environment; update `design.md` rows with any divergence (S)
  **Spec scenarios**: skill-workflow.1
  **Contracts**: contracts/workflow-dispatch/result.schema.json
  **Dependencies**: 0.2
- [ ] 1.2 Run the network-permitted live re-probe for A18: confirm OpenRouter dispatch works end-to-end, select final tier-map slugs distinct from pi's qwen3-coder lineup, and record evidence + slugs in `design.md` (M)
  **Spec scenarios**: configuration.7, skill-workflow.10
  **Dependencies**: 1.1
  **Note**: Manual/gated — requires an environment with OPENROUTER_API_KEY and permitted egress. Until done, all downstream dispatch stays dry-run (D7).
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2 — Coordinator: experimental provider class (wp-coordinator)

- [ ] 2.1 Write tests for the experimental provider class in `agents_config.py` — `experimental: true` parsing, `experimental_providers` tier-map resolution via `resolve_provider_model_spec`, unmapped-experimental warning path, unknown non-experimental provider fail-loud (M)
  **Spec scenarios**: configuration.3, configuration.7, configuration.8, agent-archetypes.6, agent-archetypes.7
  **Dependencies**: 0.2
- [ ] 2.2 Implement `experimental: true` agent-entry flag and `experimental_providers` tier-map support in `agent-coordinator/src/agents_config.py`; keep the first-class provider-model-map schema untouched (M)
  **Spec scenarios**: configuration.4, configuration.7, configuration.8
  **Dependencies**: 2.1
- [ ] 2.3 Write tests for archetype resolution under provider `atomic` (tier-mapped and unmapped variants) (S)
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.7
  **Dependencies**: 2.1
- [ ] 2.4 Add `atomic-local` entry to `agent-coordinator/agents.yaml` — `type: atomic`, `experimental: true`, `isolation: worktree`, `counts_toward_quorum: false`, `cli.command: atomic`, three dispatch modes (`review`/`alternative`/`quick`) with `--provider openrouter --mode json` pinned and prompt as trailing positional (A2/A10); placeholder model pending 1.2 (M)
  **Spec scenarios**: configuration.1, configuration.2
  **Dependencies**: 2.2
- [ ] 2.5 Document the `experimental_providers` structure in `openspec/schemas/provider-model-map.schema.json` comments/description without widening the closed first-class enum; add schema-level test asserting the enum still holds exactly five keys (S)
  **Spec scenarios**: configuration.4, configuration.7
  **Dependencies**: 2.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3 — Skills: dispatch, pilot adapter, transcripts (wp-skills)

- [ ] 3.1 Write tests for atomic in `review_dispatcher.py` — `which atomic` discovery, NDJSON parse reusing last-assistant-terminal-message selection (A3/A4), reauth hint text (A6/D3), quorum exclusion for experimental vendors (M)
  **Spec scenarios**: skill-workflow.7, configuration.1, configuration.2
  **Dependencies**: 0.2
- [ ] 3.2 Implement atomic support in `skills/parallel-infrastructure/scripts/review_dispatcher.py` — `_MANUAL_REAUTH["atomic"]`, experimental-vendor quorum exclusion, discovery roster extension (M)
  **Spec scenarios**: skill-workflow.7, configuration.1, configuration.2
  **Dependencies**: 3.1
- [ ] 3.3 Write tests for `workflow_dispatch.py` against recorded NDJSON fixtures — `workflow.run.end` extraction, status classification (completed/blocked/failed), first-run timeout floor, HIL rejection at build time (M)
  **Spec scenarios**: skill-workflow.1, skill-workflow.2, skill-workflow.3
  **Contracts**: contracts/workflow-dispatch/result.schema.json
  **Dependencies**: 0.2
- [ ] 3.4 Implement `skills/parallel-infrastructure/scripts/workflow_dispatch.py` per D4 — command build with pinned provider/model, worktree-cwd execution, event parsing, audit-trail recording (M)
  **Spec scenarios**: skill-workflow.1, skill-workflow.2, skill-workflow.3
  **Contracts**: contracts/workflow-dispatch/result.schema.json
  **Design decisions**: D2, D4
  **Dependencies**: 3.3
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.5 Write tests for the `fix-scrub --executor atomic-workflow` opt-in — default path unchanged, opt-in routing, fail-soft fallback when binary absent (S)
  **Spec scenarios**: skill-workflow.4, skill-workflow.5, skill-workflow.6
  **Dependencies**: 3.4
- [ ] 3.6 Implement the opt-in executor flag in `skills/fix-scrub/scripts/vendor_dispatch.py` (+ `main.py` argument plumbing), keeping skill-side verification authoritative over workflow self-report (M)
  **Spec scenarios**: skill-workflow.4, skill-workflow.5, skill-workflow.6
  **Design decisions**: D5
  **Dependencies**: 3.5
- [ ] 3.7 Write tests + fixtures for the `atomic_cli` transcript adapter — discovery glob, v3 header, prompt-echo role mapping, fail-soft on missing store, empty result for workflow-only runs (M)
  **Spec scenarios**: harness-engineering.1, harness-engineering.2
  **Dependencies**: 0.2
- [ ] 3.8 Implement `skills/collect-transcripts/scripts/adapters/atomic_cli.py` (`HARNESS_ID="atomic_cli"`, `SCHEMA_VERSION="atomic-jsonl-v3"`), aligned with the `build-structured-vendor-result-channel` envelope where already landed (M)
  **Spec scenarios**: harness-engineering.1, harness-engineering.2
  **Design decisions**: D6
  **Dependencies**: 3.7
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.9 Write tests for `smoke_provider_dispatch.py` experimental handling — `atomic` accepted with warning in dry-run, undeclared provider rejected listing both rosters (S)
  **Spec scenarios**: skill-workflow.10, skill-workflow.11
  **Dependencies**: 3.2
- [ ] 3.10 Extend `skills/autopilot/scripts/smoke_provider_dispatch.py` (and `provider_dispatch.py` experimental passthrough) per the modified Manual Provider Smoke Path requirement (S)
  **Spec scenarios**: skill-workflow.10, skill-workflow.11
  **Dependencies**: 3.9
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4 — Frontend: experimental badge (wp-frontend)

- [ ] 4.1 Write/extend kanban-viz tests for an experimental vendor entry rendering with a badge (S)
  **Spec scenarios**: vendor-ux.1, vendor-ux.3
  **Dependencies**: 2.4
- [ ] 4.2 Add `atomic` to the vendor color/label map with experimental badge in `apps/kanban-viz` (`VendorSwimlanes.tsx` vendor map + types) (S)
  **Spec scenarios**: vendor-ux.1, vendor-ux.2
  **Dependencies**: 4.1
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5 — Docs and prose (wp-docs-finalize)

- [ ] 5.1 Update `docs/autopilot-provider-smoke.md` and vendor-roster prose (`agent-coordinator/README.md`, `agent-coordinator/CLAUDE.md`) with the experimental class and atomic entry (S)
  **Spec scenarios**: skill-workflow.10
  **Dependencies**: 3.10
- [ ] 5.2 Update affected SKILL.md prose — `fix-scrub` executor flag documentation, `collect-transcripts` adapter roster (S)
  **Spec scenarios**: skill-workflow.4, harness-engineering.1
  **Dependencies**: 3.6, 3.8
- [ ] 5.3 Sync runtime skill mirrors via `install.sh` and verify parity (S)
  **Dependencies**: 5.2
- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6 — Integration and validation (wp-docs-finalize)

- [ ] 6.1 Run full gate suites (coordinator venv + skills venv) and `openspec validate add-atomic-harness --strict`; fix regressions (M)
  **Dependencies**: all Phase 2–5 tasks
- [ ] 6.2 Run `smoke_provider_dispatch.py --provider atomic --dry-run --json` end-to-end and attach output as evidence (S)
  **Spec scenarios**: skill-workflow.10
  **Dependencies**: 6.1
- [ ] 6.3 Record pilot activation criteria in `design.md`: live re-probe (1.2) complete + one successful `fix-scrub --executor atomic-workflow` run on a real fix batch; file the promotion/retire decision as a follow-up proposal stub (S)
  **Dependencies**: 6.2

## Migration Notes

No breaking changes. Rollback = remove the `atomic-local` entry, the two adapters, the
fix-scrub flag, and the experimental-class definitions; first-class roster behavior and
the closed provider-model-map enum are untouched throughout.
