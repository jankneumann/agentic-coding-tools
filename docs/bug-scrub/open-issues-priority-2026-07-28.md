# Open GitHub Issue Priority — 2026-07-28

## Scope and baseline

- Repository: `jankneumann/agentic-coding-tools`
- Baseline: `origin/main` at `247bc201cbfab7ee4a1441f0d293ad16031247a5`
- Isolation: managed worktree on
  `openspec/prioritize-open-github-issues-2026-07-28`
- Inventory: all 44 issues open at the start of the scrub, plus
  [#321](https://github.com/jankneumann/agentic-coding-tools/issues/321),
  filed from the additional cross-repository handoff failure reported during
  the scrub
- Bug-scrub inputs:
  `docs/bug-scrub/bug-scrub-report.md` and
  `docs/bug-scrub/bug-scrub-report.json`, severity filter `low`

Priority is based on current blast radius, whether the defect can lose or
misattribute evidence, whether it makes an automated gate falsely green,
whether it blocks a documented workflow, and whether a safe workaround exists.
Age is not used as a proxy for importance.

## Recommended order

### P0 — restore trust in coordination and automation

These should be addressed before relying on the affected workflows for
unattended or cross-repository work.

| Order | Issue | Why now | Recommended handling |
|---:|---|---|---|
| 1 | [#321 — Coordinator `write_handoff` returns 403 when runtime identity differs from API-key profile](https://github.com/jankneumann/agentic-coding-tools/issues/321) | Blocks durable handoffs across repositories and strands session context in local scratch files. Reproduced operationally; the client sends an explicit identity that the key-bound server identity correctly rejects. | Fix the client/preflight path while preserving the server anti-spoofing check. |
| 2 | [#312 — merge-pull-requests has 21 test files that CI collects zero of](https://github.com/jankneumann/agentic-coding-tools/issues/312) | Merge, rollback, rebase, and convergence automation can regress without any gate noticing. Current `skills/pyproject.toml` still omits both test directories. | Add both paths to `testpaths` first; consolidate layout separately. |
| 3 | [#309 — `merge_worktrees.py` checks out a branch already owned by another worktree](https://github.com/jankneumann/agentic-coding-tools/issues/309) | The documented integration tool fails by construction under the managed-worktree model. Current code still calls `git checkout <feature-branch>` from the wrong checkout. | Run integration in the parent feature worktree or operate on refs without checkout. |
| 4 | [#300 — one malformed vendor finding aborts a review round](https://github.com/jankneumann/agentic-coding-tools/issues/300) | One vendor can strand every peer's paid review output and prevent the manifest from being written. Both unguarded per-vendor write loops remain. | Isolate validation failure per vendor and always write the partial manifest. |
| 5 | [#302 — file-emitting vendor findings are never collected](https://github.com/jankneumann/agentic-coding-tools/issues/302) | A well-formed `critical` finding was silently omitted. This is direct review-evidence loss. | Collect a recognized findings artifact or at minimum warn on new worktree files; prefer scratch execution directories. |
| 6 | [#286 — review dispatcher discards vendor stdout on JSON parse failure](https://github.com/jankneumann/agentic-coding-tools/issues/286) | Actionable root-cause output is replaced with `Invalid JSON output`, multiplying diagnosis time and hiding vendor faults. Current adapter still drops the raw stdout on this path. | Preserve truncated stdout/stderr in the failure envelope. |
| 7 | [#306 — gen-eval silently drops requested scenarios and can still pass](https://github.com/jankneumann/agentic-coding-tools/issues/306) | A partial evaluation can report 100% and exit 0. This is a false-green quality gate. | Make requested/evaluated set equality authoritative and fail closed on generation/filtering loss. |
| 8 | [#317 — gen-eval MCP can return another run's report from cwd](https://github.com/jankneumann/agentic-coding-tools/issues/317) | Explicitly isolated callers can receive stale metrics from a different run with no warning. The unanchored cwd candidate remains in `_find_latest_report`. | Anchor lookup to `base_dir`; make cwd fallback opt-in only when no explicit base was supplied. |
| 9 | [#313 — decision index exits 0 with an empty index outside repo root](https://github.com/jankneumann/agentic-coding-tools/issues/313) | `--strict` reports success for work it did not do and writes into an unrelated cwd. | Resolve an explicit repository root and fail loudly on missing/empty inputs in strict mode. Audit sibling scripts at the same time. |
| 10 | [#308 — code-search `work_package` scope rejects every production request](https://github.com/jankneumann/agentic-coding-tools/issues/308) | A documented, schema-valid production capability is entirely unusable. The production runtime still constructs `CodeSearchRuntime` without the required resolver. | Bind the resolver in `start_code_search_runtime` and add a serving-path integration test. |
| 11 | [#260 — autopilot phase-archetype integration fixtures lack `write_capable`](https://github.com/jankneumann/agentic-coding-tools/issues/260) | Confirmed in this scrub: 7 of 9 targeted integration tests fail against current `origin/main`. | Refresh fixtures and document the coordinator-environment test command. |

### P1 — next reliability and determinism tranche

| Order | Issue | Why next |
|---:|---|---|
| 12 | [#318 — CI installs OpenSpec from npm latest](https://github.com/jankneumann/agentic-coding-tools/issues/318) | The same commit can change validation result without a repository change. Current CI remains unpinned. |
| 13 | [#316 — gen-eval credits a flag for being passed, not asserted](https://github.com/jankneumann/agentic-coding-tools/issues/316) | Coverage completeness can be laundered by incidental argv presence. Decide whether to add mutation-based discrimination or report earned versus incidental credit. |
| 14 | [#311 — five install-asset schemas keep every bootstrapped checkout dirty](https://github.com/jankneumann/agentic-coding-tools/issues/311) | Reproduced by this scrub's managed-worktree bootstrap. It undermines clean-tree gates and teardown on every install. |
| 15 | [#320 — worktree GC calls pushed-only branches “merged”](https://github.com/jankneumann/agentic-coding-tools/issues/320) | The destructive step is recoverable, but the false message can cause an operator to abandon unmerged work. Current code still prints the claim after `git branch -d`. |
| 16 | [#307 — context-refresh identity changes with clone directory name](https://github.com/jankneumann/agentic-coding-tools/issues/307) | Idempotence and convergence history split across clones. The current workflow documents an environment-variable workaround, confirming the default remains unsafe. |
| 17 | [#301 — DAG scheduler default reports all contracts missing](https://github.com/jankneumann/agentic-coding-tools/issues/301) | The validator's false positives hide genuine missing contracts; the documented `--validate` invocation is also unsupported. |
| 18 | [#280 — 24 of 62 work-package files fail their own schema](https://github.com/jankneumann/agentic-coding-tools/issues/280) | Dispatch-time validation cannot be trusted until the schema-versus-authoring convention is reconciled. Fix active changes first, then gate them in CI. |
| 19 | [#275 — architecture graph covers at most 14.6% of Python and 0% of TypeScript](https://github.com/jankneumann/agentic-coding-tools/issues/275) | The scrub imported 2,878 architecture findings, dominating every other signal. The report is current but still structurally partial, so downstream prioritization is noisy. |
| 20 | [#261 — merge PR discovery imports a sibling coordinator module in consumer repos](https://github.com/jankneumann/agentic-coding-tools/issues/261) | Consumer installations can fail before PR discovery starts. The import remains local-path dependent. |
| 21 | [#219 — enable Dependabot security updates](https://github.com/jankneumann/agentic-coding-tools/issues/219) | Scheduled manifests exist, but automated security-update enablement is an external repository setting and should be verified explicitly. |
| 22 | [#216 — enable multi-repo on `coord.rotkohl.ai`](https://github.com/jankneumann/agentic-coding-tools/issues/216) | External operational prerequisite for cross-repository coordination; combine validation with #321's identity preflight. |
| 23 | [#168 — decision-index writer drift outside cleanup](https://github.com/jankneumann/agentic-coding-tools/issues/168) | `cleanup-feature` regenerates decisions, but the other session-log writers inspected in this scrub still do not. Prefer a write-site-independent hook/check. |
| 24 | [#151 — parallel implementation leaves `tasks.md` behind reality](https://github.com/jankneumann/agentic-coding-tools/issues/151) | Current guidance says task updates are canonical, but the parallel-tier reconciliation path still needs proof that package completion updates the parent artifact. |

### P2 — planned contract and lifecycle hardening

| Order | Issue | Why later |
|---:|---|---|
| 25 | [#310 — coordinator detection returns transport-dependent capability keys](https://github.com/jankneumann/agentic-coding-tools/issues/310) | Low current impact, but a stable response schema prevents future truthiness/key-existence bugs. |
| 26 | [#305 — gen-eval report numeric fields are unbounded](https://github.com/jankneumann/agentic-coding-tools/issues/305) | Contract correctness issue with a downstream workaround already in place; coordinate with a contract-version bump. |
| 27 | [#288 — coordinator descriptor covers 38 of 82 HTTP routes](https://github.com/jankneumann/agentic-coding-tools/issues/288) | Large coverage gap, but it depends on publishing an authoritative OpenAPI contract first. |
| 28 | [#169 — lint MODIFIED-vs-ADDED requirements during planning](https://github.com/jankneumann/agentic-coding-tools/issues/169) | Prevents a late cleanup failure; valuable but fail-closed P0/P1 defects should land first. |
| 29 | [#158 — validation gate parses brittle markdown](https://github.com/jankneumann/agentic-coding-tools/issues/158) | Current parser remains markdown-driven, but it fails closed rather than producing a false green. Move to a structured status block. |
| 30 | [#154 — verify remote branch deletion after PR merge](https://github.com/jankneumann/agentic-coding-tools/issues/154) | Cleanup correctness/diagnostics improvement; remote residue is recoverable. |
| 31 | [#152 — validation phases need a project profile](https://github.com/jankneumann/agentic-coding-tools/issues/152) | Removes broad `--force` use for library projects; requires a small design decision about defaults and overrides. |

### P3 — low-risk improvements and explicit verification

| Order | Issue | Handling |
|---:|---|---|
| 32 | [#137 — add `isolation_provided` to coordinator registration](https://github.com/jankneumann/agentic-coding-tools/issues/137) | Useful authoritative signal, but existing environment/heuristic fallbacks make it non-blocking. |
| 33 | [#153 — dirty teardown should list files](https://github.com/jankneumann/agentic-coding-tools/issues/153) | Operator-experience fix; current teardown is safely fail-closed. |
| 34 | [#160 — cache transcript parsing between Stop hooks](https://github.com/jankneumann/agentic-coding-tools/issues/160) | Performance-only; schedule after correctness work. |
| 35 | [#159 — replace AI-DORA prefix heuristics](https://github.com/jankneumann/agentic-coding-tools/issues/159) | Metric calibration improvement with the heuristic explicitly documented as approximate. |
| 36 | [#314 — tighten “never raises” documentation](https://github.com/jankneumann/agentic-coding-tools/issues/314) | Documentation-only and correctly argues against catching `BaseException`. |
| 37 | [#148 — old SonarCloud hotspot/duplication findings](https://github.com/jankneumann/agentic-coding-tools/issues/148) | Recheck the current dashboard, record triage, then close if the old new-code window no longer applies. |

## Verify and close as already resolved

These issues are still open, but current `origin/main` contains the requested
behavior or dependency level. Verify the cited focused test/check, then close
instead of spending implementation capacity on them.

| Issue | Evidence on current main |
|---|---|
| [#135 — expose `phase_archetype` in discovery](https://github.com/jankneumann/agentic-coding-tools/issues/135) | `AgentInfo.phase_archetype`, heartbeat persistence, migration `023_add_phase_archetype.sql`, and API/MCP response projection are present. |
| [#136 — INIT archetype and status reporter emission](https://github.com/jankneumann/agentic-coding-tools/issues/136) | State-only resolution exists for INIT/SUBMIT_PR and `report_status.py` reads and posts `phase_archetype`. |
| [#150 — linter exit code swallowed by pipe-to-tail](https://github.com/jankneumann/agentic-coding-tools/issues/150) | Current iteration skill dispatches quality commands independently and contains no `| tail` pipeline. Add/confirm the regression check, then close. |
| [#167 — worktree `--branch` shadows an existing remote branch](https://github.com/jankneumann/agentic-coding-tools/issues/167) | `_existing_branch_start_point` now prefers the same-named local branch or `origin/<branch>` before falling back to main. |
| [#213 — dependency CVE bump set](https://github.com/jankneumann/agentic-coding-tools/issues/213) | Current lock resolves `cryptography 49.0.0`, `pydantic-settings 2.14.2`, `python-multipart 0.0.32`, and `starlette 1.3.1`, meeting or exceeding the issue's requested versions. |
| [#221 — rebase merge skips OpenSpec archive](https://github.com/jankneumann/agentic-coding-tools/issues/221) | Current merge workflow runs `cleanup-feature --post-merge --defer-commit` for every approved merged OpenSpec change before convergence. |
| [#232 — bump `joserfc` for CVEs](https://github.com/jankneumann/agentic-coding-tools/issues/232) | Current lock resolves `joserfc 1.7.3` with a declared floor of `>=1.6.8`. |
| [#289 — stale contracts inventory](https://github.com/jankneumann/agentic-coding-tools/issues/289) | Current generated inventory reports 13 schemas, including all project-context-refresh and gen-eval contracts. |

## Bug-scrub evidence and limitations

The refreshed bug scrub produced 3,813 findings:

| Severity | Count |
|---|---:|
| high | 7 |
| medium | 3,123 |
| low | 683 |

| Source | Result |
|---|---|
| Ruff | 13 findings: 7 high E402 errors and 6 medium unused-import/variable findings. |
| Mypy | Executed successfully with 0 parsed findings. |
| OpenSpec | Executed with no parsed findings, although the CLI returned exit 1; this should be interpreted alongside #318's version instability. |
| Architecture | 2,878 findings. This is a useful hotspot signal but not a trustworthy issue count because #275 documents partial graph coverage and the diagnostics include many expected API/MCP entrypoints as disconnected. |
| Deferred | 889 findings, including 887 unchecked task boxes. Most are from archived change artifacts, so they are historical evidence rather than 887 live work items. |
| Markers | 33 findings. Most are marker-collector test fixtures or installed skill mirrors; deduplicate before creating work. |
| Pytest | Collector error: repository-root discovery hit 153 collection errors in the mixed multi-environment repository. The report intentionally does not treat this as “zero failures.” A focused current-main run for #260 independently confirmed 7 failures and 2 passes. |
| Security | Skipped because no current `docs/security-review/security-review-report.json` exists. Dependency versions were checked directly for #213 and #232, but this is not a replacement for a fresh security review. |

The raw scrub report is valuable primarily as corroboration for #275, #260,
and the current Ruff debt. It should not be fed directly to `fix-scrub` without
first excluding archived task checkboxes, marker fixtures/mirrors, and noisy
architecture diagnostics.

## Suggested batching

1. **Coordinator continuity:** #321, then #216; use the same preflight to make
   the effective key-bound identity visible.
2. **Merge/worktree trust:** #312, #309, #311, #320, and focused closure checks
   for #167 and #221.
3. **Review evidence preservation:** #300, #302, and #286 as one proposal,
   because all three harden the same dispatcher boundary.
4. **False-green evaluation:** #306, #316, #317, and #305, with #318 handled
   separately as CI supply-chain determinism.
5. **Context correctness:** #313, #307, #301, #280, #275, and #168.
6. **Close resolved backlog:** verify and close the eight issues listed above
   before starting P2/P3 work.
