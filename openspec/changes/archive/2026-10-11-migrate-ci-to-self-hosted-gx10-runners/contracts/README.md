# Contracts — migrate-ci-to-self-hosted-gx10-runners

| Sub-type | Applies? | Artifact |
|---|---|---|
| OpenAPI | No. The change adds no HTTP endpoint. `ci_wallclock.py` only *consumes* GitHub's REST API through `gh api` | — |
| Database | No. The change makes no schema change | — |
| Events | No. The change adds no event payload | — |
| Config schema | **Yes** | `schemas/runner-lanes.schema.json` |

The lane manifest is the coordination boundary between packages. `wp-workflows` routes jobs
according to it. `wp-runner-kit` reads `routing.self_hosted_labels` for the JIT label set.
`wp-tooling` uses it to verify runs.

`wp-contracts` promotes the draft here to `.github/runner-lanes.schema.json`. Every
downstream package validates against that promoted copy.

Two companion contracts are defined in `design.md` and tested in place, not schema'd:

- The canonical `runs-on` expression (D3).
- The container env-file contract (D5). The file contains only `ACTIONS_RUNNER_INPUT_JITCONFIG`
  and `GX10_RUNNER_ID`.
