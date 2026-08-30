# Tasks — iterate-traceability-sweep-over-touched-changes

- [x] 1.1 Test: two-change pull request invokes the gate once per change and never reports ambiguous; a failing invocation blocks after visiting every id — **XS**
      **Spec scenarios**: gen-eval-framework *A pull request touching two change directories is evaluated once per change*
      **Dependencies**: None
- [x] 1.2 Replace the ambiguity block in the `pull_request` branch of `.github/workflows/ci.yml` with the per-change loop; sync `SWEEP_FRAGMENT` — **XS**
      **Dependencies**: 1.1
- [x] 1.3 Amend the `gen-eval-framework` requirement paragraph and scenario in this change's spec delta — **XS**
      **Dependencies**: None
- [x] Checkpoint: `skills/tests/validate-feature/test_ci_sweep_wiring.py` green; `openspec validate --strict` green
- [ ] 1.4 Archive so the canonical spec merge lands — **BLOCKED** on an OpenSpec
      limitation, issue #439 — **XS**
      **Dependencies**: 1.2, 1.3

      `openspec archive` refuses this change:

      > gen-eval-framework MODIFIED failed ... current spec contains scenario(s) not
      > present in the modified block: "A pull request touching two change directories
      > fails as ambiguous". Refresh the change spec before archiving to avoid dropping
      > scenarios.

      That scenario is retired on purpose — the behaviour it asserts is exactly what
      this change removes. A `MODIFIED` block must be a superset of the current
      requirement's scenarios, so OpenSpec 1.7.0 cannot express "retire one scenario
      from a requirement that otherwise stays". The two workarounds are both wrong:
      re-listing the scenario would leave the canonical spec asserting a rule the code
      no longer has, and `REMOVED` + `ADDED` of the same requirement is rejected
      ("Requirement present in both ADDED and REMOVED"). Renaming the requirement to
      dodge that would orphan the `gen-eval-framework.the-full-sweep-blocks-opted-in-\
      surfaces-and-reports-the-rest` traceability citation.

      Until the tooling can express it, this change stays active and the canonical
      spec keeps the retired scenario. The delta here is the accurate statement of
      intent. `--skip-specs` is deliberately NOT used: it would archive the change
      while silently leaving the stale scenario with no record of why.
