# Validation Report: gen-eval-testing

**Date**: 2026-03-31
**Commit**: 7f31316
**Branch**: claude/generator-evaluator-testing-fqJlS
**Commits ahead of main**: 17

---

## Phase Results

### ✓ Unit Tests: PASS
- **322 passed**, 1 warning, 0 failures
- Runtime: ~5.6s
- Coverage: 15+ test files across all modules (config, descriptor, models, clients, generators, evaluator, feedback, orchestrator, reports, integration)

### ✓ Lint: PASS
- `ruff check evaluation/gen_eval/` — All checks passed
- No formatting issues

### ✓ Scenario Templates: PASS
- **81 YAML templates** across 12 categories
- Categories: lock-lifecycle (8), auth-boundary (8), cross-interface (10), multi-agent (8), work-queue (10), guardrails (5), memory-crud (6), policy-engine (6), handoffs (4), audit-trail (4), feature-registry (6), merge-queue (6)

### ✓ Dogfood Descriptor: PASS
- **114 interfaces** mapped (38 HTTP + 39 MCP + 37 CLI)
- All agent-coordinator services covered

### ✗ Template Coverage: FAIL
- **Measured**: 24.6% of interfaces exercised by scenario templates
- **Threshold**: 80% (REQ-DOG-03)
- **Root cause**: Scenario `interfaces` fields use transport-level names (e.g., `"http"`) instead of endpoint-specific identifiers (e.g., `"POST /locks/acquire"`). The coverage computation in `_build_report` compares `interfaces_tested` against `all_interfaces()`, which returns endpoint-specific names. The templates never match.
- **Fix complexity**: Medium — update 81 scenario YAML files to use endpoint-specific interface names, or adjust coverage computation to map transport names to endpoints.

### ○ Deploy: SKIPPED
- No Docker environment available in validation context

### ○ Smoke: SKIPPED
- Depends on Deploy phase

### ○ Security: SKIPPED
- No live services to scan

### ○ E2E: SKIPPED
- No Playwright/live services available

### ○ Architecture: SKIPPED
- No architecture graph artifact available

### ○ Logs: SKIPPED
- No log file (Deploy skipped)

### ○ CI/CD: SKIPPED
- No PR created yet

---

## Spec Compliance

### Passed (27)

| Requirement | Description |
|-------------|-------------|
| REQ-GEN-01 | Template-based scenario generation with Jinja2 expansion |
| REQ-GEN-02 | LLM-augmented generation via CLI backend |
| REQ-GEN-03 | SDK backend for LLM generation |
| REQ-GEN-04 | Hybrid generator composing template + LLM |
| REQ-GEN-05 | Focus-area filtering in generators |
| REQ-EVAL-01 | Multi-transport evaluation (HTTP, MCP, CLI, DB, Wait) |
| REQ-EVAL-02 | JSON path assertions on step results |
| REQ-EVAL-03 | Cross-interface mismatch detection → fail verdict |
| REQ-EVAL-04 | Cleanup steps always run, status preserved |
| REQ-EVAL-05 | Variable interpolation across steps |
| REQ-BDG-01 | Time budget with wall-clock tracking |
| REQ-BDG-02 | SDK cost budget with can_afford checks |
| REQ-BDG-03 | Budget-aware orchestration loop |
| REQ-BDG-04 | Three-tier prioritization (changed/critical/full) |
| REQ-BDG-05 | Max expansions cap on template parameters |
| REQ-CFG-01 | GenEvalConfig with all required fields |
| REQ-CFG-02 | CLI-first execution mode selection |
| REQ-CFG-03 | Adaptive backend with CLI→SDK fallback |
| REQ-RPT-01 | Markdown report generation |
| REQ-RPT-02 | JSON report generation |
| REQ-RPT-03 | Per-interface and per-category aggregation |
| REQ-RPT-04 | Unevaluated interface tracking |
| REQ-FBK-01 | Feedback synthesis from verdicts |
| REQ-FBK-02 | Under-tested category detection |
| REQ-FBK-03 | Near-miss detection (pass with low confidence) |
| REQ-SCN-01 | YAML scenario format with all required fields |
| REQ-DOG-01 | Agent-coordinator interface descriptor (114 interfaces) |

### Failed (2)

| Requirement | Description | Issue |
|-------------|-------------|-------|
| REQ-DOG-03 | ≥80% template coverage of dogfood interfaces | Scenario `interfaces` field uses transport names ("http") not endpoint-specific names ("POST /locks/acquire"). Coverage computes to 24.6%. |
| REQ-INT-01 | Integration with existing evaluation/metrics.py | No GenEvalMetrics integration implemented. The metrics dataclass exists but is never populated or returned by the orchestrator. |

### Partial (5)

| Requirement | Description | Gap |
|-------------|-------------|-----|
| REQ-GEN-06 | Auto-discovery of interfaces from descriptors | Descriptor provides `all_interfaces()` but generators don't auto-discover missing coverage |
| REQ-SCN-06 | Scenario validation against descriptor | Template generator validates structure but doesn't cross-check endpoint existence |
| REQ-EVAL-06 | LLM-based judgment for complex assertions | Infrastructure exists (LLMGeneratorMixin) but no LLM-as-judge evaluator |
| REQ-BDG-06 | Per-verdict backend attribution | `backend_used` field exists on ScenarioVerdict but only set to "cli" in budget tracking |
| REQ-INT-04 | CI job configuration | `.github/workflows/ci.yml` has gen-eval job but needs project-specific environment variables |

---

## Summary

| Metric | Value |
|--------|-------|
| Unit tests | 322 passed |
| Lint | Clean |
| Scenario templates | 81 |
| Dogfood interfaces | 114 |
| Spec requirements passed | 27 / 34 (79%) |
| Spec requirements failed | 2 |
| Spec requirements partial | 5 |

---

## Result

**FAIL** — 2 requirements not met (REQ-DOG-03, REQ-INT-01)

### Recommended Next Steps

1. **Fix REQ-DOG-03** (template coverage): Update the 81 scenario YAML files to populate `interfaces` with endpoint-specific names matching `InterfaceDescriptor.all_interfaces()` output (e.g., `"POST /locks/acquire"` instead of `"http"`). This is the highest-impact fix.

2. **Fix REQ-INT-01** (metrics integration): Wire `GenEvalReport` data into `GenEvalMetrics` and return it from the orchestrator or CLI entry point.

3. **Re-run validation** after fixes: `/validate-feature gen-eval-testing --phase spec`

4. **Alternative**: Proceed to `/cleanup-feature gen-eval-testing` accepting partial gaps — the framework is functional and all 322 tests pass. The coverage computation issue is a data-quality gap in scenario templates, not a code bug.
