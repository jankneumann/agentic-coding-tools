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

The skill operates in two complementary modes:

- **Preventive mode** (this section, below) — applied while *writing or reviewing code*, before scanners are invoked. Catches whole categories of vulnerability through three-tier boundary rules and an OWASP Top 10 checklist.
- **Scanner-runner mode** (Steps 1–5 below) — applied to a built artifact / running service. Runs OWASP Dependency-Check (SCA) and ZAP (DAST) and applies a deterministic risk gate.

Both modes are mutually reinforcing: the preventive checklist eliminates the easy bugs so the scanners surface the hard ones. Run preventive mode on every change; run scanner-runner mode at integration boundaries.

## Preventive Mode

Adopted from the `security-and-hardening` reference skill. Use this section while authoring or reviewing code that touches authentication, authorization, input validation, secrets, network exposure, or data persistence.

### Three-Tier Boundary System

The boundary system replaces ad-hoc judgment with a tiered policy. Map every security-sensitive operation to one of the tiers below.

#### Tier 1 — Always do (no permission needed)

These are always-correct defaults; deviating from them requires explicit justification in the change description.

- Parameterize every SQL query (use bind variables / `?` placeholders).
- Validate all external input at the system boundary (HTTP handler, CLI parser, MCP tool call) using a schema library (`pydantic` / `zod` / JSON Schema), not deep in business logic.
- Use list-form `subprocess.run([...])` — never `shell=True` with concatenated user data.
- Hash passwords with a slow KDF (bcrypt / argon2 / scrypt). Never store, log, or transmit plaintext passwords.
- Set HTTPS / TLS for all network egress; reject downgrades.
- Prefer the platform's secret manager (env-injected vault token → KV lookup) over reading raw files in source control.
- Apply allow-listing for redirects, file paths, and host headers; reject by default.
- Encode output for the consuming context: HTML escape for browsers, JSON-encode for APIs, log-encode for log lines.

#### Tier 2 — Ask first (requires explicit human approval)

Operations in this tier are sometimes correct but always risky. Pause and request confirmation before proceeding; document the approval in the PR.

- Disabling CSRF, CORS, or auth on an endpoint (even temporarily for debugging).
- Rolling your own crypto (custom hashing, encryption, signing). Default to a vetted library.
- Logging request/response bodies that may contain secrets, PII, tokens, or credentials.
- Granting write access to production data from a non-production environment.
- Adding a new dependency that handles authentication, sessions, or crypto — verify maintenance status and security advisories first.
- Bypassing rate-limiting or input size limits for a "trusted" client.
- Storing user-supplied data in a path constructed from that data (path traversal risk).

#### Tier 3 — Never do (no exceptions, no overrides)

These are absolute prohibitions. Treat any code that crosses these lines as broken and refuse to merge.

- `eval()` / `exec()` / `Function()` on attacker-controlled or external input.
- Hardcoded production secrets, API keys, or private keys in source code or config files.
- Disabling TLS certificate verification in production code (`verify=False`, `rejectUnauthorized: false`).
- SQL string concatenation with user input ("just this once").
- Storing passwords with reversible encryption (or any non-KDF hash like MD5/SHA-1).
- Logging raw passwords, MFA codes, session tokens, or credit-card numbers.
- Sending secrets via URL query parameters (they appear in access logs and Referer headers).
- Returning stack traces or framework error pages to unauthenticated users in production.

### OWASP Top 10 Prevention Checklist

Apply this checklist to every meaningful change. The deeper, item-level guidance lives in `references/security-checklist.md` — use that file as the authoritative source when triaging an audit finding.

