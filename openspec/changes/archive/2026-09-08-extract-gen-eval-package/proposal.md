# Extract gen-eval into a reusable package

## Why

`gen-eval` is a ~6.5 KLOC generator-evaluator framework that currently lives **only** inside `agent-coordinator/evaluation/gen_eval/`. It has no `pyproject.toml`, no published distribution surface, and no formal extraction. The canonical home at the repo root (`evaluation/gen_eval/`) was carved out months ago but holds only a sample descriptor and a stub fixtures dir — the framework was never actually moved into a shareable location.

This is real architectural debt with two consequences:

1. **Sibling repos can't reuse the framework.** A recent session in `agentic-assistant` (the original prompt for this change) confirmed it: any other repo that wants gen-eval would have to copy-paste the 23 Python files. That's exactly the failure mode the shared-component strategy is meant to prevent.
2. **The pattern for future extractions is undefined.** `agentic-coding-tools` is conceptually a *coordinator service + shared component libraries*. Planned future extractions include simulation (Hoverfly), prompt optimization, harness optimization, and the vendor convention skills (Railway / Neon / FalkorDB / Postgres) which are library-shaped today but trapped inside skill directories. This change establishes the `packages/<name>/` convention that all of them will follow.

The current state also obscures gen-eval's quality: it isn't bloat (the 6.5 KLOC maps to real functional layers — evaluator, judge, 4 generator backends, 5 transport clients, OpenSpec integration, MCP service, reports, findings emitter, scaffolding). The size is correct for what it does. The *packaging* is wrong.

## What Changes

This change executes a **full cutover** in a single atomic change:

1. **Create `packages/gen-eval/`** as a new top-level monorepo location with a proper `pyproject.toml` (uv-based build). Module name remains `gen_eval`.
2. **Move all framework code** (23 `.py` files, ~6.5 KLOC) from `agent-coordinator/evaluation/gen_eval/` into `packages/gen-eval/src/gen_eval/`. Delete the source tree at the old location.
3. **Resolve the one reverse coupling**: `evaluation/metrics.py` (which contains `GenEvalMetrics`) is moved *into* the package as `gen_eval/metrics.py` — it is gen-eval-specific by name and only consumed by gen-eval's `reports.py`.
4. **Repurpose `agent-coordinator` as a consumer**. Its `pyproject.toml` adds `gen-eval = { path = "../packages/gen-eval", extras = ["mcp"] }` (workspace-style path dep). All in-tree imports `from evaluation.gen_eval import …` become `from gen_eval import …`. The lazy MCP service imports in `coordination_api.py` and `coordination_mcp.py` update accordingly.
5. **Split framework vs. consumer data**:
   - **Package keeps**: `schemas/` (gen-eval's own response schemas), `dtu/` (scaffolding templates), and a minimal example descriptor + fixtures in `packages/gen-eval/tests/fixtures/`.
   - **`agent-coordinator` keeps** (as project-local fixtures): its `descriptors/agent-coordinator.yaml`, all 15 `manifests/*.manifest.yaml`, and the full `scenarios/` tree (~150 YAML files). These move to `agent-coordinator/evaluation/descriptors/`, `evaluation/manifests/`, `evaluation/scenarios/` — alongside (not inside) the dependency.
6. **Optional MCP extra**. `packages/gen-eval/pyproject.toml` declares `[project.optional-dependencies] mcp = ["fastmcp>=…"]`. Pure-Python consumers (e.g., `agentic-assistant`) install bare `gen-eval`; MCP consumers (e.g., `agent-coordinator`) install `gen-eval[mcp]`. The MCP service module is conditionally importable.
7. **Update Dockerfile**. `agent-coordinator/Dockerfile` line 38 (`COPY evaluation/ /app/evaluation/`) is replaced with the appropriate package install via `uv sync`, plus a `COPY evaluation/` for the *remaining* per-project descriptors / manifests / scenarios (no longer the framework code).
8. **Update every skill that invokes gen-eval**:
   - `skills/gen-eval/SKILL.md`: `python -m evaluation.gen_eval` → `python -m gen_eval`
   - `skills/validate-feature/SKILL.md`: same
   - `skills/playwright-validator/SKILL.md`: `from evaluation.gen_eval.openspec_seed import …` → `from gen_eval.openspec_seed import …`
   - `skills/gen-eval-scenario/SKILL.md`: no change (uses MCP tool, which is namespace-stable)
   - All runtime mirrors (`.claude/skills/`, `.agents/skills/`) regenerated via `bash skills/install.sh --mode rsync --deps none --python-tools none`.
9. **Ship `packages/gen-eval/examples/agentic-assistant-quickstart.md`** — a concrete adopter walkthrough showing the `uv add` command, the per-project descriptor template, and one scenario run end-to-end. This documents the consumer contract without forcing a cross-repo PR into this change's done definition. The actual `agentic-assistant` adoption is a follow-up in that repo.
10. **CI**: extend `.github/workflows/ci.yml` to run gen-eval's own test suite under `packages/gen-eval/` (the package gets its own pytest run, not just the coordinator's).

