# Change: add-coordinator-profiles

## Why

The parallel-* skills require a running agent-coordinator, but there is no streamlined way to configure and launch it. The coordinator's `config.py` loads everything from scattered environment variables with no structure, no secret management, and no deployment-specific presets. Agent identity and permissions are split across env vars (`AGENT_ID`, `AGENT_TYPE`), a JSON blob (`COORDINATION_API_KEY_IDENTITIES`), and SQL seed data (`007_agent_profiles.sql`) with no single source of truth.

The user's other project (`agentic-newsletter-aggregator`) has a proven YAML-based profile system with inheritance, `${VAR}` interpolation, `.secrets.yaml` for credentials, and env var override. Adapting that pattern here gives the coordinator:

1. **Two deployment profiles** (local + railway) with inheritance from a shared base
2. **A declarative agents config** (`agents.yaml`) as the single source of truth for agent identity, trust levels, permissions, and API key mapping
3. **Profile-driven setup-coordinator skill** with auto-start Docker and vendor config generation

## What Changes

### Deployment Profiles

- Add `agent-coordinator/profiles/` directory with YAML profile files: `base.yaml`, `local.yaml`, `railway.yaml`
- Add `agent-coordinator/.secrets.yaml.example` (git-tracked template) and gitignore `.secrets.yaml`
- Add `agent-coordinator/src/profile_loader.py` — loads profiles, resolves inheritance, interpolates `${VAR}` from secrets + env, injects into `os.environ` as defaults (env vars always win)
- Add `agent-coordinator/src/docker_manager.py` — detects Docker Desktop / Podman, auto-starts ParadeDB container, waits for healthy
- Modify `agent-coordinator/src/config.py` — call `apply_profile()` at top of `Config.from_env()`, add `active_profile` and `transport` fields
- **BREAKING**: Default `DB_BACKEND` changes from `"supabase"` to `"postgres"` when a profile is active (profiles set `db_backend: postgres`). Existing users without profiles are unaffected (no profiles/ dir = no change).

### Agent Configuration

- Add `agent-coordinator/agents.yaml` — declarative agent definitions replacing scattered config sources:

```yaml
# agents.yaml — single source of truth for agent identity and permissions
agents:
  claude-code-local:
    type: claude_code
    profile: claude_code_cli          # references agent_profiles DB name
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue, memory, guardrails, handoff, discover, audit]
    description: Local Claude Code CLI agent with full coordination access

  claude-code-web:
    type: claude_code
    profile: claude_code_web_implementer
    trust_level: 2
    transport: http
    api_key: ${CLAUDE_WEB_API_KEY}
    capabilities: [lock, queue, memory, guardrails, handoff, discover]
    description: Claude Code web agent for cloud-based implementation

  codex-cloud:
    type: codex
    profile: codex_cloud_worker
    trust_level: 2
    transport: http
    api_key: ${CODEX_API_KEY}
    capabilities: [lock, queue, memory, guardrails]
    description: Codex cloud worker for parallel task execution

  gemini-cloud:
    type: gemini
    profile: gemini_cloud_worker
    trust_level: 2
    transport: http
    api_key: ${GEMINI_API_KEY}
    capabilities: [lock, queue, memory]
    description: Gemini cloud agent for parallel task execution
```

- Add `agent-coordinator/src/agents_config.py` — loads `agents.yaml`, validates with JSON schema (following `teams.py` pattern), provides:
  - `get_agent_config(agent_id)` — look up agent definition by name
  - `get_api_key_identities()` — generate `COORDINATION_API_KEY_IDENTITIES` JSON from HTTP agents
  - `get_mcp_env(agent_id)` — generate env vars needed for MCP server registration
  - `seed_profiles_from_config()` — optionally bootstrap `agent_profiles` DB table from YAML definitions
- Modify `ApiConfig.from_env()` to auto-populate `api_key_identities` from `agents.yaml` when no explicit `COORDINATION_API_KEY_IDENTITIES` env var is set

