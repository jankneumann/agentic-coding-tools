---
name: bao-vault
description: "OpenBao/Vault credential seeding and management scripts"
category: Infrastructure
tags: [bao, vault, credentials, infrastructure]
user_invocable: false
---

# Bao Vault Infrastructure Skill

Non-user-invocable infrastructure skill for OpenBao/Vault credential seeding and management.

## Scripts

### scripts/bao_seed.py

Seeds OpenBao with agent API keys and secrets from agents.yaml configuration. Reads any string-valued key in `.secrets.yaml` and writes it under the configured KV mount, so adding new credential names (e.g. `LANGFUSE_PUBLIC_KEY`) requires no code change — just add the key to `.secrets.yaml` and re-run.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/bao_seed.py" [options]
```

**Environment variables**:
- `BAO_ADDR` — OpenBao server address
- `BAO_TOKEN` — Root or privileged token for seeding

**Exit codes**: 0 = seeded successfully, 1 = error

### scripts/langfuse_env.sh

Resolves `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` from OpenBao (preferring values already in the environment), computes `LANGFUSE_BASIC_AUTH = base64(public:secret)`, and emits four `export` lines on stdout. Designed to be sourced via `eval`:

```bash
eval "$(skills/bao-vault/scripts/langfuse_env.sh)"
```

Falls back silently when `BAO_ADDR` is unset or the keys are already populated, so it is safe to put in shell init or scripts.

**Authentication**: prefers `BAO_TOKEN` if set, otherwise uses AppRole login via `BAO_ROLE_ID` + `BAO_SECRET_ID` (matches `bao_seed.py`).

**Consumed by**:
- `skills/langfuse/scripts/install-mcp.sh` — to compute the literal Basic-auth token written into Codex / Gemini user-global config files.
- `skills/langfuse/scripts/run_stop_hook.sh` — to populate the env for the Claude Code Stop-hook tracer.
