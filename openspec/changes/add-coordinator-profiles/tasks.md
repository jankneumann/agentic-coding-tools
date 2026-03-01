# Tasks: add-coordinator-profiles

## 1. Foundation (no dependencies — parallel)

- [x] 1.1 Create profile YAML files (base, local, railway)
  **Dependencies**: None
  **Files**: `agent-coordinator/profiles/base.yaml`, `agent-coordinator/profiles/local.yaml`, `agent-coordinator/profiles/railway.yaml`
  **Traces**: Configuration/Profile-Based Configuration

- [x] 1.2 Create secrets template and gitignore entry
  **Dependencies**: None
  **Files**: `agent-coordinator/.secrets.yaml.example`, `.gitignore`
  **Traces**: Configuration/Secret Interpolation

- [x] 1.3 Create agents.yaml with agent definitions
  **Dependencies**: None
  **Files**: `agent-coordinator/agents.yaml`
  **Traces**: Agent Identity/Declarative Agent Configuration

## 2. Core Modules (depends on 1.1, 1.2 — parallel within group)

- [x] 2.1 Implement profile_loader.py (load, inherit, interpolate, inject)
  **Dependencies**: 1.1, 1.2
  **Files**: `agent-coordinator/src/profile_loader.py`
  **Traces**: Configuration/Profile-Based Configuration, Configuration/Secret Interpolation, Configuration/Field-to-Environment Mapping
  **Notes**: Follow `agentic-newsletter-aggregator/src/config/profiles.py` patterns for inheritance and interpolation. Follow `teams.py` pattern for YAML loading.

- [x] 2.2 Implement docker_manager.py (detect runtime, start, health wait)
  **Dependencies**: None (can parallel with 2.1)
  **Files**: `agent-coordinator/src/docker_manager.py`
  **Traces**: Docker Lifecycle/Container Runtime Detection, Docker Lifecycle/Container Auto-Start, Docker Lifecycle/Health Wait

- [x] 2.3 Implement agents_config.py (load agents.yaml, API key generation, MCP env)
  **Dependencies**: 1.3
  **Files**: `agent-coordinator/src/agents_config.py`
  **Traces**: Agent Identity/Declarative Agent Configuration, Agent Identity/API Key Identity Generation, Agent Identity/MCP Environment Generation

## 3. Integration (depends on 2.1, 2.3)

- [x] 3.1 Modify config.py to call apply_profile() and auto-populate API key identities
  **Dependencies**: 2.1, 2.3
  **Files**: `agent-coordinator/src/config.py`
  **Traces**: Configuration/Profile-Based Configuration, Agent Identity/API Key Identity Generation
  **Notes**: Add `apply_profile()` call at top of `Config.from_env()`. Add `active_profile` and `transport` fields. Auto-populate `ApiConfig.api_key_identities` from agents.yaml when env var not set.

## 4. Tests (depends on corresponding modules — parallel within group)

- [x] 4.1 Add tests for profile_loader.py
  **Dependencies**: 2.1, 3.1
  **Files**: `agent-coordinator/tests/test_profile_loader.py`
  **Traces**: Configuration/Profile-Based Configuration, Configuration/Secret Interpolation, Configuration/Field-to-Environment Mapping
  **Notes**: Test cases: no profiles dir, local profile, railway profile, env override, secret interpolation, `${VAR:-default}`, circular inheritance, docker block not mapped. Use `monkeypatch` + `tmp_path`.

- [x] 4.2 Add tests for docker_manager.py
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/tests/test_docker_manager.py`
  **Traces**: Docker Lifecycle/Container Runtime Detection, Docker Lifecycle/Container Auto-Start, Docker Lifecycle/Health Wait
  **Notes**: Mock `subprocess.run` and `shutil.which`. Test detect, running check, start, disabled, missing compose, health wait.

- [x] 4.3 Add tests for agents_config.py
  **Dependencies**: 2.3
  **Files**: `agent-coordinator/tests/test_agents_config.py`
  **Traces**: Agent Identity/Declarative Agent Configuration, Agent Identity/API Key Identity Generation, Agent Identity/MCP Environment Generation
  **Notes**: Test load/validate, duplicate name rejection, missing file graceful, API key identity generation, MCP env generation.

## 5. Skill & Documentation Updates (depends on 2.1, 2.2, 2.3 — parallel)

- [x] 5.1 Update setup-coordinator SKILL.md (all 4 runtime copies)
  **Dependencies**: 2.1, 2.2, 2.3
  **Files**: `skills/setup-coordinator/SKILL.md`, `.claude/skills/setup-coordinator/SKILL.md`, `.codex/skills/setup-coordinator/SKILL.md`, `.gemini/skills/setup-coordinator/SKILL.md`
  **Traces**: Setup Coordinator/Profile-Aware Setup
  **Notes**: Add `--profile` flag, profile-driven steps, read agents.yaml, vendor config generation.

- [x] 5.2 Update .env.example header and coordination-detection-template
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/.env.example`, `docs/coordination-detection-template.md`
  **Traces**: Configuration/Profile-Based Configuration

## 6. Verification

- [x] 6.1 Run full test suite and type/lint checks
  **Dependencies**: 4.1, 4.2, 4.3
  **Files**: (read-only)
  **Commands**:
  - `cd agent-coordinator && .venv/bin/python -m pytest -m "not e2e and not integration" -v`
  - `cd agent-coordinator && .venv/bin/python -m mypy --strict src/profile_loader.py src/docker_manager.py src/agents_config.py`
  - `cd agent-coordinator && .venv/bin/python -m ruff check src/profile_loader.py src/docker_manager.py src/agents_config.py`

- [x] 6.2 Local smoke test
  **Dependencies**: 6.1, 5.1
  **Commands**:
  - Copy `.secrets.yaml.example` to `.secrets.yaml`
  - `export COORDINATOR_PROFILE=local`
  - `cd agent-coordinator && docker compose up -d`
  - Verify `Config.from_env()` loads profile values
  - `python -m src.coordination_mcp` — verify MCP tools load
