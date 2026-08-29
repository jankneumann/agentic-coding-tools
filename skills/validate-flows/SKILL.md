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

### `<skill-base-dir>/scripts/validate_flows.py`

Validates cross-layer architecture flows (API → DB, MCP → service, etc.).

The validator is a pure reader: it consumes the graph at `--graph` and never
regenerates it, so that a caller which passes a fixture path gets exactly the file
it named. Freshness is therefore the caller's job, at the moment of the call:

```bash
# Ensure architecture artifacts are current, immediately before the first read.
# `--ensure` is `--check` plus a staged refresh only when the check is not fresh,
# so on an already-fresh checkout it writes nothing. PYTHON must name the same
# interpreter this repository's architecture targets use: the check runs in-process
# and the pipeline runs in a subprocess, and if the two disagree about which
# optional grammars are importable they report permanent, unfixable drift.
ARCH_PY="${PYTHON:-python3}"
if "$ARCH_PY" "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --ensure --python "$ARCH_PY"; then
  ARCH_FRESHNESS="ensured"
else
  ARCH_FRESHNESS="DEGRADED"
  echo "DEGRADED: architecture artifacts could not be made current; the last known-good analysis is left intact but unverified. Report every architecture-derived finding below as unverified rather than as current." >&2
fi
```

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_flows.py" \
  --graph docs/architecture-analysis/architecture.graph.json [options]
```

**Exit codes**: 0 = all flows valid, 1 = validation errors found
