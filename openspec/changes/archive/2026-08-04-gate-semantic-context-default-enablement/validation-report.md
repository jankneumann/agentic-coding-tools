# Validation Report: gate-semantic-context-default-enablement

**Date**: 2026-08-03 02:40:58 UTC
**Commit**: 2864bbfc
**Branch**: openspec/gate-semantic-context-default-enablement

## Phase Results

✓ Spec: 16/16 requirements across 3 capability deltas mapped to concrete tests/artifacts. Actual scenario count is 47 (semantic-context-evaluation 30, code-search 11, skill-workflow 6), not the 42 in the orchestrator's addendum — see note below. No requirement found with zero evidence.
✓ Evidence: `packages/context-eval` 380 passed / 0 skipped (exact match). `skills/tests/context-engineering/` 735 passed (exact match). `ruff check src/ tests/` clean. `mypy src/context_eval/ --strict` clean, 17 source files. `make semantic-enablement-gate` exit 0. `openspec validate gate-semantic-context-default-enablement --strict` valid at both local (1.1.1) and CI-matching (npx @fission-ai/openspec@latest, 1.7.0). Both CI jobs (`context-eval`, `semantic-enablement-gate`) present and correctly wired in `.github/workflows/ci.yml`. `docs/evaluation/semantic-context/report.json`: 0 schema errors against `openspec/contracts/semantic-context-evaluation/schemas/context-eval-report.schema.json`, verdict `fail` with `fail_reasons: [unmeasured, denominator_mismatch, index_tier_insufficient]` (D11's correct recorded outcome, not a defect), `harness.fingerprint` recomputed from HEAD source (`dc25e1ce...`) matches the recorded value exactly. All three schema pairs (report/case/corpus) byte-identical via `cmp`. `INJECTION_DEFAULT_ENABLED = False` confirmed at `skills/context-engineering/scripts/semantic_context.py:571`.
○ Deploy: Skipped — this change deploys nothing (no database, embedder, coordinator, or HTTP surface).
○ Smoke: Skipped — no service to probe; nothing here reaches a network boundary.
✓ Security: Two in-scope surfaces reviewed (JSON I/O, git shell-out). No shell=True anywhere; every subprocess call uses list-form argv with no string interpolation, so shell injection is not possible. See details below.
○ E2E: Skipped — no deployed behavior to drive with a browser or live service.

## Pre-existing condition confirmed, not this change's

`make context-drift-gate` exits 2 on this tree. Confirmed by direct reproduction:
- `blocking_drift`: `decisions.timeline` on `docs/decisions/skill-workflow.md`, owner `skills/explore-feature/scripts/archive_index.py (make decisions)` — this is issue #157 per project memory (docs/decisions writer-drift).
- `informational_drift`: `openspec.projection` naming ~40 active spec files including `openspec/specs/skill-workflow/spec.md`, `openspec/specs/code-search/spec.md`.

Confirmed independently, not taken on trust:
- `git diff --stat origin/main..HEAD -- docs/decisions/ openspec/specs/code-search/spec.md` is empty — this branch touches neither path.
- 9 active (unarchived) changes declare a `specs/skill-workflow/spec.md` delta (`fix-compact-hook-phase-boundary-detection`, `fix-autopilot-archetype-and-apply-outcome`, `add-branch-local-context-checkpoints`, `add-product-management-skills`, `inject-scoped-semantic-context-into-coding-jobs`, `gate-semantic-context-default-enablement`, `factory-missions-architecture-alignment`, `add-visual-plan-review`, `add-update-documentation-skill`), matching the addendum's claim.

The addendum's claim is confirmed correct: this drift is pre-existing, structural, and not attributable to this change.

## Security review (the two named surfaces)

**Shell injection in git reachability calls**: not present. `packages/context-eval/src/context_eval/enablement_gate.py:568` runs `["git", "-C", str(repository_root), "merge-base", "--is-ancestor", revision, "HEAD"]` via `subprocess.run(..., check=False)` with no `shell=True` — list-form argv, no shell ever parses the string. `revision` originates from the report body (`index.indexed_revision`), so a forged report could pass a hostile string, but list-form argv means it can only ever be interpreted as a single positional git argument, not shell syntax. `packages/context-eval/src/context_eval/producers/exact_search.py` similarly shells out to `rg` (list-form, `--` before the path argument) and `git ls-files -z` (no untrusted input) — both clean.

**Path traversal in report/schema resolution**: no exploitable instance for the actual attack surface (CLI args from a human/CI, hardcoded relative constants `REPORT_RELATIVE`/`CORPUS_RELATIVE`/`SEMANTIC_CONTEXT_RELATIVE` in `enablement_gate.py`). One observation, not a finding: `context_eval/producers/semantic_runtime.py:265` (`recorded_response()`) does `Path(corpus_root) / case.recorded_response.path` without normalizing `..` — if `case.recorded_response.path` in a corpus YAML were adversarial, this would read outside `corpus_root`. This requires repo-write access to the corpus fixtures, which already implies arbitrary code execution in this package, so it adds no real privilege boundary. Consistent with the documented, correctly-scoped-elsewhere limitation that a hand-built coherent forged report/corpus can defeat the harness's own checks.

No other file-write path was found; the harness only ever writes the report JSON to the fixed durable path or a caller-supplied `tmp_path` in tests.

## Note on the addendum's scenario count

The orchestrator addendum states "42 WHEN/THEN scenarios (semantic-context-evaluation 29, code-search 7, skill-workflow 6)". Direct `grep -c '^#### Scenario:'` against the three spec delta files gives semantic-context-evaluation 30 (11 requirements), code-search 11 (3 requirements), skill-workflow 6 (2 requirements) — 47 total, 16 requirements. The requirement count (16) matches; the scenario count does not. This does not change the validation outcome — every scenario found maps to concrete evidence — but is reported as a correction per instruction to verify rather than trust.

## Result

**PASS** — Ready for `/cleanup-feature gate-semantic-context-default-enablement`. No spec requirement found without evidence; all expected-results checks reproduced exactly; the one non-green gate (`context-drift-gate`) is a confirmed pre-existing condition outside this change's scope.
