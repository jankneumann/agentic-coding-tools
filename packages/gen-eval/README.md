# gen-eval

Generator-evaluator framework for agentic-system testing.

`gen-eval` runs scenario-driven behavioral tests against live services (HTTP
APIs, MCP tools, CLI commands, database state) and emits structured verdicts.
It is provider-neutral: generators can be template-driven, LLM-backed via the
CLI, or SDK-driven; evaluators compose pluggable transport clients.

---

## Install

`gen-eval` is **not published to PyPI**; it ships as a path dependency
consumed by sibling repos in the same workspace. Install with `uv add`
pointing at the package directory:

```bash
# Base — template-only test runs, no fastmcp dependency
uv add 'gen-eval @ ../agentic-coding-tools/packages/gen-eval'

# With the MCP service surface (FastMCP / coordinator integration)
uv add 'gen-eval[mcp] @ ../agentic-coding-tools/packages/gen-eval'

# Everything (sdk + mcp + db extras)
uv add 'gen-eval[all] @ ../agentic-coding-tools/packages/gen-eval'
```

Adjust the relative path to match your repo's checkout of
`agentic-coding-tools` (siblings, parent, etc.). For a containerized consumer
that ships gen-eval inside its own image, see
[Running gen-eval inside your own container](#running-gen-eval-inside-your-own-container)
below.

### Extras

| Extra  | Pulls in                | When you need it |
|--------|-------------------------|------------------|
| `mcp`  | `fastmcp`               | Expose gen-eval via FastMCP or consume from a coordinator. |
| `sdk`  | `anthropic`, `openai`   | LLM-backed scenario generators (sdk-only mode). |
| `db`   | `asyncpg`               | DB state verification in scenarios. |
| `all`  | all of the above        | One-line "give me everything". |

Confirm the install:

```bash
python -c "import gen_eval; print(gen_eval.__version__)"
```

---

## Quickstart

See [examples/agentic-assistant-quickstart.md](examples/agentic-assistant-quickstart.md)
for a step-by-step walkthrough: install, create a descriptor, run scenarios,
read the report.

---

## Public API summary

### CLI

Two equivalent forms — the installed console script and the module path:

```bash
gen-eval --descriptor <path> [options]        # console script
python -m gen_eval --descriptor <path> [...]  # module form
```

| Flag | Default | Description |
|------|---------|-------------|
| `--descriptor PATH` | required | Path to interface descriptor YAML. |
| `--mode` | `template-only` | `template-only`, `cli-augmented`, or `sdk-only`. |
| `--categories` | all | Limit to specific scenario categories. |
| `--parallel` | 5 | Concurrent scenario execution. |
| `--max-iterations` | 1 | Feedback loop iterations. |
| `--fail-threshold` | 0.95 | Minimum pass rate to exit 0. |
| `--report-format` | `both` | `markdown`, `json`, or `both`. |
| `--output-dir` | `.` | Directory for report files. |
| `--no-services` | off | Skip service startup/teardown. |
| `--min-coverage` | 0 | Minimum interface coverage to exit 0, as a **percent** (0–100). Unlike `--fail-threshold`, which is a rate — values between 0 and 1 are rejected as a usage error rather than read as a sub-1% floor. |
| `--print-contract-version` | — | Print the JSON Schema contract version and exit 0. |

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | Pass rate met `--fail-threshold` and coverage met `--min-coverage`. |
| `1` | Either gate failed, **or no scenarios were evaluated**, **or the descriptor declared no interfaces**. |
| `2` | Argparse usage error (e.g. missing `--descriptor`). |
| `64` | `--openspec-change` failed validation (`EX_USAGE`). |

Two vacuous-success guards are explicit rather than left to threshold
arithmetic, because no threshold can express either one:

- **Zero scenarios evaluated** always exits `1`, regardless of
  `--fail-threshold`.
- **A descriptor declaring zero interfaces** always exits `1`. `coverage_pct`
  is covered ÷ declared, so an empty surface reports `0.0` and satisfies every
  floor at or below zero — the same exit as a suite that exercised everything.
  Both numerator and denominator are empty, so lowering or raising a floor
  cannot separate the two states.

The pass-rate and coverage gates are otherwise independent, and a failure
message names every gate that tripped. An operator told `FAIL (100.0% <
95.0%)` when the real problem is coverage goes looking in the wrong place.

### Python

```python
# Top-level re-exports (via gen_eval.__init__)
from gen_eval import run_evaluation                    # async pipeline runner
from gen_eval.descriptor import load_descriptor       # archetype-aware loader
from gen_eval import InterfaceDescriptor              # the legacy flat document
from gen_eval import ServiceDescriptor, ToolDescriptor  # the two archetypes
from gen_eval.models import Scenario, Step            # data models
from gen_eval.evaluator import Evaluator              # verdict producer
from gen_eval.orchestrator import GenEvalOrchestrator # full pipeline
from gen_eval.openspec_seed import parse_openspec_change  # spec parser
from gen_eval.metrics import GenEvalMetrics           # result dataclass
from gen_eval.findings_emitter import emit_findings   # findings writer
```

### MCP service (requires `[mcp]` extra)

```python
from gen_eval.mcp_service import get_gen_eval_service, GenEvalMCPService

service = get_gen_eval_service()          # module-level singleton
service = GenEvalMCPService(base_dir=...) # explicit data dir

await service.list_scenarios(category="lock-lifecycle")
await service.validate_scenario(yaml_content)
await service.create_scenario(category, name, ...)
await service.run_evaluation(mode="template-only", ...)
```

The MCP service reads scenario data from the directory set by:

1. `base_dir` constructor argument.
2. `GEN_EVAL_DATA_DIR` environment variable.
3. Fallback: `Path(__file__).parent` (for package-internal fixtures).

---

## Contract-derived descriptors

A descriptor names the interfaces gen-eval measures coverage against. Where
that list comes from decides what coverage can mean.

**Hand-authored** — the original form, still supported. The declared surface is
whatever someone typed. That makes drift between it and the implementation
undetectable by construction: a flag added without a descriptor entry is not
uncovered, it is invisible, and coverage stays at 100% of a surface that no
longer describes the program. Loading one now emits a `DeprecationWarning`
naming the generator to use. It is deprecated, not removed, and removal will
get its own notice.

**Contract-derived** — the descriptor is generated from a machine-readable
contract and says so:

```yaml
contract: ../../openspec/contracts/my-tool/cli/my-tool.yaml
```

The contract is the source; introspection only *verifies* against it. That
direction matters: if introspection populated the declared surface, an
uninstalled or broken tool would derive an empty one and then report full
coverage of nothing.

### Two archetypes

|  | Ground truth | Coverage unit | Lifecycle |
|---|---|---|---|
| `ServiceDescriptor` | OpenAPI contract | operation × surface | starts services |
| `ToolDescriptor` | CLI contract (`cli-contract.schema.json`) | flag, positional, named subcommand | starts nothing |

The unit is the point of the split. Counting *commands* reports a surface of
one for a flat CLI that declares nothing testable — which is how gen-eval's own
dogfood ran at `0 interfaces` and passed its coverage assertion for free. The
flag is what a flat CLI can be named by.

For a service, coverage is keyed on the **operation**, with per-surface
`exposed` and `covered` recorded separately. One operation published on HTTP,
MCP and CLI and exercised once is covered — not one-third covered — and a
surface that does not expose an operation is not a gap.

```bash
python scripts/generate_tool_descriptor.py            # write the artifact
python scripts/generate_tool_descriptor.py --check    # CI drift gate
```

`--check` fails on three things: the artifact drifting from the contract, the
derivation producing an *empty* declared surface, and the unit count
disagreeing with the contract's. The first is the obvious one; the other two
exist because an empty artifact would otherwise compare equal to an empty
derivation forever.

Load a descriptor with `load_descriptor()`, which dispatches on the document's
own shape. Loading a derived descriptor through the base `InterfaceDescriptor`
silently discards exactly the fields that make it derived, so it arrives
declaring nothing.

### Coverage floors

The 80% interface-coverage floor applies to **service** descriptors. For a
**tool** descriptor the gate is completeness, not a percentage: every
contracted coverage unit is either exercised by a scenario or listed in an
exclusions file with a written reason.

A percentage answers the wrong question here. "84% covered" does not say
whether the missing 16% is `--verbose` or `--fail-threshold`. It is also
frequently unreachable — gen-eval's own suite would need 14 of its 17 flags
exercised, and a gate that can never pass gets disabled as fast as one that can
never fail. See `evaluation/coverage-exclusions.yaml` for the shape, and
`scripts/check_coverage_completeness.py` for the gate.

---

## Descriptor path conventions

Paths inside descriptor YAML files are resolved **relative to the descriptor
file's parent directory**, matching the convention used by npm, pip, and
docker (the file is the anchor, not the invoking process's CWD). This
applies to `scenario_dirs`.

Concretely, if your descriptor lives at `evaluation/descriptors/foo.yaml`
and scenarios at `evaluation/scenarios/`, declare:

```yaml
scenario_dirs:
  - ../scenarios/
```

Absolute paths are left untouched.

---

## Projects with nothing to start

`startup` is **optional**. Omit the block entirely for a CLI-only surface, or
for services managed out-of-band:

```yaml
project: my-cli
version: "1.0"
services:
  - name: my-cli
    type: cli
    command: my-tool
scenario_dirs:
  - scenarios
# no startup: block — there is nothing to start
```

When absent, the orchestrator skips startup, health check, seeding and
teardown.

This used to be required, which forced such projects to invent a
`StartupConfig` they never used. The health check made it worse than three
inert strings: it runs even under `--no-services` (to verify
externally-managed services are reachable), so the placeholder `health_check`
had to be a URL that genuinely *succeeded*. Those placeholders read as
meaningful configuration to the next person to open the file.

`--no-services` remains the right flag for the *different* case where a
startup block exists but the operator has already started the services.

---

## Dogfooding

gen-eval evaluates its own CLI surface:

```bash
make -C packages/gen-eval dogfood
```

Eight scenarios under [`evaluation/`](evaluation/README.md) drive the
installed console script through the descriptor loader, template generator,
CLI transport, evaluator and report writer. Runs at `--fail-threshold 1.0`
and gates CI.

This exists because the unit suite imports `gen_eval` and drives Python
objects — a shape that cannot catch packaging defects. The console script
named by `[project.scripts]` was broken in every release while 551 tests
passed, because none of them had ever executed the installed executable.

`evaluation/README.md` also records the findings the suite surfaced, including
one framework bug it caught and fixed.

---

## Running gen-eval inside your own container

`gen-eval` is portable inside slim runtime images (e.g. `python:3.14-slim`):

- **No `curl` required** — health checks use stdlib `urllib.request`.
- **No `docker-compose` required** when invoked with `--no-services` — the
  orchestrator skips `startup`/`teardown` commands and assumes the operator
  has started services out-of-band (the health check still runs, so an
  unreachable service is still caught).
- **`file://` health-check URLs** are accepted (treats a successful open
  with no HTTP status as healthy), useful for test fixtures.

This means you can `pip install`/`uv add` gen-eval into a service container
and call its CLI or HTTP/MCP surface from within that container without
pulling in shell dependencies or running a nested Docker daemon.

### In-container loopback authentication

If your service exposes a `/run-evaluation`-style endpoint that spawns the
gen-eval CLI to call back into the **same service's** HTTP API (the pattern
used by `agent-coordinator`'s `/gen-eval/run`), set the
`COORDINATION_API_KEY`-equivalent client-side env var that your descriptor's
`auth.env_var` declares. Without it, all loopback requests get `401`. For
agent-coordinator this means:

```yaml
# docker-compose.yml — coordinator service
environment:
  COORDINATION_API_KEYS: "${COORDINATOR_API_KEYS:-dev-key-001}"   # server allowlist
  COORDINATION_API_KEY: "${COORDINATOR_CLIENT_API_KEY:-dev-key-001}"  # client cred
```

Apply the same pattern for your own consumer: server-side allowlist + a
matching client-side credential the CLI subprocess can pick up.

---

## Report artifacts

`gen-eval-report.md` — human-readable scenario verdicts  
`gen-eval-report.json` — machine-readable structured results  
`findings-gen-eval.json` — review-findings schema-conformant failures  
`gen-eval-metrics.json` — metrics for pipeline integration  

---

## Versioned schema contract

gen-eval publishes JSON Schema documents for its three public data shapes, so
a consumer can validate its descriptor, its scenarios, and the reports it
receives **without installing gen-eval**. Schema conformance and runtime
availability are deliberately decoupled.

```
src/gen_eval/contracts/
  VERSION                            # contract version, one line
  interface-descriptor.schema.json   # generated from descriptor.InterfaceDescriptor
  scenario.schema.json               # generated from models.Scenario
  eval-report.schema.json            # generated from reports.GenEvalReport
```

The files ship in the wheel *and* are readable straight from the repo or a raw
URL. Pin the version, then validate with nothing but the stdlib and a JSON
Schema validator:

```python
import json, urllib.request
from jsonschema import Draft202012Validator

BASE = ("https://raw.githubusercontent.com/jankneumann/agentic-coding-tools"
        "/main/packages/gen-eval/src/gen_eval/contracts")

schema = json.load(urllib.request.urlopen(f"{BASE}/eval-report.schema.json"))
assert schema["x-gen-eval-contract-version"] == "2"          # pin the contract
Draft202012Validator(schema).validate(json.load(open("gen-eval-report.json")))
```

If gen-eval *is* installed, load them from the package instead of vendoring:

```python
from gen_eval.contracts import CONTRACT_VERSION, load_schema

assert CONTRACT_VERSION == "2"
Draft202012Validator(load_schema("eval-report")).validate(report_data)
```

To assert the contract version of an arbitrary gen-eval on `PATH`:

```bash
test "$(gen-eval --print-contract-version)" = "2"
```

### Regenerating

All four artifacts are generated from the pydantic models that actually
produce and consume the data:

```bash
python scripts/generate_contract_schemas.py            # rewrite in place
python scripts/generate_contract_schemas.py --check    # exit 1 on drift
```

`--check` runs in CI and is asserted by `tests/test_contract_schemas.py`, so a
model change that is not reflected in the published schema fails the build.

Bump `CONTRACT_VERSION` in `src/gen_eval/contracts/__init__.py` on any
*breaking* change — a field removed, made required, or narrowed in type.
Adding an optional field does not require a bump.

---

## Layout

```
packages/gen-eval/
  pyproject.toml           # PEP 621, uv_build backend, extras
  Makefile                 # dogfood / test / lint / contracts
  README.md                # you are here
  evaluation/              # gen-eval's dogfood suite for gen-eval
  scripts/                 # schema + descriptor generators, coverage gate
  src/gen_eval/
    __init__.py            # public re-exports
    __main__.py            # gen-eval console script + python -m gen_eval
    contracts/             # published JSON Schema contract + VERSION
    descriptor.py          # InterfaceDescriptor / ToolDescriptor + load_descriptor
    service_descriptor.py  # ServiceDescriptor — the OpenAPI-derived archetype
    openapi.py             # the OpenAPI reader both the extractor and verifier share
    verify/                # per-surface subset verifiers (excess detection)
    models.py              # Scenario, Step data models
    evaluator.py           # verdict producer
    orchestrator.py        # end-to-end pipeline
    generator.py           # template generator
    hybrid_generator.py    # CLI + template hybrid
    openspec_seed.py       # OpenSpec WHEN/THEN parser
    metrics.py             # GenEvalMetrics dataclass
    findings_emitter.py    # findings-gen-eval.json writer
    mcp_service.py         # optional [mcp] FastMCP service
    clients/               # transport clients (http, cli, mcp, wait)
    ...
  tests/
    fixtures/              # sample descriptors shipped with the package
    test_smoke.py          # import resolution smoke
    test_public_api_parity.py
    ...
  examples/
    agentic-assistant-quickstart.md  # adoption walkthrough
    descriptor-template.yaml        # annotated copy-and-adapt template
```

---

## Links

- Spec: `openspec/specs/gen-eval-framework/`
- Change: `openspec/changes/extract-gen-eval-package/`
- Design decisions: `openspec/changes/extract-gen-eval-package/design.md`
