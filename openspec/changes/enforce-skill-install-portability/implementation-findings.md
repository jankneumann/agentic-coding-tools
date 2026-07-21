# Implementation Review Findings

## Review 1 — Installed-payload contract

- The first manifest draft dynamically probed only the five known-safe regression
  entry points. The final consumer gate also compiles every shipped Python file in
  both generated mirrors, while static validation scans every runtime-bearing
  payload file. Optional-dependency and side-effect modules remain intentionally
  excluded from eager import.
- Remaining executable references to canonical `skills/` paths were found in
  Playwright dispatch and several skill instructions. Runtime references now use
  the installed skill base; intentional source-checkout maintenance is explicitly
  identified as source-only.
- The manifest now declares installed OpenSpec assets and cross-skill dependencies,
  and validation rejects missing dependency targets and undeclared sibling use.
- `setup-coordinator` now requires `COORDINATOR_DIR` only for local administration;
  web mode relies on the public coordination URL.
- P1 work-package verification paths and output artifacts were corrected to match
  the implemented files.

Verdict: all blocking contract findings resolved.

## Review 2 — Runtime correctness

- Process-scoped port locks would have disappeared when the launch command exited.
  Docker validation now keeps reservations in a lock-protected, file-backed
  registry until teardown, with bind probes for unrelated local processes.
- Dependency gates now cover canonical `skills/.venv`, `skills/install.sh`, and
  `skills/shared/*` runtime references across the complete installed payload.
- Stack status no longer resolves a Compose file when it only needs persisted
  environment state.
- The shipped Langfuse hook and installation metadata now consistently target the
  Langfuse v4 observation API.

Verdict: all blocking runtime findings resolved.

## Deliberate review resolutions

- A blanket ban on `Path.parents[N]` was not adopted because installed sibling
  discovery legitimately uses bounded parent traversal. The gates instead reject
  coordinator-source injection and runtime references that escape the manifest
  boundary.
- Dynamic import of every Python file was not adopted because some skill modules
  intentionally require optional executables, services, or import-time context.
  Full-payload compilation plus static closure validation covers those files, and
  the manifest retains behavioral probes for safe public entry points.

No unresolved P0 or P1 implementation finding remains.
