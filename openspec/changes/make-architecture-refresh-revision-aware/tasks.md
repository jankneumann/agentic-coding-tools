# Tasks: Make Architecture Refresh Revision-Aware

> Change ID: `make-architecture-refresh-revision-aware`
> Dependency: `add-durable-context-refresh-records`
> Selected approach: architecture provenance adapter over `project-context-runtime`

## 1. Publish the Architecture Contract

- [x] 1.1 Write failing contract tests for architecture provenance plus canonical
  ri-06 `ProducerResult` integration. **Size: S**
  **Spec scenarios:** architecture-refresh.1, architecture-refresh.6,
  architecture-refresh.10
  **Contracts:** `contracts/architecture-provenance.schema.json`; ri-06
  `context-refresh-types.schema.json`
  **Design decisions:** D1, D5
  **Dependencies:** ri-06 installed schemas/runtime
- [x] 1.2 Publish the architecture provenance schema under `openspec/schemas/`; make
  contract tests pass without copying shared operation/result schemas. **Size: S**
  **Dependencies:** 1.1
- [x] Checkpoint: run contract tests; review the diff; verify scope.

## 2. Make Repository Artifacts Deterministic and Checkable

- [x] 2.1 Write failing tests for input discovery, fingerprints, producer versions,
  deterministic timestamps, stable JSON, and mtime independence. **Size: M**
  **Spec scenarios:** architecture-refresh.1, architecture-refresh.2,
  architecture-refresh.3, architecture-refresh.5
  **Contracts:** `contracts/architecture-provenance.schema.json`
  **Design decisions:** D1, D2, D3
  **Dependencies:** 1.2
- [x] 2.2 Implement architecture provenance utilities; migrate committed artifact
  writers to deterministic metadata/serialization. **Size: M**
  **Dependencies:** 2.1
- [x] 2.3 Write failing runner tests for staged generation, read-only check output,
  precise drift reasons, quick/full identity, and last-known-good recovery. **Size: M**
  **Spec scenarios:** architecture-refresh.4, architecture-refresh.5,
  architecture-refresh.6, architecture-refresh.7, architecture-refresh.8
  **Contracts:** `contracts/architecture-provenance.schema.json`
  **Design decisions:** D2, D4
  **Dependencies:** 2.2
- [x] Checkpoint: run provenance/runner tests; review the diff; verify producer scope.
- [x] 2.4 Implement stage/validate/promote plus `--check`; emit architecture provenance
  and require it in `affected_tests.py`. **Size: M**
  **Dependencies:** 2.3
- [x] 2.5 Add regression tests for byte-identical reruns, artifact-only convergence,
  mtime touches, and changed/added/removed inputs. **Size: M**
  **Spec scenarios:** architecture-refresh.3, architecture-refresh.3b,
  architecture-refresh.4, architecture-refresh.5, architecture-refresh.7,
  architecture-refresh.9
  **Contracts:** `contracts/architecture-provenance.schema.json`
  **Design decisions:** D2, D3, D4
  **Dependencies:** 2.4
- [x] Checkpoint: run refresh-architecture tests; inspect fixtures; verify no drift.

## 3. Adapt Architecture Status to project-context-runtime

- [x] 3.1 Write failing adapter tests for canonical operation reuse, cross-process
  architecture-result reads, retryable producer updates, and non-finalization of the
  whole operation. **Size: M**
  **Spec scenarios:** architecture-refresh.10, architecture-refresh.11,
  architecture-refresh.12, architecture-refresh.13
  **Contracts:** ri-06 `context-refresh-operation.schema.json` and
  `context-refresh-types.schema.json`
  **Design decisions:** D5, D6
  **Dependencies:** ri-06 runtime; 1.2
- [x] 3.2 Implement the architecture adapter using only the supported
  `project-context-runtime` facade; remove module-local status ownership. **Size: M**
  **Dependencies:** 3.1
- [x] 3.3 Write failing coordinator-client tests for projected status, additive
  provenance, deprecated arguments, malformed shared records, and safe fallback.
  **Size: S**
  **Spec scenarios:** architecture-refresh.14, architecture-refresh.15
  **Contracts:** `contracts/architecture-provenance.schema.json`; ri-06 canonical
  types
  **Design decisions:** D6, D7
  **Dependencies:** 3.2
- [x] Checkpoint: run adapter/RPC/client tests; inspect canonical records; verify no
  architecture-specific ledger exists.
- [x] 3.4 Update the RPC/client compatibility facade while preserving legacy fields,
  status strings, and sentinel failure behavior. **Size: S**
  **Dependencies:** 3.3

## 4. Integrate and Document the Producer

- [x] 4.1 Write end-to-end tests for generate → canonical producer result →
  cross-process projected status → check, including failure recovery. **Size: M**
  **Spec scenarios:** architecture-refresh.4, architecture-refresh.8,
  architecture-refresh.9, architecture-refresh.11, architecture-refresh.13
  **Contracts:** `contracts/architecture-provenance.schema.json`; all ri-06 runtime
  contracts
  **Design decisions:** D1, D4, D5, D6
  **Dependencies:** 2.5, 3.4
- [x] 4.2 Add check/skill entry points; document provenance, shared runtime ownership,
  projected status, and remediation. **Size: S**
  **Dependencies:** 4.1
- [x] 4.3 Run strict OpenSpec/schema validation plus producer, affected-test, adapter,
  RPC, and coordinator-client suites. **Size: S**
  **Dependencies:** 4.2
- [x] Checkpoint: review every requirement; run verification; confirm no task is XL.

## Task Sizing Summary

- S: 1.1, 1.2, 3.3, 3.4, 4.2, 4.3
- M: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 4.1
- L: none
- XL: none

All behavior changes follow failing tests. Checkpoints occur after at most three
implementation tasks.
