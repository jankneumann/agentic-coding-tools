# Plan Findings

<!-- Each iteration of /iterate-on-plan appends a new section below.
     Do not remove previous iterations — this is a cumulative record. -->

## Iteration 1

<!-- Date: 2026-10-05 -->

Baseline: `openspec validate ownership-map --strict` passed; `validate_work_packages.py
--check-overlap` passed (schema, DAG, lock keys, scope and lock overlap). Analysis ran inline
(architect archetype; no sub-agent tool exposed to this phase session) against proposal.md,
design.md (D1–D13), tasks.md, both spec deltas, work-packages.yaml, the draft schemas, the
existing `agent-identity` spec, `agents_config.py`, `test_registry_projection.py`,
`validate_install_manifest.py`, `install.sh`, and the roadmap item `ri-02`.

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | high | D4's `resolve_path()` consults only `paths` rules, but D8 emits `CODEOWNERS` lines from *capability* assignments and reconcile compares GitHub's pick against the resolver for every file under `openspec/specs/`. A capability-only map therefore yields `default_owner` from the resolver and the capability owner from GitHub — a guaranteed false disagreement on every spec file; the scenario "Hand-edited line that disagrees is reported" already presumes the resolver knows the capability owner of a spec path. | Fixed. D4: capability assignments imply `openspec/specs/<cap>/` and `openspec/contracts/<cap>/` rules ranked with explicit rules; implied rules order before explicit so an explicit rule of equal specificity wins; `matched_rule == "capability:<cap>"`. D8 emit order mirrors it. Spec Owner Resolution text + 2 scenarios; task 3.3, 4.1; proposal What Changes. |
| 2 | clarity | high | The "restricted glob subset" never states the matching rules (anchoring of patterns without `/`, leading/trailing `/`, `*` not crossing `/`, `**` whole-segment vs embedded). Two valid implementations diverge, and fixture tests pass with either; only the real-tree reconcile would catch it, late. | Fixed. D3 gains the matching-semantics table; loader rejects embedded `**` (`OwnershipConfigError`). Spec Ownership Map Schema sentence + scenario "Embedded double-star rejected"; schema description; task 3.3. |
| 3 | feasibility | high | Task 5.2 + the repository invariant (5.1, warning-free `--strict`) require an explicit assignment for all 40 capabilities and ~190 roadmap items. Every later `/plan-feature` (new spec dir) or `/plan-roadmap` run would break CI until `owners.yaml` is edited — the solo-mode friction the roadmap constraint forbids — and the file would churn with every planning change. | Fixed. New D14: `unowned_capability` / `unowned_roadmap_item` are team-mode-only warnings. Task 5.2 asks for a representative assignment set that exercises every resolver branch; task 5.1 adds the "stays green when a capability is added" probe. Spec Ownership Check text, scenario "Solo mode emits no unowned findings", "Clean repository passes" GIVEN relaxed accordingly. |
| 4 | completeness | medium | No behaviour defined for `emit`, `reconcile` or `check --codeowners` when `owners.yaml` is absent (solo mode without a map): emission is impossible (the solo principal may have no handle) and solo mode must add no checks. | Fixed. D8: `emit` exits 1 with `no_ownership_map` writing nothing; `reconcile` exits 0 with an informational finding unless a managed block survives (`orphan_managed_block` warning). Spec CODEOWNERS Projection text + scenarios "Emit without a map fails closed", "Orphaned managed block reported"; tasks 4.1, 4.3. |
| 5 | completeness | medium | A typo in a `capabilities` or `roadmap_items` key is silently inert — the intended assignment never matches and nothing reports the dangling key. | Fixed. D9: `unknown_capability` / `unknown_roadmap_item` warnings (closed key sets; `paths` keys deliberately unchecked). Spec Ownership Check text + scenario "Dangling capability assignment reported"; task 3.5. |
| 6 | consistency | medium | tasks.md 3.5 and the spec name finding codes (`unowned_capability`, `unknown_owner`, …) that D9's table does not carry, yet the `--json` codes are the machine contract later items consume. | Fixed. D9 table gains a `Code` column enumerating every code (including the new ones); spec requires codes to be those identifiers and `info` never promoted; task 3.5 asserts every emitted code is in the table. |
| 7 | security | medium | `registry:` in `owners.yaml` accepted any non-absolute path, including `../…`, so a reviewed-but-careless map could make the reader parse a file outside the repository. | Fixed. Schema pattern rejects `..` segments; D3/D10 require the resolved path to stay inside `repo_root` (`registry_outside_repo`); `OWNERSHIP_REGISTRY_PATH` stays operator-controlled and exempt. Spec scenario "Registry path escaping the repository rejected"; tasks 1.2, 3.1. |
| 8 | testability | medium | The 250 ms performance NFR was to be asserted directly in a unit test — a known CI flake source. | Fixed. NFR row and task 3.3: 250 ms remains the design budget; the test asserts a 4× margin (1 s). |
| 9 | clarity | medium | `load_ownership(repo_root)` never says how `repo_root` is found, and the resolver's dependence on the `git` binary / a `.git` directory (`git config`, `git ls-files` for the probe set) contradicts an unqualified "works from the checkout alone". | Fixed. D4: `repo_root` defaults to `git rev-parse --show-toplevel`, else cwd. D5/D8: exported tree → sentinel principal; reconcile fails with `not_a_git_checkout`. Spec Coordinator Independence text; proposal What Changes names the `git` binary. |
| 10 | consistency | medium | D5 step 2 ("match `git config user.email` to a declared human") is unreachable: step 1 fires whenever exactly one human is declared and two or more without a map is an error, so `email` has no consumer anywhere in ri-02 while being declared as if it had one. | Fixed. D5 step 2 is the synthetic `git:<email>` principal only; `email` documented as declared for `ri-03` attribution and optional (PII a maintainer may withhold). Spec Solo Mode text; schema description; D1 comment; tasks 2.6, 3.1; new open question on whether to drop the field until ri-03. |
| 11 | parallelizability | medium | `skills/tests/ownership-runtime/__init__.py` and `conftest.py` sat in wp-resolver's scope while wp-contracts (the DAG root) already writes `test_schema_copies.py` and `fixtures/` into that directory and runs pytest there, and wp-codeowners adds modules too. | Fixed. New task 1.3 creates the package skeleton and shared fixture builder in wp-contracts; wp-resolver's `write_allow` drops the two files; `plan_revision` → 2. Overlap check re-run clean. |
| 12 | assumptions | medium | Whether to commit the maintainer's `email` into `agents.yaml` (PII) could go either way. No interactive user is available in this autopilot phase, so it could not be surfaced via AskUserQuestion. | Resolved conservatively by the architect: `email` is optional, unused by ri-02, and task 2.6 includes it only if the maintainer wants it published; recorded as an open question for the human reviewer at approval. Logged as a skill-procedure deviation. |
| 13 | consistency | low | tasks.md preamble said the L-adjacent split was "3.3 / 3.4 → emit vs reconcile"; those are the owners tasks, emit/reconcile are 4.1–4.4. | Fixed (co-located with other tasks.md edits). |
| 14 | clarity | low | Task 1.1 did not name its test file although work-packages.yaml does (`test_schema_copies.py`). | Fixed (co-located). |
| 15 | feasibility | low | Task 2.6 relies on `gh api user`, which may be unauthenticated in the implementing agent's container. | Fixed (co-located): fall back to the `origin` remote owner and say so in the checkpoint. |
| 16 | parallelizability | low | Tasks 5.4/5.5 (state-artifacts row + test) have no dependencies yet sit in wp-dogfood-docs behind wp-registry and wp-codeowners. | Deferred: two S docs tasks do not justify a seventh package; noted for the implementer, who may run them first inside wp-dogfood-docs. |

