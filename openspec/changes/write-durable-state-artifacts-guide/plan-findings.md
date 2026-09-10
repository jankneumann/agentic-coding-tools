# Plan Iteration Findings

## Round 1

### Execution note

The provider-neutral plan-iteration worker exceeded its bounded material-output window and was interrupted. Direct deterministic recovery was used to inspect and refine the already-pushed plan. The earlier GATEKEEPER phase also ran in documented degraded signal-only mode because the collaboration runtime had no free agent thread; deterministic scope inspection found no broad-scope, multi-service, identity, billing, migration, or destructive-work signal.

### Findings resolved

1. **Task titles mixed multiple actions and metadata on one line.** Reworked every numbered task into one imperative title followed by explicit size, scenario, decision, dependency, and coverage fields. This removes ambiguous compound titles and makes dependency review mechanical.
2. **The RED target was directory-only.** Pinned the structural contract test to `skills/tests/state-artifacts/test_state_artifacts_guide.py` while retaining the directory-level verification command in `work-packages.yaml`.
3. **Mirror work appeared to be two independent tasks.** Kept it as one synchronization task because `skills/install.sh` owns both runtime mirrors and parity must be assessed atomically.

### Findings retained by design

- One sequential package is intentional: the guide, skill links, supervise ordering, test contract, and generated mirrors share a single semantic drift boundary.
- No ADR is required because this change documents established authority relationships and does not add a new runtime or public interface decision.
- Security, deployment, and browser validation are explicitly not applicable to the documentation-only product surface; strict OpenSpec, structural tests, mirror parity, context drift, and scope checks remain mandatory.

### Remaining review questions

- Confirm the five artifact classes and question-scoped authority descriptions match current runtime behavior.
- Confirm all skill sources that materially create, mutate, or rehydrate these artifacts are in the link and mirror allowlists.
- Confirm the bootstrap-locator language cannot be read as elevating a handoff above canonical state.

## Vendor review round 1 disposition

- **Quorum**: met with substantive Antigravity and Grok reviews; Pi was excluded after schema validation failed.
- **Blocking findings**: none.
- **Lock-surface nit**: fixed by adding the documentation index plus the implement-feature and validate-feature canonical sources to `locks.files`.
- **Coordination-bridge optional finding**: accepted without scope expansion. The bridge owns transport-specific queue projection behavior; it does not create, mutate, or rehydrate the five durable file classes. The canonical guide will describe the projection boundary and may cite the bridge for transport detail, but the bridge remains outside the required link/mirror set.
- **Supervise ledger FYI**: accepted. `cycle-ledger.json` remains supervise-local operational/idempotency state and is not elevated into the five-class cross-workflow authority ladder.

## Implementation scope reconciliation

`PhaseRecord.write_both()` correctly regenerated `docs/decisions/skill-workflow.md` after the implementation entry introduced a `skill-workflow` decision. The work package now names that deterministic derived artifact in both `locks.files` and `scope.write_allow`, and declares the validator-required `decisions` context-impact surface alongside `documentation` and `semantic_code`. This is an exact generated-output amendment, not a broad scope expansion.

## Fresh canonical plan review — 2026-09-09

### Dispatch and consensus

- Antigravity, Claude Code, and Grok returned schema-valid reviews; Codex supplied the primary review. Pi failed closed because its OpenRouter credential was unavailable, and the dispatch manifest preserves that degraded reviewer result.
- The mechanical synthesizer reported two confirmed positive observations, seventeen unconfirmed findings, and two disagreements. Both disagreements were false matches between positive and negative observations about the same artifact, so they were adjudicated from source evidence rather than treated as human product decisions.

### Findings fixed in the plan

1. Made all eight named rehydration stages normative in the surviving `skill-workflow` spec, including projection rebuild after advisory reconciliation.
2. Replaced overbroad link language with the portable repository-relative reference contract and named the exact six in-scope workflow skills.
3. Clarified that a missing checkpoint is valid only before any locator or advisory record claims progress, while keeping the recent-learning bound runtime-configurable rather than freezing its current default into the normative spec.
4. Reconciled the proposal's inventory and Impact sections with the actual plan by separating shared writer-ordering rules and naming `skills/pyproject.toml` plus the generated decision index.
5. Added the schema-required no-contract README rationale so context-impact validation does not misclassify the documentation stub as an API change.
6. Added explicit install-payload and no-contract context-impact verification steps to the work package.

### Findings retained by design

- The exact eight-step order remains a deliberate drift contract. It is not relaxed to a partial-order assertion because roadmap definition, first-run checkpoint handling, canonical change state, advisory context, and one-way projection rebuild are individually meaningful recovery stages.
- One sequential package remains proportionate because the guide, six shared skill references, generated mirrors, and structural tests form one semantic drift boundary.
- Skills outside the six named sources are not silently pulled into scope. The roadmap requires replacing prior duplicated semantics, not adding a reference to every utility that ever reads or moves a durable artifact.

## Round 6 convergence follow-up - 2026-09-09

- Accepted the high archive-stability blocker: the default-CI test must resolve the change directory with `change_dir()` from `openspec_paths` rather than pinning `openspec/changes/<id>/`. Task 3.2 now records the unfinished implementation repair explicitly.
- Replaced the single-file context-impact probe with the repository-standard `--base main` gate and declared the implied `capabilities` surface, so the full branch scope is checked rather than one schema stub.
- Removed the inaccurate `runtime-configured` wording. The recent-learning window remains bounded and selected by roadmap runtime, while its numeric default stays outside this documentation contract.
- Removed the cycle ledger from the shared roadmap-definition stage and retained it as `supervise`-local operational validation outside the five-class authority inventory.
- Connected `skills/install.sh --check` explicitly to portable reference-form validation and normalized remaining plan wording from links to references.
- Retained the conditional mirror test: installed mirrors are byte-compared locally, fresh CI checkouts may omit ignored mirrors, and payload/reference portability is independently enforced by `skills/install.sh --check`.

## Round 7 prerequisite clarification - 2026-09-09

- The feature branch predates the repository-wide OpenSpec path-stability infrastructure, but current `main` already contains `skills/tests/_shared/openspec_paths.py` and `skills/tests/openspec_paths/`. Task 3.2 now requires synchronizing the branch first, then consuming those existing inputs.
- The documentation package does not create, copy, or own the shared helper or guard, so its existing write allowlist remains correct. The final verification command is intentionally executable after the required branch synchronization.

## Round 8 convergence - 2026-09-09

- Codex, Antigravity, and Grok produced schema-valid findings for the focused prerequisite review. Claude Code timed out after 420 seconds and Pi failed authentication; both degraded outcomes remain explicit in the dispatch manifest.
- Consensus met the requested three-reviewer quorum with 11 unique findings, zero disagreements, and zero blocking findings.
- The prior feasibility blockers are resolved at plan level: implementation must synchronize with current `main`, then consume the existing `openspec_paths` helper and guard without expanding the package write scope.
- The canonical loop was resumed through the recorded operator gates and advanced from `PLAN_REVIEW` to `IMPLEMENT`; tasks 3.2 and 3.3 remain intentionally unchecked.
