# OpenBao Secret Management

OpenBao (open-source fork of HashiCorp Vault) manages API keys and credentials for multi-vendor agent dispatch. Agents authenticate via AppRoles and retrieve secrets at runtime — no keys in git, no keys in `agents.yaml`.

## Architecture

```
agents.yaml                .secrets.yaml (gitignored)
  openbao_role_id ──┐        API keys ──┐
                    │                    │
                    ▼                    ▼
              ┌──────────┐        ┌──────────┐
              │ AppRoles │        │  KV v2   │
              │ (auth)   │        │ (secrets)│
              └────┬─────┘        └────┬─────┘
                   │                   │
                   ▼                   ▼
              ┌─────────────────────────────┐
              │         OpenBao             │
              │    http://localhost:8200     │
              └──────────┬──────────────────┘
                         │
            ┌────────────┼────────────────┐
            ▼            ▼                ▼
     ApiKeyResolver  profile_loader  coordination_api
     (SDK dispatch)  (agent config)  (HTTP API auth)
```

## Resolution Order

The `ApiKeyResolver` (used by SDK dispatch) and `profile_loader` (used by the coordinator) both follow the same priority:

1. **OpenBao** — if `BAO_ADDR` is set, authenticate with the agent's `openbao_role_id` and read the secret
2. **Environment variable** — if OpenBao is unavailable, fall back to `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.
3. **Skip** — if neither is available, the vendor is silently skipped

## Setup Options

### Option 1: Docker Dev Server (Recommended for Local Development)

Fastest way to get started. Data is ephemeral — lost when the container stops.

```bash
# Start OpenBao in dev mode
docker run -d --name openbao \
  -p 8200:8200 \
  -e BAO_DEV_ROOT_TOKEN_ID=dev-root-token \
  quay.io/openbao/openbao:latest server -dev

# Verify it's running
curl -s http://localhost:8200/v1/sys/health | python3 -m json.tool
```

Then seed it (see [Seeding](#seeding) below).

### Option 2: Docker with Persistent Storage

Data survives container restarts. Good for long-running development.

```bash
# Create volume for persistence
docker volume create openbao-data

# Start with persistent storage (not dev mode — requires manual init + unseal)
docker run -d --name openbao \
  -p 8200:8200 \
  -v openbao-data:/openbao/data \
  -e BAO_LOCAL_CONFIG='
    storage "file" { path = "/openbao/data" }
    listener "tcp" { address = "0.0.0.0:8200", tls_disable = true }
    api_addr = "http://localhost:8200"
  ' \
  quay.io/openbao/openbao:latest server

# Initialize (first time only — save the unseal keys and root token!)
docker exec openbao bao operator init -key-shares=1 -key-threshold=1

# Unseal (required after every restart)
docker exec openbao bao operator unseal <UNSEAL_KEY>
```

### Option 3: Native Binary

Install OpenBao directly for maximum control.

```bash
# macOS
brew install openbao

# Start dev server
bao server -dev -dev-root-token-id=dev-root-token

# Or start production server with config file
bao server -config=/path/to/config.hcl
```

### Option 4: Environment Variables Only (No OpenBao)

For quick testing or CI where OpenBao isn't available. Set API keys directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...
```

The `ApiKeyResolver` falls back to these automatically when `BAO_ADDR` is not set.

## Seeding

Once OpenBao is running, populate it with secrets and AppRoles:

### 1. Create `.secrets.yaml`

```bash
# agent-coordinator/.secrets.yaml (gitignored — never commit this file)
cat > agent-coordinator/.secrets.yaml << 'EOF'
ANTHROPIC_API_KEY: sk-ant-your-key-here
OPENAI_API_KEY: sk-your-openai-key-here
GOOGLE_API_KEY: your-google-api-key
CLAUDE_WEB_API_KEY: your-claude-web-key
CODEX_API_KEY: your-codex-api-key
GEMINI_API_KEY: your-gemini-api-key
EOF
```

### 2. Run the Seed Script

```bash
# Preview what will be written (safe — no changes made)
BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token \
  python3 skills/bao-vault/scripts/bao_seed.py --dry-run

# Seed secrets and create AppRoles
BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token \
  python3 skills/bao-vault/scripts/bao_seed.py

# Optional: also configure database secrets engine
BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token \
  python3 skills/bao-vault/scripts/bao_seed.py --with-db-engine
```

The seed script:
- Writes all keys from `.secrets.yaml` to `secret/coordinator` (KV v2)
- Creates AppRoles for each HTTP-transport agent in `agents.yaml` (`claude-code-web`, `codex-cloud`, `gemini-cloud`)
- Each AppRole gets a read-only policy on the secrets path

### 3. Verify

```bash
# Read secrets (using root token)
BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token \
  bao kv get secret/coordinator

# List AppRoles
BAO_ADDR=http://localhost:8200 BAO_TOKEN=dev-root-token \
  bao list auth/approle/role
```

## Runtime Configuration

### For SDK Dispatch (ApiKeyResolver)

Set these environment variables so the dispatcher can resolve API keys:

```bash
export BAO_ADDR=http://localhost:8200
export BAO_SECRET_ID=<secret-id>       # Shared bootstrap secret for AppRole login
export BAO_MOUNT_PATH=secret           # Default: "secret"
export BAO_SECRET_PATH=coordinator     # Default: "coordinator" (was "agents" in some configs)
```

To get the `BAO_SECRET_ID` for an agent's AppRole:

```bash
BAO_TOKEN=dev-root-token \
  bao write -f auth/approle/role/claude-code-web/secret-id
```

### For the Coordinator (HTTP API)

The coordinator uses the same OpenBao instance for API key identity resolution:

```bash
export BAO_ADDR=http://localhost:8200
export BAO_ROLE_ID=<coordinator-role-id>
export BAO_SECRET_ID=<coordinator-secret-id>
```

## Security Notes

- **Never commit `.secrets.yaml`** — it's in `.gitignore`
- **Dev mode is insecure** — data is in-memory, root token is static. Use only for local development
- **Production should use TLS** — configure `tls_cert_file` and `tls_key_file` in the listener
- **Rotate AppRole secret IDs** — the seed script creates initial ones; rotate periodically in production
- **The `BAO_SECRET_PATH` default differs** between components: `bao_seed.py` uses `"coordinator"`, `ApiKeyResolver` uses `"agents"`. Ensure they match via environment variables

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `BAO_ADDR not set` | OpenBao not configured | Set `BAO_ADDR` or use env var fallback (Option 4) |
| `Authentication failed` | Bad token or unsealed vault | Check `BAO_TOKEN` or unseal the vault |
| `Permission denied` | AppRole doesn't have read access | Re-run `bao_seed.py` to recreate policies |
| `Connection refused` | OpenBao not running | Start the container: `docker start openbao` |
| API key resolves to `None` | Key name mismatch | Ensure `.secrets.yaml` key names match `sdk.api_key_env` in `agents.yaml` |

## Related Files

| File | Purpose |
|------|---------|
| `skills/bao-vault/scripts/bao_seed.py` | Seeds secrets and AppRoles from config files |
| `skills/parallel-infrastructure/scripts/api_key_resolver.py` | Runtime API key resolution (OpenBao → env var → None) |
| `agent-coordinator/src/agents_config.py` | Parses `openbao_role_id` from `agents.yaml` |
| `agent-coordinator/src/profile_loader.py` | Resolves secrets for coordinator startup |
| `agent-coordinator/.secrets.yaml` | Local secrets file (gitignored) |
| `agent-coordinator/agents.yaml` | Agent definitions with `openbao_role_id` fields |
