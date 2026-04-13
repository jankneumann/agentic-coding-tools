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

Seeds OpenBao with agent API keys and secrets from agents.yaml configuration.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/bao_seed.py" [options]
```

**Environment variables**:
- `BAO_ADDR` — OpenBao server address
- `BAO_TOKEN` — Root or privileged token for seeding

**Exit codes**: 0 = seeded successfully, 1 = error
