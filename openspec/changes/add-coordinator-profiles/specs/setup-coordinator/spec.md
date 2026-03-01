# Delta Spec: Setup Coordinator — Profile-Driven Setup

## MODIFIED Requirements

### Requirement: Profile-Aware Setup

The setup-coordinator skill SHALL accept a `--profile <local|railway>` argument and drive setup steps from the active profile.

- When `--profile` is not provided, the skill SHALL read `COORDINATOR_PROFILE` env var, defaulting to `"local"`
- The skill SHALL read `agents.yaml` to determine which agents to configure
- The skill SHALL check for `.secrets.yaml` and prompt the user to create it from `.secrets.yaml.example` if missing

#### Scenario: Local profile setup
- **WHEN** `--profile local` is specified
- **THEN** the skill SHALL:
  1. Detect container runtime (Docker / Podman)
  2. Auto-start ParadeDB container if `docker.auto_start` is true
  3. Wait for container health
  4. Register MCP server in vendor config (e.g., `~/.claude/mcp.json`) with env vars from `get_mcp_env()`
  5. Verify MCP tool discovery
  6. Report capability flags

#### Scenario: Railway profile setup
- **WHEN** `--profile railway` is specified
- **THEN** the skill SHALL:
  1. Verify `COORDINATION_API_URL` is resolved (from profile + secrets)
  2. Test API health via `curl $COORDINATION_API_URL/health`
  3. Verify API key acceptance on a write endpoint
  4. Run `coordination_bridge.py detect` to verify capability flags
  5. Report capability flags

#### Scenario: Secrets file missing
- **WHEN** `.secrets.yaml` does not exist
- **THEN** the skill SHALL copy `.secrets.yaml.example` to `.secrets.yaml`
- **AND** prompt the user to fill in real values before continuing
