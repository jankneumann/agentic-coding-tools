# Quickstart: adopting gen-eval in agentic-assistant

This guide walks you through adding behavioral gen-eval coverage to any
consumer service — using `agentic-assistant` as a concrete example.  After
following it you will have:

1. `gen-eval` installed in your project.
2. An interface descriptor at `evaluation/descriptors/agentic-assistant.yaml`.
3. A passing scenario run whose verdict appears in `gen-eval-report.md`.

---

## 1. Install gen-eval

From your repo root, install the base package:

```bash
uv add 'gen-eval @ ../agentic-coding-tools/packages/gen-eval'
```

Or with the optional MCP service surface (needed if you expose gen-eval over
an MCP channel):

```bash
uv add 'gen-eval[mcp] @ ../agentic-coding-tools/packages/gen-eval'
```

Two install profiles are available:

| Profile | Command | When to use |
|---------|---------|-------------|
| Base    | `uv add gen-eval` | Template-only test runs; no `fastmcp` dependency required. |
| MCP     | `uv add 'gen-eval[mcp]'` | Expose gen-eval via FastMCP or consume it from a running coordinator. |

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

## 5. CI integration

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

## 6. Next steps

- **Add more interfaces** to the descriptor (see [descriptor-template.yaml](descriptor-template.yaml)).
- **Try `--mode cli-augmented`** to drive scenarios through the `claude` or `codex` CLI.
- **Inspect failing verdicts** in `findings-gen-eval.json` — each entry traces to
  a spec scenario and an HTTP endpoint.
- **Read the spec** at `openspec/specs/gen-eval-framework/` for the full
  behavioral contract.
