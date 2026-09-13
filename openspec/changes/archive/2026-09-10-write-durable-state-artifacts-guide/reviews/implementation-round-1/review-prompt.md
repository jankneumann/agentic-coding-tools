Review the committed implementation of OpenSpec change `write-durable-state-artifacts-guide`, package `wp-state-artifacts-docs`, in read-only mode.

The feature branch is intentionally stacked on `origin/openspec/roadmap-roadmap-supervisor-orchestration` at `4f794962`. Commit `34d8c330` merges current `origin/main` as an approved prerequisite; do not report files whose only provenance is that main import as package scope violations. Review the package-authored implementation and task 3.2 integration in these surfaces:

- `docs/guides/state-artifacts.md`
- `docs/guides/documentation.md`
- `docs/decisions/skill-workflow.md` (generated)
- `skills/{autopilot,autopilot-roadmap,session-log,supervise,implement-feature,validate-feature}/SKILL.md`
- `skills/pyproject.toml`
- `skills/tests/state-artifacts/test_state_artifacts_guide.py`
- `openspec/changes/write-durable-state-artifacts-guide/**`

Read `proposal.md`, `design.md`, `tasks.md`, `specs/skill-workflow/spec.md`, `work-packages.yaml`, `change-context.md`, and `impl-findings.md`. Inspect commit history from `4f794962` through HEAD and the exact task-3.2 changes in merge commit `34d8c330`. The imported helper/guard are current-main commits `c12e5389`, `4dd9a852`, and `8efb87d1`.

Verification already observed: 719 focused state-artifact/path tests; 71 coordinator merge tests; 73 decision/bridge tests; 118 supervisor workflow tests; 735 context-engineering tests; 23 archetype tests; ruff on the changed Python test; strict OpenSpec 90/90. Independently verify relevant claims as needed.

Context checkpoint caveat: base-relative `validate_context_impact.py ... --base 4f794962` is VALID/rationalized. The per-package checkpoint command degrades because `checkpoint.load_package()` drops the feature-level `contracts` block and therefore falsely labels its approved API rationale `spurious_rationale`. This shared-infrastructure gap is documented in `impl-findings.md`; do not treat the absence of a fresh checkpoint as a hidden pass.

Review all eight axes: correctness, readability, architecture, security, performance, observability, resilience, compatibility. Verify package scope, requirements, tests, archive stability, generated/mirror semantics, and rollback safety. Return ONLY a single JSON document conforming to `openspec/schemas/review-findings.schema.json`, with `review_type: implementation`, `target: wp-state-artifacts-docs`, your actual reviewer vendor, and `package_id: wp-state-artifacts-docs` on every finding. Every description must start with the severity prefix matching its enum (`Critical:`, `Nit:`, `Optional:`, `FYI:`, or `none:`). Critical findings must use disposition `fix` or `escalate`; security findings must never use `accept`; positive observations use severity `none` and disposition `accept`. Include file paths and line ranges for file-specific findings. For a clean review, emit substantive positive observations across at least two axes rather than an empty findings list.