1. **A01 — Broken Access Control** — Every endpoint enforces authentication AND authorization (role/ownership checks). Default deny; no IDOR by URL guessing; admin endpoints reject non-admin tokens with 403.
2. **A02 — Cryptographic Failures** — TLS for all transport; KDF for passwords; AES-GCM (or equivalent AEAD) for at-rest encryption; no MD5/SHA-1 for security purposes; no hardcoded keys.
3. **A03 — Injection** — Parameterized SQL; list-form subprocess; output encoding for HTML/log/template contexts; no `eval` / dynamic SQL / `os.system` on user input.
4. **A04 — Insecure Design** — Threat-model the new feature; document the trust boundary; rate-limit by default; design for failure (denial-of-service safety, idempotency).
5. **A05 — Security Misconfiguration** — Production has CSRF + CORS + secure cookies + HSTS + CSP enabled; debug and stack traces disabled; default admin accounts removed; no `.env` in source control.
6. **A06 — Vulnerable & Outdated Components** — Dependency-check / Dependabot is wired in CI (the scanner-runner mode below covers this); pin major versions; review security advisories before upgrading auth/crypto libs.
7. **A07 — Identification & Authentication Failures** — Slow KDF for passwords; account lockout / rate-limit on login; MFA available for high-privilege accounts; session tokens are random, server-side-revocable, and rotate on privilege change.
8. **A08 — Software & Data Integrity Failures** — Verify checksums / signatures of downloaded artifacts; pin CI action versions to a SHA; no auto-update of code from external sources without review.
9. **A09 — Security Logging & Monitoring Failures** — Log auth events (success, failure, lockout, privilege change) with structured fields; alert on anomalies; never log secrets; preserve logs across the incident-response window.
10. **A10 — Server-Side Request Forgery (SSRF)** — Allow-list outbound destinations; reject internal/loopback/metadata IPs (169.254.169.254, 10.0.0.0/8, 127.0.0.1) for user-driven fetches; resolve DNS once and pin the resolved IP for the request.

For the deeper, language-specific checks behind each item, consult `references/security-checklist.md`.

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
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_check_guardrails(...)`

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

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "Dependency-Check passed, so the change is secure" | SCA only catches known-CVE'd dependencies. It says nothing about your authn/authz logic, your input validation, or the shell injection you wrote yesterday. Run preventive mode AND scanner mode. |
| "I'll skip the OWASP checklist — this PR is small" | The most expensive vulnerabilities ship in small PRs (a one-line `verify=False`, a `f"... {user_input} ..."` SQL string). Small PRs are exactly when humans skip review; the checklist exists to compensate. |
| "We don't have a threat model, so I can't tell what tier this falls into" | When in doubt, treat the operation as Tier 2 (ask first). Tier-3 prohibitions (eval, hardcoded secrets, TLS bypass) are absolute and don't require a threat model to recognize. |
| "ZAP scan target isn't deployed yet — I'll skip the scan" | Run preventive mode anyway. ZAP-INCONCLUSIVE is fine for a PR that doesn't add new endpoints; it is not fine when the PR is the new endpoint. Wire ZAP into staging before merge. |
| "The scanner finding is a false positive — I'll suppress it without a note" | Suppressing without a justification (issue link, threat-model reference, compensating-control description) is how real findings get buried. Always document the suppression in the report. |

## Red Flags

- A PR that touches authentication, sessions, or crypto without explicit reference to the OWASP A02/A07 checklist items in the description.
- Any new `subprocess` call with `shell=True` or any new SQL string that includes `f"..."` / `+` / `%` formatting with non-literal data — Tier 3 prohibition.
- `verify=False`, `rejectUnauthorized: false`, or `InsecureRequestWarning` suppression appearing anywhere outside a clearly-labelled local-test fixture — Tier 3 prohibition.
- A new dependency in `package.json` / `pyproject.toml` / `Cargo.toml` that handles auth, crypto, or sessions, without a note in the PR explaining why and confirming it has recent commits and no open critical advisories.
- `gate.json` reports `INCONCLUSIVE` and `--allow-degraded-pass` was applied without a justification in the PR description.
- Logging that emits `request.body`, `headers["Authorization"]`, `request.cookies`, or password-bearing form fields — Tier 2 violation that often slips through review.
- A `.env` file, private key, or `kubeconfig` appearing in `git status` for the PR.

## Verification

1. Confirm preventive mode was applied: every Tier 3 prohibition listed above has been searched (e.g., `rg "shell=True|verify=False|eval\(|exec\("`) and zero violations remain in the PR diff.
2. Confirm the OWASP Top 10 checklist was walked: cite at least one item the PR exercises (e.g., "A03 Injection: all new SQL uses bound parameters at handlers/users.py:42") in the PR description.
3. Confirm the scanner-runner mode produced `gate.json` with `PASS` (or `INCONCLUSIVE` with `--allow-degraded-pass` AND a written justification).
4. Confirm `references/security-checklist.md` was consulted for the relevant item-level checks (cite the section heading) when the change touches an OWASP category.
5. Confirm any Tier 2 operation in the diff has explicit human approval recorded in the PR (review comment or commit trailer).
