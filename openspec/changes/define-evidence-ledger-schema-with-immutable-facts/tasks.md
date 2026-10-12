# Tasks — define-evidence-ledger-schema-with-immutable-facts

> Change ID: `define-evidence-ledger-schema-with-immutable-facts` · Roadmap item `evidence-grounded-debugging/ri-01`

**Conventions**

Sizing and ordering:
- No task is L or XL.
- Tasks are ordered TDD-first. Each test task comes before the implementation task that it
  verifies.

References:
- Spec scenarios are cited as `evidence-ledger / "<scenario>"`.
- Design decisions are cited by their D-number from `design.md`.

Tests:
- All tests live in `skills/tests/evidence-ledger/`. Run them with
  `skills/.venv/bin/python -m pytest skills/tests/evidence-ledger -q`, from `skills/`.
- No test may pin `openspec/changes/<id>/`. Use `change_dir()` from `openspec_paths`.

## 1. Schema promotion

- [ ] 1.1 Write the schema drift tests (S)
  - File: `skills/tests/evidence-ledger/test_schema_copies.py`.
  - Spec: `evidence-ledger / "Schema copies stay identical"`, `"Drift test survives archival"`.
  - Contract: `contracts/schemas/evidence-ledger.schema.json`.
  - Design: D2.
  - The test asserts that three copies are byte-identical:
    - the canonical copy;
    - the `install_assets` copy;
    - the change-local draft, located through `change_dir()`.
  - It also asserts that the schema is valid Draft 2020-12.
  - It walks the schema and asserts that every object node sets `additionalProperties: false`.
- [ ] 1.2 Promote the draft schema to its canonical copy (S)
  - Destination: `openspec/schemas/evidence-ledger.schema.json`.
  - Depends on 1.1. Design: D2, D3.
- [ ] 1.3 Promote the draft schema to the skill install_assets copy (S)
  - Destination: `skills/evidence-ledger/install_assets/openspec/schemas/evidence-ledger.schema.json`.
  - Depends on 1.1. Design: D2.

**Checkpoint A:** `pytest skills/tests/evidence-ledger/test_schema_copies.py` passes.

## 2. Single-ledger validation

- [ ] 2.1 Write the valid-fixture tests (S)
  - Fixtures:
    - `fixtures/valid/minimal_facts_only.json`;
    - `fixtures/valid/full_ledger.json`, which contains a variable fact, a control fact, a
      signal, a cited hypothesis, a composite hypothesis and a reverify request;
    - `fixtures/valid/full_ledger.yaml`.
  - Test file: `test_validate.py`.
  - Spec: `evidence-ledger / "Fixture ledger with variable and control facts, a signal and a cited hypothesis validates"`, `"YAML ledger validates identically to JSON"`.
  - Design: D3, D8.
- [ ] 2.2 Write the invalid-fixture tests (M)
  - Fixtures go in `fixtures/invalid/<code>__<case>.json`. There is one fixture per
    violation code in D6. The expected code is read from the filename prefix.
  - Spec, schema scenarios:
    - `evidence-ledger / "Fact missing a provenance field is rejected"`;
    - `"Unknown property is rejected"`;
    - `"Signal referencing a list of facts is rejected"`;
    - `"Signal with an unknown classification is rejected"`.
  - Spec, reference and role scenarios:
    - `"Signal referencing two variable facts is rejected"`;
    - `"Signal referencing a missing fact is rejected"`;
    - `"Hypothesis citing an unknown fact is rejected"`;
    - `"Duplicate id across collections is rejected"`;
    - `"Self-referencing component is rejected"`.
  - Spec, time scenario: `"Inverted time window is rejected"`.
  - Design: D4, D5, D6.
- [ ] 2.3 Implement the module loader (S)
  - Function: `load_ledger` in `skills/evidence-ledger/scripts/evidence_ledger.py`. It loads
    JSON or YAML by suffix.
  - Depends on 2.1. Design: D8.
- [ ] 2.4 Implement schema validation (S)
  - Function: `validate_ledger`, using a `Draft202012Validator` over the `install_assets`
    schema.
  - Errors are sorted deterministically. Each error is reported as `schema_violation` with a
    pointer path.
  - Depends on 2.1, 2.2. Design: D2, D6.
- [ ] 2.5 Implement semantic checks (M)
  - Checks:
    - duplicate ids;
    - fact references;
    - signal roles and same-fact pairs;
    - hypothesis components;
    - reverify targets and replacements;
    - timestamp parse and order.
  - Depends on 2.2, 2.4. Design: D4, D5, D6.

**Checkpoint B:** `test_validate.py` passes.

## 3. Revision immutability

- [ ] 3.1 Write the revision tests (S)
  - File: `test_revision.py`, with revision-pair fixtures under `fixtures/revisions/`.
  - Spec:
    - `evidence-ledger / "In-place edit of a recorded fact is rejected"`;
    - `"Same dispute expressed as reverify request plus new fact is accepted"`;
    - `"Removing a recorded fact is rejected"`;
    - `"Hypothesis status change is accepted"`.
  - Design: D6, D7.
  - The test also covers reverify removal or mutation, and `ledger_id` changes.
- [ ] 3.2 Implement check_revision (S)
  - Compares facts and reverify requests by canonical JSON.
  - Depends on 3.1. Design: D6, D7.

## 4. CLI

- [ ] 4.1 Write the CLI tests (S)
  - File: `test_cli.py`. It runs the script with `subprocess`.
  - Exit-code cases:
    - a valid ledger exits 0;
    - an invalid ledger exits 1;
    - a `--previous` edited-fact pair exits 1;
    - the reverify pair exits 0;
    - a missing file exits 2.
  - `--json` output has the expected shape, and output is deterministic across two runs.
  - Spec: `evidence-ledger / "Unreadable ledger exits with code 2"`, `"In-place edit of a recorded fact is rejected"`.
  - Design: D9.
- [ ] 4.2 Implement the `validate` CLI subcommand (S)
  - Depends on 4.1, 3.2. Design: D9.

**Checkpoint C:** the full `skills/tests/evidence-ledger` suite passes. Ruff is clean on the
new module and tests.

## 5. Skill packaging

- [ ] 5.1 Write the SKILL.md contract test (S)
  - File: `test_skill_md.py`.
  - The test asserts:
    - the frontmatter has a `name` and a `category`;
    - `user_invocable` is false;
    - SKILL.md documents every violation code in the module's `VIOLATION_CODES`;
    - SKILL.md documents the reserved `source_unavailable` kind;
    - SKILL.md uses `<skill-base-dir>` paths, with no canonical `skills/` runtime path.
  - Design: D1, D6.
- [ ] 5.2 Write `skills/evidence-ledger/SKILL.md` (S)
  - Depends on 5.1. Design: D1, D3, D7, D9.
- [ ] 5.3 Register the skill in the install manifest (S)
  - Edit `skills/install-manifest.json`, with `distribution: portable`.
  - Verified by `skills/tests/install_sh` manifest-catalog test. Design: D1.
- [ ] 5.4 Register the test directory in shared testpaths (S)
  - Edit `skills/pyproject.toml`.
  - Verified by `skills/tests/ci_coverage`. Design: D10.
- [ ] 5.5 List the skill in workflow docs (S)
  - Add it under Infrastructure Skills in `docs/guides/workflow.md`.

**Checkpoint D:** the following all pass:
- `openspec validate define-evidence-ledger-schema-with-immutable-facts --strict`;
- `skills/tests/ci_coverage`;
- the install-manifest catalog test;
- the evidence-ledger suite.
