# Security Checklist

A compact, language-agnostic checklist cited by `security-review`, `code-review-and-quality`, and any skill that touches secrets, authentication, input validation, or network exposure. Adapted from OWASP Top 10 (2021) prevention guidance.

Use this as a checkbox lint pass before merging.

## Input validation (boundary-only)

- [ ] All user input is validated at the system boundary (HTTP handler, CLI parser, MCP tool call), not deep in business logic.
- [ ] Validation uses a schema library (`pydantic`/`zod`/JSON Schema) rather than ad-hoc `if` chains.
- [ ] Numeric inputs are bounded (min/max); string inputs have max length and allowed-character constraints.
- [ ] File path inputs are normalized and rejected if they escape an allowed root (`Path.resolve()` + prefix check; not just `..` blocking).
- [ ] Untrusted data from external systems (browser DOM, third-party APIs, MCP responses) is treated as adversarial — never `eval`'d, never used as a command/URL/template.

## Injection (SQL, command, template, log)

- [ ] All SQL uses parameterized queries (`?` / named binds) — never string-format SQL with user data.
- [ ] Subprocess calls use list-form args (`subprocess.run([...])`), not `shell=True` with concatenated strings.
- [ ] Template rendering escapes by default; raw HTML is opt-in and reviewed.
- [ ] Log messages use structured fields, not f-strings with user input (prevents log injection / log forging).

## Authentication & session

- [ ] Passwords stored with a memory-hard hash (Argon2id, bcrypt cost ≥12); never plaintext, never SHA-256 alone.
- [ ] Session tokens are random ≥128 bits, set `HttpOnly` + `Secure` + `SameSite=Lax`.
- [ ] Failed-login attempts are rate-limited per identifier AND per source IP.
- [ ] Multi-factor recovery flows are themselves rate-limited and require the recovery factor (don't downgrade to email-only after MFA).

## Authorization (access control)

- [ ] Every mutating endpoint checks the caller's authorization on the resource — not just authentication.
- [ ] IDs in URLs/payloads are scoped: `GET /users/<id>` checks that the requested `<id>` belongs to (or is visible to) the caller.
- [ ] Default-deny: new endpoints require explicit allow; never `if user.is_admin: skip`.

## Secrets

- [ ] No secrets in source files (`grep -i "password\|secret\|api_key\|token" $(git diff --cached --name-only)` returns nothing actionable).
- [ ] Secrets loaded from environment variables or a secret manager (OpenBao/Vault, KMS) at process start.
- [ ] `.env`, `.env.local`, `*.pem`, `*.key` are in `.gitignore`.
- [ ] Rotated secrets do not require redeployment of dependent services (use short-lived tokens or a refresh mechanism).

## Cross-site (web only)

- [ ] CSRF protection on every state-changing endpoint that uses cookie-based auth.
- [ ] CSP header set with no `unsafe-inline` for scripts.
- [ ] User content rendered as HTML uses an allow-list sanitizer (DOMPurify, bleach).

## Dependencies

- [ ] `npm audit` / `pip-audit` / `cargo audit` runs in CI; high+critical vulnerabilities block merge.
- [ ] Direct dependencies pinned to a minor version; transitive resolved via lockfile (no floating `latest`).
- [ ] When a dependency vulnerability has no patch, document the residual risk in `docs/decisions/`.

## Crypto

- [ ] No custom crypto. Use `cryptography`, `libsodium`, or platform primitives.
- [ ] AES-GCM (or ChaCha20-Poly1305) for symmetric; never AES-ECB; never AES-CBC without HMAC.
- [ ] Random for security uses `secrets.token_bytes()` / `crypto.randomBytes()` — never `random` / `Math.random`.

## Logging & observability

- [ ] Sensitive fields (tokens, PII, payment data) are redacted before logging — even in error stack traces.
- [ ] Failed authentication, authorization, and validation events are logged with enough context to alert on (but never the secret itself).
- [ ] Log output is rate-limited or sampled to avoid log-storm DoS via crafted bad input.

## Network exposure

- [ ] New ports/endpoints are documented and reviewed against the threat model.
- [ ] Internal-only services bind to `127.0.0.1` or a private network; never `0.0.0.0` by default.
- [ ] HTTPS everywhere — no plaintext HTTP for anything carrying credentials, tokens, or PII.
