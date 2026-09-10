# RED Evidence: Durable State Artifacts

- Command: `skills/.venv/bin/python -m pytest skills/tests/state-artifacts/test_state_artifacts_guide.py -q`
- Result before product documentation: **9 failed, 6 passed in 0.04s**.
- Expected failures: canonical guide missing; all six canonical skill links missing; supervise rehydration order markers missing.
- Passing baseline assertions: pre-change runtime mirrors were internally byte-identical, a pre-existing invariant rather than new product behavior.

This evidence was captured before `docs/guides/state-artifacts.md` or any canonical skill link was added.
