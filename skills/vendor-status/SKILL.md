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
- `missing_flags` → the installed CLI lacks a flag a dispatch mode passes; update the CLI
- `auth_status: auth_failed` → log in to the CLI again, then re-run this skill to refresh the cached verdict
- `runtime_failure` set → a recent dispatch hit an auth or billing error; auth clears on a passing re-probe, billing clears after one hour

## Probe tiers and cache

Health comes from the shared token-free probe (`vendor_probe.py`); no model request is ever sent:

| Tier | Checks |
|---|---|
| L0 presence | the lane's `cli.command` is on `PATH` |
| L1 capability | the version command succeeds and every flag a dispatch mode passes appears in that mode's `--help` output |
| L2 auth | exit code of `cli.probe.auth_status_args`, else existence of `cli.probe.credential_files`, else `auth_unknown` |

Results are cached per user at `$AGENTIC_PROBE_CACHE`, else `$XDG_CACHE_HOME/agentic-coding-tools/vendor-probe.json`, else `~/.cache/agentic-coding-tools/vendor-probe.json`. This skill always re-probes; `review_dispatcher.py` reads the cache (it never probes) and skips lanes with a fresh failure. Set `AGENTIC_PROBE_IGNORE_CACHE=1` to disable that filter. `install.sh --check` prints the same report, informational only.

## Output

Human-readable table (default) or JSON report of vendor health status.
