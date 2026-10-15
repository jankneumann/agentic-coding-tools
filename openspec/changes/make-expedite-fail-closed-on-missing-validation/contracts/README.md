# Contracts: make-expedite-fail-closed-on-missing-validation

No contract sub-types apply to this change:

- **OpenAPI:** none — `expedite.py` is a local CLI with no HTTP surface.
- **Database:** none.
- **Events:** none.

The only interface change is the CLI's JSON verdict, which gains an `overrides`
list (`[{check, reason}]`, always present, empty by default) and the
`--accept-missing-validation "<reason>"` flag. That shape is specified normatively
in `specs/expedite/spec.md` ("Recorded Override for a Missing Validation Report")
and pinned by `skills/expedite/scripts/tests/test_expedite.py`; there are no
code consumers of the JSON today, so a separate schema file would have no reader.
