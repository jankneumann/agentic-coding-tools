---
name: vendor-status
description: Check all configured vendors' readiness in one shot
category: Infrastructure
tags: [vendor, health, status, diagnostic]
triggers:
  - "vendor status"
  - "vendor health"
  - "check vendors"
requires:
  coordinator:
    required: []
    safety: []
    enriching: []
---

# Vendor Status

Check all configured vendors' availability, CLI installation, API key validity, and dispatch mode support. Standalone — no coordinator dependency.

Inspired by the `/codex:setup` command from [codex-plugin-cc](https://github.com/openai/codex-plugin-cc).

## Arguments

`$ARGUMENTS` - Optional flags

Optional flags:
- `--json` — Machine-readable JSON output

## Steps

### 1. Run Health Check

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/vendor_health.py" \
  --agents-yaml agent-coordinator/agents.yaml
```

Or with JSON output:

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/vendor_health.py" \
  --agents-yaml agent-coordinator/agents.yaml --json
```

### 2. Present Results

Display the vendor status table to the user. Highlight any vendors that are unhealthy.

### 3. Recommendations

If any vendors are unhealthy, suggest fixes:
- CLI not installed → "Install <command> CLI"
- API key missing → "Set <ENV_VAR> environment variable"
- No dispatch modes → "Check agents.yaml configuration"

## Output

Human-readable table (default) or JSON report of vendor health status.
