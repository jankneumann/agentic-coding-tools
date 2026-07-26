# Implementation review resolution

Independent implementation review found one blocker and five high-severity
integrity, contract, and reliability defects. All were repaired before the
branch was published:

- the CocoIndex adapter hashes and decodes one final byte read against the
  exact planned Git-blob digest;
- decisive storage verification, table locking, rename, and registry manifest
  publication share one fenced transaction;
- direct SQL inserts receive the same ready, compatible, non-legacy parent
  validation as updates;
- configured registry connection failures return ephemeral `failed`, while
  only missing configuration returns `not_configured`;
- garbage collection excludes indexes referenced as incremental parents in
  both selection and atomic claim;
- the custom embedder supplies a canonical memo key, float32 vector schema, and
  declared dimension to the pinned CocoIndex API.

Regression tests were added for each defect. The complete package suite passes
252 tests with seven explicit live-resource skips; the relevant coordinator
migration suites pass 14 tests with five live-Postgres skips. Ruff, source
Pyright, architecture lint, strict OpenSpec validation, work-package
validation, and `git diff --check` pass.

The live ParadeDB/embedder scenarios remain environment-deferred, not silently
skipped: they require an explicit opt-in, acknowledged scratch DSN, and
explicit provider configuration.

An independent post-repair re-audit checked all six findings against the
implementation and regression tests and reported no remaining blocker or
high-severity issue.
