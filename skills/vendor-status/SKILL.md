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

Check all configured vendors' availability, CLI installation, API key validity, and dispatch mode support. Configuration is read from `AGENTS_YAML` first, then the public coordinator HTTP endpoint when `COORDINATION_API_URL` is set. A local `agent-coordinator/agents.yaml` is only a compatibility fallback.

Inspired by the `/codex:setup` command from [codex-plugin-cc](https://github.com/openai/codex-plugin-cc).

## Arguments

`$ARGUMENTS` - Optional flags

Optional flags:
- `--json` — Machine-readable JSON output

## Steps

### 1. Run Health Check

```bash
AGENTS_YAML=/path/to/agents.yaml \
  python3 "<skill-base-dir>/../parallel-infrastructure/scripts/vendor_health.py"
```

Or with JSON output:

```bash
python3 "<skill-base-dir>/../parallel-infrastructure/scripts/vendor_health.py" --json
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
