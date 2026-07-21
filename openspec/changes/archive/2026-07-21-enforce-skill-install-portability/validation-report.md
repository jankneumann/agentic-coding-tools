# Validation Report: enforce-skill-install-portability

## Verdict

PASS. The canonical payload validates, both generated mirrors sync successfully,
and manifest-declared entry points run in clean consumers with no canonical
`skills/` tree or `agent-coordinator/` source package.

## Evidence

| Gate | Result |
|---|---|
| `openspec validate enforce-skill-install-portability --strict` | PASS |
| `validate_work_packages.py` schema/DAG/locks | PASS |
| `bash skills/install.sh --check` | PASS |
| complete-payload dependency-direction CLI | PASS |
| canonical `install.sh` sync to Claude + agents mirrors | PASS, 65 skills per mirror |
| clean-consumer + shipped Langfuse tests | 10 passed |
| complete installer suite | 18 passed |
| affected validate-feature suites | 98 passed |
| classifier skill + coordinator suites | 60 passed |
| focused P1 portability suites | 169 passed |
| default skills suite | 837 passed |
| changed Python Ruff checks | PASS |
| scoped changed-runtime mypy (10 files) | PASS |
| changed shell `bash -n` checks | PASS |
| `git diff --check` | PASS |

## Behavioral Coverage

- Both `.claude/skills` and `.agents/skills` installs are exercised from a
  temporary consumer without coordinator source or canonical skills paths.
- The manifest probes PR discovery/classification, result validation, provider
  dispatch smoke, prototype outcome collection, and flow validation.
- Static validation covers private coordinator imports, path injection,
  canonical runtime commands, ambiguous bare scripts, manifest completeness,
  smoke-target existence, and escaping/missing Markdown links.
- Langfuse hook registration resolves the concrete installed mirror and its
  shipped runtime uses the Langfuse v4 observation API.
- Coordinator container packaging includes the same canonical shared PR
  classifier used by installed consumers.

## Limitations and Non-Blocking Notes

- Live Docker, Bao, vendor CLI, coordinator HTTP/MCP, and Langfuse service calls
  were not executed because they require external services or credentials.
  Their path/configuration behavior is covered with focused tests.
- Docker port selection retains reservations in a lock-protected persistent
  registry and bind-probes each candidate. An unrelated process can still claim
  a port between probe and Compose bind; the start fails explicitly and releases
  its reservation.
- OpenSpec emitted telemetry DNS warnings after successful local validation;
  the validation command itself exited successfully.
- A broader non-default package sweep observed pre-existing missing archived
  fixtures/source assets. The repository's configured default skills suite is
  green at 834 tests.