### Setup & Skills

- Update `skills/setup-coordinator/SKILL.md` (+ `.claude/`, `.codex/`, `.gemini/` copies):
  - Add `--profile <local|railway>` flag and profile-driven setup steps
  - Read `agents.yaml` to determine which agents to configure
  - For MCP agents: generate vendor-specific MCP config (e.g., `~/.claude/mcp.json` entry) using `get_mcp_env()`
  - For HTTP agents: derive `COORDINATION_API_KEY_IDENTITIES` from `get_api_key_identities()`
- Update `.gitignore` to add `.secrets.yaml`
- Update `agent-coordinator/.env.example` header to reference the profile system
- Update `docs/coordination-detection-template.md` with profile-based configuration note
- Add unit tests for profile_loader, docker_manager, and agents_config

### Rollback Plan

Remove the `apply_profile()` call from `Config.from_env()` and the agents_config import from `ApiConfig.from_env()`. All downstream code reverts to env-var-only behavior. YAML files remain inert.

## Impact

### Affected Specs

| Spec | Capability | Delta |
|------|-----------|-------|
| `agent-coordinator` | Configuration | New requirement: profile-based configuration with inheritance and secret interpolation |
| `agent-coordinator` | Docker lifecycle | New requirement: auto-start ParadeDB container for local profile |
| `agent-coordinator` | Agent identity | New requirement: declarative agent config as single source of truth for identity, trust, and API key mapping |
| `skill-workflow` | Setup coordinator | Updated: profile-aware setup with `--profile` flag and vendor config generation |

### Architecture Layers

- **Coordination layer**: `config.py` gains profile loading (non-invasive — 61 dependents unchanged)
- **Execution layer**: `docker_manager.py` manages container lifecycle
- **Trust layer**: `agents.yaml` becomes the declarative source for agent profiles, seeding the DB table that the policy engine already reads; existing `profiles.py` service, `policy_engine.py`, and `007_agent_profiles.sql` schema are unchanged

### Major Touchpoints

| File | Change |
|------|--------|
| `agent-coordinator/profiles/base.yaml` | New — shared deployment defaults |
| `agent-coordinator/profiles/local.yaml` | New — MCP + Docker |
| `agent-coordinator/profiles/railway.yaml` | New — HTTP + Railway |
| `agent-coordinator/agents.yaml` | New — declarative agent definitions |
| `agent-coordinator/.secrets.yaml.example` | New — secrets template |
| `agent-coordinator/src/profile_loader.py` | New — ~150 lines |
| `agent-coordinator/src/docker_manager.py` | New — ~80 lines |
| `agent-coordinator/src/agents_config.py` | New — ~120 lines |
| `agent-coordinator/src/config.py` | Modified — profile loading + auto API key identities |
| `agent-coordinator/tests/test_profile_loader.py` | New — ~10 test cases |
| `agent-coordinator/tests/test_docker_manager.py` | New — ~6 test cases |
| `agent-coordinator/tests/test_agents_config.py` | New — ~8 test cases |
| `skills/setup-coordinator/SKILL.md` (x4 copies) | Modified — profile-driven + vendor config |
| `.gitignore` | Modified — add `.secrets.yaml` |
| `agent-coordinator/.env.example` | Modified — profile reference header |
| `docs/coordination-detection-template.md` | Modified — profile note |

### Existing Patterns Reused

- `teams.py`: `yaml.safe_load()` + `jsonschema.validate()` + `from_dict()` + lazy singleton pattern
- `config.py`: `from_env()` + lazy singleton + `reset_config()` test pattern
- `007_agent_profiles.sql`: existing DB schema and seed data (agents.yaml aligns with these profiles)
- `agentic-newsletter-aggregator/src/config/profiles.py`: inheritance resolution, `${VAR:-default}` interpolation regex, `deep_merge()`
- `pyyaml>=6.0` and `jsonschema>=4.0` already in `pyproject.toml`
