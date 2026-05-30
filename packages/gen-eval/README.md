# gen-eval

Generator-evaluator framework for agentic-system testing.

> **Status:** scaffolded package shell. The framework code (~6.5 KLOC) is being
> moved out of `agent-coordinator/evaluation/gen_eval/` into this directory
> incrementally; consumers should not yet rely on the package's public API
> from this location. Track the migration in OpenSpec change
> `extract-gen-eval-package`.

## What it is

`gen-eval` runs generator-evaluator scenarios against live services
(HTTP APIs, MCP tools, CLI commands, database state) and emits structured
verdicts. It is provider-neutral: generators can be LLM-backed, SDK-backed,
or template-driven; evaluators compose pluggable transport clients.

## Install profiles

Two install profiles are planned (per design decision D2):

| Profile | Install command | Use case |
|---|---|---|
| Base | `uv add gen-eval` | Pure-Python consumers (template generators only). |
| MCP | `uv add 'gen-eval[mcp]'` | Consumers that route via the FastMCP service surface (e.g. `agent-coordinator`). |

Additional extras (`sdk`, `db`, `all`) are reserved for future consumer
profiles; see `pyproject.toml`.

## Layout

```
packages/gen-eval/
  pyproject.toml         # build + extras
  README.md              # you are here
  src/gen_eval/          # framework code (moves here under wp-framework-move)
  tests/                 # package-owned tests
  examples/              # adoption walkthroughs (added under wp-examples-doc)
```

## Links

- Spec: `openspec/specs/gen-eval-framework/`
- Change: `openspec/changes/extract-gen-eval-package/`
- Design: `openspec/changes/extract-gen-eval-package/design.md`
