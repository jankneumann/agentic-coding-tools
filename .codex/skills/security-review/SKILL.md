---
name: security-review
description: Run reusable cross-project security review with profile detection, OWASP Dependency-Check, ZAP container scanning, and risk-gated reporting
category: Git Workflow
tags: [security, owasp, dependency-check, zap, dast, sca, risk-gate]
triggers:
  - "security review"
  - "run security review"
  - "owasp scan"
  - "dependency check"
  - "zap scan"
---

# Security Review

Run a reusable security review workflow across repositories. This skill auto-detects project profile(s), executes compatible scanners, normalizes findings, and applies a deterministic risk gate.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--repo <path>` (default: current directory)
- `--out-dir <path>` (default: `<repo>/docs/security-review`)
- `--profile-override <profiles>` (for example `python,node`)
- `--fail-on <info|low|medium|high|critical>` (default: `high`)
- `--zap-target <url-or-spec>` (required for ZAP execution)
- `--zap-mode <baseline|api|full>` (default: `baseline`)
- `--change <change-id>` (optional; writes OpenSpec artifact to `openspec/changes/<id>/security-review-report.md`)
- `--openspec-root <path>` (optional override when resolving OpenSpec change directory)
- `--bootstrap <auto|never>` (default: `auto`)
- `--apply-bootstrap` (execute install commands, otherwise print-only)
- `--allow-degraded-pass` (allow pass when scanners are unavailable and no threshold findings exist)
- `--dry-run`

## Script Location

Scripts live in `<agent-skills-dir>/security-review/scripts/`. Each agent runtime substitutes `<agent-skills-dir>` with its config directory:
- **Claude**: `.claude/skills`
- **Codex**: `.codex/skills`
- **Gemini**: `.gemini/skills`

If scripts are missing, run `skills/install.sh` to sync them from the canonical `skills/` source.

## Prerequisites

- Python 3.11+
- Optional scanner runtime dependencies:
  - Java 17+ for native OWASP Dependency-Check
  - Podman Desktop (preferred) with Docker CLI compatibility enabled
  - or another Docker-compatible container runtime
- For dependency setup/repair:
  - `<agent-skills-dir>/security-review/scripts/install_deps.sh`
  - `<agent-skills-dir>/security-review/docs/dependencies.md`

## Coordinator Integration (Optional)

Use `docs/coordination-detection-template.md` as the shared detection preamble.

- Detect transport and capability flags at skill start
- Execute hooks only when the matching `CAN_*` flag is `true`
- If coordinator is unavailable, continue with standalone behavior

## Steps

### 0. Detect Coordinator and Run Guardrail Pre-check (Informational)

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_GUARDRAILS=true`, run an informational guardrail pre-check before scanners:

- MCP path: `check_guardrails`
- HTTP path: `scripts/coordination_bridge.py` `try_check_guardrails(...)`

Pre-check target text should summarize intended scan commands and any write actions (report generation paths, temp outputs).

Phase 1 behavior:

- Report violations with category/severity details
- Continue execution without hard-blocking

### 1. Detect Project Profile

```bash
python3 <agent-skills-dir>/security-review/scripts/detect_profile.py --repo <path> --pretty
```

### 2. Build Scanner Plan

```bash
python3 <agent-skills-dir>/security-review/scripts/build_scan_plan.py \
  --repo <path> \
  --zap-target <url-or-spec> \
  --zap-mode baseline \
  --fail-on high \
  --pretty
```

### 3. Check Prerequisites

```bash
<agent-skills-dir>/security-review/scripts/check_prereqs.sh --json
```

If requirements are missing:

```bash
# print-only by default
<agent-skills-dir>/security-review/scripts/install_deps.sh --components java,podman,dependency-check

# execute install commands
<agent-skills-dir>/security-review/scripts/install_deps.sh --apply --components java,podman,dependency-check
```

### 4. Run End-to-End Orchestrator

```bash
python3 <agent-skills-dir>/security-review/scripts/main.py \
  --repo <path> \
  --out-dir docs/security-review \
  --fail-on high \
  --zap-target <url-or-spec> \
  --zap-mode baseline \
  --change <change-id> \
  --bootstrap auto
```

Outputs (default under `<repo>/docs/security-review/`):
- `aggregate.json`
- `gate.json`
- `security-review-report.json`
- `security-review-report.md`
- optional OpenSpec artifact: `openspec/changes/<change-id>/security-review-report.md`

Dry-run behavior:
- `--dry-run` still writes deterministic files under `docs/security-review/`.
- `--dry-run` does **not** overwrite `openspec/changes/<change-id>/security-review-report.md`.

### 5. Interpret Gate

- `PASS`: no findings at/above threshold and scanner execution acceptable.
- `FAIL`: findings met/exceeded threshold.
- `INCONCLUSIVE`: scanner execution incomplete (unless degraded pass is explicitly allowed).
- For DAST-capable profiles, omitting `--zap-target` marks ZAP as unavailable and yields `INCONCLUSIVE` unless `--allow-degraded-pass` is set.

## Manual Scanner Commands (Optional)

Dependency-Check adapter (native or container fallback):

```bash
<agent-skills-dir>/security-review/scripts/run_dependency_check.sh --repo <path> --out <dir>
python3 <agent-skills-dir>/security-review/scripts/parse_dependency_check.py --input <dir>/dependency-check-report.json --pretty
```

ZAP adapter (container runtime):

```bash
<agent-skills-dir>/security-review/scripts/run_zap_scan.sh --target <url-or-spec> --out <dir> --mode baseline
python3 <agent-skills-dir>/security-review/scripts/parse_zap_results.py --input <dir>/zap-report.json --pretty
```

## Quality Checks

```bash
python3 -m pytest <agent-skills-dir>/security-review/tests -q
openspec validate add-security-review-skill --strict
```
