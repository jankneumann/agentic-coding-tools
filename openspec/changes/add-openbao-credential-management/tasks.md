# Tasks: add-openbao-credential-management

## 1. Core Infrastructure

- [x] 1.1 Add `hvac` dependency to `agent-coordinator/pyproject.toml`
  **Dependencies**: None
  **Files**: `agent-coordinator/pyproject.toml`
  **Traces**: OpenBao Configuration Dataclass
  **Parallel**: Can run in parallel with 1.1b, 3.1, 5.1, 5.2, 7.1

- [x] 1.1b Add `hvac` dependency to `scripts/pyproject.toml` for `bao-seed.py`
  **Dependencies**: None
  **Files**: `scripts/pyproject.toml`
  **Traces**: Bootstrap Seeding Script
  **Parallel**: Can run in parallel with 1.1, 3.1, 5.1, 5.2, 7.1

- [x] 1.2 Add `OpenBaoConfig` dataclass to `agent-coordinator/src/config.py`
  **Dependencies**: 1.1
  **Files**: `agent-coordinator/src/config.py`
  **Traces**: OpenBao Configuration Dataclass

- [x] 1.3 Write unit tests for `OpenBaoConfig` (from_env, is_enabled, create_client)
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/tests/test_config.py`
  **Traces**: OpenBao Configuration Dataclass

## 2. Profile Loader OpenBao Backend

- [x] 2.1 Add `_load_secrets_openbao()` function to `agent-coordinator/src/profile_loader.py`
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/src/profile_loader.py`
  **Traces**: OpenBao Secret Backend

- [x] 2.2 Add conditional dispatch in `_load_secrets()` — call `_load_secrets_openbao()` when `BAO_ADDR` is set
  **Dependencies**: 2.1
  **Files**: `agent-coordinator/src/profile_loader.py`
  **Traces**: OpenBao Secret Backend

- [x] 2.3 Write unit tests for OpenBao secret loading (success, auth failure, missing credentials, unreachable, fallback, non-string filtering)
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/tests/test_profile_loader.py`
  **Traces**: OpenBao Secret Backend, Secret Interpolation (modified)

## 3. Agent Identity AppRole Integration

- [x] 3.1 Add `openbao_role_id` optional field to agent config in `agent-coordinator/src/agents_config.py`
  **Dependencies**: None
  **Files**: `agent-coordinator/src/agents_config.py`
  **Traces**: OpenBao AppRole per Agent
  **Parallel**: Can run in parallel with 1.1, 1.1b, 5.1, 5.2, 7.1

- [x] 3.2 Update `agents.yaml` with `openbao_role_id` entries for HTTP-transport agents
  **Dependencies**: 3.1
  **Files**: `agent-coordinator/agents.yaml`
  **Traces**: OpenBao AppRole per Agent

- [x] 3.3 Update `get_api_key_identities()` to resolve API keys from OpenBao when enabled
  **Dependencies**: 2.2, 3.1
  **Files**: `agent-coordinator/src/agents_config.py`
  **Traces**: API Key Identity Generation (modified)

- [x] 3.4 Write unit tests for AppRole-based agent identity and key resolution
  **Dependencies**: 3.3
  **Files**: `agent-coordinator/tests/test_agents_config.py`
  **Traces**: OpenBao AppRole per Agent, API Key Identity Generation (modified)

## 4. Bootstrap Seeding Script

- [x] 4.1 Create `scripts/bao-seed.py` — read `.secrets.yaml`, write to OpenBao KV v2
  **Dependencies**: 1.1b, 1.2
  **Files**: `scripts/bao-seed.py`
  **Traces**: Bootstrap Seeding Script

- [x] 4.2 Add AppRole creation from `agents.yaml` to `bao-seed.py` (HTTP-transport agents only)
  **Dependencies**: 4.1, 3.1
  **Files**: `scripts/bao-seed.py`
  **Traces**: Bootstrap Seeding Script

- [x] 4.3 Add database secrets engine configuration to `bao-seed.py --with-db-engine`
  **Dependencies**: 4.1
  **Files**: `scripts/bao-seed.py`
  **Traces**: Bootstrap Seeding Script, Dynamic Database Credentials per Agent

- [x] 4.4 Add `--dry-run` flag and idempotency verification to `bao-seed.py`
  **Dependencies**: 4.3
  **Files**: `scripts/bao-seed.py`
  **Traces**: Bootstrap Seeding Script

- [x] 4.5 Write unit tests for `bao-seed.py` (seed secrets, create roles, dry-run, idempotency)
  **Dependencies**: 4.4
  **Files**: `scripts/tests/test_bao_seed.py`
  **Traces**: Bootstrap Seeding Script

## 5. Docker Compose and Profile

- [x] 5.1 Add OpenBao dev service to `agent-coordinator/docker-compose.yml`
  **Dependencies**: None
  **Files**: `agent-coordinator/docker-compose.yml`
  **Traces**: OpenBao Secret Backend
  **Parallel**: Can run in parallel with 1.1, 1.1b, 3.1, 5.2, 7.1

- [x] 5.2 Create `agent-coordinator/profiles/openbao.yaml` extending `local.yaml` with `BAO_ADDR`
  **Dependencies**: None
  **Files**: `agent-coordinator/profiles/openbao.yaml`
  **Traces**: OpenBao Secret Backend
  **Parallel**: Can run in parallel with 1.1, 1.1b, 3.1, 5.1, 7.1

- [x] 5.3 Add `bao-dev` and `bao-seed` targets to `agent-coordinator/Makefile`
  **Dependencies**: 5.1, 4.4
  **Files**: `agent-coordinator/Makefile`
  **Traces**: Bootstrap Seeding Script

## 6. Dynamic Database Credentials

- [x] 6.1 Add dynamic DSN resolution to `profile_loader.py` when database engine is available
  **Dependencies**: 2.2
  **Files**: `agent-coordinator/src/profile_loader.py`
  **Traces**: Dynamic Database Credentials per Agent

- [x] 6.2 Write unit tests for dynamic DSN resolution (success, engine not configured, renewal)
  **Dependencies**: 6.1
  **Files**: `agent-coordinator/tests/test_profile_loader.py`
  **Traces**: Dynamic Database Credentials per Agent

## 7. Worktree and Integration

- [x] 7.1 Update `scripts/worktree-bootstrap.sh` to skip `.secrets.yaml` copy when `BAO_ADDR` is set
  **Dependencies**: None
  **Files**: `scripts/worktree-bootstrap.sh`
  **Traces**: OpenBao Secret Backend, Worktree Secret Handling
  **Parallel**: Can run in parallel with 1.1, 1.1b, 3.1, 5.1, 5.2

- [x] 7.2 Run full test suite and verify backward compatibility (all tests pass without `BAO_ADDR`)
  **Dependencies**: 2.3, 3.4, 4.5, 6.2
  **Files**: (all test files)
  **Traces**: All requirements — backward compatibility verification

- [x] 7.3 Update `.secrets.yaml.example` with documentation for OpenBao environment variables
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/.secrets.yaml.example`
  **Traces**: OpenBao Configuration Dataclass
