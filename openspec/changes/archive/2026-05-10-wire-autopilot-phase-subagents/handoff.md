# Autopilot handoff — wire-autopilot-phase-subagents

**Status**: DONE — awaiting human approval for merge via `/cleanup-feature wire-autopilot-phase-subagents`
**PR**: https://github.com/jankneumann/agentic-coding-tools/pull/146

## Run summary

| Metric | Value |
|---|---|
| Total convergence rounds | 3 (PLAN_REVIEW → IMPL_REVIEW → VAL_REVIEW) |
| Total findings raised | 56 (34 + 14 + 8) |
| Findings applied | 16 (7 + 5 + 4) |
| False positives | 1 (G-R-001 in IMPL_REVIEW) |
| Acknowledged with reasoning | 12 |
| Files changed | 78 (+11,739 / -163) |
| Total tests | 312 (0 regressions vs main) |
| Duration | ~5 days elapsed (2026-05-02 → 2026-05-08), much idle |

## Phases executed

PLAN → PLAN_ITERATE → PLAN_REVIEW (round 1) → PLAN_FIX → IMPLEMENT (3 work-package agents) → IMPL_ITERATE (round 1) → IMPL_REVIEW (round 2) → IMPL_FIX → VALIDATE (env-safe) → VAL_REVIEW (round 3) → SUBMIT_PR → DONE

## Vendor effectiveness

| Vendor | Rounds participated | Findings raised | Findings confirmed | Fixes authored |
|---|---|---|---|---|
| claude (claude-opus-4-7) | 3/3 | 34 (20+9+5) | 11 high+medium | many (PLAN_FIX, IMPL_FIX, VAL_FIX) |
| codex (gpt-5.5) | 1/3 (auth expired rounds 2&3) | 9 (PLAN_REVIEW only) | 2 high | 0 (didn't run as fixer) |
| gemini (gemini-cli-jules) | 3/3 | 13 (5+5+3) | 4 (incl. 1 false positive) | 0 (review-only) |

**Vendor diversity dividend**: claude tended to spot architecture-level gaps
(C-R-001: SKILL.md prose path didn't invoke the resolver; C-V-002: state↔report
contradiction); gemini tended to spot surgical line-level bugs (G-R-001:
replay-detection, even though that one was a false positive; G-V-001: PLAN
phase missing archetype recording). Single-vendor review would have missed
at least the report↔state contradiction.

## Convergence pattern

| Round | Vendors successful | Time-to-converge | Pattern |
|---|---|---|---|
| 1 (PLAN_REVIEW) | 3/3 | ~2 rounds | Fast — vendors aligned quickly |
| 2 (IMPL_REVIEW) | 2/3 (codex auth) | 1 retry needed (timeout extension) | Slow — 600s budget too small for 13-file review; 1800s + diff-prioritized prompt converged |
| 3 (VAL_REVIEW) | 2/3 (codex auth) | 141s/vendor on first try | Fast — single-doc review, focused prompt |

## Implementation strategy per package

Per `loop-state.json:package_authors`:
* `wp-contracts`: claude (planning-time only — DB migration + JSON schemas + OpenAPI fragment)
* `wp-skills-autopilot`: claude with `Agent(isolation="worktree")` — built `build_phase_dispatch_kwargs`, `apply_phase_outcome`, runner.py, INIT/SUBMIT_PR resolver, SKILL.md prose, token-budget gate
* `wp-coordinator-status-discovery`: claude with `Agent(isolation="worktree")` — DB column + RPC + Pydantic Literal + AgentInfo + DiscoveryService + /discovery/agents response
* `wp-integration`: claude (mixed) — first attempt as Agent hit org usage limit at 56 tool uses; salvaged work and finished inline

**Lesson**: The `Agent(isolation="worktree")` pattern worked for the first two
packages but the third hit a usage cap because the e2e tests + audit-log
validator + runtime sync + docs were 4 distinct deliverables in one package.
For future runs, decompose work-packages by deliverable rather than by
ownership area when the deliverable count exceeds 2-3.

## Key architectural decisions (from design.md)

| ID | What | Why |
|---|---|---|
| D1 | SKILL.md dispatches `Agent(...)`, not Python orchestrator | Lets harness — not Python — own invocation, matching every other skill |
| D2 | `_PROMPT_SEPARATOR` folded inside `build_phase_dispatch_kwargs` only | SKILL.md never folds; single source of truth |
| D3 | `build-dispatch` returns JSON `{prompt, model, system_prompt, isolation, archetype}` | Stable contract orchestrator passes opaquely |
| D4 | Replay rule: `last_handoff_id == handoff_id AND previous_phase == phase` | Idempotent retries don't double-write |
| D5 | Inline fallback when `archetype: null` | Coordinator outages don't break autopilot |
| D6 | `report_status.py` POSTs `phase_archetype` (not just phase) | Closes observability gap surfaced by archived change |
| D7 | State-only archetype recorded for INIT/PLAN/SUBMIT_PR | Every non-terminal phase has phase_archetype in state |
| D8 | Dedicated `phase_archetype TEXT` column with CHECK constraint | DB-level enforcement of 5-archetype enum |

(D7's allowed-phase set was extended at VAL_REVIEW round 3 to include PLAN, since PLAN dispatches via slash command rather than Agent().)

## Open follow-ups (filed, not blocking merge)

| ID | Source | Severity | Note |
|---|---|---|---|
| C-R-003 | IMPL_REVIEW | medium (downgraded) | Token-budget gate uses synthetic data; rationale for keeping it pinned is in validation-report.md C-V-005 disposition |
| C-R-004 | IMPL_REVIEW | medium | `audit_log_validator` hardcodes 7-phase happy path; FIX iterations skew counts |
| C-R-006 | IMPL_REVIEW | medium | `AUTOPILOT_PHASE_MODEL_OVERRIDE` silently drops `system_prompt` |
| C-R-007 | IMPL_REVIEW | medium | Network-timeout-fallback test stubs the bridge function |
| C-R-008 | IMPL_REVIEW | low | `_DEFAULT_PHASE_MODEL` and `_FALLBACK_MODEL_BY_PHASE` disagree on IMPLEMENT default |
| C-R-009 | IMPL_REVIEW | low | `apply_phase_outcome` silently aborts on missing/malformed loop-state.json |
| G-R-003 | IMPL_REVIEW | low | `coordination_mcp.heartbeat` MCP tool doesn't accept `phase_archetype` (HTTP API does) |
| G-R-005 | IMPL_REVIEW | low | Cache checksum mismatch silently writes `phase_archetype = None` |
| G-V-002 | VAL_REVIEW | medium | `test_phase_dispatch_e2e.py` skips PLAN in drive loop (duplicate coverage with new tests) |

## Next step

**STOP** — await human approval. To merge:
```
/cleanup-feature wire-autopilot-phase-subagents
```

`/cleanup-feature` will run the Docker-dependent validation phases
(deploy / smoke / security / e2e) before merge.
