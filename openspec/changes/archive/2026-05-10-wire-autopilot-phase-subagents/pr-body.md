## Summary

Wires the **per-phase archetype machinery** (built but not connected in `add-per-phase-archetype-resolution`) into the production autopilot pipeline so that each phase actually dispatches to a sub-agent with the right archetype, model, and system prompt — rather than running every phase as the orchestrator's own thread.

* SKILL.md prose now drives sub-agent dispatches via explicit 3-step blocks: `runner.py build-dispatch` → `Agent(...)` → `runner.py apply-outcome`.
* INIT and SUBMIT_PR (state-only phases) use `runner.py record-state-only-archetype` so observability covers all 13 non-terminal phases.
* The coordinator's `/discovery/agents` and `/status/report` carry `phase_archetype` end-to-end (DB column + RPC + Pydantic Literal validation + MCP discover_agents response parity).
* `report_status.py` reads `phase_archetype` from `loop-state.json` and POSTs it.
* Inline fallback (D5) preserved: when `runner.py build-dispatch` returns `archetype: null` (coordinator unreachable) OR the harness `Agent(...)` is unavailable, the dispatch block falls through to the slash-command path with `phase_archetype = null`.

Linked proposal: `openspec/changes/wire-autopilot-phase-subagents/proposal.md`

## Evidence Trail

### Multi-vendor review convergence
| Round | Phase | Vendors | Findings | Applied |
|---|---|---|---|---|
| 1 | PLAN_REVIEW | claude=20, codex=9, gemini=5 | 34 | 7 high (inline) |
| 2 | IMPL_REVIEW | claude=9, gemini=5 (codex auth expired) | 14 | 5 high + 1 false positive documented |
| 3 | VAL_REVIEW | claude+gemini | TBD (this PR pending) | TBD |

### Test coverage
* `skills/tests/autopilot/`: 126 tests (8 new files since plan)
* `skills/autopilot/scripts/tests/`: 80 tests (existing)
* `agent-coordinator/tests/`: 106 tests (5 new/extended modules)
* **Total: 312 unit tests passing** across 3 venvs, 0 regressions.

### Quality gates (env-safe)
* ruff: clean across all changed files
* mypy: clean (`agent-coordinator/src/discovery.py`, `coordination_api.py`)
* openspec: `validate wire-autopilot-phase-subagents --strict` passes
* token-budget gate: all 7 dispatching phases ≤0.25% of 200k context window
* `audit_log_validator` exit-code contract verified (0/1/2)

Docker-dependent phases (deploy/smoke/security/e2e) are deferred to `/cleanup-feature` per project policy (CLAUDE.md "Validation is automatic" section).

## Architectural Decisions (from design.md)

| ID | Decision | Why |
|---|---|---|
| D1 | SKILL.md prose dispatches `Agent(...)` (not Python orchestrator) | Lets the harness — not Python — own sub-agent invocation, matching how every other skill works |
| D2 | `_PROMPT_SEPARATOR` folded inside `build_phase_dispatch_kwargs` only | Single-source-of-truth: SKILL.md never folds, never splits |
| D3 | `build_phase_dispatch_kwargs(phase, change_id) -> dict` shape | Stable JSON schema runner.py prints; orchestrator passes opaquely to Agent |
| D4 | Replay rule: `state.last_handoff_id == handoff_id AND state.previous_phase == phase` | Idempotent retries don't double-write phase_archetype |
| D5 | Inline fallback when `archetype: null` | Coordinator outages don't break the autopilot |
| D6 | `report_status.py` POSTs `phase_archetype` (not just phase) | Closes observability gap surfaced in archived change |
| D7 | State-only archetype recorded for INIT/SUBMIT_PR | Every non-terminal phase has phase_archetype in state |
| D8 | Dedicated `phase_archetype TEXT` column with CHECK constraint | DB-level enforcement of the 5-archetype enum |

## Test plan

- [ ] CI green (ruff, mypy, pytest, openspec validate strict)
- [ ] Manually verify `runner.py record-state-only-archetype --phase INIT` writes `phase_archetype` to loop-state.json (smoke-tested against live coordinator during VALIDATE — returned `runner`)
- [ ] Manually verify `runner.py build-dispatch --phase IMPLEMENT` returns `{prompt, model, system_prompt, isolation, archetype}` JSON (covered by `test_build_phase_dispatch_kwargs.py`)
- [ ] Verify `coordination_mcp.discover_agents` response includes `phase_archetype` (G-R-002 fix; covered by existing MCP tests)
- [ ] After merge: run `/cleanup-feature` to execute Docker-dependent validation (deploy/smoke/security/e2e)

## Out of scope (filed for follow-up)

* C-R-003: Token-budget CI gate uses synthetic data too small to catch realistic prompt growth (~0.4% vs 60%/75% thresholds).
* C-R-004: `audit_log_validator.expected_phase_models_from_loop_state` hardcodes the 7-phase happy path; FIX iterations skew counts.
* C-R-006: `AUTOPILOT_PHASE_MODEL_OVERRIDE` silently drops `system_prompt` (design intent — needs spec clarification).
* C-R-007: Network-timeout-fallback test stubs the bridge function rather than exercising absorption inside it.
* C-R-008: `_DEFAULT_PHASE_MODEL` and `_FALLBACK_MODEL_BY_PHASE` disagree on IMPLEMENT default (no shared source of truth).
* C-R-009: `apply_phase_outcome` silently aborts on missing/malformed loop-state.json (no spec scenario).
* G-R-003: `coordination_mcp.heartbeat` MCP tool doesn't accept `phase_archetype` argument (HTTP API does — MCP parity gap).
* G-R-005: Cache checksum mismatch silently writes `phase_archetype = None` (design intent per spec).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
