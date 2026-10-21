# Pilot run notes — 2026-10-13

Deterministic stages (task 9.2) over both pilot suites, from a full clone (task 9.1, `git fetch --unshallow`).

| Suite | Tests | inventory + static + history | mutate | refactor |
|---|---:|---:|---:|---:|
| `test_evaluation` | 99 | 9 s | 474 s | 14 s |
| `parallel_infrastructure` | 299 | 53 s | 720 s | 24 s |

- **NFR, ≤ 2 min for inventory + static + history:** met (9 s, 53 s).
- **NFR, mutation wall clock ≤ 60 min per suite:** met (8 min, 12 min). Backend `AstMutantRunner`
  (the mutmut probe fails on its relocated `mutants/` tree; design D4 spike verdict).
- **NFR, read-only:** `git status --porcelain --untracked-files=all` over the four audited paths
  (`agent-coordinator/tests/test_evaluation`, `agent-coordinator/evaluation`,
  `skills/tests/parallel-infrastructure`, `skills/parallel-infrastructure`) was empty after the run,
  and `git worktree list` showed no leaked isolation copies.
- Every record is `ok` except two `rename` records in `parallel_infrastructure` that are
  `skipped_in_baseline` (the test already failed in the unmodified isolated copy).

Judged (task 9.4) did not run: no `TYPESAFE_API_KEY` in this environment, so validation Gate 2
stays open per design D15.
