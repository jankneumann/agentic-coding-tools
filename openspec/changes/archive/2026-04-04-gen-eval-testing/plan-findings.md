# Plan Findings: gen-eval-testing

## Iteration 1

### Analysis Method
Four parallel analysis agents reviewing: completeness, clarity/consistency, feasibility/parallelizability, testability.

### Findings Addressed (24 at medium+ threshold)

| # | Type | Criticality | Description | Fix Applied |
|---|------|-------------|-------------|-------------|
| F1 | consistency | CRITICAL | Mode naming: `api-fallback` in spec vs `sdk-only` in design | Standardized to `sdk-only` everywhere (spec, design, tasks, work-packages) |
| F2 | consistency | CRITICAL | Generator files: work-packages referenced `llm_generator.py` but tasks said `cli_generator.py`/`sdk_generator.py` | Fixed work-packages to reference `cli_generator.py`, `sdk_generator.py`, `hybrid_generator.py` |
| F3 | completeness | CRITICAL | T3.9b (hybrid_generator) missing from work-packages | Added T3.10 (was T3.9b) to wp-generator tasks list |
| F4 | parallelizability | CRITICAL | 81 scenario templates in one wp-scenarios package — bottleneck | Split into wp-scenarios-critical (34), wp-scenarios-standard (27), wp-scenarios-secondary (20) |
| F5 | completeness | CRITICAL | Missing spec requirements for LLM judgment, rate-limit detection, scenario validation | Added REQ-EVAL-06 (LLM judgment), expanded REQ-GEN-07 (rate-limit patterns), expanded REQ-GEN-03 (Pydantic validation) |
| F6 | testability | CRITICAL | Success criteria subjective — "at least 1 real bug" | Rewrote all 6 success criteria with measurable definitions |
| F7 | consistency | HIGH | Scenario count: design claimed 80, tasks described 72 | Recounted: 81 total (38 success + 43 failure/edge). Updated design table with success/failure split. |
| F8 | consistency | HIGH | Budget terminology: `APIBudget` class vs `sdk_budget_usd` field | Renamed `APIBudget` → `SDKBudget` throughout design |
| F9 | clarity | HIGH | Backend class role confusion | Added "Module Organization" table to design clarifying file→class mapping |
| F10 | parallelizability | HIGH | wp-entry-points missing dependency on wp-generator | Added wp-generator to wp-entry-points dependencies |
| F11 | parallelizability | HIGH | wp-feedback priority 3 but blocks priority-2 wp-orchestrator | Changed wp-feedback priority to 2 |
| F12 | parallelizability | HIGH | Test fixtures collision across packages | Designated wp-foundation as owner of conftest.py; other packages list it as read_allow |
| F13 | completeness | HIGH | Missing spec for cleanup failure, JSONPath, health check retries, step timeout | Added REQ-SCN-03 (JSONPath), REQ-SCN-04 (cleanup failure=warning), REQ-SCN-07 (step timeout), REQ-ORC-01 (health retry), REQ-DESC-02 (health timeout) |
| F14 | testability | HIGH | No failure/edge-case scenarios in template categories | Added REQ-SCN-06 requiring both success+failure paths; updated all template task descriptions with explicit success/failure counts |
| F15 | feasibility | HIGH | T8.1 descriptor for 105+ interfaces too large | Split into T8.1a (HTTP endpoints) + T8.1b (MCP/CLI) + T8.3 (docker-compose verification) |
| F16 | completeness | MEDIUM | No coverage metric formula | Added formula to REQ-ORC-04 and REQ-DOG-03: unique interfaces tested / total × 100 |
| F17 | completeness | MEDIUM | No seed data management requirement | Added seed data step to REQ-ORC-01 lifecycle |
| F18 | completeness | MEDIUM | No scenario execution timeout requirement | Added REQ-SCN-07: per-step configurable timeout (default 30s) |
| F19 | clarity | MEDIUM | "appropriate transport client" vague in REQ-EVAL-01 | Changed to "transport client specified by each step's `transport` field" + added REQ-TRN-05 (explicit selection) |
| F20 | consistency | MEDIUM | Generator module organization unclear | Added Module Organization table to design with file→class mapping |
| F21 | feasibility | MEDIUM | T2.7 browser stub is dead code | Removed browser stub task; renumbered T2.7 to tests |
| F22 | feasibility | MEDIUM | T1.6 too trivial as standalone | Merged T1.6 (pyproject.toml) into T1.2 (config) |
| F23 | testability | MEDIUM | Integration tests only cover 3/12 categories | Expanded to 6 integration tests: lock-lifecycle, cross-interface, auth-boundary, work-queue, full orchestrator, adaptive fallback |
| F24 | consistency | MEDIUM | First-iteration feedback loop unclear | Added explicit note: "feedback=None on first iteration" in design and REQ-FBK-02 |

### Remaining Findings (below threshold — LOW)
- Scenario template categories unevenly distributed (17 in one sub-package vs 34 in another) — acceptable tradeoff for logical grouping
- write_allow scope enforcement is advisory only — existing parallel-infrastructure scope validator handles this
- T12.1 CI job triggering strategy — specified in tasks: "triggered on agent-coordinator/ changes"
- REQ-EVAL-05 "skeptical" is vague — replaced with concrete independence definition ("no access to generator internals")
- REQ-GEN-04 vs REQ-GEN-08 mode overlap — clarified: three modes, cli-augmented includes adaptive fallback behavior
