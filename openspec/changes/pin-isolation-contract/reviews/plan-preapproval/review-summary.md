# dg-05 Plan Review: pin-isolation-contract

## Executive Summary

The proposed dg-05 plan is **architecturally sound** but has **multiple blocking correctness issues and compatibility hazards** that must be resolved before implementation. The plan correctly identifies the need for a single isolation vocabulary and precedence resolver, but the current codebase has three independent vocabulary definitions, no per-mode isolation in `ModeConfig`, and no shared precedence logic.

---

## Blocking Correctness Issues

### 1. Three Independent Vocabulary Definitions (Drift Hazard)
**Location**:
- `agent-coordinator/src/agents_config.py:54` — `VALID_ISOLATION_MODES = {"worktree", "sandbox", "none"}`
- `agent-coordinator/src/model_routing/routing_policy.py:18` — `Isolation = Literal["none", "worktree", "sandbox"]`
- `agent-coordinator/src/model_routing/api.py:88, 118` — `required_isolation` and `RoutingAssignmentResponse.isolation` use inline Literals

**Impact**: Any change to the vocabulary (e.g., adding "container") requires editing 3+ files. Silent drift is guaranteed.

**Required**: Single source of truth in `isolation_contract` module; all three locations must import from it.

### 2. `ModeConfig` Missing `isolation` Field (Schema Gap)
**Location**: `agent-coordinator/src/agents_config.py:188` — `ModeConfig` only has `args`, `async_dispatch`, `poll`

**Impact**: The plan requires `cli.dispatch_modes.<mode>.isolation` override parsed into `ModeConfig`. Current schema (`AGENTS_SCHEMA` lines 167-178) does not include `isolation` in dispatch_modes properties.

**Required**:
- Add `isolation: str | None = None` to `ModeConfig` dataclass
- Add `"isolation": {"type": "string", "enum": sorted(VALID_ISOLATION_MODES)}` to dispatch_modes schema
- Update `_parse_mode()` to extract and pass isolation
- Update `CliConfig` serialization in `get_dispatch_configs()` to include per-mode isolation

### 3. No Precedence Resolver Exists (Logic Gap)
**Plan**: "router when reachable, then agents.yaml via get_agent_isolation(), then none"

**Current**:
- Router path: `RoutingService.select_model()` → `policy.evaluate()` → `PolicyEvaluation.isolation`
- agents.yaml path: `get_agent_isolation(agent_type)` (no dispatch_mode awareness)
- No shared function implements the precedence ladder
- No "router unreachable → fallback" logic; router errors raise `RoutingUnavailableError`

**Required**: New `resolve_isolation(agent_type, dispatch_mode, router_isolation=None, router_reachable=True)` in `isolation_contract` that:
1. Returns `router_isolation` if `router_reachable and router_isolation is not None`
2. Else calls `get_agent_isolation(agent_type, dispatch_mode)`
3. Else returns `"none"`
4. Returns typed result with `source: Literal["router", "agents_yaml", "default"]`

### 4. `get_agent_isolation` Signature Change (Breaking Change)
**Current**: `get_agent_isolation(agent_type: str) -> str | None`
**Proposed**: `get_agent_isolation(agent_type: str, dispatch_mode: str | None = None) -> str | None`

**Impact**:
- Must search for `(agent_type, dispatch_mode)` match first (per-mode override in `ModeConfig.isolation`)
- Fall back to agent-level `AgentEntry.isolation`
- Return `None` if no agent matches (current behavior preserved)

**Call sites to audit**: Only used in tests currently (`test_agents_config_isolation.py`), but `vendor_registry.py` reads `agent.isolation` directly — not through this helper.

---

## Compatibility Hazards

### 5. agents.yaml Schema Backward Compatibility
**Risk**: Adding `isolation` to dispatch_modes schema as optional field.
- Existing agents.yaml files lack per-mode isolation → must default to agent-level isolation
- JSON Schema `additionalProperties: False` on dispatch_modes (line 178) — adding new property is safe if optional
- **Mitigation**: Make schema property optional with no default; parsing logic applies default

### 6. RoutingPolicyDocument Imports Local Literal
**Location**: `routing_policy.py:18` defines `Isolation` Literal used in `RuleConstraint` and `FallbackOrder`
**Risk**: Changing to import from `isolation_contract` requires:
- `isolation_contract` must be dependency-neutral (no pydantic, no yaml)
- `routing_policy.py` must import the vocabulary as a tuple/set for Pydantic `Literal[...]` construction
- `FallbackOrder.isolation_order` validation must use shared vocabulary

### 7. API Layer Uses Inline Literals
**Location**: `api.py:88` `required_isolation: Literal["none", "worktree", "sandbox"] | None`
**Location**: `api.py:118` `isolation: Literal["none", "worktree", "sandbox"]`
**Risk**: Must import from shared contract. Pydantic `Literal` requires actual values — can use `IsolationVocabulary` tuple from contract.

