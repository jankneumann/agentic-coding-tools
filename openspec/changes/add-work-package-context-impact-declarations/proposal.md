# Add Work-Package Context Impact Declarations

Roadmap item **ri-08** of `project-context-refresh-lifecycle`
(capability: *Add work-package context-impact checkpoints*).

## Why

A work package already declares *what files it may touch* (`scope.write_allow`)
and *what it may read* (`scope.read_allow`). It declares nothing about which
**derived project context** it invalidates. So when a package lands, nobody —
human or agent — knows whether `docs/`, `openspec/specs/`, the architecture
graph, the decision index, the API contract inventory, or the semantic index are
now stale.

ri-05 gave us deterministic producers that can *detect* drift and ri-07 gave us
an orchestrator that can *refresh* it. Both operate on the whole repository after
the fact. What is missing is the planning-time counterpart: a per-package,
reviewable declaration of intended context impact, plus a check that catches the
packages which forgot to declare one.

The declaration alone is not trustworthy — a planner can simply omit it. So the
declaration is a **reviewable hint**, and changed-file plus contract analysis is
the **detector**. The check compares the two and fails when the detector implies
a surface the package never declared and never justified.

## What Changes

1. **Schema.** `work-packages.schema.json` gains an optional `context_impact`
   block on every work package: the surfaces it may affect, and an optional
   per-surface rationale for a surface the detector will flag.

2. **Detector.** A new `context_impact.py` in the `validate-packages` skill maps
   a package's changed files and the change's contract files onto the six
   context surfaces using a reviewable glob rule table, then diffs implied
   against declared.

3. **Gate.** A new `validate_context_impact.py` CLI fails when a package with a
   `context_impact` block omits an implied surface without an approved
   rationale. Packages with **no** block are reported as `unmigrated` with the
   inferred surfaces spelled out — a compatibility result, not a hard failure,
   until `--strict-legacy` is passed.

4. **Downstream scope exposure.** `index_scopes()` resolves each package's
   effective `read_allow` / `deny` globs so ri-12's scoped context injection and
   the ri-01/ri-02 semantic index can query with the planner's own boundaries
   instead of re-deriving them.

5. **Template + docs.** The `feature-workflow` work-packages template carries a
   commented `context_impact` example; `validate-packages/SKILL.md` documents
   the new script and surfaces.

## Surfaces

The six surfaces are pinned to the producers that own them, so a declaration is
directly actionable — refreshing surface *S* means running producer *P*.

| Surface | Owning producer / skill | Introduced by |
|---|---|---|
| `capabilities` | `openspec.projection` | ri-05 |
| `apis` | `api.contracts` | ri-05 |
| `architecture` | `refresh-architecture` | ri-04 |
| `decisions` | `decisions.timeline` | ri-05 |
| `documentation` | `documentation.inventory` | ri-05 |
| `semantic_code` | `code-search` index | ri-01 / ri-02 |

## Impact

- **Affected specs:** `skill-workflow` (owns the work-package contract and DAG
  scheduling requirements).
- **Affected code:** `skills/validate-packages/` (new detector + CLI + tests),
  `skills/validate-packages/install_assets/openspec/schemas/work-packages.schema.json`,
  `skills/plan-feature/install_assets/openspec/schemas/feature-workflow/templates/work-packages.yaml`,
  plus the `install.sh`-regenerated copies under `openspec/schemas/`.
- **Backward compatibility:** `context_impact` is optional and every existing
  `work-packages.yaml` in the repo validates unchanged. The detector's default
  mode never fails a package that predates the field.

## Out of Scope

- **Running the producers.** This change infers impact from paths and contracts
  only. Executing ri-05 `check` producers to confirm real drift is ri-10
  (`add-deterministic-context-drift-gates`).
- **Branch-local checkpoints.** Generating the per-package checkpoint report and
  the revision-isolated index is ri-09
  (`add-branch-local-context-checkpoints`), which consumes this declaration.
- **Consuming the scopes.** ri-12 injects scoped semantic context into coding
  jobs; ri-08 only exposes the resolver.
