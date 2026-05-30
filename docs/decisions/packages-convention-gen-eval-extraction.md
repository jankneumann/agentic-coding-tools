# ADR: `packages/` convention and gen-eval extraction

**Date:** 2026-05-30  
**Status:** accepted  
**Change:** `extract-gen-eval-package`  
**Design file:** `openspec/changes/extract-gen-eval-package/design.md`

---

## Context

The `gen-eval` framework (~6.5 KLOC, 23 Python files) lived inside
`agent-coordinator/evaluation/gen_eval/` — an in-tree subdirectory of the
coordinator service.  This arrangement created three problems:

1. **Reuse friction.**  External consumers (e.g. `agentic-assistant`) that
   wanted gen-eval had to clone the entire coordinator repo and add it to
   `sys.path`.  There was no installable package.

2. **Coupling.**  Skills and tools referenced `python -m evaluation.gen_eval`
   and `from evaluation.gen_eval import ...`, making the import path a
   deployment detail that bled into all call sites.

3. **Docker build complexity.**  The coordinator's Dockerfile used
   `context: agent-coordinator` so it could only see files under that
   directory — making it impossible to co-locate the framework with its
   consumer without keeping both under the coordinator root.

---

## Decision

**Establish a `packages/` convention in this monorepo** for shared Python
libraries that are consumed by multiple first-party services or skills.

Apply it immediately to gen-eval:

- Move framework code to `packages/gen-eval/src/gen_eval/`.
- Declare a PEP 621 `pyproject.toml` with `uv_build` backend and optional
  extras (`mcp`, `sdk`, `db`, `all`).
- Consumer (`agent-coordinator`) declares a path dependency via
  `[tool.uv.sources]`:
  ```toml
  gen-eval = { path = "../packages/gen-eval" }
  ```
- Rebuild coordinator's Docker image from a repo-root build context
  (`docker build -f agent-coordinator/Dockerfile .`) so both
  `agent-coordinator/` and `packages/gen-eval/` are in-context.
- Per-project consumer data (descriptors, manifests, scenarios) stays in
  `agent-coordinator/evaluation/` — only framework code and package-shipped
  fixtures move to `packages/gen-eval/`.

---

## Consequences

**Good:**

- **Installable by any consumer** via `uv add 'gen-eval @ ../agentic-coding-tools/packages/gen-eval'`
  with no source tree surgery.
- **Clean import boundary** — `gen_eval.*` is the public namespace; the
  legacy `evaluation.gen_eval.*` path is removed and any mistaken use
  fails loudly at import time.
- **Skills stay simple** — `python -m gen_eval --descriptor ...` works
  regardless of which repository the skill runs in, as long as `gen-eval`
  is installed in the active venv.
- **Docker build is straightforward** — `COPY packages/gen-eval/ ...` in the
  Dockerfile resolves because the build context is repo root.

**Neutral:**

- **One-time Railway dashboard change required** — Source > Root Directory
  must be changed from `agent-coordinator` to `/` before the new Dockerfile
  context works in Railway CI.  Documented in `agent-coordinator/railway.toml`
  and `agent-coordinator/README.md`.

**Accepted cost:**

- **`packages/` grows over time** — this convention should only be applied
  to libraries with genuine multi-consumer demand.  Single-consumer libraries
  belong inside their consumer directory.
- **uv path-dep is non-editable by default** — changes to `packages/gen-eval/`
  require `uv sync --reinstall-package gen-eval` to take effect in dependent
  venvs.  This is intentional (D5): non-editable installs ensure the runtime
  Docker image stage contains a self-contained wheel, not a `.pth` pointing at
  a source tree that doesn't exist in the runtime container.

---

## Alternatives considered

**Keep gen-eval in-tree.**  Rejected: the reuse and import-coupling problems
remain; external consumers still can't install it.

**Publish to PyPI.**  Future option; premature at this stage.  The relative
path dependency is sufficient for the monorepo use-case and is supported by
both `uv` and `pip -e`.

**Git submodule.**  Too heavyweight for a library in the same monorepo.
