# Tasks — iterate-traceability-sweep-over-touched-changes

- [x] 1.1 Test: two-change pull request invokes the gate once per change and never reports ambiguous; a failing invocation blocks after visiting every id — **XS**
      **Spec scenarios**: gen-eval-framework *A pull request touching two change directories is evaluated once per change*
      **Dependencies**: None
- [x] 1.2 Replace the ambiguity block in the `pull_request` branch of `.github/workflows/ci.yml` with the per-change loop; sync `SWEEP_FRAGMENT` — **XS**
      **Dependencies**: 1.1
- [x] 1.3 Amend the `gen-eval-framework` requirement paragraph and scenario in this change's spec delta — **XS**
      **Dependencies**: None
- [x] Checkpoint: `skills/tests/validate-feature/test_ci_sweep_wiring.py` green; `openspec validate --strict` green
- [ ] 1.4 Archive via `/cleanup-feature` so the canonical spec merge lands — **XS**
      **Dependencies**: 1.2, 1.3