**Out of scope (deliberately not in this change):**
- Publishing `gen-eval` to PyPI. Relative-path installs cover the immediate need; PyPI publishing is a follow-up if/when an external (non-Jan-owned) repo wants it.
- Setting up a uv workspace at the repo root (parent `pyproject.toml` listing `packages/*` as members). Useful when there are 2+ packages; defer until the second extraction lands.
- Extracting other future packages (Hoverfly, prompt optimization, etc.). This change establishes the convention; the other packages each get their own change.
- Migrating `agentic-assistant` to use the new package. Tracked as a follow-up in that repo.

## Approaches Considered

### Approach 1 — Full cutover into `packages/gen-eval/` (Recommended)

**Description.** New top-level `packages/` directory; full code move from `agent-coordinator/evaluation/gen_eval/` into `packages/gen-eval/src/gen_eval/`; `agent-coordinator` re-installs gen-eval as a path dependency with `[mcp]` extra; per-project descriptors/manifests/scenarios stay in the coordinator as fixtures; optional MCP extra serves both MCP-routing and pure-Python consumers; documentation includes a quickstart for the agentic-assistant adoption path.

**Pros.**
- Establishes the `packages/<name>/` convention with one example, at the lowest possible cost (one extraction is much cheaper to introduce a convention with than three).
- Single source of truth: no in-tree copy to drift from the package version.
- Optional `[mcp]` extra cleanly serves the two consumer profiles in the ecosystem (coordinator wants MCP, agentic-assistant wants pure Python).
- "Code in agentic-coding-tools, config in consumer repo" — the data split matches the stated architectural intent verbatim.
- Sets the precedent that future extractions (Hoverfly, prompt opt, vendor conventions) will follow.

**Cons.**
- Largest single-change diff (~30 file moves + Dockerfile + 4 skill updates + pyproject changes in two places).
- agentic-assistant adoption is unproven inside this change — only the quickstart doc and the coordinator migration prove that consumers can install it; the doc could be subtly wrong.
- One small dependency inversion: gen-eval's `coordinator.py` makes optional HTTP calls back to agent-coordinator. The package retains that integration as a soft (graceful-degradation) coupling; it does not import `agent_coordinator` Python code.

**Effort.** M — large diff but mechanical; no algorithmic work.

### Approach 2 — Phased: extract framework first, migrate coordinator in a follow-up

**Description.** This change creates `packages/gen-eval/` populated with a copy of the framework code and its own `pyproject.toml`. The in-tree `agent-coordinator/evaluation/gen_eval/` stays in place, marked deprecated. A follow-up change migrates the coordinator to depend on the new package and deletes the in-tree copy.

**Pros.**
- Smallest per-change risk; coordinator behavior is bit-for-bit unchanged.
- agentic-assistant could adopt the new package immediately, before the coordinator migration lands.
- Easier to reason about — extraction and migration are two separate review surfaces.

**Cons.**
- Two sources of truth for an unknown window (drift window). Any bug fixed in one location has to be back-ported to the other.
- The convention isn't really set until the coordinator actually uses the package — until then, "packages/" is aspirational.
- Doubles total work (this change + follow-up change), and the follow-up change has all the same skill / Dockerfile updates as Approach 1 anyway — just deferred.

**Effort.** S (this change) + M (follow-up) = larger total than Approach 1.

### Approach 3 — Use `evaluation/gen_eval/` at repo root as the package home

**Description.** Reuse the existing carved-out empty `evaluation/gen_eval/` at the repo root. Add a `pyproject.toml` there. Move the .py files from `agent-coordinator/evaluation/gen_eval/` into it. Otherwise identical to Approach 1.