`workflow.prototype-recommended` advisory: not emitted (2 high findings in clarity+feasibility;
threshold is 3).

### Quality Checks

- `openspec validate ownership-map --strict`: valid (before and after the edits).
- `validate_work_packages.py --check-overlap`: valid — schema, depends_on refs, DAG, lock keys,
  scope overlap, lock overlap all pass after moving the test-package skeleton to wp-contracts.
- Both draft schemas parse as Draft 2020-12; the new `registry` pattern accepts
  `agents.yaml` / `agent-coordinator/agents.yaml` and rejects `../x`, `a/../b`, `/abs`.
- Traceability (scripted): 46/46 scenarios across the two deltas are referenced by at least
  one task and every task reference names a real scenario. 28 tasks; the 10 without a direct
  scenario or design citation (2.3, 2.5, 3.2, 3.4, 3.6, 4.2, 4.4, 5.3, 5.5, 6.1) are the
  implementation halves of TDD pairs whose test task carries the trace, as tasks.md declares.
- Scenario coverage: every requirement has at least one success and one failure/edge scenario
  (Ownership Map Schema 8, Owner Resolution 7, Ownership Check 6, Solo Mode 5, Coordinator
  Independence 3, CODEOWNERS Projection 7, Durable Artifact Registration 2, Portable
  Distribution 2, Human Principal Registry Extension 6).
- Session log: `Plan Iteration 1` appended and sanitized; coordinator handoff
  `77c72b47-0742-4a9c-8c1d-fdc2f6800349`; decision index regenerated.

### Parallelizability Assessment

- Independent tasks: 4 (1.1, 1.3, 2.1, 5.4)
- Sequential chains: 5 (contracts 1.1→1.2; registry 2.1/2.2→2.3→2.4→2.5, 2.3→2.6;
  resolver 3.1→3.2→3.3→3.4→{3.5→3.6, 3.7}; codeowners 4.1→4.2→4.3→4.4; dogfood/docs
  5.1→5.2→5.3→5.7, 5.4→5.5, 5.6) converging on 6.1
- Max parallel width: 2 packages (wp-registry ‖ wp-resolver after wp-contracts); 3 at task
  level (2.x ‖ 3.x ‖ 5.4/5.5)
- File overlap conflicts: none after moving `__init__.py`/`conftest.py` to wp-contracts
  (`--check-overlap` clean)

---

## Summary

<!-- Populated after the final iteration -->
