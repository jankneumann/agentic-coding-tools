# Contracts: reject-vacuous-worker-results-in-the-package-executor

The only contract this change touches is the existing work-queue result schema,
`openspec/schemas/work-queue-result.schema.json`, and its installed copy under
`skills/parallel-infrastructure/install_assets/openspec/schemas/`. Both copies must
stay byte-identical.

The changes to it are additive and optional, and `schema_version` stays `1`:

- top level: `outcome`, one of `PASS`, `ISSUES` or `BLOCKED`;
- `VerificationStepResult`: `method`, one of `executed`, `ci`, `inspected` or `not_run`.

No other contract sub-type applies:

- **OpenAPI:** none. The package executor, validator, scheduler and orchestrator
  are local Python modules. The coordinator stores the result payload opaquely.
- **Database:** none.
- **Events:** none.

The rest of the interface change is in-process Python:

- `PackageAcceptance` and `accept_package_result`;
- `mark_completed(package_id, acceptance)`;
- `record_package_result(..., acceptance=None)`;
- the gate status `blocked_not_passing` and the gate response's `not_passing` and
  `overrides`.

It is specified normatively in `specs/parallel-infrastructure/spec.md` and pinned by
the co-located tests and `skills/tests/parallel-infrastructure/test_vacuous_results.py`.