**Pros.**
- No new top-level directory.
- Preserves the existing skill descriptor-discovery glob (`find . -path "*/evaluation/gen_eval/descriptors/*.yaml"`) — fewer skill updates required.
- Honors the original intent of the empty carve.

**Cons.**
- **Namespace ambiguity during cutover.** `evaluation/gen_eval/` at repo root vs. `agent-coordinator/evaluation/gen_eval/` (same name, different depths) — `python -m evaluation.gen_eval` from the repo root is ambiguous; IDEs may resolve to the wrong copy.
- The directory name `evaluation/` is single-purpose. The next planned extraction (Hoverfly simulation) doesn't fit there, so a `packages/` (or equivalent) convention has to be invented later anyway — meaning this option doesn't actually avoid the new convention, it just defers it.
- The existing `evaluation/gen_eval/descriptors/sample-frontend.yaml` and `fixtures/` would have to be either deleted or relocated; they're sample data, not framework code, and they mix awkwardly with a `src/` directory.
- Reuses the descriptor discovery pattern that has been the source of "which evaluation/gen_eval/ — root or coordinator?" confusion.

**Effort.** M — same code-move cost as Approach 1, plus the existing-content untangling.

## Selected Approach

**Approach 1 — Full cutover into `packages/gen-eval/`.** Confirmed via Gate 1 discovery questions with the following decisions:

- **Package layout**: `packages/gen-eval/` (the new top-level `packages/` convention) — chosen because the repo will host multiple future shared libraries (Hoverfly simulation, prompt optimization, harness optimization, vendor convention packages). Establishing the convention with one extraction is cheaper than retrofitting with three.
- **Data split**: framework-only in the package; descriptors/manifests/scenarios stay in `agent-coordinator` as project-local fixtures. Matches the architectural intent "code in agentic-coding-tools, configuration in consumer repos".
- **MCP surface**: optional `[mcp]` extra inside the package. `agent-coordinator` installs `gen-eval[mcp]`; `agentic-assistant` and other pure-Python consumers install bare `gen-eval`. Single package, two consumer profiles.
- **Cutover scope**: full cutover in one atomic change. Delete the in-tree copy; update agent-coordinator's pyproject, Dockerfile, and lazy imports; update all skills that invoke `python -m evaluation.gen_eval`.
- **External adoption proof**: ship `packages/gen-eval/examples/agentic-assistant-quickstart.md` only — no cross-repo PR in this change's done definition. The real agentic-assistant adoption is a follow-up change in that repo.

## Impact

- **Affected specs**: `gen-eval-framework` — MODIFIED to reflect the new module location and packaging contract. The behavioral requirements (descriptor schema, scenario execution model, transport clients, verdicts) are unchanged; only the import path and distribution contract change.
- **Affected code**:
  - `agent-coordinator/evaluation/gen_eval/` → moved out (deleted).
  - `agent-coordinator/evaluation/{descriptors,manifests,scenarios}/` → relocated from inside gen_eval/ (these stay; only the framework moves).
  - `agent-coordinator/evaluation/metrics.py` → moved into the package as `gen_eval/metrics.py` (only consumed by gen-eval's `reports.py`).
  - `agent-coordinator/evaluation/__init__.py` → simplified or deleted (no more `from . import gen_eval`).
  - `agent-coordinator/pyproject.toml` → drops the `gen-eval` optional-deps stub; adds `gen-eval = { path = "../packages/gen-eval", extras = ["mcp"] }` as a regular dep.
  - `agent-coordinator/Dockerfile` → updates the `COPY evaluation/` line to cover only the remaining per-project data.
  - `agent-coordinator/src/coordination_api.py` and `coordination_mcp.py` → update lazy imports from `from evaluation.gen_eval.mcp_service` to `from gen_eval.mcp_service`.
  - `packages/gen-eval/` → new directory with `pyproject.toml`, `src/gen_eval/`, `tests/`, `examples/`, `README.md`.
  - `skills/gen-eval/SKILL.md`, `skills/validate-feature/SKILL.md`, `skills/playwright-validator/SKILL.md` → updated invocations; mirrors regenerated.
  - `.github/workflows/ci.yml` → adds gen-eval package test job.
  - `docs/decisions/` → new ADR documenting the packages/ convention and the gen-eval extraction.
- **Affected consumers** (not in this change but enabled by it): `agentic-assistant` (and any future repo) can now `uv add ../agentic-coding-tools/packages/gen-eval` and use the framework without copy-paste.
