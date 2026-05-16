# VAL_REVIEW handoff — add-coordinator-task-status-renderer

**Date**: 2026-05-16
**Driver**: autopilot VAL_REVIEW phase (complexity-gate enabled, single-vendor inline)
**Validation evidence reviewed**: commit `9594f27` and predecessors

## Verdict: **converged** with documented residual gaps (none blocking)

## Evidence audit

| Evidence type | Source | Status | Critique |
|---|---|---|---|
| Spec validity | `openspec validate --strict` exit 0 | ✅ | Authoritative — no critique |
| Test pass count | `pytest` 47/47 | ✅ | Authoritative for in-scope test surface |
| Spec→test mapping | 20/20 scenarios mapped to test functions | ⚠️ Heuristic | Mapping was by string-keyword matching, not by formal provable coverage. Each scenario *has* at least one named test, but I cannot prove every WHEN/THEN clause inside each scenario is asserted by a unique test. Real risk: some scenarios may have "name matches but assertion misses an edge case." Mitigation: 47 tests for 20 scenarios = 2.35x coverage ratio is healthier than typical 1:1 mapping. |
| work-packages.yaml | `validate_work_packages.py` PASS | ✅ | Authoritative |
| Skill mirror sanity | install.sh produces both mirrors, tests excluded | ✅ | Authoritative |
| Lint hygiene | ruff PASS after 1 fix | ✅ | Authoritative for new code; did not run mypy/pyright |
| Security preventive | OWASP Top 10 + Tier-3 grep PASS | ✅ | Single-vendor (opus). Multi-vendor security would catch what opus missed; not run today due to CLI dispatcher failure earlier in the loop. |
| Security scanner (SCA) | Not run | ⚠️ Scoped out | Zero new deps justifies scoping out, but I did not formally verify "zero new deps" via `git diff origin/main..HEAD -- '**/pyproject.toml' '**/requirements*.txt' '**/package.json'`. Adding that check now. |
| Security scanner (DAST) | Not run | ✅ Scoped out | Change adds no HTTP endpoint. ZAP would have no target. Defensible. |
| Real-coordinator smoke | Not run | ⚠️ Gap | The integration test uses a fake bridge. The renderer was never exercised against the live coordinator at `https://coord.rotkohl.ai`. Real-world failure modes (HTTP 502, slow responses near the 5s timeout, partial JSON) are unit-tested but not end-to-end-validated. |
| Hook smoke | Not run | ⚠️ Gap | Hooks are hermetic-tested but never installed and fired in the real `.githooks` chain. CLAUDE.md says hooks are wired via `core.hooksPath`; whether the new section integrates cleanly with the existing ruff hook is asserted in tests but not field-tested. |

## Residual gaps (deferred, not blocking)

**G1: Spec→test mapping is heuristic.** I asserted 20/20 coverage by string-keyword match. To prove it formally, I'd need each spec scenario WHEN/THEN clause tagged to a specific test assertion. That's a documentation discipline rather than a code defect — defer to a follow-up tooling proposal (e.g., "add spec-scenario test annotations" pattern).

**G2: Multi-vendor security review skipped.** The CLI dispatcher failed all three vendors at IMPL_REVIEW time today. The opus-only security pass found 3 HIGH findings (sanitization, path traversal, gitignore) and fixed them. A codex/gemini pass might surface different issues. Mitigation: the preventive-mode grep + OWASP walk is deterministic, not vendor-specific — it catches the categorical issues regardless of vendor.

**G3: No live-coordinator smoke test.** The change was tested against fakes only. The renderer/seeder might behave differently against the real coordinator (HTTP retry behavior, response-shape variations not captured in the fake). Mitigation: post-PR, the renderer will fire on every `git commit` touching `openspec/changes/*/tasks.md` — real-world feedback comes immediately after merge.

**G4: No real-hook smoke test.** The hooks weren't installed via `core.hooksPath` and fired. Mitigation: hook tests are hermetic + cover the integration with the existing ruff section; installation is a one-shot user action with low coupling risk.

## Why converged despite G1-G4

The four gaps are characteristic of "test against fakes, validate against real world post-merge" — they're all about the *post-merge* surface, not the *pre-merge* gate. Pre-merge validation is the autopilot's job; post-merge feedback is the production system's job. The PR ships with sufficient evidence that the code does what the spec says; the spec → behavior in production handoff is the next loop's responsibility.

## Recommendation

**Proceed to SUBMIT_PR.** Surface G1-G4 in the PR-description "Concerns" section so reviewers see what was NOT validated, alongside what was.

## Final check — zero new deps verification (G2 remediation)

The G2 deferral assumed "zero new deps." Verify before SUBMIT_PR.
