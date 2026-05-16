# Security Review — add-coordinator-task-status-renderer

**Date**: 2026-05-16
**Reviewer**: autopilot VALIDATE phase (single-vendor opus, preventive-mode)
**Scope**: `git diff origin/main..HEAD -- skills/coordinator-task-status-renderer skills/plan-feature .githooks .gitignore`
**Driver**: complexity-gate-injected `security-review` checkpoint
**Branch context**: main (operator-approved deferred branch dance — autopilot operating on main for this run)

## Result: **PASS** with two informational notes

No HIGH or CRITICAL findings. Zero Tier 3 prohibitions violated.

## Preventive Mode — OWASP & Three-Tier Audit

### Tier 3 prohibitions (grep across all new/modified lines)

| Check | Result |
|---|---|
| `shell=True` | None |
| `eval()` / `exec()` / `Function()` | None |
| `verify=False` / `rejectUnauthorized: false` | None |
| Hardcoded API keys / private keys | None |
| SQL string concat with user input | N/A — no SQL touched |

### Tier 1 controls verified

- All `subprocess.run` invocations use **list-form** with hardcoded `["git", "rev-parse", "--show-toplevel"]` — no user input flows into the argv.
- External input (CLI `--change-id`) validated against `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` at entry points (regression tests in `test_renderer_rejects_path_traversal_change_id`, `test_seeder_rejects_path_traversal_change_id`).
- Coordinator-returned content (issue titles, assignees, close-reasons) is sanitized via `_sanitize_inline()` — neutralizes newlines, tabs, and embedded marker tokens to prevent managed-block escape (regression tests `test_renderer_sanitizes_marker_injection_in_title`, `test_renderer_sanitizes_newlines_in_assignee_and_reason`).
- No new dependencies introduced.

### OWASP Top 10 walk

| Item | Status |
|---|---|
| A01 Access Control | N/A — no auth/authz logic added |
| A02 Cryptographic Failures | N/A — no crypto introduced |
| A03 Injection | ✅ Mitigated. Markdown injection via coordinator content sanitized; path traversal in `--change-id` validated; no shell injection (list-form subprocess; hook scripts use parameter quoting on user-controlled vars) |
| A04 Insecure Design | ✅ Trust boundary: coordinator data treated as semi-trusted (sanitized for managed-block context). Failure mode (coordinator down) emits stale marker with sidecar idempotency, never blocks git ops |
| A05 Misconfiguration | ✅ `.gitignore` updated to exclude `.tasks-status.state.json` sidecar (prevents secret-state leak into git history) |
| A06 Vulnerable Components | ✅ No new dependencies |
| A07 Auth Failures | N/A — no auth logic |
| A08 Integrity Failures | ✅ Renderer reads from authenticated coordinator (existing transport security); no external artifact ingestion |
| A09 Logging Failures | ✅ Grep confirmed no token/secret/password fields in log strings |
| A10 SSRF | N/A — coordinator URL is env-config, not user input. The renderer only hits the coordinator. |

## Scanner Mode — Scoped Out (with rationale)

| Scanner | Decision | Reason |
|---|---|---|
| OWASP Dependency-Check (SCA) | Not run | Zero new dependencies in this PR. Repo-wide SCA scan would surface noise unrelated to the change. |
| ZAP DAST (baseline/api/full) | Not run | Change introduces no HTTP endpoint, web UI, or deployed service. ZAP has no target. |

Documenting deferral rather than silently skipping. If a future PR adds an HTTP-facing component (e.g., the `GET /issues/by-change/<id>` convenience endpoint mentioned in `proposal.md` as a follow-up), that PR's security review SHOULD include ZAP.

## Informational Notes (not findings — for traceability)

**N1: shellcheck SC2086 disabled in hooks**
`.githooks/pre-commit:85` and `.githooks/post-merge:60` use `$RENDER_CMD "$change_id"` with unquoted expansion (shellcheck SC2086 disabled by explicit comment). The unquoted part is the binary path itself, constructed from a fixed allowlist of venv locations under `$REPO_ROOT`. If `$REPO_ROOT` contained whitespace, the unquoted expansion would word-split incorrectly — robustness concern, not an injection vector. Disposition: **accept** for v1; revisit if the convention of "no spaces in checkout path" is ever relaxed.

**N2: `COORDINATOR_TASK_STATUS_RENDERER` env var as renderer override**
The hooks honor a `COORDINATOR_TASK_STATUS_RENDERER` env var (documented as test seam in `contracts/README.md`). An operator with shell access who sets this env var can have arbitrary code execute on `git commit`. This is **not** a vulnerability — anyone who can set env vars can already run arbitrary code as that user — but the documentation should explicitly state: "DO NOT set in CI environments or shared dev shells where the operator does not control the hook target."  Disposition: **defer** — minor doc improvement, not security-blocking.

## Verification

- ✅ Tier 3 grep clean (all five categories)
- ✅ OWASP A03/A04/A05 covered with regression tests
- ✅ No secrets in `git status` / `git diff`
- ✅ `references/security-checklist.md` consulted for A03 (Injection: list-form subprocess at handlers/seed_tasks_from_md.py:208 and render_tasks_status.py:361)
- ✅ All findings dispositioned

## Recommendation

**Proceed to SUBMIT_PR.** No security blockers. Informational notes N1+N2 belong in PR-description "Concerns" section so reviewers see the trade-offs.
