---
name: validate-packages
description: "Validation scripts for work packages, parallel zones, and work results"
category: Infrastructure
tags: [validation, packages, parallel, infrastructure]
user_invocable: false
---

# Validate Packages Infrastructure Skill

Non-user-invocable infrastructure skill that bundles validation scripts for the parallel workflow.

## Scripts

### `<skill-base-dir>/scripts/validate_work_packages.py`

Validates `work-packages.yaml` against the JSON schema.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_work_packages.py" <path-to-work-packages.yaml>
```

**Checks**: schema compliance, depends_on references, DAG cycles, lock key canonicalization
**Exit codes**: 0 = VALID, 1 = INVALID (details on stderr)

This script is deliberately git-free — it validates a file in isolation and is
run against fixtures with no repository. Context-impact checking needs a diff,
so it lives in a sibling script rather than here.

### `<skill-base-dir>/scripts/validate_context_impact.py`

Fails a work package that invalidates derived project context it never declared.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_context_impact.py" <path-to-work-packages.yaml> --base main
python3 "<skill-base-dir>/scripts/validate_context_impact.py" <path> --changed-file docs/guide.md --json
```

**Exit codes**: 0 = VALID, 1 = INVALID, 2 = usage or rule-table error

`--base` resolves changed files with `git diff --name-only <base>...HEAD`, so it
sees **committed** changes only — which is what a pre-merge gate should judge.
While iterating, pass `--changed-file` explicitly (repeatable) to classify
working-tree paths; that path also takes no git dependency at all, which is how
ri-09 will feed it a checkpoint's own file list.

#### Context surfaces

A package declares which surfaces it may invalidate in an optional
`context_impact.surfaces` list. Each surface names the producer that owns
refreshing it, so a declaration is directly actionable:

| Surface | Owning producer / skill |
|---|---|
| `capabilities` | `openspec.projection` |
| `apis` | `api.contracts` |
| `architecture` | `refresh-architecture` |
| `decisions` | `decisions.timeline` |
| `documentation` | `documentation.inventory` |
| `semantic_code` | `code-search` index |

#### Enforcement

The declaration is a *reviewable hint*, never evidence of completeness — a
planner can omit it. The authoritative signal is the package's changed files
(intersected with `scope.write_allow`, minus `scope.deny`) plus the change's
`contracts.openapi.files`, classified by the glob rule table at
`openspec/schemas/context-impact-rules.yaml`.

Enforcement keys off whether the block exists, so the gate can be strict without
a flag day:

| Package state | Implied surface not declared | Result |
|---|---|---|
| has `context_impact` | no rationale | `undeclared` → **exit 1** |
| has `context_impact` | rationale with `approved_by` | `rationalized` → pass |
| has `context_impact` | nothing implied | `declared` → pass |
| no `context_impact` | anything implied | `unmigrated` → pass, reports inferred surfaces |

Declaring is opt-in but one-way: once the block is present it must be complete.
An empty `surfaces: []` is a real "affects nothing" assertion, checked strictly —
not a placeholder. A rationale needs both a non-empty `reason` and a non-empty
`approved_by`, and a rationale for a surface the detector does *not* imply fails
as `spurious_rationale`, so rationales cannot be pre-sprinkled.

`--strict-legacy` promotes `unmigrated` to a failure, so the repository can flip
to full enforcement in one flag once packages are migrated.

#### Rule table

`context-impact-rules.yaml` maps globs to surfaces and is deliberately data, not
code — reviewability is the point of this gate. Every surface must have at least
one rule; a surface with no rule silently stops being detectable, which the test
suite pins. Loading fails on a missing file rather than yielding an empty rule
set.

#### Downstream scope resolution

`context_impact.index_scopes(package)` resolves a package's `scope.read_allow`
and `scope.deny` (deny wins) for semantic indexing and scoped context injection.
It resolves rather than duplicates — adding a parallel copy of the globs under
`context_impact` would create two sources of truth.

### `<skill-base-dir>/scripts/parallel_zones.py`

Validates scope non-overlap for parallel work packages.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/parallel_zones.py" --validate-packages <path> [--json]
```

**Exit codes**: 0 = no overlap, 1 = overlap detected

### `<skill-base-dir>/scripts/validate_work_result.py`

Validates work results against the work-queue-result schema.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_work_result.py" <path-to-result.json>
```

**Exit codes**: 0 = valid, 1 = invalid

### `<skill-base-dir>/scripts/validate_schema.py`

Generic JSON schema validator. When the document it is pointed at is an
architecture artifact, make that artifact current first — validating a stale
graph reports the shape of an analysis nobody is going to act on:

```bash
# Ensure architecture artifacts are current, immediately before the first read.
# `--ensure` is `--check` plus a staged refresh only when the check is not fresh,
# so on an already-fresh checkout it writes nothing. Resolve the interpreter the
# way the Makefile does: the producers and the freshness check must agree about
# which optional grammars are importable, or they report permanent drift.
ARCH_PY="$([ -x skills/.venv/bin/python ] && echo skills/.venv/bin/python || echo python3)"
if "$ARCH_PY" "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --ensure --python "$ARCH_PY"; then
  ARCH_FRESHNESS="ensured"
else
  ARCH_FRESHNESS="DEGRADED"
  echo "DEGRADED: architecture artifacts could not be made current; the last known-good analysis is left intact but unverified. Report every architecture-derived finding below as unverified rather than as current." >&2
fi
```

The ensure call belongs here, in the caller's step, and not inside
`validate_schema.py`: the script takes an explicit document path, is run against
fixtures with no repository, and must keep validating the file it was handed.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_schema.py" <schema-path> <document-path>
```

### `<skill-base-dir>/scripts/architecture_schema.json`

JSON schema for architecture analysis artifacts.
