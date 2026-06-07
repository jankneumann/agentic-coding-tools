# Quickstart: adopting gen-eval in agentic-assistant

This guide walks you through adding behavioral gen-eval coverage to any
consumer service — using `agentic-assistant` as a concrete example.  After
following it you will have:

1. `gen-eval` installed in your project.
2. An interface descriptor at `evaluation/descriptors/agentic-assistant.yaml`.
3. A passing scenario run whose verdict appears in `gen-eval-report.md`.

---

## 1. Install gen-eval

`gen-eval` is **not on PyPI** — it ships as a path-dependency that monorepo
siblings consume directly. From your repo root, with `agentic-coding-tools`
checked out as a sibling directory:

```bash
# Base — template-only test runs
uv add 'gen-eval @ ../agentic-coding-tools/packages/gen-eval'

# With the MCP service surface (FastMCP / coordinator integration)
uv add 'gen-eval[mcp] @ ../agentic-coding-tools/packages/gen-eval'

# Everything
uv add 'gen-eval[all] @ ../agentic-coding-tools/packages/gen-eval'
```

Adjust the relative path if `agentic-coding-tools` lives elsewhere relative
to your repo. The `uv.lock` will pin the resolved local path; CI needs the
same checkout layout (typically via a sibling clone step).

Extras: `mcp` (`fastmcp`), `sdk` (Anthropic/OpenAI generators), `db`
(`asyncpg` for DB state verification), `all` (everything).

Confirm the install:

```bash
python -c "import gen_eval; print(gen_eval.__version__)"
```

---

## 2. Create a descriptor

Copy the annotated template from the gen-eval package:

```bash
cp packages/gen-eval/examples/descriptor-template.yaml \
   evaluation/descriptors/agentic-assistant.yaml
```

Edit the file to describe your service's interface.  A minimal HTTP service
example:

```yaml
# evaluation/descriptors/agentic-assistant.yaml
name: agentic-assistant
description: Behavioral coverage for the Agentic Assistant HTTP API.

services:
  - name: api
    type: http
    base_url: "http://localhost:8080"
    auth:
      type: header
      header: "X-API-Key"
      value: "${AGENTIC_ASSISTANT_API_KEY}"

interfaces:
  - id: suggest
    name: Suggest action
    http_path: "/suggest"
    http_method: POST
    description: Returns a suggested next action for the given context.

  - id: health
    name: Health check
    http_path: "/health"
    http_method: GET
    description: Returns 200 when the service is healthy.
```

See [descriptor-template.yaml](descriptor-template.yaml) for the full annotated
schema with all optional fields.

### Where to put scenarios

When you start adding scenario YAML files, point `scenario_dirs` at the
directory using a path **relative to this descriptor file** (the package
resolves these relative to the descriptor's parent, not your CWD — matching
npm/pip/docker conventions). With descriptors at
`evaluation/descriptors/agentic-assistant.yaml` and scenarios at
`evaluation/scenarios/`:

```yaml
scenario_dirs:
  - ../scenarios/
```

---

## 3. Run your first scenario (template-only mode)

Template-only mode is the zero-dependency path — it exercises your HTTP
endpoints via synthetic requests generated from the descriptor, with no LLM
required.

```bash
python -m gen_eval \
  --descriptor evaluation/descriptors/agentic-assistant.yaml \
  --mode template-only \
  --no-services \
  --report-format both \
  --output-dir .
```

Expected output:

```
gen-eval: loading descriptor from evaluation/descriptors/agentic-assistant.yaml
gen-eval: descriptor loaded — 1 services, 2 interfaces, mode=template-only
gen-eval: PASS (1.00 >= 0.95)
gen-eval: report written to ./gen-eval-report.md
gen-eval: report written to ./gen-eval-report.json
```

Open `gen-eval-report.md` to see per-scenario verdicts.

---

## 4. (Optional) MCP install reasoning

Install `gen-eval[mcp]` only if you need one of:

- **Exposing gen-eval as a FastMCP tool** — e.g. from a coordinator that serves
  `/gen-eval/list-scenarios` and `/gen-eval/run` over MCP.
- **Routing scenario execution through the MCP channel** — when the service
  under test is only reachable via a coordinator proxy.

The base install (`gen-eval` without `[mcp]`) is sufficient for `--mode
template-only` and `--mode cli-augmented` runs that drive services directly.

---

## 5. Running gen-eval inside the agentic-assistant container

`gen-eval` is portable inside slim runtime images — no `curl`, no
`docker-compose` required when invoked with `--no-services`. This means you
can ship gen-eval as part of the agentic-assistant image and expose it via
your existing API surface (e.g. a protected `/eval/run` endpoint).

Key requirements:

- `--no-services` so the orchestrator doesn't try to start a nested stack
  (it will still health-check the externally-managed service).
- A client-side credential env var that matches your descriptor's
  `auth.env_var` (e.g. `AGENTIC_ASSISTANT_API_KEY`), so the loopback call
  the CLI makes back into your own API authenticates.
- `GEN_EVAL_DATA_DIR` pointing at where you copied your descriptors and
  scenarios into the image (e.g. `/app/evaluation`).

See the [Running gen-eval inside your own container](../README.md#running-gen-eval-inside-your-own-container)
section in the package README for the full pattern, including the
`COORDINATION_API_KEY`-style loopback-auth recipe that
`agent-coordinator`'s `/gen-eval/run` uses.

---

## 6. CI integration

Add gen-eval to your CI pipeline:

```yaml
# .github/workflows/ci.yml
- name: Run gen-eval (template-only smoke)
  run: |
    uv run python -m gen_eval \
      --descriptor evaluation/descriptors/agentic-assistant.yaml \
      --mode template-only \
      --no-services \
      --fail-threshold 0.90
```

---

## 7. Next steps

- **Add more interfaces** to the descriptor (see [descriptor-template.yaml](descriptor-template.yaml)).
- **Try `--mode cli-augmented`** to drive scenarios through the `claude` or `codex` CLI.
- **Inspect failing verdicts** in `findings-gen-eval.json` — each entry traces to
  a spec scenario and an HTTP endpoint.
- **Read the spec** at `openspec/specs/gen-eval-framework/` for the full
  behavioral contract.
