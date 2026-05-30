# gen-eval

Generator-evaluator framework for agentic-system testing.

`gen-eval` runs scenario-driven behavioral tests against live services (HTTP
APIs, MCP tools, CLI commands, database state) and emits structured verdicts.
It is provider-neutral: generators can be template-driven, LLM-backed via the
CLI, or SDK-driven; evaluators compose pluggable transport clients.

---

## Install profiles

| Profile | Install command | Use case |
|---------|-----------------|----------|
| Base    | `uv add gen-eval` | Template-only test runs; no `fastmcp` dependency. |
| MCP     | `uv add 'gen-eval[mcp]'` | Expose gen-eval via FastMCP or consume it from a coordinator. |

Additional extras: `sdk` (Anthropic/OpenAI SDK generators), `db` (asyncpg for
DB state verification), `all` (everything).

Install from the repo using a relative path:

```bash
uv add 'gen-eval @ ../agentic-coding-tools/packages/gen-eval'
```

---

## Quickstart

See [examples/agentic-assistant-quickstart.md](examples/agentic-assistant-quickstart.md)
for a step-by-step walkthrough: install, create a descriptor, run scenarios,
read the report.

---

## Public API summary

### CLI

```bash
python -m gen_eval --descriptor <path> [options]
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

### Python

```python
# Top-level re-exports (via gen_eval.__init__)
from gen_eval import run_evaluation                    # async pipeline runner
from gen_eval.descriptor import InterfaceDescriptor   # descriptor loader
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

## Report artifacts

`gen-eval-report.md` — human-readable scenario verdicts  
`gen-eval-report.json` — machine-readable structured results  
`findings-gen-eval.json` — review-findings schema-conformant failures  
`gen-eval-metrics.json` — metrics for pipeline integration  

---

## Layout

```
packages/gen-eval/
  pyproject.toml           # PEP 621, uv_build backend, extras
  README.md                # you are here
  src/gen_eval/
    __init__.py            # public re-exports
    __main__.py            # python -m gen_eval entry point
    descriptor.py          # InterfaceDescriptor loader
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
