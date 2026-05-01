# Tasks

Phase ordering is sequential at the phase level; within Phases 1 and 2, packages run in parallel. Within each package, test tasks precede the implementation tasks they verify.

## Phase 0 — Scaffold the convention (sequential, work package `wp-scaffold`)

- [ ] 0.1 Write tests for `install.sh` `references/` rsync handling
  - **Spec scenarios**: `skill-workflow.references-installed-alongside-skills`, `skill-workflow.references-not-auto-discovered`
  - **Design decisions**: D3 (references/ as sibling library)
  - **Dependencies**: None
  - Add `skills/tests/install_sh/test_references_rsync.py` with two cases: (a) rsync mode places `skills/references/*.md` under `.claude/skills/references/` and `.agents/skills/references/`; (b) `references/` is excluded from skill-discovery enumeration.

- [ ] 0.2 Create `skills/references/` library
  - **Spec scenarios**: `skill-workflow.references-installed-alongside-skills`
  - **Design decisions**: D3
  - **Dependencies**: 0.1
  - Create `skills/references/security-checklist.md`, `performance-checklist.md`, `accessibility-checklist.md`, `testing-patterns.md` (port content from external repo's references), and `skill-tail-template.md` (canonical tail-block template with placeholders + one filled example per section).

- [ ] 0.3 Write tests for `related:` frontmatter validation
  - **Spec scenarios**: `skill-workflow.related-key-parsed`, `skill-workflow.install-warns-on-unknown`, `skill-workflow.related-optional`
  - **Design decisions**: D4 (related: advisory)
  - **Dependencies**: None
  - Add `skills/tests/install_sh/test_related_validation.py`: a fixture skill with `related: [test-driven-development]` parses cleanly; a fixture with `related: [nonexistent]` produces a warning to stderr; a fixture with no `related:` key emits no warning.

- [ ] 0.4 Extend `skills/install.sh` for `references/` rsync and `related:` validation
  - **Spec scenarios**: All under "Shared References Library" and "`related:` Frontmatter Key" requirements
  - **Design decisions**: D3, D4
  - **Dependencies**: 0.1, 0.2, 0.3
  - Add a branch in the skill-discovery loop that handles directories without `SKILL.md` as flat-rsync sources (currently they would be silently skipped). Add a `validate_related_keys()` shell function that scans every installed `SKILL.md` for `related:` and warns when targets don't exist. Tests from 0.1 and 0.3 must pass.

- [ ] 0.5 Write tests for shared `conftest.py` invariant helpers
  - **Spec scenarios**: `skill-workflow.frontmatter-parse-failure-caught`, `skill-workflow.missing-tail-block-caught`, `skill-workflow.reference-cross-link-rot-caught`
  - **Design decisions**: D2 (content invariants over CI lint)
  - **Dependencies**: None
  - Add `skills/tests/_shared/test_conftest_helpers.py`: each of the 5 assertion helpers (`assert_frontmatter_parses`, `assert_required_keys_present`, `assert_references_resolve`, `assert_related_resolve`, `assert_tail_block_present`) is invoked against a deliberately-broken fixture skill and a known-good fixture skill, asserting fail/pass respectively.

- [ ] 0.6 Create `skills/tests/_shared/conftest.py` with the 5 assertion helpers
  - **Spec scenarios**: All under "Content-Invariant Test Framework for Skills"
  - **Design decisions**: D2
  - **Dependencies**: 0.5
  - Implement the 5 helpers with clear failure messages. Reuse `skills/shared/` Python utilities where applicable.

- [ ] 0.7 Update `skills/pyproject.toml` `[tool.pytest.ini_options]` `testpaths`
  - **Spec scenarios**: `skill-workflow.test-paths-registered`
  - **Dependencies**: 0.6
  - Append the 18 new test paths: 10 new methodology skills + 8 ADAPT-target test dirs (some already exist; only append the missing). Verify `cd skills && uv run pytest --collect-only` enumerates them.

- [ ] 0.8 Document tail-block convention in `docs/skills-workflow.md`
  - **Spec scenarios**: `skill-workflow.user-invocable-skill-ships-tail-block`, `skill-workflow.tail-block-template-available`
  - **Design decisions**: D2
  - **Dependencies**: 0.2 (template exists)
  - Add a top-level section "Skill Tail-Block Convention" with: which skills must include it (`user_invocable: true` only), the three section names and order, minimum content thresholds, link to `skills/references/skill-tail-template.md`, and the test invariant that enforces it.

## Phase 1 — New methodology skills (parallel work packages)

### Phase 1.1 — Testing & quality cluster (`wp-skills-testing-quality`)

- [ ] 1.1.1 Write tests for `test-driven-development` skill
  - **Spec scenarios**: `skill-workflow.new-methodology-skill-auto-discovered`, `skill-workflow.frontmatter-schema-preserved`, all tail-block scenarios
  - **Design decisions**: D5, D7
  - **Dependencies**: 0.6, 0.7
  - Add `skills/tests/test-driven-development/test_skill_md.py` invoking all 5 conftest helpers plus `assert_tail_block_present` (skill is `user_invocable: true`).

- [ ] 1.1.2 Author `skills/test-driven-development/SKILL.md`
  - **Spec scenarios**: `skill-workflow.new-methodology-skill-auto-discovered`
  - **Dependencies**: 1.1.1
  - Port from `addyosmani/agent-skills`: RED/GREEN/REFACTOR cycle, Prove-It Pattern, Beyonce Rule, 80/15/5 pyramid. Preserve npm/jest examples; add pytest equivalents alongside (e.g., `pytest -k`, `pytest --cov`, `pytest-asyncio`). Set `user_invocable: true`. Include tail block citing common rationalizations like "I'll write tests after." Test 1.1.1 must pass.

- [ ] 1.1.3 Write tests for `debugging-and-error-recovery` skill
  - **Spec scenarios**: Same as 1.1.1
  - **Dependencies**: 0.6, 0.7
  - Same pattern as 1.1.1.

- [ ] 1.1.4 Author `skills/debugging-and-error-recovery/SKILL.md`
  - **Spec scenarios**: `skill-workflow.new-methodology-skill-auto-discovered`
  - **Dependencies**: 1.1.3
  - Port the 6-step Stop-the-Line, reproduction decision tree, layer taxonomy. Preserve external commands; add Python equivalents (`python -m pdb`, `pytest --pdb`, `pytest -k`, `git bisect run`). Set `user_invocable: true`. Tail block.

- [ ] 1.1.5 Write tests for `browser-testing-with-devtools` skill
  - **Spec scenarios**: Same as 1.1.1; note `user_invocable: false` so tail block is *exempt*
  - **Dependencies**: 0.6, 0.7

- [ ] 1.1.6 Author `skills/browser-testing-with-devtools/SKILL.md`
  - **Spec scenarios**: `skill-workflow.new-methodology-skill-auto-discovered`, `skill-workflow.user-invocable-assignment-honored`
  - **Dependencies**: 1.1.5
  - Port DevTools MCP integration content with untrusted-data boundary discipline. Set `user_invocable: false`. Cross-reference from `validate-feature` smoke phase via `related:` key. No tail block required.

### Phase 1.2 — Knowledge cluster (`wp-skills-knowledge`)

- [ ] 1.2.1 Write tests for `context-engineering` skill — `user_invocable: false`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.2.2 Author `skills/context-engineering/SKILL.md`
  - **Spec scenarios**: `skill-workflow.user-invocable-assignment-honored`
  - **Dependencies**: 1.2.1
  - Port 5-level hierarchy + packing strategies + anti-patterns. Tie examples to coordinator/work-package/worktree patterns. Set `user_invocable: false`.

- [ ] 1.2.3 Write tests for `source-driven-development` skill — `user_invocable: false`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.2.4 Author `skills/source-driven-development/SKILL.md`
  - **Dependencies**: 1.2.3
  - Port DETECT→FETCH→IMPLEMENT→CITE flow. Wire to `WebFetch` patterns and to our `langfuse`/`neon-postgres`/`use-railway` skills as authority sources via `related:`. Set `user_invocable: false`.

### Phase 1.3 — Engineering practices cluster (`wp-skills-engineering`)

- [ ] 1.3.1 Write tests for `api-and-interface-design` skill — `user_invocable: true`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.3.2 Author `skills/api-and-interface-design/SKILL.md`
  - **Dependencies**: 1.3.1
  - Port Hyrum's Law, contract-first, discriminated unions, branded types, One-Version Rule. Add Python pydantic / dataclass / Protocol / Literal-discriminated-union equivalents alongside TS examples. Set `user_invocable: true`. Tail block.

- [ ] 1.3.3 Write tests for `frontend-ui-engineering` skill — `user_invocable: true`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.3.4 Author `skills/frontend-ui-engineering/SKILL.md`
  - **Dependencies**: 1.3.3
  - Port "AI aesthetic" anti-pattern table, state-management decision ladder, WCAG 2.1 AA. Reference `skills/references/accessibility-checklist.md` (created in 0.2). Set `user_invocable: true`. Tail block.

- [ ] 1.3.5 Write tests for `performance-optimization` skill — `user_invocable: true`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.3.6 Author `skills/performance-optimization/SKILL.md`
  - **Dependencies**: 1.3.5
  - Port MEASURE→IDENTIFY→FIX→VERIFY→GUARD with explicit Core Web Vitals budgets. Add backend perf section: p95 latency budgets, EXPLAIN ANALYZE for DB query plans, async profiling. Reference `skills/references/performance-checklist.md`. Set `user_invocable: true`. Tail block.

### Phase 1.4 — Governance cluster (`wp-skills-governance`)

- [ ] 1.4.1 Write tests for `deprecation-and-migration` skill — `user_invocable: true`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.4.2 Author `skills/deprecation-and-migration/SKILL.md`
  - **Dependencies**: 1.4.1
  - Port Churn Rule, Strangler/Adapter/FF migration patterns. Tie to OpenSpec deprecation workflow and `update-specs` / `cleanup-feature` via `related:`. Set `user_invocable: true`. Tail block.

- [ ] 1.4.3 Write tests for `documentation-and-adrs` skill — `user_invocable: true`
  - **Dependencies**: 0.6, 0.7

- [ ] 1.4.4 Author `skills/documentation-and-adrs/SKILL.md`
  - **Dependencies**: 1.4.3
  - Port ADR template + lifecycle (PROPOSED → ACCEPTED → SUPERSEDED). Reference our existing `docs/decisions/` directory. Set `user_invocable: true`. Tail block.

## Phase 2 — Adaptations + tail-block additions (parallel work packages)

### Phase 2.1 — Lifecycle skills cluster (`wp-adapt-lifecycle`)

- [ ] 2.1.1 Write/extend tests for `implement-feature` adaptation
  - **Spec scenarios**: `skill-workflow.implement-feature-contains-scope-discipline-template`, `skill-workflow.user-invocable-skill-ships-tail-block`
  - **Design decisions**: D6 (combined edit), D7 (TDD)
  - **Dependencies**: 0.6, 0.7
  - Add `skills/tests/implement-feature/test_skill_md.py` (or extend existing) asserting: `Rules 0–5` framing section present, `NOTICED BUT NOT TOUCHING:` template literal present, tail block sections present and ordered.

- [ ] 2.1.2 Adapt `skills/implement-feature/SKILL.md`
  - **Spec scenarios**: `skill-workflow.implement-feature-contains-scope-discipline-template`
  - **Dependencies**: 2.1.1
  - Add Rules 0–5 framing (Simplicity / Scope Discipline / One Thing / Compilable / Feature Flags / Safe Defaults / Rollback) as a top-level section. Inject `NOTICED BUT NOT TOUCHING:` template into the work-package execution prompt. Add tail block. Test 2.1.1 passes.

- [ ] 2.1.3 Write/extend tests for `plan-feature` adaptation
  - **Spec scenarios**: `skill-workflow.user-invocable-skill-ships-tail-block`
  - **Dependencies**: 0.6, 0.7

- [ ] 2.1.4 Adapt `skills/plan-feature/SKILL.md`
  - **Dependencies**: 2.1.3
  - Add task-sizing table (XS/S/M/L/XL with line-count or task-count guidance), the "title contains 'and' → split signal" heuristic, and explicit checkpoint cadence guidance (every 2–3 tasks). Add tail block.

- [ ] 2.1.5 Write/extend tests for `simplify` adaptation (also tail-block pilot)
  - **Spec scenarios**: `skill-workflow.user-invocable-skill-ships-tail-block`
  - **Dependencies**: 0.6, 0.7

- [ ] 2.1.6 Adapt `skills/simplify/SKILL.md`
  - **Dependencies**: 2.1.5
  - Add Chesterton's Fence pre-check questions, "Rule of 500" trigger (>500 lines → automate the simplification check), pattern catalog (deep nesting, long functions, nested ternaries, boolean flags, generic names, premature abstractions). Add tail block.

### Phase 2.2 — Review skills cluster (`wp-adapt-review`)

- [ ] 2.2.1 Write tests for `review-findings.schema.json` extension
  - **Spec scenarios**: All under "Review Findings Schema Extension"
  - **Dependencies**: None
  - Add `skills/tests/parallel-infrastructure/test_review_findings_schema.py`: a finding with `axis: "correctness"` and `severity: "critical"` validates; a finding without `axis` fails; pre-existing required fields still required; existing enum values still valid.

- [ ] 2.2.2 Extend `review-findings.schema.json` with axis and severity fields
  - **Spec scenarios**: All under "Review Findings Schema Extension"
  - **Dependencies**: 2.2.1
  - Locate the schema file (under `skills/parallel-infrastructure/schemas/` or wherever it lives — may need to confirm during implementation). Add `axis` enum (correctness, readability, architecture, security, performance) and `severity` enum (critical, nit, optional, fyi, none). Mark both required.

- [ ] 2.2.3 Write tests for `parallel-review-plan` and `parallel-review-implementation` adaptations
  - **Spec scenarios**: `skill-workflow.user-invocable-skill-ships-tail-block`
  - **Dependencies**: 0.6, 0.7, 2.2.2

- [ ] 2.2.4 Adapt both parallel-review skills
  - **Dependencies**: 2.2.3
  - Update both SKILL.md files to: (a) instruct reviewer agents to categorize findings by 5-axis schema, (b) instruct reviewer agents to prefix each finding with severity, (c) add tail block.

- [ ] 2.2.5 Write tests for `security-review` adaptation
  - **Dependencies**: 0.6, 0.7

- [ ] 2.2.6 Adapt `skills/security-review/SKILL.md`
  - **Dependencies**: 2.2.5
  - Add a "Preventive Mode" top-level section documenting the three-tier boundary system (Always / Ask first / Never) and OWASP Top 10 prevention rules. Reference `skills/references/security-checklist.md`. Preserve the existing scanner-runner mode untouched. Add tail block.

- [ ] 2.2.7 Write tests for `bug-scrub` and `tech-debt-analysis` tail-block additions (pilots)
  - **Dependencies**: 0.6, 0.7

- [ ] 2.2.8 Add tail block to `bug-scrub` and `tech-debt-analysis`
  - **Dependencies**: 2.2.7
  - Pure tail-block addition; no other content changes. Use the canonical template from `skills/references/skill-tail-template.md`.

### Phase 2.3 — Sync-points and meta cluster (`wp-adapt-sync`)

- [ ] 2.3.1 Write tests for `cleanup-feature` adaptation
  - **Dependencies**: 0.6, 0.7

- [ ] 2.3.2 Adapt `skills/cleanup-feature/SKILL.md`
  - **Dependencies**: 2.3.1
  - Add a "Staged Rollout" phase with the 5%→25%→50%→100% sequence and rollback triggers (errors >2× baseline, p95 +50%, integrity, security). Add a pre-launch checklist sub-phase before the merge step. Add tail block.

- [ ] 2.3.3 Write tests for `merge-pull-requests` adaptation
  - **Dependencies**: 0.6, 0.7

- [ ] 2.3.4 Adapt `skills/merge-pull-requests/SKILL.md`
  - **Dependencies**: 2.3.3
  - Add Save Point Pattern and Change Summary template (CHANGES MADE / DIDN'T TOUCH / CONCERNS). Add tail block.

- [ ] 2.3.5 Write tests for `explore-feature` adaptation
  - **Dependencies**: 0.6, 0.7

- [ ] 2.3.6 Adapt `skills/explore-feature/SKILL.md`
  - **Dependencies**: 2.3.5
  - Add "How Might We" reframing prompt template, the 8 ideation lenses, and an explicit `NOT DOING:` list as a discovery output. Add tail block.

- [ ] 2.3.7 Light pull into `CLAUDE.md`
  - **Dependencies**: None
  - Add a brief "Save Point Pattern" and "Change Summary template" subsection under the existing Git Conventions section. Cross-reference `merge-pull-requests` skill.

## Phase 3 — Integration and validation (sequential, `wp-integration`)

- [ ] 3.1 Populate `related:` cross-references across all 21 affected skills
  - **Spec scenarios**: `skill-workflow.related-key-parsed`
  - **Design decisions**: D4
  - **Dependencies**: All Phase 1 and Phase 2 tasks
  - Add `related:` keys connecting kindred skills (e.g., `test-driven-development` ↔ `debugging-and-error-recovery`; `frontend-ui-engineering` ↔ `browser-testing-with-devtools`; `deprecation-and-migration` ↔ `update-specs`). Validate with install.sh.

- [ ] 3.2 Run full `skills/install.sh --mode rsync --deps none --python-tools none` dry run
  - **Dependencies**: 3.1
  - Verify all 10 new skills install, all 8 adapted skills install, `references/` is rsynced, no warnings on unknown `related:` targets.

- [ ] 3.3 Run `cd skills && uv run pytest`
  - **Dependencies**: 3.1
  - Full test suite. All 18 new test directories collected. All content invariants pass. No regressions in pre-existing tests.

- [ ] 3.4 Run `openspec validate add-engineering-methodology-skills --strict`
  - **Dependencies**: All artifacts complete
  - Spec deltas validate against schema. Strict mode enforces canonical headers and scenarios.

- [ ] 3.5 Update `docs/lessons-learned.md` with the methodology-layer addition
  - **Dependencies**: 3.2, 3.3
  - One short section: "Adopted external methodology skills (10) and folded patterns into 8 existing skills. Convention: tail block on user-invocable skills enforced by content-invariant tests at `skills/tests/_shared/conftest.py`."

- [ ] 3.6 Update `README.md` and slash-command catalogue (if maintained) with the 7 new user-invocable skills
  - **Dependencies**: 3.2

- [ ] 3.7 Verify orchestrator integration points still function
  - **Dependencies**: 3.2, 3.3
  - Smoke-test `plan-feature` Step 6 (TDD ordering reference) and `validate-feature` smoke phase (browser-testing-with-devtools reference) by reading the SKILL.md outputs to confirm `related:` references resolve and no broken cross-links.
