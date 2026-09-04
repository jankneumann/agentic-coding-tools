# Contracts — add-visual-code-explainer

This change adds a prompt-only skill and one CLI flag on an existing script. The four contract sub-types were evaluated; none apply:

| Sub-type | Applies? | Why not |
|---|---|---|
| OpenAPI | No | No HTTP endpoints are added or changed. The skill runs entirely in the agent harness and shells out to two co-installed scripts. |
| Database | No | No schema, migration, or query changes. The graph it reads is a committed JSON artifact. |
| Events | No | No events are emitted or consumed; the coordinator is not involved. |
| Type generation | No | No schema source from which to generate types. |

## What *is* the contract this change establishes

Two text-level contracts, both captured in the spec deltas rather than as machine-readable schemas:

- **`build_atlas.py --tree` output format and exit codes** — `specs/codebase-analysis/spec.md` "Atlas Symbol Tree Export" and `design.md` D3/D4. Consumers: the `show-me` skill (parses the footer for the disclosure line) and humans pasting the tree into PRs.
- **The disclosure line** — `specs/skill-workflow/spec.md` "Explainer Grounding and Coverage Disclosure" and `design.md` D5. Consumer: anyone reading a `show-me` answer; the behavioural tests assert its presence.

Consuming skills treat a `contracts/` directory containing only this README as "no contracts applicable".