### 8. Resolver Compares Isolation Strings Directly
**Location**: `resolver.py:287` `assignment.isolation != required_isolation`
**Risk**: If vocabulary expands, comparison still works (string equality), but validation must reject unknown values at boundaries (router input, agents.yaml load).

---

## Missed Tests

### 9. No Tests for Per-Mode Isolation Override
**Required test scenarios**:
- Agent entry with per-mode isolation for `review` ≠ `alternative`
- Agent entry with agent-level isolation only → all modes inherit
- Agent entry with neither → defaults to `"none"`
- `get_agent_isolation("claude_code", "review")` returns per-mode value
- `get_agent_isolation("claude_code", "quick")` falls back to agent-level

### 10. No Tests for Precedence Ladder
**Required test scenarios**:
- Router returns isolation → used (router wins)
- Router reachable but returns `None` → agents.yaml used
- Router unreachable (exception) → agents.yaml used → then `"none"`
- Resolution result carries `source` field for observability

### 11. No Tests for Unrecognized Value Rejection
**Required test scenarios**:
- agents.yaml with `isolation: "container"` → load fails with explicit error
- Router returns `isolation: "container"` → select_model fails with explicit error
- routing.yaml with `constrain: {isolation: "container"}` → load fails

### 12. No Tests for ModeConfig Isolation Serialization
**Required**: `get_dispatch_configs()` includes per-mode isolation in CLI output for dispatch consumers.

---

## Scope Conflicts

### 13. dg-06 Consumer Dispatch Wiring Excluded but Contract Must Be Consumable
**Plan statement**: "Scope excludes dg-06 consumer dispatch wiring"
**Conflict**: The isolation contract module **must** expose types/functions that dg-06 dispatch layer will import. If the contract module doesn't exist or has wrong API, dg-06 cannot proceed.
**Resolution**: Define the contract module's public API explicitly in dg-05:
- `IsolationMode` type (Literal or Enum)
- `VALID_ISOLATION_MODES` tuple
- `validate_isolation(value: str) -> IsolationMode` / raises
- `resolve_isolation(...) -> IsolationResolution` (typed result with source)
- `get_agent_isolation(agent_type, dispatch_mode)` — updated signature

### 14. dg-07 OS Sandbox Enforcement Excluded but "sandbox" Vocabulary Exists
**Plan statement**: "Scope excludes dg-07 OS sandbox enforcement"
**Conflict**: The vocabulary includes `"sandbox"` which implies OS-level enforcement semantics. The contract must **not** encode enforcement behavior — only the vocabulary value.
**Resolution**: Document in `isolation_contract` that `"sandbox"` is a posture label only; enforcement is a separate concern (dg-07).

### 15. Module Location Unclear — "Dependency-Neutral" Placement
**Plan**: "add one dependency-neutral isolation_contract module"
**Options**:
- `agent-coordinator/src/isolation_contract.py` — simplest, but skills/tests may need it
- New package `packages/isolation-contract/` — cleanest for cross-component use
- `skills/` — not appropriate (runtime code)
**Recommendation**: `agent-coordinator/src/isolation_contract.py` for now; export via `agent-coordinator` package. Skills can depend on agent-coordinator or vendor the module.

---

## Implementation Sequence Recommendations

1. **Create `isolation_contract.py`** with vocabulary, validation, typed resolution result, precedence resolver
2. **Update `agents_config.py`**:
   - Import vocabulary from contract
   - Add `isolation` to `ModeConfig` and schema
   - Update `get_agent_isolation(agent_type, dispatch_mode=None)`
   - Update `_parse_mode()` and serialization
3. **Update `routing_policy.py`**: Import vocabulary; replace local Literal
4. **Update `api.py`**: Import vocabulary; replace inline Literals
5. **Update `resolver.py`**: Import validation helper (optional, for defense in depth)
6. **Add tests** for all scenarios in §9-12
7. **Run existing test suite** — ensure no regressions

---

## Risk Assessment

| Issue | Severity | Effort to Fix |
|-------|----------|---------------|
| Triple vocabulary definition | 🔴 Critical | Low (extract to shared module) |
| ModeConfig missing isolation | 🔴 Critical | Medium (schema + dataclass + parsing + serialization) |
| No precedence resolver | 🔴 Critical | Medium (new function with tests) |
| get_agent_isolation signature | 🟡 High | Low (only test callers affected) |
| Schema backward compat | 🟡 High | Low (optional field) |
| RoutingPolicyDocument import | 🟡 High | Low (import change) |
| API layer inline Literals | 🟡 High | Low (import change) |
| Missing test coverage | 🟡 High | Medium (new test file) |
| Scope conflicts | 🟢 Medium | Low (API design clarity) |

---

## Verdict

**Plan is APPROVABLE with mandatory fixes** for issues #1-4 before implementation starts. Issues #5-8 are compatibility hazards requiring careful implementation. Issues #9-12 are test gaps that must be filled in the same PR. Issues #13-15 are scope clarifications needed for downstream work.

**Estimated implementation effort**: M (was S) — the schema changes, precedence resolver, and test coverage add significant scope beyond the original "single vocabulary definition" description.
