# Post-CI isolation review dispositions

- Quorum: 3/5 configured vendors returned valid findings (Codex Sol, Grok, Pi).
- Consensus: 0 blocking findings; 12 advisory findings.
- Pi finding 5: fixed by documenting the two suite-key forms in `_suite_for`.
- Grok finding 6: fixed by adding a regression guard that the skills-root conftest owns both pytest isolation hooks.
- Grok findings 3 and 7: accepted. The explicit dependency edge is intentional and the manually maintained dependency map is existing architecture; both minimal reproducers and the full infrastructure suite pass.
- Remaining findings are positive observations or scope confirmations and require no change.

Post-fix verification: isolation regressions 4 passed; infrastructure suite 4,775 passed and 13 skipped; Ruff passed; work-package validation passed; strict OpenSpec validation passed 90/90.
