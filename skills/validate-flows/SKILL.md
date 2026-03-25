---
name: validate-flows
description: "Architecture flow validation for cross-layer interactions"
category: Infrastructure
tags: [validation, flows, architecture, infrastructure]
user_invocable: false
---

# Validate Flows Infrastructure Skill

Non-user-invocable infrastructure skill for architecture flow validation during implementation and validation phases.

## Scripts

### scripts/validate_flows.py

Validates cross-layer architecture flows (API → DB, MCP → service, etc.).

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_flows.py" [options]
```

**Exit codes**: 0 = all flows valid, 1 = validation errors found
