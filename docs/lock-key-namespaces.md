# Lock Key Namespaces

The coordinator's `file_locks.file_path` column stores both raw file paths and logical resource lock keys. Logical keys use namespace prefixes to distinguish them from file paths. Both types share the same `acquire_lock`/`release_lock`/`check_locks` API — the coordinator treats the string as an opaque resource key.

## Namespace Reference

| Prefix | Format | Normalization Rule | Example |
|--------|--------|--------------------|---------|
| *(none)* | Repo-relative path | No leading slash, no trailing whitespace | `src/api/users.py` |
| `api:` | `api:<METHOD> <PATH>` | Method uppercase, single space, path normalized | `api:GET /v1/users` |
| `db:migration-slot` | Literal | Only one migration package at a time | `db:migration-slot` |
| `db:schema:` | `db:schema:<table>` | Lowercase identifiers | `db:schema:users` |
| `event:` | `event:<channel>` | Dot-separated, lowercase | `event:user.created` |
| `flag:` | `flag:<namespace>` | Slash-delimited, lowercase | `flag:billing/*` |
| `env:` | `env:<resource>` | For non-port shared resources only | `env:shared-fixtures` |
| `contract:` | `contract:<path>` | Contract artifact lock | `contract:openapi/v1.yaml` |
| `feature:` | `feature:<id>:<purpose>` | Feature-level coordination lock | `feature:FEAT-123:pause` |

## Usage in Work Packages

Work packages declare locks in two categories:

```yaml
locks:
  files:
    - src/api/users.py        # Raw file path
    - src/api/routes.py
  keys:
    - "api:GET /v1/users"     # Logical lock
    - "db:schema:users"
  ttl_minutes: 120
  reason: "Backend API implementation"
```

Both types are acquired via `acquire_lock(file_path=<key>)` and released via `release_lock(file_path=<key>)`.

## Canonicalization Rules

All lock keys are validated at `work-packages.yaml` validation time:

- **File paths**: Must be repo-relative (no leading `/`), no trailing whitespace.
- **`api:` keys**: Method must be uppercase (`GET`, `POST`, etc.), exactly one space between method and path, path starts with `/`.
- **`db:schema:` keys**: Table name must be lowercase alphanumeric with underscores.
- **`event:` keys**: Channel name must be dot-separated lowercase.
- **`flag:` keys**: Namespace must be slash-delimited lowercase.
- **`env:` keys**: Resource name must not be a port number (use `allocate_ports()` for ports).
- **`contract:` keys**: Path must match an entry in `contracts.openapi.files` or a generated artifact path.
- **`feature:` keys**: Must follow `feature:<id>:<purpose>` format where purpose is a known value (e.g., `pause`).

## Validation Regex

The JSON Schema pattern for logical lock keys:

```
^(api|db|event|flag|env|contract|feature):.+$
```

File paths match the `FilePath` pattern:

```
^(?!/)(?!.*\s+$).+
```

## Port Allocation

Port allocation uses `allocate_ports(session_id)` (coordinator primitive with TTL refresh), **not** `env:` lock keys. The `env:` namespace is reserved for non-port shared resources like test fixtures or shared temporary directories.

## Policy Requirements

Policy rules must permit the logical lock key patterns. Agents attempting to acquire a key with an unrecognized prefix will receive an `operation_not_permitted` failure. The permitted pattern is:

```
^(api|db|event|flag|env|contract|feature):.+$
```

## Feature Pause Lock

The `feature:<id>:pause` lock key is a stop-the-line coordination mechanism. When acquired by the orchestrator:

1. All in-flight work package agents check for this lock before starting work (B2) and before finalizing results (B9).
2. If the lock exists and is not owned by the checking agent, the agent stops and waits.
3. The orchestrator releases the lock after handling the escalation (contract revision bump, plan revision bump, etc.).

Example:

```
acquire_lock(
  file_path="feature:FEAT-123:pause",
  reason="handling escalation: contract revision bump",
  ttl_minutes=120
)
```
