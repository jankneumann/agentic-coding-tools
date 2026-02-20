---
name: security-review
description: Run reusable cross-project security review with profile detection, OWASP Dependency-Check, ZAP Docker, and risk-gated reporting
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

## Script Layout Convention

All executable helper scripts for this skill live in `skills/security-review/scripts/`.

## Prerequisites

- Python 3.11+
- Optional scanner runtime dependencies:
  - Java 17+ for native OWASP Dependency-Check
  - Docker for ZAP and Dependency-Check Docker fallback
- For dependency setup/repair:
  - `skills/security-review/scripts/install_deps.sh`
  - `skills/security-review/docs/dependencies.md`

## Steps

### 1. Detect Project Profile

```bash
python skills/security-review/scripts/detect_profile.py --repo <path> --pretty
```

### 2. Build Scanner Plan

```bash
python skills/security-review/scripts/build_scan_plan.py \
  --repo <path> \
  --zap-target <url-or-spec> \
  --zap-mode baseline \
  --fail-on high \
  --pretty
```

### 3. Check Prerequisites

```bash
skills/security-review/scripts/check_prereqs.sh --json
```

If requirements are missing:

```bash
# print-only by default
skills/security-review/scripts/install_deps.sh --components java,docker,dependency-check

# execute install commands
skills/security-review/scripts/install_deps.sh --apply --components java,docker,dependency-check
```

### 4. Run End-to-End Orchestrator

```bash
python skills/security-review/scripts/main.py \
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

### 5. Interpret Gate

- `PASS`: no findings at/above threshold and scanner execution acceptable.
- `FAIL`: findings met/exceeded threshold.
- `INCONCLUSIVE`: scanner execution incomplete (unless degraded pass is explicitly allowed).
- For DAST-capable profiles, omitting `--zap-target` marks ZAP as unavailable and yields `INCONCLUSIVE` unless `--allow-degraded-pass` is set.

## Manual Scanner Commands (Optional)

Dependency-Check adapter:

```bash
skills/security-review/scripts/run_dependency_check.sh --repo <path> --out <dir>
python skills/security-review/scripts/parse_dependency_check.py --input <dir>/dependency-check-report.json --pretty
```

ZAP adapter:

```bash
skills/security-review/scripts/run_zap_scan.sh --target <url-or-spec> --out <dir> --mode baseline
python skills/security-review/scripts/parse_zap_results.py --input <dir>/zap-report.json --pretty
```

## Quality Checks

```bash
python -m pytest skills/security-review/tests -q
openspec validate add-security-review-skill --strict
```
