# Implementation review remediation

**PR:** https://github.com/jankneumann/agentic-coding-tools/pull/346  
**Mode:** whole-branch  
**Vendors:** claude_code (12), codex (7), grok (10); antigravity timeout; pi invalid JSON  
**Consensus:** 7 confirmed / 12 unconfirmed / 6 blocking at synthesis time  

Self-review findings in `review-findings-impl.json` plus multi-vendor consensus drove the fix commit.

## Fixed (blocking / confirmed)

| Finding | Fix |
|---|---|
| Deleted test files invisible to contract scanner | Track path from `---` when `+++` is `/dev/null` |
| HEAD dual-run used dirty live tree | Both baseline and HEAD run in detached worktrees |
| Stash-fallback docstring lie | Docstring/docs match worktree-only implementation |
| Worktree missing `.venv` / tooling | Symlink `.venv`, `node_modules`, `skills/.venv` from main repo |
| Misleading “baseline suite red” only note | Notes now mention toolchain/path diagnosis |
| Silent 0-churn on dirty tree (scope) | Include working tree + untracked in scope measure when head is live+dirty |
| Assertion path coverage (Go/Rust) | `_test.go` / `_test.rs` paths; `assert_eq!`, gtest, Go `t.Errorf`, matcher lines |
| Docstring vs pure `+assert` strictness | Docstring states `--base` after characterization; pure `+assert` fails in-range |
| Weak content invariants | Stronger manual-only + `redundant intermediate` tests |
| SKILL.md pytest example | Prefer `skills/.venv/bin/python -m pytest` |

## Accepted / deferred

| Finding | Disposition |
|---|---|
| `shell=True` for trusted `--test-cmd` | accept (documented) |
| Multiline expectation bodies still imperfect | accept residual risk; expanded matchers reduce gap |
| `--skip-baseline-run` incomplete dual-run | accept with `dual_run_complete: false` in report |
| No full Phase C automated tests for tech-debt/implement text | accept; content is short routing prose |
| Optional subprocess timeout | shipped as `--timeout` |
| Quoted unusual git paths | partial (strip simple quotes) |

## Re-verify

```bash
skills/.venv/bin/python -m pytest skills/tests/simplify/ -q   # 28 passed
```
