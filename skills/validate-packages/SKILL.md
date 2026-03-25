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

### scripts/validate_work_packages.py

Validates `work-packages.yaml` against the JSON schema.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_work_packages.py" <path-to-work-packages.yaml>
```

**Checks**: schema compliance, depends_on references, DAG cycles, lock key canonicalization
**Exit codes**: 0 = VALID, 1 = INVALID (details on stderr)

### scripts/parallel_zones.py

Validates scope non-overlap for parallel work packages.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/parallel_zones.py" --validate-packages <path> [--json]
```

**Exit codes**: 0 = no overlap, 1 = overlap detected

### scripts/validate_work_result.py

Validates work results against the work-queue-result schema.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_work_result.py" <path-to-result.json>
```

**Exit codes**: 0 = valid, 1 = invalid

### scripts/validate_schema.py

Generic JSON schema validator.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/validate_schema.py" <schema-path> <document-path>
```

### scripts/architecture_schema.json

JSON schema for architecture analysis artifacts.
