# Tasks: expose-coordinator-apis

## Package: wp-bridge-fix

- [ ] T1: Remove stale handoff endpoint variants from `_CAPABILITY_PROBES` in `scripts/coordination_bridge.py`
- [ ] T2: Remove stale `_HANDOFF_WRITE_ENDPOINTS` entries — keep only `("POST", "/handoffs/write")`
- [ ] T3: Remove stale `_HANDOFF_READ_ENDPOINTS` entries — keep only `("POST", "/handoffs/read")`
- [ ] T4: Add `CAN_FEATURE_REGISTRY` and `CAN_MERGE_QUEUE` to `_CAPABILITY_FLAGS` and `_CAPABILITY_PROBES`
- [ ] T5: Add `try_register_feature`, `try_deregister_feature` bridge functions
- [ ] T6: Add `try_enqueue_merge`, `try_pre_merge_checks`, `try_mark_merged` bridge functions
- [ ] T7: Update `check_coordinator.py` (in all parallel skill copies) with new `ROUTE_PROBES` and `MCP_TOOL_PROBES` entries
- [ ] T8: Write tests for new bridge functions and updated probes

## Package: wp-mcp-tools

- [ ] T9: Add 5 feature registry MCP tools to `coordination_mcp.py` (`register_feature`, `deregister_feature`, `get_feature`, `list_active_features`, `analyze_feature_conflicts`)
- [ ] T10: Add 6 merge queue MCP tools to `coordination_mcp.py` (`enqueue_merge`, `get_merge_queue`, `get_next_merge`, `run_pre_merge_checks`, `mark_merged`, `remove_from_merge_queue`)
- [ ] T11: Add MCP resources for feature registry (`features://active`) and merge queue (`merge-queue://pending`)
- [ ] T12: Write unit tests for all new MCP tools

## Package: wp-http-endpoints

- [ ] T13: Add Pydantic request models for feature registry and merge queue endpoints
- [ ] T14: Add 5 feature registry HTTP endpoints (`POST /features/register`, `POST /features/deregister`, `GET /features/{id}`, `GET /features/active`, `POST /features/conflicts`)
- [ ] T15: Add 6 merge queue HTTP endpoints (`POST /merge-queue/enqueue`, `GET /merge-queue`, `GET /merge-queue/next`, `POST /merge-queue/check/{id}`, `POST /merge-queue/merged/{id}`, `DELETE /merge-queue/{id}`)
- [ ] T16: Wire auth middleware and policy checks for all new endpoints
- [ ] T17: Write unit tests for all new HTTP endpoints

## Package: wp-cli

- [ ] T18: Create `coordination_cli.py` with argparse-based subcommand structure
- [ ] T19: Implement `feature` subcommand group (register, deregister, show, list, conflicts)
- [ ] T20: Implement `merge-queue` subcommand group (enqueue, status, check, next, merged, remove)
- [ ] T21: Implement existing capability subcommands (lock, work, handoff, memory, health, guardrails, policy, audit, ports, approval)
- [ ] T22: Add `--json` global flag with JSON/human-readable output modes
- [ ] T23: Add `coordination-cli` entry point to `pyproject.toml`
- [ ] T24: Write unit tests for CLI subcommands

## Package: wp-skill-update

- [ ] T25: Update `skills/parallel-cleanup-feature/SKILL.md` — replace pseudo-code with real MCP/HTTP API calls
- [ ] T26: Add coordinator capability requirements (`CAN_MERGE_QUEUE`, `CAN_FEATURE_REGISTRY`) to skill frontmatter
- [ ] T27: Verify all parallel skill `check_coordinator.py` copies are in sync

## Package: wp-integration

- [ ] T28: Run full test suite (pytest, mypy, ruff) across agent-coordinator
- [ ] T29: Validate OpenSpec artifacts (`openspec validate expose-coordinator-apis --strict`)
- [ ] T30: Manual smoke test: CLI → MCP → HTTP all reach same service layer
