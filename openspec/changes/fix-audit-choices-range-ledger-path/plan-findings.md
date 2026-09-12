# Plan Findings

<!-- Each iteration of /iterate-on-plan appends a new section below.
     Do not remove previous iterations — this is a cumulative record. -->

## Iteration 1

<!-- Date: 2026-09-11 — autopilot PLAN_ITERATE, architect archetype -->

Inputs read beyond the change directory: `skills/audit-choices/scripts/run_audit.py`,
`collect_evidence.py`, `choices_ledger.py`, `SKILL.md`; `skills/prioritize-proposals/scripts/priorities_paths.py`,
`retention.py`, `SKILL.md`; the three existing `skills/tests/prioritize-proposals/` modules that import
the functions being moved; `skills/tests/audit-choices/test_readonly_posture.py` and
`test_end_to_end.py`; `skills/worktree/scripts/worktree.py` (the `skills/shared/` import bootstrap
precedent); `skills/install.sh` `SHARED_LIBS`; `dependency_direction.py`; the canonical
`skill-workflow` requirement and its "Re-audit is idempotent" scenario.

Two framing notes from the dispatch were checked against the tree. `has_db_migration: true` is a
false positive — no database exists anywhere in scope; the signal substring-matched "migration" in
the work-package description. Design decision D4's guard was judged **necessary but insufficient**
as written (finding 3).

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | feasibility | high | The `skills/shared/` import bootstrap is unspecified. `priorities_paths.py`, `retention.py` and the new `choices_paths.py` are run as scripts from installed copies (`<target>/<skill>/scripts/`) and imported by tests via a `scripts/`-only `sys.path` entry. `from shared.artifact_paths import ...` needs the skills root (`parents[2]`) on `sys.path`, the way `worktree.py` reaches `shared.environment_profile`. Tasks 2.2, 3.1 and 4.2 do not say so; an implementer following them literally produces modules that import in one layout and fail in the other. | D2 now specifies the bootstrap and that each importing module carries it itself. Tasks 2.2, 3.1, 4.2 name it. |
| 2 | consistency | high | `parse_run_id` is omitted from the move. `list_active_runs` calls `priorities_paths.parse_run_id`, and `test_priorities_paths.py` imports `parse_run_id` from `priorities_paths`; task 2.2 moves `RUN_ID_RE` but not the function that gives the regex its contract. Task 2.1's "cover `RUN_ID_RE` … legacy forms" is really `parse_run_id`'s `(date, "", "legacy")` tuple. | D2 and tasks 2.1/2.2 move `parse_run_id`; `priorities_paths.py` and `retention.py` re-export every moved name so the three pre-existing test modules pass without edits (task 3.1). |
| 3 | testability | high | D4's characterization test drives Python functions, but `prioritize-proposals/SKILL.md` only ever calls the CLI entry points (`priorities_paths.py run-id`, `priorities_paths.py paths`, `retention.py --base --retain`), and no existing test invokes them as subprocesses (`test_smoke_e2e.py` runs only `artifact_header.py`). The one risk the migration introduces — finding 1's bootstrap — only manifests when the module runs as a script from an installed copy, so the guard as written would stay green through the exact failure it exists to catch. | D4 gains two more parts: subprocess cases for the three CLI entry points from a runtime-shaped copy (`<tmp>/prioritize-proposals/scripts/` beside `<tmp>/shared/`), and a requirement that the three pre-existing test modules are byte-unchanged, enforced by a `git diff --quiet` verification step in `work-packages.yaml`. Task 1.1 and the Phase 3 checkpoint updated. |
| 4 | consistency | high | Retention contradicts the read-only contract. D6 makes the contract a "literal, checkable set" (pair + `latest.*`) and the Red Flags bullet flags any other path in `git status`; task 5.2 then has every range run call `apply_retention`, which moves whole run directories into `openspec/choices/archive/` once the limit is exceeded. The skill would violate its own contract by design on the 31st run. | D6 names three permitted effects — the pair, the `latest.*` copies, and retention's archive move — in both the contract paragraph and the Red Flags bullet. Task 5.1's posture case asserts exactly pair + `latest.*` under the limit; task 5.2's case asserts pair + `latest.*` + the one archive move over it. |
| 5 | assumptions | medium | Which sha and time name the run directory is ambiguous: `build_run_id(now, head_sha)` could take the audited `head_sha` or the repository `HEAD` the header records as `git_sha`. Separately, the header's `run_id` is caller-supplied and required (`iterate-on-implementation-<ts>` today), so unlike `prioritize-proposals` the directory run-id and the header `run_id` will differ. No user is reachable from this dispatch (autopilot sub-agent; `AskUserQuestion` not exposed), so this is recorded as an explicit decision rather than resolved silently, and flagged in the handoff for the human at plan approval. | New D7: the directory is `build_run_id(generated_at, git_sha)` using the two values already written into the ledger header, so a ledger's location is derivable from its own contents and matches the shipped precedent's "run identity in the path" semantics; the header `run_id` stays the caller's. The audited head is in `audited_range`. Alternative (audited `head_sha`) recorded as rejected. Task 4.1 tests the derivation. |
| 6 | completeness | medium | Idempotency semantics for the range form are unstated. Canonical scenario "Re-audit is idempotent" is satisfied today by `write_ledger` merging into an existing `choices.json` by `stable_id`; a range run always targets a fresh dated directory, so the merge never fires. The scenario still holds (ids are content-derived, no file ever gains a duplicate) but "update in place" becomes change-id-only, and `latest.*` is a copy of the newest run, not a merged view. `SKILL.md`'s verification step 5 ("re-run and confirm `choices.json` unchanged") now compares two files. | New D8 states that range ledgers are per-run snapshots and why the scenario holds by construction. Task 4.3 asserts the two-run behaviour; task 5.3 rewords verification step 5. |
| 7 | completeness | medium | Retention failure semantics inside a never-raises driver. If `apply_retention` raises after the pair is written (a failed `shutil.move`), the driver's catch-all returns `ok=False, json_path=None` for a run whose ledger was in fact persisted — a misleading signal to the workflow. | D8 and task 5.2: retention runs last, after the pair and `latest.*`, and is wrapped so a failure logs a warning and leaves `ok=True` with both paths set. Tested by monkeypatching `apply_retention` to raise. |
| 8 | consistency | medium | The proposal says `run_audit.py` "has one path derivation" and that the range encoding is "the only place" a range reaches a path; `collect_evidence.py:276` derives `openspec/changes/<change_id>` too. It is read-only and degrades to empty excerpts, so it is not part of the defect, but D5's routing helper is silently not applied there and task 4.3's "no `range:` directory anywhere" assertion depends on the collector never creating one. | D5 addendum says the collector is deliberately left alone and why; the proposal's Why section is corrected. |
| 9 | completeness | medium | The `latest.*` write and the "only writer" sentence. `SKILL.md` line 34 states `write_ledger_pair` is the only thing in `scripts/` that opens a file for writing; task 4.2 adds a `latest.*` rewrite and task 5.1 updates the pair paragraph and the Red Flags bullet but not that sentence, nor the Output section that lists destinations. How `latest.*` is produced is also unspecified. | D6: `latest.*` are byte-identical copies of the run's pair via `shutil.copyfile`; `write_ledger_pair` remains the only producer of ledger content. Task 5.1 updates the "only writer" sentence and the Output section; task 4.3 asserts the byte equality. |
| 10 | clarity | low | The default retain count exists twice in `prioritize-proposals` (`retention.py` CLI default and `SKILL.md`'s `RETAIN_N=30`) and the shared `apply_retention` has no default; task 5.2 says "the same default" without naming where it lives. The Plan phase left this as an open question. | D3: the shared module exports `DEFAULT_RETAIN = 30`; both callers use it. 30 is kept rather than re-derived. |
| 11 | scope | low | `work-packages.yaml`'s description uses "migration", which the complexity gate substring-matched into `has_db_migration: true`. Harmless this time because the operator caught it, but the same text will re-trigger at every later gate evaluation. | Description reworded to say what happens without the word. Design and proposal prose keep the ordinary English. |
| 12 | parallelizability | low | Tasks 5.1 and 5.3 both edit `skills/audit-choices/SKILL.md` with no ordering between them; 5.2 shares `choices_paths.py` with 4.2 and `test_output_routing.py` with 4.1 (already ordered). Inside the single sequential package this cannot conflict, but the dependency should be explicit for any future split. | Task 5.3 now depends on 5.1. |

### Parallelizability Assessment

- Independent tasks: 0 (every task has at least one predecessor except 1.1)
- Sequential chains: 1 spine — 1.1 → 2.1 → 2.2 → 4.1 → 4.2 → {4.3, 5.1 → 5.3, 5.2}; 3.1 hangs off 2.2
- Max parallel width: 2 after 2.2 (3.1 ∥ 4.1); 3 after 4.2 (4.3 ∥ 5.1 ∥ 5.2)
- File overlap between concurrently-eligible tasks: none (5.1/5.3 now ordered; 4.3/5.1/5.2 touch disjoint files)
- Single work package retained: the chain is real and the S-sized parallel edges do not justify a second worktree.

### Quality Checks

- `openspec validate fix-audit-choices-range-ledger-path --strict`: valid before and after this iteration.
- Scenario coverage: 12 (success + the "no `range:` directory" negative), 13 (negative for the change-id form), 14 (bounded; archive-not-delete). Retention-failure and two-run idempotency paths are covered at task level (5.2, 4.3) rather than as new spec scenarios, since the spec is deliberately path-agnostic.
- Task traceability: every task cites a scenario or a design decision; 1.1, 2.x and 3.1 trace to D2–D4 (the guarded refactor has no spec scenario of its own by design — it must not change observable behaviour).
- Design rationale: D1, D2, D5, D7 record a rejected alternative; D3, D4, D6, D8 record the failure they prevent.

## Iteration 2

<!-- Date: 2026-09-11 — convergence pass -->

Re-read proposal, design, tasks, the spec delta and work-packages after the iteration-1 edits,
checking each cross-reference (D-numbers cited by tasks, files named in tasks versus the package's
`write_allow` and `locks`, scenario ordinals, the two checkpoints' commands against the package's
verification steps). No finding at or above the medium threshold. Termination: threshold met.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| — | — | — | No findings at or above `medium`. | Loop converged after one refining iteration. |

Residual, below threshold and deliberately left: the header `run_id` and the D7 directory run-id are
two identities on one ledger (recorded as an accepted trade-off), and D7 itself awaits a human at plan
approval.
