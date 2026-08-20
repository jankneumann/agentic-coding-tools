# Contracts — make-setup-coordinator-script-backed

## Sub-types evaluated

| Sub-type | Applicable | Reason |
|---|---|---|
| OpenAPI | No | The change introduces no HTTP surface. It consumes `GET /health` on an existing coordinator, but defines no endpoint. |
| Database | No | No schema, no migration, no persisted state. |
| Events | No | Emits no events. |
| Type generation | No | No cross-language consumers. |
| **CLI output schema** | **Yes** | `harness-report.schema.json` — see below. |

## Why a CLI output schema is the canonical contract here

The spec requires every subcommand to accept `--json` and emit a single JSON
document. That document is the coordination boundary: it is what `SKILL.md`
narrates against, what tests assert on, and what any future caller
(`/vendor-status`, a dispatcher daemon, the GX10 host-provisioning flow) would
consume. Leaving it unspecified would make "emits JSON" untestable beyond
"parses as JSON".

The same convention was used by `add-deterministic-context-drift-gates`, which
placed its gate-report schema in the `openapi` contract slot because the change
had no HTTP surface either.

## Load-bearing constraint encoded in the schema

`state` is a closed enum of exactly four values, and `unknown` is a first-class
member rather than a variant of `config_missing`. This is design decision D5: a
vendor whose credentials live outside a detectable dotfile (antigravity, which
has no `agy login`) must not be reported as unconfigured, because doing so emits
a remediation instruction for a command that does not exist.

`checked_validity` is `const: false`. Presence detection never verifies that a
credential is valid or unexpired, and the contract states this rather than
leaving consumers to assume otherwise.
